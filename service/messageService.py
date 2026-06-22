import logging

from telethon import TelegramClient
from telethon.tl.types import PeerChannel
from datetime import datetime
from typing import List, Tuple, Any, Dict
import difflib
import json

logger = logging.getLogger(__name__)

from model.unifiedMessage import UnifiedMessage
from service.util import Util
from service.dbService import DBService
from service.textAnalyzer import TextAnalyzer
from service.calendarService import CalendarService
from service.runContext import RunContext
from service.llmJoin import assign_handles, resolve_llm_results
from service.decisionLog import build_decision_rows
import hashlib


class MessageService:
    def __init__(
        self,
        client: TelegramClient,
        db_service: DBService,
        text_analyzer: TextAnalyzer,
        calendar_service: CalendarService,
        env: Any,
    ):
        self.client = client
        self.db_service = db_service
        self.text_analyzer = text_analyzer
        self.calendar_service = calendar_service
        self.env = env

    async def process_sources(
        self,
        sources: List[Any],
        sent_messages: List[str],
        run_ctx: RunContext = None,
    ) -> Tuple[int, int, int]:
        """
        Process all messages from all sources at once.
        """
        Util.reset_offset()
        all_messages: List[UnifiedMessage] = []
        # (source, chat_id, message_id) -> {source, chat_info, message}
        # Composite key: message_id alone collides across chats.
        dialog_map: Dict[Tuple[str, str, str], dict] = {}
        # Track source instances by source_name for reference generation
        source_map: Dict[str, Any] = {}
        # Track chat-level data for DB updates
        chat_latest: Dict[str, UnifiedMessage] = {}  # "source:chat_id" -> latest message

        for source in sources:
            source_map[source.source_name] = source
            try:
                chats = await source.get_target_chats()
            except Exception as e:
                await self.client.send_message(
                    PeerChannel(self.env.error_dialog_id),
                    f'Error getting chats from {source.source_name}.\nError: {e}'
                )
                continue

            for chat in chats:
                try:
                    messages = await source.fetch_messages(chat)
                except Exception as e:
                    await self.client.send_message(
                        PeerChannel(self.env.error_dialog_id),
                        f'Error fetching messages for {source.source_name} chat {chat.chat_id}.\nError: {e}'
                    )
                    continue

                if not messages:
                    continue

                dialog_id = f"{source.source_name}:{chat.chat_id}"
                chat_title = chat.chat_title or (messages[0].chat_title if messages else '')
                if chat_title:
                    self.db_service.store_dialog_name(dialog_id, chat_title)

                if run_ctx:
                    run_ctx.record_messages_fetched(source.source_name, chat.chat_id, chat_title, len(messages))

                for m in messages:
                    dialog_map[(m.source, m.chat_id, m.message_id)] = {
                        "source": source,
                        "chat_id": m.chat_id,
                        "chat_title": m.chat_title or chat_title,
                        "message": m,
                    }

                all_messages.extend(messages)

                # Track latest message per chat for cursor updates
                latest = max(messages, key=lambda m: m.timestamp)
                if dialog_id not in chat_latest or latest.timestamp > chat_latest[dialog_id].timestamp:
                    chat_latest[dialog_id] = latest

        if not all_messages:
            return 0, 0, 0

        # Sort messages by timestamp (newest first)
        all_messages.sort(key=lambda m: m.timestamp, reverse=True)

        # Limit to 500 messages (take oldest 500 for contiguous processing)
        if len(all_messages) > 500:
            all_messages = all_messages[-500:]

        # Prepare message objects for analyzer. Hand the LLM run-unique synthetic
        # handles ("m0", "m1", ...) instead of real message_ids, which collide
        # across chats and make the result->message join ambiguous (see llmJoin).
        ordered_messages = list(reversed(all_messages))
        message_objects = assign_handles([
            Util.construct_message_object(m, self.env.timezone) for m in ordered_messages
        ])

        try:
            response = self.text_analyzer.findMessages(json.dumps(message_objects, ensure_ascii=False))
        except Exception as e:
            await self.client.send_message(
                PeerChannel(self.env.error_dialog_id),
                f'Error processing messages from all sources.\nError: {e}'
            )
            if run_ctx:
                run_ctx.record_error(f"LLM call failed: {e}")
            return len(all_messages), 0, 0

        messages_found_count = 0
        events_found_count = 0

        if response is not None:
            meta = response.get('_meta', {})
            messages_found_count = len(response.get('results', []))
            events_found_count = len(response.get('Events', []))

            # Record LLM metadata into RunContext
            if run_ctx and meta:
                run_ctx.llm_phase1_duration_sec = meta.get('phase1_duration_sec', 0.0)
                run_ctx.llm_phase2_duration_sec = meta.get('phase2_duration_sec', 0.0)
                run_ctx.llm_phase1_tokens = meta.get('phase1_tokens')
                run_ctx.llm_phase2_tokens = meta.get('phase2_tokens')

            # Resolve handles back to real messages (collision-safe join + recovery).
            resolved = resolve_llm_results(ordered_messages, response)

            # Record borderline messages
            if run_ctx:
                for b_msg, exclusion_reason in resolved.borderline:
                    run_ctx.record_borderline(
                        b_msg.message_id, b_msg.chat_title, b_msg.text, exclusion_reason,
                    )

            # Hallucination recovery accounting
            if resolved.recoveries:
                if run_ctx:
                    run_ctx.hallucination_recoveries = resolved.recoveries
                await self.client.send_message(
                    PeerChannel(self.env.error_dialog_id),
                    f'Info: Recovered {resolved.recoveries} messages via text fallback.'
                )
            if resolved.still_missing:
                if run_ctx:
                    run_ctx.still_missing_ids = resolved.still_missing
                await self.client.send_message(
                    PeerChannel(self.env.error_dialog_id),
                    f'Warning: {len(resolved.still_missing)} reported messages could not be matched.\n'
                    f'Unresolved handles: {resolved.still_missing}'
                )

            # Handle found messages
            dedup_keys = set()
            for message_found, reason in resolved.matched:
                dialog_info = dialog_map.get(
                    (message_found.source, message_found.chat_id, message_found.message_id)
                )
                chat_title = dialog_info["chat_title"] if dialog_info else message_found.chat_title
                if Util.is_message_in_list(message_found.text, sent_messages):
                    dedup_keys.add(
                        (message_found.source, message_found.chat_id, message_found.message_id)
                    )
                    if run_ctx:
                        run_ctx.record_dedup_skip(message_found.message_id, chat_title, message_found.text)
                    continue
                # Record match
                if run_ctx:
                    run_ctx.record_match(
                        message_found.message_id, chat_title, message_found.text,
                        reason,
                        source=message_found.source, chat_id=message_found.chat_id,
                    )
                try:
                    source = source_map.get(message_found.source)
                    await Util.send_message_report(self.client, message_found, self.env.output_dialog_id, source)
                except Exception as e:
                    await self.client.send_message(
                        PeerChannel(self.env.error_dialog_id),
                        f'Error processing message {message_found.message_id},\n'
                        f'From chat: {chat_title},\nError: {e}'
                    )
                    if run_ctx:
                        run_ctx.record_error(f"Report error for {message_found.message_id}: {e}")
                sent_messages.append(message_found.text)

            # Handle events
            for msg, event in resolved.events:
                dialog_id = f"{msg.source}:{msg.chat_id}"
                dialog_info = dialog_map.get((msg.source, msg.chat_id, msg.message_id))
                chat_title = dialog_info["chat_title"] if dialog_info else msg.chat_title
                source = source_map.get(msg.source)
                try:
                    await self._process_single_event(event, msg, source, dialog_id, chat_title, run_ctx)
                except Exception as e:
                    await self.client.send_message(
                        PeerChannel(self.env.error_dialog_id),
                        f'Error creating event from message {event["message_id"]},\n'
                        f'From chat: {chat_title},\nError: {e}'
                    )
                    if run_ctx:
                        run_ctx.record_error(f"Event creation error for {event['message_id']}: {e}")

            # Persist a per-message decision log for retrospective FP/FN
            # detection (see ADR 0004). Best-effort: never break the run.
            try:
                base_prompt = getattr(self.env, "base_prompt", "") or ""
                prompt_version = hashlib.sha1(base_prompt.encode("utf-8")).hexdigest()[:8]
                run_id = run_ctx.start_time.isoformat() if run_ctx else datetime.utcnow().isoformat()
                rows = build_decision_rows(
                    ordered_messages, resolved, dedup_keys,
                    run_id=run_id,
                    llm_model=getattr(self.env, "llm_model", ""),
                    prompt_version=prompt_version,
                )
                self.db_service.store_decision_log(rows)
            except Exception as e:
                logger.warning("Failed to write decision_log: %s", e)
                if run_ctx:
                    run_ctx.record_error(f"decision_log write failed: {e}")

        # Update last processed message for each chat
        for dialog_id, latest_msg in chat_latest.items():
            self.db_service.update_last_processed_message(
                dialog_id, latest_msg.message_id, latest_msg.timestamp
            )

        return len(all_messages), messages_found_count, events_found_count

    async def _process_single_event(self, event: dict, message: UnifiedMessage, source: Any, dialog_id: str, dialog_name: str, run_ctx: RunContext = None):
        """Dedup-check and create/store a single calendar event."""
        start_datetime = datetime.fromisoformat(event['start_datetime'])
        end_datetime = datetime.fromisoformat(event['end_datetime'])

        candidates = self.db_service.get_events_starting_around(start_datetime, window_minutes=120)
        is_duplicate = False
        existing_google_event_id = None
        matched_title = ""
        matched_similarity = 0.0

        for candidate in candidates:
            candidate_title = candidate[4]
            candidate_google_id = candidate[3]
            similarity = difflib.SequenceMatcher(None, event['title'], candidate_title).ratio()
            if similarity > 0.6 or event['title'] in candidate_title or candidate_title in event['title']:
                is_duplicate = True
                existing_google_event_id = candidate_google_id
                matched_title = candidate_title
                matched_similarity = similarity
                logger.info("Duplicate event detected: '%s' is similar to '%s' (score: %.2f)", event['title'], candidate_title, similarity)
                break

        if run_ctx:
            run_ctx.record_event(event['title'], is_duplicate, matched_similarity, matched_title)

        if is_duplicate:
            self.db_service.store_calendar_event(
                dialog_id=dialog_id,
                event_id=event['message_id'],
                title=event['title'],
                start_time=start_datetime,
                end_time=end_datetime,
                description=event['description'],
                google_event_id=existing_google_event_id
            )
            return

        # Build description with the source's Source reference (see CONTEXT.md).
        # The source adapter owns its locator format; "" means no locator.
        ref = source.get_event_reference(message) if source else ""
        description = event['description']
        if ref:
            description += f'\n\n{ref}'

        created_event = self.calendar_service.create_event(
            name=event['title'],
            description=description,
            start_datetime=start_datetime,
            end_datetime=end_datetime
        )
        google_event_id = created_event.get('id')

        self.db_service.store_calendar_event(
            dialog_id=dialog_id,
            event_id=event['message_id'],
            title=event['title'],
            start_time=start_datetime,
            end_time=end_datetime,
            description=event['description'],
            google_event_id=google_event_id
        )