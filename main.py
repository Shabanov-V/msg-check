from telethon import TelegramClient
from model.envLoader import EnvLoader
from service.textAnalyzer import TextAnalyzer
from service.calendarService import CalendarService
from telethon.tl import functions
from service.dbService import DBService
from telethon.tl.types import PeerChannel, InputPeerChannel, InputPeerChat, InputPeerUser
from datetime import datetime, timedelta
from service.util import Util
from tenacity import retry, stop_after_attempt, wait_fixed
from model.dialog import Dialog
from model.dialogType import DialogType
from service.messageService import MessageService

env = EnvLoader()
client = TelegramClient('main', env.telegram_api_id, env.telegram_api_hash)


@retry(stop=stop_after_attempt(5), wait=wait_fixed(10))
async def get_dialog_filters_with_retry(client):
    return await client(functions.messages.GetDialogFiltersRequest())

def build_dialog_object(peer):
    if type(peer) == InputPeerChannel:
        return Dialog(peer.channel_id, DialogType.CHANNEL)
    elif type(peer) == InputPeerChat:
        return Dialog(peer.chat_id, DialogType.CHAT)
    elif type(peer) == InputPeerUser:
        return Dialog(peer.user_id, DialogType.USER)

def get_target_dialog_objects(request, env):
    for dialog_filter in request.filters:
        if hasattr(dialog_filter, 'id') and dialog_filter.title.text == env.target_dialog_filter:
            return list(map(lambda peer: build_dialog_object(peer), dialog_filter.include_peers))
    return []

async def main():
    text_analyzer = TextAnalyzer(env.gemini_key, env.base_prompt)
    await client.start()
    db_service = DBService()
    sent_messages = []

    try:
        calendar_service = CalendarService(env.calendar_id)
    except Exception as e:
        await client.send_message(
            PeerChannel(env.error_dialog_id),
            f'Error initializing Calendar Service: {e}'
        )
        return

    except Exception as e:
        print(f"Error initializing services: {e}")
        return

    message_service = MessageService(
        client=client,
        db_service=db_service,
        text_analyzer=text_analyzer,
        calendar_service=calendar_service,
        env=env,
    )

    request = await get_dialog_filters_with_retry(client)
    target_dialog_objects = get_target_dialog_objects(request, env)

    # Collect all peers from all target dialogs
    all_peers = []
    for dialog_object in target_dialog_objects:
        all_peers.append(dialog_object)

    total_messages_processed = 0
    total_messages_found = 0
    total_events_found = 0

    # Process all messages from all dialogs at once
    processed, messages_found, events_found = await message_service.process_dialogs(
        all_peers, sent_messages
    )
    total_messages_processed += processed
    total_messages_found += messages_found
    total_events_found += events_found

    await client.send_message(
        PeerChannel(env.error_dialog_id),
        f'Execution completed.\nMessages processed: {total_messages_processed},\nMessages found: {total_messages_found},\nEvents found: {total_events_found}'
    )

with client:
    client.loop.run_until_complete(main())