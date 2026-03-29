import logging
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from service.runContext import RunContext
    from service.dbService import DBService

logger = logging.getLogger(__name__)

MAX_MESSAGE_LEN = 4000


class ReportGenerator:
    def __init__(self, verbosity: str = "normal"):
        self.verbosity = verbosity if verbosity in ("minimal", "normal", "verbose") else "normal"

    def generate(self, run_ctx: "RunContext", db_service: Optional["DBService"] = None) -> List[str]:
        """Generate report messages from RunContext. Returns list of strings <=4000 chars each."""
        sections: List[str] = []

        # -- Minimal: always present --
        sections.append(self._section_summary(run_ctx))

        if self.verbosity in ("normal", "verbose"):
            sections.append(self._section_timing(run_ctx))
            sections.append(self._section_per_chat(run_ctx))
            sections.append(self._section_dedup(run_ctx))
            sections.append(self._section_events(run_ctx))
            sections.append(self._section_hallucination(run_ctx))
            sections.append(self._section_borderline(run_ctx))
            sections.append(self._section_errors(run_ctx))

        if self.verbosity == "verbose":
            sections.append(self._section_matched_with_reasons(run_ctx))
            if db_service is not None:
                sections.append(self._section_trends(run_ctx, db_service))
            sections.append(self._section_llm_tokens(run_ctx))

        # Filter empty sections
        sections = [s for s in sections if s.strip()]

        return self._chunk_sections(sections)

    # -- Section builders --

    def _section_summary(self, ctx: "RunContext") -> str:
        return (
            f"Execution completed.\n"
            f"Messages processed: {ctx.total_fetched},\n"
            f"Messages found: {ctx.total_matched},\n"
            f"Events found: {ctx.total_events}"
        )

    def _section_timing(self, ctx: "RunContext") -> str:
        return (
            f"\n\u23f1\ufe0f Duration: {ctx.duration_sec:.1f}s "
            f"(Phase 1: {ctx.llm_phase1_duration_sec:.1f}s, "
            f"Phase 2: {ctx.llm_phase2_duration_sec:.1f}s)"
        )

    def _section_per_chat(self, ctx: "RunContext") -> str:
        stats = ctx.get_chat_stats()
        if not stats:
            return ""
        lines = ["\n\ud83d\udcca Per-Chat Breakdown:"]
        for c in stats:
            warning = " \u26a0\ufe0f" if c["rate"] > 20 else ""
            lines.append(
                f"\u2022 {c['chat_title']} ({c['source']}): "
                f"{c['fetched']} fetched, {c['matched']} matched "
                f"({c['rate']:.1f}%){warning}"
            )
        return "\n".join(lines)

    def _section_dedup(self, ctx: "RunContext") -> str:
        count = len(ctx.dedup_skips)
        if count == 0:
            return ""
        return f"\n\ud83d\udd04 Dedup: {count} messages skipped (already reported)"

    def _section_events(self, ctx: "RunContext") -> str:
        if not ctx.event_results:
            return ""
        lines = ["\n\ud83d\udcc5 Events:"]
        for e in ctx.event_results:
            if e["is_duplicate"]:
                lines.append(
                    f"\u2022 \"{e['title']}\" \u2192 Duplicate "
                    f"(\u2194 \"{e['matched_against']}\", similarity: {e['similarity_score']:.2f})"
                )
            else:
                lines.append(f"\u2022 \"{e['title']}\" \u2192 New")
        return "\n".join(lines)

    def _section_hallucination(self, ctx: "RunContext") -> str:
        if ctx.hallucination_recoveries == 0 and not ctx.still_missing_ids:
            return ""
        parts = [f"\n\ud83d\udd27 Hallucination Recovery: {ctx.hallucination_recoveries} recovered"]
        if ctx.still_missing_ids:
            parts[0] += f", {len(ctx.still_missing_ids)} still missing"
        return parts[0]

    def _section_borderline(self, ctx: "RunContext") -> str:
        if not ctx.borderline_messages:
            return ""
        lines = [f"\n\u26a0\ufe0f Borderline Messages ({len(ctx.borderline_messages)}):"]
        for b in ctx.borderline_messages[:10]:  # Cap at 10 for readability
            lines.append(
                f"\u2022 [{b['chat_title']}] \"{b['text_preview']}...\" \u2014 {b['exclusion_reason']}"
            )
        return "\n".join(lines)

    def _section_errors(self, ctx: "RunContext") -> str:
        if not ctx.errors:
            return ""
        return f"\n\u274c Errors: {len(ctx.errors)} non-fatal errors"

    def _section_matched_with_reasons(self, ctx: "RunContext") -> str:
        if not ctx.matched_messages:
            return ""
        lines = ["\n\ud83c\udff7\ufe0f Matched Messages with Reasons:"]
        for m in ctx.matched_messages:
            reason = m.get("reason") or "N/A"
            lines.append(
                f"\u2022 [{m['chat_title']}] \"{m['text_preview']}...\" \u2014 Reason: {reason}"
            )
        return "\n".join(lines)

    def _section_trends(self, ctx: "RunContext", db_service: "DBService") -> str:
        try:
            recent = db_service.get_recent_runs(5)
        except Exception:
            return ""
        if not recent:
            return ""

        avg_match_rate = sum(r[15] or 0 for r in recent) / len(recent) * 100
        avg_duration = sum(r[2] or 0 for r in recent) / len(recent)
        avg_halluc = sum(r[9] or 0 for r in recent) / len(recent)

        this_rate = ctx.match_rate * 100

        return (
            f"\n\ud83d\udcc8 Trend (last {len(recent)} runs):\n"
            f"\u2022 Avg match rate: {avg_match_rate:.1f}% (this run: {this_rate:.1f}%)\n"
            f"\u2022 Avg duration: {avg_duration:.1f}s (this run: {ctx.duration_sec:.1f}s)\n"
            f"\u2022 Avg hallucination recoveries: {avg_halluc:.1f} "
            f"(this run: {ctx.hallucination_recoveries})"
        )

    def _section_llm_tokens(self, ctx: "RunContext") -> str:
        p1 = ctx.llm_phase1_tokens
        p2 = ctx.llm_phase2_tokens
        if p1 is None and p2 is None:
            return ""
        parts = ["\n\ud83d\udd22 LLM Tokens:"]
        if p1 is not None:
            parts.append(f" Phase 1: ~{p1}")
        if p2 is not None:
            parts.append(f" Phase 2: ~{p2}")
        return "".join(parts)

    # -- Chunking --

    def _chunk_sections(self, sections: List[str]) -> List[str]:
        """Combine sections into messages that fit within the Telegram limit."""
        messages: List[str] = []
        current = ""

        for section in sections:
            # If adding this section exceeds limit, flush current
            if current and len(current) + len(section) + 1 > MAX_MESSAGE_LEN:
                messages.append(current.strip())
                current = ""

            # If a single section exceeds limit, split it by lines
            if len(section) > MAX_MESSAGE_LEN:
                if current:
                    messages.append(current.strip())
                    current = ""
                messages.extend(self._split_long_section(section))
            else:
                current += section

        if current.strip():
            messages.append(current.strip())

        return messages if messages else ["Execution completed."]

    def _split_long_section(self, section: str) -> List[str]:
        """Split a single section that exceeds MAX_MESSAGE_LEN by lines."""
        lines = section.split("\n")
        messages: List[str] = []
        current = ""
        for line in lines:
            if current and len(current) + len(line) + 1 > MAX_MESSAGE_LEN:
                messages.append(current.strip())
                current = ""
            current += line + "\n"
        if current.strip():
            messages.append(current.strip())
        return messages
