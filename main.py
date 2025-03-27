from telethon import TelegramClient
from model.envLoader import EnvLoader
from service.textAnalyzer import TextAnalyzer
from telethon.tl import functions
from service.messageServiceDB import MessageServiceDB
from telethon.tl.types import PeerChannel
from datetime import datetime, timedelta
from service.util import Util

env = EnvLoader()
client = TelegramClient('main', env.telegram_api_id, env.telegram_api_hash)


async def main():
    # Init
    textAnalyzer = TextAnalyzer(env.gemini_key, env.base_prompt)
    await client.start()
    messageServiceDB = MessageServiceDB()
    

    target_dialog_ids = []
    request = await client(functions.messages.GetDialogFiltersRequest())
    for dialog_filter in request.filters:
        if  hasattr(dialog_filter, 'id') and dialog_filter.title.text == env.target_dialog_filter:
            target_dialog_ids = list(map(lambda peer: peer.channel_id, dialog_filter.include_peers))

    total_messages_processed = 0
    total_messages_found = 0
    for dialog_id in target_dialog_ids:
        last_processed_message = messageServiceDB.get_last_processed_message(dialog_id)
        if last_processed_message is None:
            last_processed_message = -1

        messages = await client.get_messages(PeerChannel(dialog_id), min_id=last_processed_message, limit=10000)
        messages = list(filter(lambda m: m.date.timestamp() > (datetime.now() - timedelta(days=1)).timestamp(), messages))

        if not messages:
            continue
        total_messages_processed += len(messages)
        dialog_name = messages[0].chat.title
        messageServiceDB.store_dialog_name(dialog_id, dialog_name)
        messages_text = list(reversed(list((map(lambda m: '{}: {}'.format(m.id, m.text), messages)))))

        try:
            response = textAnalyzer.findMessages(str(messages_text))
        except Exception as e:
            await client.send_message(PeerChannel(env.error_dialog_id), 'Error processing messages from dialog {}, \nError: {}'.format(dialog_name, e))
            continue
        if response is not None:
            total_messages_found += len(response)
            messages_found = list(filter(lambda m: m.id in response, messages))
            for message_found in messages_found:
                try:
                    await Util.send_message_report(client, message_found, env.output_dialog_id)
                except Exception as e:
                    await client.send_message(PeerChannel(env.error_dialog_id), 'Error processing message {},\nFrom char: {},\nError: {}'.format(message_found.id, dialog_name, e))
        messageServiceDB.update_last_processed_message(dialog_id, messages[0].id, messages[-1].date)

    await client.send_message(PeerChannel(env.error_dialog_id), 'Execution completed.\nMessages processed: {},\nMessages found: {}'.format(total_messages_processed, total_messages_found))

with client:
    client.loop.run_until_complete(main())