import re
from html import escape
from zoneinfo import ZoneInfo
from telethon import TelegramClient
from telethon.tl.types import PeerChannel
from datetime import timedelta
from model.unifiedMessage import UnifiedMessage

class Util:

    _offset = 0

    @staticmethod
    def reset_offset():
        Util._offset = 0

    @staticmethod
    async def send_message_report(client: TelegramClient, message: UnifiedMessage, output_dialog_id: int, source):
        if message is None:
            return None

        report_text = source.get_message_reference(message)

        # For WhatsApp or any other source, we should ensure the report is valid HTML
        # if we are going to send it with parse_mode='html'.
        # Since TelegramSource already returns HTML, we only need to worry about others.
        if message.source != "telegram":
            # Simple approach: escape everything from non-telegram sources
            # But wait, source.get_message_reference(message) might have some structure.
            # It's better to escape the components inside the source's get_message_reference.
            pass

        await client.send_message(
            PeerChannel(output_dialog_id),
            report_text,
            parse_mode='html',
            link_preview=False,
            schedule=timedelta(seconds=60 + Util._offset * 60),
        )

        Util._offset += 1

    @staticmethod
    def construct_message_object(message: UnifiedMessage, timezone_name: str = "Europe/Madrid"):
        return {
            'source': message.source,
            'chat_title': message.chat_title,
            'chat_id': message.chat_id,
            'text': message.text,
            'sender_name': message.sender_name,
            'message_id': message.message_id,
            'datetime': message.timestamp.astimezone(ZoneInfo(timezone_name)).isoformat(),
        }

    @staticmethod
    def is_message_in_list(str1: str, str_list: list) -> bool:
        """
        Returns True if str1 matches any string in str_list,
        comparing only letters and ignoring newlines and case.
        Strips HTML tags first.
        """
        if not str1:
            return False

        def clean(s):
            # Strip HTML tags
            s = re.sub(r'<[^>]+>', '', s)
            # Filter only alpha
            return ''.join(filter(str.isalpha, s.replace('\n', ''))).lower()

        str1_clean = clean(str1)
        for s in str_list:
            if clean(s) == str1_clean:
                return True
        return False



