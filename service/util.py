from telethon import TelegramClient
from telethon.tl.types import Message, PeerChannel, PeerUser
from datetime import timedelta
import time

class Util:
    @staticmethod
    def get_message_link(message: Message):
        if not message.chat.megagroup and not message.chat.gigagroup and not message.chat.broadcast:
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
        await client.send_message(PeerChannel(output_dialog_id), message_link, link_preview=False, schedule=timedelta(seconds=60))
        await client.forward_messages(PeerChannel(output_dialog_id), message, schedule=timedelta(seconds=61))
        time.sleep(5)

    @staticmethod
    def construct_message_object(message: Message):
        return {
            'chat_title': message.chat.title,
            'text': message.text,
            'id': message.id
        }
            
            

