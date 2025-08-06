from zoneinfo import ZoneInfo
from telethon import TelegramClient
from telethon.tl.types import Message, PeerChannel, PeerUser, Chat
from datetime import timedelta
import asyncio

class Util:

    _offset = 0

    @staticmethod
    def get_message_link(message: Message):
        if isinstance(message.chat, Chat):
            return 'From chat: {}'.format(message.chat.title)
        if (hasattr(message.chat, 'has_link') and message.chat.has_link and message.chat.username is not None):
            return 'https://t.me/{}/{}'.format(message.chat.username, message.id)
        else:
            return 'https://t.me/c/{}/{}'.format(message.chat.id, message.id)

    @staticmethod
    async def send_message_report(client: TelegramClient, message: Message, output_dialog_id: int):
        if (message is None):
            return None
        
        message_link = Util.get_message_link(message)

        # Send message with delay to mark as unread
        await client.send_message(
            PeerChannel(output_dialog_id), 
            message_link, 
            link_preview=False, 
            schedule=timedelta(seconds=60 + Util._offset * 60)
            )
        await client.forward_messages(
            PeerChannel(output_dialog_id), 
            message, 
            schedule=timedelta(seconds=90 + Util._offset * 60)
            )

        Util._offset += 1

    @staticmethod
    def construct_message_object(message: Message):
        return {
            'chat_title': message.chat.title,
            'chat_id': message.chat.id,
            'text': Util.construct_message_text(message),
            'message_id': message.id,
            'datetime': message.date.astimezone(ZoneInfo("Europe/Madrid")).isoformat(),
        }
    
    @staticmethod
    def construct_message_text(message: Message):
        return f"{message.text}\n{Util.get_poll_question_text(message)}" if message.text else Util.get_poll_question_text(message)

    @staticmethod
    def get_poll_question_text(message: Message):
        """
        Safely returns the poll question text if it exists, otherwise returns an empty string.
        """
        try:
            return message.media.poll.question.text
        except AttributeError:
            return ""

    @staticmethod
    def is_message_in_list(str1: str, str_list: list) -> bool:
        """
        Returns True if str1 matches any string in str_list,
        comparing only letters and ignoring newlines and case.
        """
        str1_clean = ''.join(filter(str.isalpha, str1.replace('\n', ''))).lower()
        for s in str_list:
            s_clean = ''.join(filter(str.isalpha, s.replace('\n', ''))).lower()
            if str1_clean == s_clean:
                return True
        return False



