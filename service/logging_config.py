import logging


def configure_logging():
    """Set up root logging and quiet noisy third-party loggers.

    Telethon logs flood-waits, reconnects and 'very old message' at INFO,
    which buries real app-level errors. Drop it to WARNING.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)
