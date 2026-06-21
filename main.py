import logging
from service.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

from telethon import TelegramClient
from model.envLoader import EnvLoader
from service.textAnalyzer import TextAnalyzer
from service.calendarService import CalendarService
from telethon.tl.types import PeerChannel
from service.dbService import DBService
from service.messageService import MessageService
from service.runContext import RunContext
from service.reportGenerator import ReportGenerator
from source.telegramSource import TelegramSource
from source.whatsappSource import WhatsAppSource

env = EnvLoader()
client = TelegramClient('main', env.telegram_api_id, env.telegram_api_hash)


async def main():
    text_analyzer = TextAnalyzer(env.openrouter_api_key, env.base_prompt, env.phase2_prompt, env.llm_model, env.timezone)
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

    message_service = MessageService(
        client=client,
        db_service=db_service,
        text_analyzer=text_analyzer,
        calendar_service=calendar_service,
        env=env,
    )

    # Build list of healthy sources
    sources = []

    # Telegram source (always enabled)
    telegram_source = TelegramSource(client, env, db_service)
    sources.append(telegram_source)

    # WhatsApp source (optional)
    if env.whatsapp_enabled:
        whatsapp_source = WhatsAppSource(
            waha_url=env.waha_api_url,
            waha_api_key=env.waha_api_key,
            session_name=env.waha_session,
            target_label=env.whatsapp_target_label,
            timezone_name=env.timezone,
            db_service=db_service,
        )
        if await whatsapp_source.check_health():
            sources.append(whatsapp_source)
        else:
            await client.send_message(
                PeerChannel(env.error_dialog_id),
                'Warning: WhatsApp source is not healthy (WAHA session not WORKING). Skipping WhatsApp.'
            )

    # Log startup configuration
    logger.info("=== Run started ===")
    logger.info("Sources: %s", ", ".join(s.source_name for s in sources))
    logger.info("LLM Model: %s", env.llm_model)
    logger.info("Timezone: %s", env.timezone)
    logger.info("Verbosity: %s", env.log_verbosity)

    # Process all messages from all sources at once
    run_ctx = RunContext()
    processed, messages_found, events_found = await message_service.process_sources(
        sources, sent_messages, run_ctx
    )

    run_ctx.finalize()
    db_service.store_run(run_ctx, env.log_verbosity)

    report_gen = ReportGenerator(env.log_verbosity)
    report_messages = report_gen.generate(
        run_ctx, db_service if env.log_verbosity == 'verbose' else None
    )
    for msg in report_messages:
        await client.send_message(PeerChannel(env.error_dialog_id), msg, parse_mode='html')

with client:
    client.loop.run_until_complete(main())