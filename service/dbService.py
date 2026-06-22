import sqlite3
from typing import List, Tuple, Optional
from datetime import datetime, timedelta

from service.runContext import RunContext

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
                    google_event_id TEXT,
                    title TEXT NOT NULL,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME NOT NULL,
                    description TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(dialog_id, event_id)
                )
            """)
            # Migration to add google_event_id if it doesn't exist
            try:
                cursor.execute("ALTER TABLE calendar_events ADD COLUMN google_event_id TEXT")
            except sqlite3.OperationalError:
                pass # Column already exists

            # Migration: prefix existing dialog_id entries with "telegram:" for source disambiguation
            cursor.execute("UPDATE dialogs SET dialog_id = 'telegram:' || dialog_id WHERE dialog_id NOT LIKE '%:%'")
            cursor.execute("UPDATE calendar_events SET dialog_id = 'telegram:' || dialog_id WHERE dialog_id NOT LIKE '%:%'")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS run_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_timestamp DATETIME NOT NULL,
                    duration_sec REAL,
                    sources_count INTEGER,
                    chats_count INTEGER,
                    messages_processed INTEGER,
                    messages_matched INTEGER,
                    events_found INTEGER,
                    events_deduplicated INTEGER,
                    hallucination_recoveries INTEGER,
                    dedup_skips INTEGER,
                    errors_count INTEGER,
                    llm_phase1_duration_sec REAL,
                    llm_phase2_duration_sec REAL,
                    verbosity TEXT,
                    match_rate REAL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS decision_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    chat_title TEXT,
                    text TEXT NOT NULL,
                    timestamp DATETIME,
                    phase1_verdict TEXT NOT NULL,
                    feed_action TEXT,
                    phase1_reason TEXT,
                    llm_model TEXT,
                    prompt_version TEXT,
                    judge_verdict TEXT,
                    human_label TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(run_id, source, chat_id, message_id)
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

    def get_last_processed_timestamp(self, dialog_id: str) -> Optional[datetime]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT processed_message_timestamp FROM dialogs WHERE dialog_id = ?", (dialog_id,))
            result = cursor.fetchone()
            if result and result[0]:
                ts = result[0]
                if isinstance(ts, str):
                    return datetime.fromisoformat(ts)
                return ts
            return None
    
    def update_last_processed_message(self, dialog_id: str, message_id: str, message_time: datetime) -> None:
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
        description: Optional[str] = None,
        google_event_id: Optional[str] = None
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO calendar_events (
                    dialog_id, event_id, title, start_time, end_time, description, google_event_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (dialog_id, event_id, title, start_time, end_time, description, google_event_id))
            conn.commit()

    def get_events_starting_around(
        self,
        start_time: datetime,
        window_minutes: int = 120
    ) -> List[sqlite3.Row]:
        """
        Retrieve all calendar events where the event's start_time is within
        +/- window_minutes of the given start_time. Rows are accessible by
        column name (e.g. row["title"]); see calendar_events schema.
        """
        start_lower = start_time - timedelta(minutes=window_minutes)
        start_upper = start_time + timedelta(minutes=window_minutes)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM calendar_events
                WHERE start_time >= ? AND start_time <= ?
            """, (start_lower, start_upper))
            return cursor.fetchall()

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

    def store_run(self, run_ctx: RunContext, verbosity: str = "normal") -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO run_history (
                    run_timestamp, duration_sec, sources_count, chats_count,
                    messages_processed, messages_matched, events_found,
                    events_deduplicated, hallucination_recoveries, dedup_skips,
                    errors_count, llm_phase1_duration_sec, llm_phase2_duration_sec,
                    verbosity, match_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_ctx.start_time.isoformat(),
                run_ctx.duration_sec,
                run_ctx.sources_count,
                run_ctx.chats_count,
                run_ctx.total_fetched,
                run_ctx.total_matched,
                run_ctx.total_events,
                run_ctx.total_events_deduplicated,
                run_ctx.hallucination_recoveries,
                len(run_ctx.dedup_skips),
                len(run_ctx.errors),
                run_ctx.llm_phase1_duration_sec,
                run_ctx.llm_phase2_duration_sec,
                verbosity,
                run_ctx.match_rate,
            ))
            conn.commit()

    # -- Decision log (retrospective FP/FN detection; see ADR 0004) --

    _DECISION_COLS = (
        "run_id", "source", "chat_id", "message_id", "chat_title", "text",
        "timestamp", "phase1_verdict", "feed_action", "phase1_reason",
        "llm_model", "prompt_version",
    )

    def store_decision_log(self, rows: List[dict]) -> None:
        if not rows:
            return
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.executemany(
                f"INSERT OR IGNORE INTO decision_log "
                f"({', '.join(self._DECISION_COLS)}) "
                f"VALUES ({', '.join('?' for _ in self._DECISION_COLS)})",
                [tuple(r.get(c) for c in self._DECISION_COLS) for r in rows],
            )
            conn.commit()

    def get_decision_rows(self, run_id: Optional[str] = None) -> List[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if run_id is None:
                cursor.execute("SELECT * FROM decision_log")
            else:
                cursor.execute("SELECT * FROM decision_log WHERE run_id = ?", (run_id,))
            return [dict(r) for r in cursor.fetchall()]

    def get_unjudged_rows(self) -> List[dict]:
        """Rows awaiting a judge verdict (judging is done by Claude, not a model)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM decision_log WHERE judge_verdict IS NULL ORDER BY id")
            return [dict(r) for r in cursor.fetchall()]

    def set_judge_verdict(self, row_id: int, verdict: str) -> None:
        if verdict not in ("relevant", "not"):
            raise ValueError(f"judge_verdict must be 'relevant' or 'not', got {verdict!r}")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE decision_log SET judge_verdict = ? WHERE id = ?", (verdict, row_id)
            )
            conn.commit()

    def set_human_label(self, row_id: int, label: str) -> None:
        if label not in ("relevant", "not"):
            raise ValueError(f"human_label must be 'relevant' or 'not', got {label!r}")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE decision_log SET human_label = ? WHERE id = ?", (label, row_id)
            )
            conn.commit()

    def purge_stale_skipped(self, days: int = 90) -> int:
        """Delete untouched skipped rows older than `days` (PII retention, ADR 0004 §6)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM decision_log WHERE phase1_verdict = 'skipped' "
                "AND judge_verdict IS NULL AND human_label IS NULL "
                "AND created_at < datetime('now', ?)",
                (f"-{int(days)} days",),
            )
            conn.commit()
            return cursor.rowcount

    def get_recent_runs(self, n: int = 5) -> List[sqlite3.Row]:
        """Recent run_history rows, accessible by column name (e.g. row["match_rate"])."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM run_history ORDER BY id DESC LIMIT ?", (n,)
            )
            return cursor.fetchall()