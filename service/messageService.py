from telethon import TelegramClient
from telethon.tl.types import PeerChannel
from datetime import datetime
from typing import List, Tuple, Any
import difflib

from model.dialog import Dialog
from service.util import Util
from service.dbService import DBService
from service.textAnalyzer import TextAnalyzer
from service.calendarService import CalendarService
from tenacity import retry, stop_after_attempt, wait_fixed


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

    async def process_dialog(
        self,
        dialog_object: Dialog,
        sent_messages: List[str],
    ) -> Tuple[int, int, int]:
        last_processed_message = self.db_service.get_last_processed_message(dialog_object.id)
        if last_processed_message is None:
            last_processed_message = -1

        messages = await self.get_messages_with_retry(dialog_object.peer, last_processed_message)
        messages = self.filter_recent_messages(messages)
        if not messages:
            return 0, 0, 0

        dialog_name = messages[0].chat.title
        self.db_service.store_dialog_name(dialog_object.id, dialog_name)
        message_objects = list(reversed([Util.construct_message_object(m) for m in messages]))

        try:
            response = self.text_analyzer.findMessages(str(message_objects))
        except Exception as e:
            await self.client.send_message(
                PeerChannel(self.env.error_dialog_id),
                f'Error processing messages from dialog {dialog_name}, \nError: {e}'
            )
            return len(messages), 0, 0

        messages_found_count = 0
        events_found_count = 0
        if response is not None:
            results = response.get('results', [])
            events = response.get('Events', [])
            messages_found_count = len(results)
            events_found_count = len(events)
            message_ids = [item['message_id'] for item in results]
            await self.handle_found_messages(messages, message_ids, sent_messages, dialog_name)
            await self.handle_events(messages, events, dialog_name, dialog_object.id)
        self.db_service.update_last_processed_message(dialog_object.id, messages[0].id, messages[-1].date)
        return len(messages), messages_found_count, events_found_count

    async def handle_found_messages(
        self,
        messages,
        message_ids,
        sent_messages,
        dialog_name,
    ):
        messages_found = list(reversed([m for m in messages if m.id in message_ids]))
        for message_found in messages_found:
            if Util.is_message_in_list(message_found.message, sent_messages):
                continue
            try:
                await Util.send_message_report(self.client, message_found, self.env.output_dialog_id)
            except Exception as e:
                await self.client.send_message(
                    PeerChannel(self.env.error_dialog_id),
                    f'Error processing message {message_found.id},\nFrom char: {dialog_name},\nError: {e}'
                )
            sent_messages.append(message_found.message)

    async def handle_events(
        self,
        messages,
        events,
        dialog_name,
        dialog_id,
    ):
        for event in events:
            try:
                # Find message by both chat_id and message_id
                message = next(
                    (
                        m for m in messages
                        if str(m.id) == str(event['message_id'])
                        and str(getattr(m.chat, "id", None) or getattr(m.to_id, "channel_id", None)) == str(event['chat_id'])
                    ),
                    None
                )
                start_datetime = datetime.fromisoformat(event['start_datetime'])
                end_datetime = datetime.fromisoformat(event['end_datetime'])

                # Check for duplicates using local fuzzy matching
                candidates = self.db_service.get_events_starting_around(start_datetime, window_minutes=120)
                is_duplicate = False
                existing_google_event_id = None

                for candidate in candidates:
                    # candidate structure: (id, dialog_id, event_id, google_event_id, title, start_time, end_time, description, created_at)
                    # Note: index 4 is title, index 3 is google_event_id (based on new schema order)
                    # Let's verify index by name if possible, but tuple is returned.
                    # Schema: id, dialog_id, event_id, google_event_id, title, start_time, end_time, description, created_at
                    candidate_title = candidate[4]
                    candidate_google_id = candidate[3]
                    
                    similarity = difflib.SequenceMatcher(None, event['title'], candidate_title).ratio()
                    if similarity > 0.6 or event['title'] in candidate_title or candidate_title in event['title']:
                        is_duplicate = True
                        existing_google_event_id = candidate_google_id
                        print(f"Duplicate event detected: '{event['title']}' is similar to '{candidate_title}' (score: {similarity:.2f})")
                        break
                
                if is_duplicate:
                    # Store association but skip creation
                    self.db_service.store_calendar_event(
                        dialog_id=dialog_id,
                        event_id=event['message_id'],
                        title=event['title'],
                        start_time=start_datetime,
                        end_time=end_datetime,
                        description=event['description'],
                        google_event_id=existing_google_event_id
                    )
                    continue

                created_event = self.calendar_service.create_event(
                    name=event['title'],
                    description=event['description'] + '\n\n{}'.format(Util.get_message_link(message)),
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
            except Exception as e:
                await self.client.send_message(
                    PeerChannel(self.env.error_dialog_id),
                    f'Error creating event from message {event["message_id"]},\nFrom chat: {dialog_name},\nError: {e}'
                )
    @retry(stop=stop_after_attempt(5), wait=wait_fixed(10))
    async def get_messages_with_retry(self, dialog_peer, last_processed_message):
        return await self.client.get_messages(dialog_peer, min_id=last_processed_message, limit=10000)
    
    def filter_recent_messages(self, messages):
        from datetime import timedelta
        one_day_ago = (datetime.now() - timedelta(days=1)).timestamp()
        return [m for m in messages if m.date.timestamp() > one_day_ago]

    async def process_dialogs(
        self,
        dialog_objects: List[Dialog],
        sent_messages: List[str],
    ) -> Tuple[int, int, int]:
        """
        Process all messages from all dialogs at once.
        """
        all_messages = []
        dialog_map = {}

        # Gather all messages from all dialogs
        for dialog_object in dialog_objects:
            last_processed_message = self.db_service.get_last_processed_message(dialog_object.id)
            if last_processed_message is None:
                last_processed_message = -1

            try:
                messages = await self.get_messages_with_retry(dialog_object.peer, last_processed_message)
            except Exception as e:
                await self.client.send_message(
                    PeerChannel(self.env.error_dialog_id),
                    f'Error fetching messages for dialog {dialog_object.id}.\nError: {e}'
                )
                continue
            messages = self.filter_recent_messages(messages)
            if not messages:
                continue

            dialog_name = messages[0].chat.title
            self.db_service.store_dialog_name(dialog_object.id, dialog_name)
            for m in messages:
                dialog_map[m.id] = {
                    "dialog_object": dialog_object,
                    "dialog_name": dialog_name,
                    "message": m
                }
            all_messages.extend(messages)

        if not all_messages:
            return 0, 0, 0
        
        # Prepare message objects for analyzer
        message_objects = list(reversed([Util.construct_message_object(m) for m in all_messages]))

        try:
            response = self.text_analyzer.findMessages(str(message_objects))
        except Exception as e:
            await self.client.send_message(
                PeerChannel(self.env.error_dialog_id),
                f'Error processing messages from all dialogs.\nError: {e}'
            )
            return len(all_messages), 0, 0

        messages_found_count = 0
        events_found_count = 0
        if response is not None:
            results = response.get('results', [])
            events = response.get('Events', [])
            messages_found_count = len(results)
            events_found_count = len(events)
            message_ids = [item['message_id'] for item in results]
            # Handle found messages
            messages_found = list(reversed([m for m in all_messages if str(m.id) in message_ids]))
            for message_found in messages_found:
                dialog_info = dialog_map.get(message_found.id)
                if not dialog_info:
                    continue
                dialog_name = dialog_info["dialog_name"]
                if Util.is_message_in_list(message_found.message, sent_messages):
                    continue
                try:
                    await Util.send_message_report(self.client, message_found, self.env.output_dialog_id)
                except Exception as e:
                    await self.client.send_message(
                        PeerChannel(self.env.error_dialog_id),
                        f'Error processing message {message_found.id},\nFrom chat: {dialog_name},\nError: {e}'
                    )
                sent_messages.append(message_found.message)
            # Handle events
            for event in events:
                dialog_info = dialog_map.get(int(event['message_id']))
                if not dialog_info:
                    continue
                dialog_name = dialog_info["dialog_name"]
                dialog_object = dialog_info["dialog_object"]
                try:
                    message = dialog_info["message"]
                    start_datetime = datetime.fromisoformat(event['start_datetime'])
                    end_datetime = datetime.fromisoformat(event['end_datetime'])
                    
                    # Check for duplicates using local fuzzy matching
                    candidates = self.db_service.get_events_starting_around(start_datetime, window_minutes=120)
                    is_duplicate = False
                    existing_google_event_id = None

                    for candidate in candidates:
                        # Schema: id, dialog_id, event_id, google_event_id, title, start_time, end_time, description, created_at
                        candidate_title = candidate[4]
                        candidate_google_id = candidate[3]
                        
                        similarity = difflib.SequenceMatcher(None, event['title'], candidate_title).ratio()
                        if similarity > 0.6 or event['title'] in candidate_title or candidate_title in event['title']:
                            is_duplicate = True
                            existing_google_event_id = candidate_google_id
                            print(f"Duplicate event detected: '{event['title']}' is similar to '{candidate_title}' (score: {similarity:.2f})")
                            break
                    
                    if is_duplicate:
                        self.db_service.store_calendar_event(
                            dialog_id=dialog_object.id,
                            event_id=event['message_id'],
                            title=event['title'],
                            start_time=start_datetime,
                            end_time=end_datetime,
                            description=event['description'],
                            google_event_id=existing_google_event_id
                        )
                        continue

                    created_event = self.calendar_service.create_event(
                        name=event['title'],
                        description=event['description'] + '\n\n{}'.format(Util.get_message_link(message)),
                        start_datetime=start_datetime,
                        end_datetime=end_datetime
                    )
                    google_event_id = created_event.get('id')

                    self.db_service.store_calendar_event(
                        dialog_id=dialog_object.id,
                        event_id=event['message_id'],
                        title=event['title'],
                        start_time=start_datetime,
                        end_time=end_datetime,
                        description=event['description'],
                        google_event_id=google_event_id
                    )
                except Exception as e:
                    await self.client.send_message(
                        PeerChannel(self.env.error_dialog_id),
                        f'Error creating event from message {event["message_id"]},\nFrom chat: {dialog_name},\nError: {e}'
                    )
        # Update last processed message for each dialog
        for dialog_object in dialog_objects:
            dialog_messages = [m for m in all_messages if dialog_map[m.id]["dialog_object"].id == dialog_object.id]
            if dialog_messages:
                self.db_service.update_last_processed_message(
                    dialog_object.id, dialog_messages[0].id, dialog_messages[-1].date
                )
        return len(all_messages), messages_found_count, events_found_count