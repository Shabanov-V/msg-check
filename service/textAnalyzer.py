from openai import OpenAI
import json
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from tenacity import retry, stop_after_attempt, wait_fixed, before_sleep_log

logger = logging.getLogger(__name__)

class TextAnalyzer:
    PHASE1_SCHEMA = {
        "name": "phase1_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "required": ["found", "results", "borderline"],
            "properties": {
                "found": {"type": "boolean"},
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["chat_id", "message_id", "text", "has_explicit_datetime", "reason"],
                        "properties": {
                            "chat_id": {"type": "string"},
                            "message_id": {"type": "string"},
                            "text": {"type": "string"},
                            "has_explicit_datetime": {"type": "boolean"},
                            "reason": {"type": "string"}
                        },
                        "additionalProperties": False
                    }
                },
                "borderline": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["chat_id", "message_id", "text", "exclusion_reason"],
                        "properties": {
                            "chat_id": {"type": "string"},
                            "message_id": {"type": "string"},
                            "text": {"type": "string"},
                            "exclusion_reason": {"type": "string"}
                        },
                        "additionalProperties": False
                    }
                }
            },
            "additionalProperties": False
        }
    }

    PHASE2_SCHEMA = {
        "name": "phase2_extraction",
        "strict": True,
        "schema": {
            "type": "object",
            "required": ["Events"],
            "properties": {
                "Events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["chat_id", "message_id", "title", "description", "start_datetime", "end_datetime"],
                        "properties": {
                            "chat_id": {"type": "string"},
                            "message_id": {"type": "string"},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "start_datetime": {"type": "string"},
                            "end_datetime": {"type": "string"}
                        },
                        "additionalProperties": False
                    }
                }
            },
            "additionalProperties": False
        }
    }

    def __init__(self, key, base_prompt, phase2_prompt, model, timezone_name="Europe/Madrid"):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=key,
        )
        self.model = model
        self.base_prompt = base_prompt
        self.phase2_prompt = phase2_prompt
        self.timezone_name = timezone_name

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(30),
           before_sleep=before_sleep_log(logger, logging.WARNING))
    def __generate_content_with_retry(self, prompt, text, schema):
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": schema
            },
            temperature=0,
        )
        return completion

    def __call_llm(self, prompt, text, schema):
        response = None
        try:
            response = self.__generate_content_with_retry(prompt, text, schema)
        except Exception as e:
            logger.error("Failed to get response: %s", e)
            
        if response is None:
            raise Exception("Failed to get response")
        return response

    def __clean_json_content(self, content):
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return content.strip()

    def _parse_datetime_lenient(self, dt_string):
        """Parse datetime string with fallback patterns."""
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(dt_string, fmt)
            except ValueError:
                continue
        # Last resort: dateutil if available
        try:
            from dateutil import parser
            return parser.parse(dt_string, ignoretz=True)
        except (ImportError, ValueError):
            return None

    def _post_process_events(self, events):
        """Apply timezone localization and default end-time to events."""
        tz = ZoneInfo(self.timezone_name)
        processed = []
        for event in events:
            start = self._parse_datetime_lenient(event['start_datetime'])
            if start is None:
                logger.warning("Skipping event with unparseable start_datetime: %s", event['start_datetime'])
                continue
            start = start.replace(tzinfo=tz)
            event['start_datetime'] = start.isoformat()

            if event['end_datetime']:
                end = self._parse_datetime_lenient(event['end_datetime'])
                if end is None:
                    logger.warning("Unparseable end_datetime '%s', defaulting to start + 2h", event['end_datetime'])
                    end = start + timedelta(hours=2)
                else:
                    end = end.replace(tzinfo=tz)
            else:
                end = start + timedelta(hours=2)
            event['end_datetime'] = end.isoformat()
            processed.append(event)
        return processed

    def _extract_tokens(self, response):
        """Extract total token count from LLM response if available."""
        try:
            return response.usage.total_tokens
        except (AttributeError, TypeError):
            return None

    def findMessages(self, text):
        # Parse original message objects for Phase 2 lookups
        try:
            original_messages = json.loads(text)
            msg_lookup = {m['message_id']: m for m in original_messages}
        except (json.JSONDecodeError, TypeError):
            msg_lookup = {}

        # Phase 1: Classification
        t0 = time.time()
        response = self.__call_llm(self.base_prompt, text, self.PHASE1_SCHEMA)
        phase1_duration = time.time() - t0
        phase1_tokens = self._extract_tokens(response)
        
        try:
            content = response.choices[0].message.content
            content = self.__clean_json_content(content)
            phase1 = json.loads(content)
        except (AttributeError, IndexError, json.JSONDecodeError) as e:
            logger.error("Failed to parse Phase 1 response: %s", e)
            return None

        if not phase1.get('found'):
            return None 
        
        results = phase1.get('results', [])
        borderline = phase1.get('borderline', [])
        logger.info("Phase 1 — messages found: %d (%.1fs)", len(results), phase1_duration)

        # Filter results with explicit datetime for Phase 2
        datetime_results = [r for r in results if r.get('has_explicit_datetime')]

        if not datetime_results:
            return {
                "results": results, "Events": [], "borderline": borderline,
                "_meta": {
                    "phase1_duration_sec": phase1_duration,
                    "phase2_duration_sec": 0.0,
                    "phase1_tokens": phase1_tokens,
                    "phase2_tokens": None,
                }
            }

        # Phase 2: Event Extraction — build full message objects for filtered results
        phase2_messages = []
        for r in datetime_results:
            orig = msg_lookup.get(r['message_id'], {})
            phase2_messages.append({
                'source': orig.get('source', ''),
                'chat_id': r['chat_id'],
                'chat_title': orig.get('chat_title', ''),
                'text': r['text'],
                'message_id': r['message_id'],
                'datetime': orig.get('datetime', '')
            })

        phase2_input = json.dumps(phase2_messages, ensure_ascii=False)
        t1 = time.time()
        response2 = self.__call_llm(self.phase2_prompt, phase2_input, self.PHASE2_SCHEMA)
        phase2_duration = time.time() - t1
        phase2_tokens = self._extract_tokens(response2)

        try:
            content2 = response2.choices[0].message.content
            content2 = self.__clean_json_content(content2)
            phase2 = json.loads(content2)
        except (AttributeError, IndexError, json.JSONDecodeError) as e:
            logger.error("Failed to parse Phase 2 response: %s", e)
            return {"results": results, "Events": [], "borderline": borderline,
                    "_meta": {
                        "phase1_duration_sec": phase1_duration,
                        "phase2_duration_sec": phase2_duration,
                        "phase1_tokens": phase1_tokens,
                        "phase2_tokens": phase2_tokens,
                    }}

        events = phase2.get('Events', [])
        events = self._post_process_events(events)

        return {
            "results": results, "Events": events, "borderline": borderline,
            "_meta": {
                "phase1_duration_sec": phase1_duration,
                "phase2_duration_sec": phase2_duration,
                "phase1_tokens": phase1_tokens,
                "phase2_tokens": phase2_tokens,
            }
        }