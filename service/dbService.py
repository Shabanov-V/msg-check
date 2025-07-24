import sqlite3
from typing import List, Tuple, Optional
from datetime import datetime, timedelta

class DBService:
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dialog_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME NOT NULL,
                    description TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(dialog_id, event_id)
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

    def store_calendar_event(
        self,
        dialog_id: str,
        event_id: str,
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: Optional[str] = None
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO calendar_events (
                    dialog_id, event_id, title, start_time, end_time, description
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (dialog_id, event_id, title, start_time, end_time, description))
            conn.commit()

    def get_events_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        delta_minutes: int = 0
    ) -> List[Tuple]:
        """
        Retrieve all calendar events where the event's start_time and end_time fall within
        the given range, expanded by +/- delta_minutes.
        """

        start_lower = start_time - timedelta(minutes=delta_minutes)
        end_upper = end_time + timedelta(minutes=delta_minutes)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM calendar_events
                WHERE start_time >= ? AND end_time <= ?
            """, (start_lower, end_upper))
            return cursor.fetchall()