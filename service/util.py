from telethon import TelegramClient
from telethon.tl.types import Message, PeerChannel, PeerUser

class Util:
    @staticmethod
    def get_message_link(message: Message):
        if (message.chat.has_link and message.chat.username is not None):
            return 'https://t.me/{}/{}'.format(message.chat.username, message.id)
        else:
            return 'https://t.me/c/{}/{}'.format(message.chat.id, message.id)

    @staticmethod
    async def send_message_report(client: TelegramClient, message: Message, dialog_id: int):
        if (message is None):
            return None
        
        message_link = Util.get_message_link(message)

        message_sent = False
        if (type(message.from_id) is PeerUser):
            await client.send_message(PeerChannel(dialog_id), message_link, link_preview=True)
            message_sent = True
        if ((not message_sent) or (not message.chat.has_link)):
            await client.forward_messages(PeerChannel(dialog_id), message)

    @staticmethod
    def construct_message_object(message: Message):
        return {
            'chat_title': message.chat.title,
            'text': message.text,
            'id': message.id
        }
            
            

