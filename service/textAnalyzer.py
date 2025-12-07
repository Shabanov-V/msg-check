from openai import OpenAI
import time
import sys
import json
import os
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_fixed

class TextAnalyzer:
    def __init__(self, key, base_prompt, model):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=key,
        )
        self.model = model
        self.base_prompt = base_prompt

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(30))
    def __generate_content_with_retry(self, client, model, base_prompt, text):
        response_schema = {
            "name": "message_analysis",
            "strict": True,
            "schema": {
                "type": "object",
                "required": ["found", "results", "Events"],
                "properties": {
                    "found": {"type": "boolean"},
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["chat_id", "message_id", "text"],
                            "properties": {
                                "chat_id": {"type": "string"},
                                "message_id": {"type": "string"},
                                "text": {"type": "string"}
                            },
                            "additionalProperties": False
                        }
                    },
                    "Events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["chat_id", "message_id", "start_datetime", "end_datetime", "title", "description"],
                            "properties": {
                                "chat_id": {"type": "string"},
                                "message_id": {"type": "string"},
                                "start_datetime": {"type": "string"},
                                "end_datetime": {"type": "string"},
                                "title": {"type": "string"},
                                "description": {"type": "string"}
                            },
                            "additionalProperties": False
                        }
                    }
                },
                "additionalProperties": False
            }
        }

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": base_prompt},
                {"role": "user", "content": text}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": response_schema
            },
            temperature=0,
        )
        return completion

    def __checkMessages(self, text):
        response = None
        try:
            response = self.__generate_content_with_retry(self.client, self.model, self.base_prompt, text)
        except Exception as e:
            # Code 429 logic might be different with OpenAI lib (usually APIConnectionError or RateLimitError)
            # Keeping generic exception logging for now but checking for status_code if available
            sys.stderr.write("{}: Failed to get response: {}\n".format(datetime.now(), e))
            
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

    def findMessages(self, text):
        response = self.__checkMessages(text)
        
        try:
            content = response.choices[0].message.content
            content = self.__clean_json_content(content)
            parsed = json.loads(content)
        except (AttributeError, IndexError, json.JSONDecodeError) as e:
             sys.stderr.write("{}: Failed to parse response: {}\n".format(datetime.now(), e))
             return None

        if not parsed.get('found'):
            return None 
        
        print("Messages found in: {}".format(text))
        results = parsed.get('results', [])
        events = parsed.get('Events', [])
        return {"results": results, "Events": events}