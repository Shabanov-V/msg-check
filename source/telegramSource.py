from typing import Dict, List
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telethon import TelegramClient, utils
from telethon.tl import functions
from telethon.tl.types import InputPeerChannel, InputPeerChat, InputPeerUser, PeerChannel, PeerChat, PeerUser, Chat
from telethon.extensions import html as telethon_html
from tenacity import retry, stop_after_attempt, wait_fixed
from html import escape

from model.unifiedMessage import UnifiedMessage
from model.chatInfo import ChatInfo
from model.dialog import Dialog
from model.dialogType import DialogType
from service.dbService import DBService


class TelegramSource:
    source_name = "telegram"

    def __init__(self, client: TelegramClient, env, db_service: DBService):
        self.client = client
        self.env = env
        self.db_service = db_service
        self._dialog_cache: Dict[str, Dialog] = {}

    async def get_target_chats(self) -> List[ChatInfo]:
        filters = await self._get_dialog_filters_with_retry()
        dialog_objects = self._get_target_dialog_objects(filters)
        chats = []
        for dialog in dialog_objects:
            chat_id = str(dialog.id)
            self._dialog_cache[chat_id] = dialog
            chats.append(ChatInfo(
                source="telegram",
                chat_id=chat_id,
                chat_title="",
            ))
        return chats

    async def fetch_messages(self, chat: ChatInfo) -> List[UnifiedMessage]:
        dialog = self._dialog_cache.get(chat.chat_id)
        if dialog is None:
            dialog = Dialog(int(chat.chat_id), DialogType.CHANNEL)

        last_processed = self.db_service.get_last_processed_message(f"telegram:{chat.chat_id}")
        if last_processed is not None:
            last_processed = int(last_processed)
        else:
            last_processed = -1

        messages = await self._get_messages_with_retry(dialog.peer, last_processed)
        messages = self._filter_recent_messages(messages)

        # Filter out own messages
        messages = [m for m in messages if not m.out]

        unified = []
        for m in messages:
            text = self._build_message_text(m)
            chat_title = getattr(m.chat, 'title', '') or ''
            chat_id_str = str(getattr(m.chat, 'id', None) or getattr(m.to_id, 'channel_id', chat.chat_id))

            # Update chat title on the ChatInfo if we got one
            if chat_title and not chat.chat_title:
                chat.chat_title = chat_title

            sender_name = utils.get_display_name(m.sender) if m.sender else ""

            unified.append(UnifiedMessage(
                source="telegram",
                chat_id=chat_id_str,
                chat_title=chat_title,
                message_id=str(m.id),
                text=text,
                timestamp=m.date,
                sender_name=sender_name,
                raw=m,
            ))
        return unified

    def get_message_reference(self, message: UnifiedMessage) -> str:
        raw = message.raw
        if raw is not None:
            link = self._get_message_link(raw)
            is_link = link.startswith('http')
        else:
            link = None
            is_link = False

        tz = ZoneInfo(self.env.timezone)
        dt_str = message.timestamp.astimezone(tz).strftime('%b %d, %H:%M')

        # Escape chat title because it might contain < > &
        safe_title = escape(message.chat_title)

        # Escape sender name
        safe_sender = escape(message.sender_name or "Unknown")

        if is_link:
            report = (
                f'📌 <b>{safe_title}</b>\n'
                f'👤 <b>From:</b> {safe_sender}\n'
                f'🔗 <a href="{link}">Open in Telegram</a>\n'
                f'📅 {dt_str}\n\n'
                f'💬 {message.text}'
            )
        else:
            report = (
                f'📌 <b>{safe_title}</b>\n'
                f'👤 <b>From:</b> {safe_sender}\n'
                f'📍 {link}\n'
                f'📅 {dt_str}\n\n'
                f'💬 {message.text}'
            )
        return report

    async def check_health(self) -> bool:
        return True

    # --- Internal helpers ---

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(10))
    async def _get_dialog_filters_with_retry(self):
        return await self.client(functions.messages.GetDialogFiltersRequest())

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(10))
    async def _get_messages_with_retry(self, dialog_peer, last_processed_message):
        return await self.client.get_messages(dialog_peer, min_id=last_processed_message, limit=10000)

    def _get_target_dialog_objects(self, filters):
        for dialog_filter in filters:
            if hasattr(dialog_filter, 'id') and dialog_filter.title == self.env.target_dialog_filter:
                return [d for d in (self._build_dialog_object(peer) for peer in dialog_filter.include_peers) if d is not None]
        return []

    @staticmethod
    def _build_dialog_object(peer):
        if type(peer) == InputPeerChannel:
            return Dialog(peer.channel_id, DialogType.CHANNEL)
        elif type(peer) == InputPeerChat:
            return Dialog(peer.chat_id, DialogType.CHAT)
        elif type(peer) == InputPeerUser:
            return Dialog(peer.user_id, DialogType.USER)
        return None

    @staticmethod
    def _filter_recent_messages(messages):
        one_day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).timestamp()
        return [m for m in messages if m.date.timestamp() > one_day_ago]

    @staticmethod
    def _build_message_text(message):
        # Use Telethon's HTML extension to get text with entities as HTML tags
        # It also automatically escapes special characters outside of tags.
        text = telethon_html.unparse(message.message, message.entities) if message.entities else (message.message or '')

        poll_text = TelegramSource._get_poll_question_text(message)
        if poll_text:
            # Poll text is raw, so escape it
            poll_text = escape(poll_text)
            if text:
                return f"{text}\n{poll_text}"
            return poll_text
        return text

    @staticmethod
    def _get_poll_question_text(message):
        try:
            return message.media.poll.question.text
        except AttributeError:
            return ""

    @staticmethod
    def _get_message_link(message):
        if isinstance(message.chat, Chat):
            return 'From chat: {}'.format(message.chat.title)
        if hasattr(message.chat, 'has_link') and message.chat.has_link and message.chat.username is not None:
            return 'https://t.me/{}/{}'.format(message.chat.username, message.id)
        else:
            return 'https://t.me/c/{}/{}'.format(message.chat.id, message.id)
