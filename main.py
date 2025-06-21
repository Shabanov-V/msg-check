from telethon import TelegramClient
from model.envLoader import EnvLoader
from service.textAnalyzer import TextAnalyzer
from service.calendarService import CalendarService
from telethon.tl import functions
from service.messageServiceDB import MessageServiceDB
from telethon.tl.types import PeerChannel, InputPeerChannel, InputPeerChat, InputPeerUser
from datetime import datetime, timedelta
from service.util import Util
from tenacity import retry, stop_after_attempt, wait_fixed
from model.dialog import Dialog
from model.dialogType import DialogType

env = EnvLoader()
client = TelegramClient('main', env.telegram_api_id, env.telegram_api_hash)


@retry(stop=stop_after_attempt(5), wait=wait_fixed(10))
async def get_dialog_filters_with_retry(client):
    return await client(functions.messages.GetDialogFiltersRequest())

@retry(stop=stop_after_attempt(5), wait=wait_fixed(10))
async def get_messages_with_retry(client, dialog_peer, last_processed_message):
    return await client.get_messages(dialog_peer, min_id=last_processed_message, limit=10000)

def build_dialog_object(peer):
    if type(peer) == InputPeerChannel:
        return Dialog(peer.channel_id, DialogType.CHANNEL)
    elif type(peer) == InputPeerChat:
        return Dialog(peer.chat_id, DialogType.CHAT)
    elif type(peer) == InputPeerUser:
        return Dialog(peer.user_id, DialogType.USER)

def is_message_in_list(message, message_list) -> bool:
    for msg in message_list:
        if Util.compare_strings(message, msg):
            return True
    return False

async def main():
    # Init
    textAnalyzer = TextAnalyzer(env.gemini_key, env.base_prompt)
    calendarService = CalendarService()
    await client.start()
    messageServiceDB = MessageServiceDB()
    sent_massages = []

    target_dialog_objects = []
    request = await get_dialog_filters_with_retry(client)
    for dialog_filter in request.filters:
        if  hasattr(dialog_filter, 'id') and dialog_filter.title.text == env.target_dialog_filter:
            target_dialog_objects = list(map(lambda peer: build_dialog_object(peer), dialog_filter.include_peers))
    total_messages_processed = 0
    total_messages_found = 0
    for dialog_object in target_dialog_objects:
        last_processed_message = messageServiceDB.get_last_processed_message(dialog_object.id)
        if last_processed_message is None:
            last_processed_message = -1

        messages = await get_messages_with_retry(client, dialog_object.peer, last_processed_message)
        messages = list(filter(lambda m: m.date.timestamp() > (datetime.now() - timedelta(days=1)).timestamp(), messages))

        if not messages:
            continue
        total_messages_processed += len(messages)
        dialog_name = messages[0].chat.title
        messageServiceDB.store_dialog_name(dialog_object.id, dialog_name)
        message_objects = list(reversed(list((map(lambda m: Util.construct_message_object(m), messages)))))

        try:
            response = textAnalyzer.findMessages(str(message_objects))
        except Exception as e:
            await client.send_message(PeerChannel(env.error_dialog_id), 'Error processing messages from dialog {}, \nError: {}'.format(dialog_name, e))
            continue
        if response is not None:
            message_ids = response.get('IDs', [])
            events = response.get('Events', [])
            total_messages_found += len(message_ids)
            messages_found = list(reversed(list(filter(lambda m: m.id in message_ids, messages))))
            for message_found in messages_found:
                if is_message_in_list(message_found.message, sent_massages):
                    continue
                try:
                    await Util.send_message_report(client, message_found, env.output_dialog_id)
                except Exception as e:
                    await client.send_message(PeerChannel(env.error_dialog_id), 'Error processing message {},\nFrom char: {},\nError: {}'.format(message_found.id, dialog_name, e))
                sent_massages.append(message_found.message)
            for event in events:
                try:
                    message = next((m for m in messages if m.id == event['id']), None)
                    start_datetime = datetime.fromisoformat(event['start_datetime'])
                    end_datetime = datetime.fromisoformat(event['end_datetime'])
                    calendarService.create_event(
                        name=event['title'],
                        description=event['description'] + '\n\n{}'.format(Util.get_message_link(message)),
                        start_datetime=start_datetime,
                        end_datetime=end_datetime
                    )
                except Exception as e:
                    await client.send_message(PeerChannel(env.error_dialog_id), 'Error creating event from message {},\nFrom char: {},\nError: {}'.format(event['id'], dialog_name, e))
        messageServiceDB.update_last_processed_message(dialog_object.id, messages[0].id, messages[-1].date)
    await client.send_message(PeerChannel(env.error_dialog_id), 'Execution completed.\nMessages processed: {},\nMessages found: {}'.format(total_messages_processed, total_messages_found))

with client:
    client.loop.run_until_complete(main())