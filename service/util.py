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
            'text': message.text,
            'id': message.id,
            'datetime': message.date.astimezone(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d %H:%M:%S %z"),
        }

    @staticmethod
    def compare_strings(str1: str, str2: str) -> bool:
        # compare only letters and remove \n
        str1 = str1.replace('\n', '')
        str2 = str2.replace('\n', '')
        str1_letters = ''.join(filter(str.isalpha, str1))
        str2_letters = ''.join(filter(str.isalpha, str2))
        return str1_letters.lower() == str2_letters.lower()



