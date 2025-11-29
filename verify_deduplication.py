import sqlite3
import os
from datetime import datetime, timedelta
import difflib

# Mock DBService to test logic without full app
class MockDBService:
    def __init__(self, db_path="test_messages.db"):
        self.db_path = db_path
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self._create_tables()

    def _create_tables(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dialog_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    google_event_id TEXT,
                    title TEXT NOT NULL,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME NOT NULL,
                    description TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(dialog_id, event_id)
                )
            """)
            conn.commit()

    def store_calendar_event(self, dialog_id, event_id, title, start_time, end_time, description, google_event_id=None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO calendar_events (
                    dialog_id, event_id, title, start_time, end_time, description, google_event_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (dialog_id, event_id, title, start_time, end_time, description, google_event_id))
            conn.commit()

    def get_events_starting_around(self, start_time, window_minutes=120):
        start_lower = start_time - timedelta(minutes=window_minutes)
        start_upper = start_time + timedelta(minutes=window_minutes)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM calendar_events
                WHERE start_time >= ? AND start_time <= ?
            """, (start_lower, start_upper))
            return cursor.fetchall()

def test_deduplication():
    db = MockDBService()
    
    # Test Case 1: "Team Dinner" vs "Team Dinner with Bob"
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=1)
    db.store_calendar_event(
        dialog_id="chat1",
        event_id="msg1",
        title="Team Dinner",
        start_time=start_time,
        end_time=end_time,
        description="Dinner at 7pm",
        google_event_id="g_event_1"
    )
    
    new_event_title = "Team Dinner with Bob"
    new_event_start = start_time + timedelta(minutes=5)
    
    print(f"Testing: '{new_event_title}' vs 'Team Dinner'")
    candidates = db.get_events_starting_around(new_event_start, window_minutes=120)
    
    is_duplicate = False
    for candidate in candidates:
        candidate_title = candidate[4]
        similarity = difflib.SequenceMatcher(None, new_event_title, candidate_title).ratio()
        print(f"Similarity: {similarity:.2f}")
        if similarity > 0.6 or new_event_title in candidate_title or candidate_title in new_event_title:
            is_duplicate = True
            break
            
    if is_duplicate:
        print("SUCCESS: Duplicate identified.")
    else:
        print("FAILURE: Duplicate NOT identified.")

    # Test Case 2: "Dinner" vs "Dinner with Bob"
    db.store_calendar_event(
        dialog_id="chat2",
        event_id="msg2",
        title="Dinner",
        start_time=start_time,
        end_time=end_time,
        description="Dinner",
        google_event_id="g_event_2"
    )
    
    new_event_title_2 = "Dinner with Bob"
    print(f"\nTesting: '{new_event_title_2}' vs 'Dinner'")
    candidates = db.get_events_starting_around(new_event_start, window_minutes=120)
    
    is_duplicate = False
    for candidate in candidates:
        candidate_title = candidate[4]
        # Skip the "Team Dinner" one for this specific check to focus on "Dinner"
        if candidate_title != "Dinner": continue
        
        similarity = difflib.SequenceMatcher(None, new_event_title_2, candidate_title).ratio()
        print(f"Similarity: {similarity:.2f}")
        if similarity > 0.6 or new_event_title_2 in candidate_title or candidate_title in new_event_title_2:
            is_duplicate = True
            break
            
    if is_duplicate:
        print("SUCCESS: Duplicate identified.")
    else:
        print("FAILURE: Duplicate NOT identified.")

    # Cleanup
    if os.path.exists("test_messages.db"):
        os.remove("test_messages.db")

if __name__ == "__main__":
    test_deduplication()
