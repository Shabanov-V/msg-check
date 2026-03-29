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

        if message.source == "telegram":
            await client.send_message(
                PeerChannel(output_dialog_id),
                report_text,
                parse_mode='html',
                link_preview=False,
                schedule=timedelta(seconds=60 + Util._offset * 60),
            )
        else:
            await client.send_message(
                PeerChannel(output_dialog_id),
                report_text,
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
            'message_id': message.message_id,
            'datetime': message.timestamp.astimezone(ZoneInfo(timezone_name)).isoformat(),
        }

    @staticmethod
    def is_message_in_list(str1: str, str_list: list) -> bool:
        """
        Returns True if str1 matches any string in str_list,
        comparing only letters and ignoring newlines and case.
        """
        if not str1:
            return False
        str1_clean = ''.join(filter(str.isalpha, str1.replace('\n', ''))).lower()
        for s in str_list:
            s_clean = ''.join(filter(str.isalpha, s.replace('\n', ''))).lower()
            if str1_clean == s_clean:
                return True
        return False



