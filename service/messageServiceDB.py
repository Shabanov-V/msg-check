import sqlite3
from typing import List, Tuple, Optional
from datetime import datetime

class MessageServiceDB:
    def __init__(self, db_path: str = "messages.db"):
        self.db_path = db_path
        self._create_tables()

    def _create_tables(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dialogs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dialog_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    processed_message_id NUMBER,
                    processed_message_timestamp DATETIME,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def store_dialog_name(self, dialog_id: str, name: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO dialogs (dialog_id, name) VALUES (?, ?)
            """, (dialog_id, name))
            conn.commit()

    def get_last_processed_message(self, dialog_id: str) -> Optional[int]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT processed_message_id FROM dialogs WHERE dialog_id = ?", (dialog_id,))
            result = cursor.fetchone()
            return result[0] if result else None
    
    def update_last_processed_message(self, dialog_id: str, message_id: int, message_time: datetime) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE dialogs SET processed_message_id = ?, processed_message_timestamp = ? WHERE dialog_id = ?", (message_id, message_time, dialog_id))
            conn.commit()