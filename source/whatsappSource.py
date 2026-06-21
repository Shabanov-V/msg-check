from typing import List, Optional
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from html import escape
import requests
from tenacity import retry, stop_after_attempt, wait_fixed

from model.unifiedMessage import UnifiedMessage
from model.chatInfo import ChatInfo
from service.dbService import DBService


class WhatsAppSource:
    source_name = "whatsapp"

    def __init__(self, waha_url: str, waha_api_key: str, session_name: str,
                 target_label: str, timezone_name: str, db_service: DBService):
        self.waha_url = waha_url.rstrip('/')
        self.waha_api_key = waha_api_key
        self.session_name = session_name
        self.target_label = target_label
        self.timezone_name = timezone_name
        self.db_service = db_service

    async def get_target_chats(self) -> List[ChatInfo]:
        # Find label matching target_label
        labels = self._request('GET', f'/api/{self.session_name}/labels')
        label_id = None
        for label in labels:
            if label.get('name') == self.target_label:
                label_id = label.get('id')
                break

        if label_id is None:
            return []

        # Get chats for this label
        label_chats = self._request('GET', f'/api/{self.session_name}/labels/{label_id}/chats')

        chats = []
        for chat_data in label_chats:
            chat_id = chat_data.get('id', chat_data) if isinstance(chat_data, dict) else str(chat_data)

            # Resolve group name for group chats
            chat_title = ''
            if str(chat_id).endswith('@g.us'):
                try:
                    group_info = self._request('GET', f'/api/{self.session_name}/groups/{chat_id}')
                    chat_title = group_info.get('subject', '') or group_info.get('name', '')
                except Exception:
                    chat_title = str(chat_id)
            else:
                chat_title = str(chat_id)

            chats.append(ChatInfo(
                source="whatsapp",
                chat_id=str(chat_id),
                chat_title=chat_title,
            ))
        return chats

    async def fetch_messages(self, chat: ChatInfo) -> List[UnifiedMessage]:
        last_ts = self.db_service.get_last_processed_timestamp(f"whatsapp:{chat.chat_id}")
        if last_ts is not None:
            since_ts = int(last_ts.timestamp())
        else:
            since_ts = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())

        params = {
            'limit': 1000,
            'filter.timestamp.gte': since_ts,
            'filter.fromMe': 'false',
            'downloadMedia': 'false',
        }

        messages_data = self._request(
            'GET',
            f'/api/{self.session_name}/chats/{chat.chat_id}/messages',
            params=params,
        )

        unified = []
        for msg in messages_data:
            msg_id = msg.get('id', '')
            body = msg.get('body', '') or ''
            ts = msg.get('timestamp', 0)
            msg_time = datetime.fromtimestamp(ts, tz=timezone.utc)

            # Apply 24h recency filter
            one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
            if msg_time < one_day_ago:
                continue

            # Extract sender name from WAHA payload
            sender_name = msg.get('sender', {}).get('pushName') or ""

            unified.append(UnifiedMessage(
                source="whatsapp",
                chat_id=chat.chat_id,
                chat_title=chat.chat_title,
                message_id=str(msg_id),
                text=body,
                timestamp=msg_time,
                sender_name=sender_name,
                raw=msg,
            ))

        unified.sort(key=lambda m: m.timestamp)
        return unified

    def get_message_reference(self, message: UnifiedMessage) -> str:
        tz = ZoneInfo(self.timezone_name)
        dt_str = message.timestamp.astimezone(tz).strftime('%b %d, %H:%M')

        safe_title = escape(message.chat_title)
        safe_text = escape(message.text)
        safe_sender = escape(message.sender_name or "Unknown")

        report = (
            f'📌 <b>{safe_title}</b>\n'
            f'👤 <b>From:</b> {safe_sender}\n'
            f'📅 {dt_str}\n\n'
            f'💬 {safe_text}'
        )
        return report

    async def check_health(self) -> bool:
        try:
            response = self._request('GET', f'/api/{self.session_name}/')
            if isinstance(response, dict):
                return response.get('status') == 'WORKING'
            if isinstance(response, list):
                for session in response:
                    if isinstance(session, dict) and session.get('status') == 'WORKING':
                        return True
            return False
        except Exception:
            return False

    # --- Internal helpers ---

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
    def _request(self, method: str, path: str, **kwargs):
        url = f'{self.waha_url}{path}'
        headers = kwargs.pop('headers', {})
        headers['X-Api-Key'] = self.waha_api_key

        response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        response.raise_for_status()
        return response.json()
