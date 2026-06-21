import os
import sys
import logging
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from service.logging_config import configure_logging


class TestLoggingConfig(unittest.TestCase):
    def test_telethon_logger_quieted_to_warning(self):
        # Telethon floods INFO with flood-waits/reconnects/'very old message',
        # burying real app errors. Configure it down to WARNING.
        logging.getLogger("telethon").setLevel(logging.NOTSET)  # reset first

        configure_logging()

        self.assertEqual(logging.getLogger("telethon").level, logging.WARNING)


if __name__ == "__main__":
    unittest.main()
