from datetime import datetime, timezone
from typing import Dict, List, Optional


class RunContext:
    def __init__(self):
        self.start_time: datetime = datetime.now(timezone.utc)
        self.end_time: Optional[datetime] = None

        # Per-source, per-chat stats: source_name -> chat_key -> {chat_title, source, fetched, matched}
        self._chat_stats: Dict[str, Dict[str, dict]] = {}

        self.llm_phase1_duration_sec: float = 0.0
        self.llm_phase2_duration_sec: float = 0.0
        self.llm_phase1_tokens: Optional[int] = None
        self.llm_phase2_tokens: Optional[int] = None

        self.hallucination_recoveries: int = 0
        self.still_missing_ids: List[str] = []

        self.dedup_skips: List[dict] = []
        self.matched_messages: List[dict] = []
        self.borderline_messages: List[dict] = []
        self.event_results: List[dict] = []
        self.errors: List[str] = []

    # -- Recording helpers --

    def record_messages_fetched(self, source: str, chat_id: str, chat_title: str, count: int):
        if source not in self._chat_stats:
            self._chat_stats[source] = {}
        key = str(chat_id)
        if key not in self._chat_stats[source]:
            self._chat_stats[source][key] = {
                "chat_title": chat_title,
                "source": source,
                "fetched": 0,
                "matched": 0,
            }
        self._chat_stats[source][key]["fetched"] += count

    def _increment_chat_matched(self, source: str, chat_id: str):
        key = str(chat_id)
        if source in self._chat_stats and key in self._chat_stats[source]:
            self._chat_stats[source][key]["matched"] += 1

    def record_match(self, message_id: str, chat_title: str, text: str, reason: str,
                     source: str = "", chat_id: str = ""):
        self.matched_messages.append({
            "message_id": message_id,
            "chat_title": chat_title,
            "text_preview": text[:60],
            "reason": reason,
        })
        if source and chat_id:
            self._increment_chat_matched(source, chat_id)

    def record_dedup_skip(self, message_id: str, chat_title: str, text: str):
        self.dedup_skips.append({
            "message_id": message_id,
            "chat_title": chat_title,
            "text_preview": text[:60],
        })

    def record_borderline(self, message_id: str, chat_title: str, text: str, exclusion_reason: str):
        self.borderline_messages.append({
            "message_id": message_id,
            "chat_title": chat_title,
            "text_preview": text[:60],
            "exclusion_reason": exclusion_reason,
        })

    def record_event(self, title: str, is_duplicate: bool,
                     similarity_score: float = 0.0, matched_against: str = ""):
        self.event_results.append({
            "title": title,
            "is_duplicate": is_duplicate,
            "similarity_score": similarity_score,
            "matched_against": matched_against,
        })

    def record_error(self, error_str: str):
        self.errors.append(error_str)

    def finalize(self, end_time: Optional[datetime] = None):
        self.end_time = end_time or datetime.now(timezone.utc)

    # -- Computed properties --

    @property
    def total_fetched(self) -> int:
        return sum(
            chat["fetched"]
            for source_chats in self._chat_stats.values()
            for chat in source_chats.values()
        )

    @property
    def total_matched(self) -> int:
        return len(self.matched_messages)

    @property
    def total_events(self) -> int:
        return len(self.event_results)

    @property
    def total_events_deduplicated(self) -> int:
        return sum(1 for e in self.event_results if e["is_duplicate"])

    @property
    def sources_count(self) -> int:
        return len(self._chat_stats)

    @property
    def chats_count(self) -> int:
        return sum(len(chats) for chats in self._chat_stats.values())

    @property
    def match_rate(self) -> float:
        total = self.total_fetched
        if total == 0:
            return 0.0
        return self.total_matched / total

    @property
    def duration_sec(self) -> float:
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()

    def get_chat_stats(self) -> List[dict]:
        """Return list of per-chat stats sorted by fetched count descending."""
        result = []
        for source_chats in self._chat_stats.values():
            for chat in source_chats.values():
                fetched = chat["fetched"]
                matched = chat["matched"]
                rate = (matched / fetched * 100) if fetched > 0 else 0.0
                result.append({
                    "chat_title": chat["chat_title"],
                    "source": chat["source"][:2].upper(),  # TG / WA
                    "fetched": fetched,
                    "matched": matched,
                    "rate": rate,
                })
        result.sort(key=lambda x: x["fetched"], reverse=True)
        return result

    def get_high_match_rate_chats(self, threshold: float = 0.20) -> List[dict]:
        """Return chats where match_rate > threshold."""
        return [
            c for c in self.get_chat_stats()
            if c["fetched"] > 0 and (c["matched"] / c["fetched"]) > threshold
        ]

    def get_zero_match_chats(self) -> List[dict]:
        """Return chats with 0 matches but >5 messages fetched."""
        return [
            c for c in self.get_chat_stats()
            if c["matched"] == 0 and c["fetched"] > 5
        ]
