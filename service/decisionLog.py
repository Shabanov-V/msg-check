"""Build per-message decision-log rows from a resolved Phase-1 result.

One row per fetched message records the system's verdict so false positives
(reported but not relevant) and false negatives (skipped but relevant) can be
detected retrospectively. An offline judge and a human fill `judge_verdict` /
`human_label` later. See docs/adr/0004 and docs/design/retrospective-decision-log.
"""

from typing import List, Set, Tuple

from model.unifiedMessage import UnifiedMessage
from service.llmJoin import ResolvedResults

Key = Tuple[str, str, str]  # (source, chat_id, message_id)


def _key(m: UnifiedMessage) -> Key:
    return (m.source, m.chat_id, m.message_id)


def build_decision_rows(
    messages: List[UnifiedMessage],
    resolved: ResolvedResults,
    dedup_keys: Set[Key],
    *,
    run_id: str,
    llm_model: str,
    prompt_version: str,
) -> List[dict]:
    """Return one dict row per message in `messages`, carrying its verdict."""
    reported = {_key(m): reason for m, reason in resolved.matched}
    borderline = {_key(m): reason for m, reason in resolved.borderline}

    rows: List[dict] = []
    for m in messages:
        k = _key(m)
        if k in reported:
            verdict = "reported"
            reason = reported[k]
            feed_action = "dedup_skipped" if k in dedup_keys else "sent"
        elif k in borderline:
            verdict = "borderline"
            reason = borderline[k]
            feed_action = None
        else:
            verdict = "skipped"
            reason = None
            feed_action = None

        rows.append({
            "run_id": run_id,
            "source": m.source,
            "chat_id": m.chat_id,
            "message_id": m.message_id,
            "chat_title": m.chat_title,
            "text": m.text,
            "timestamp": m.timestamp,
            "phase1_verdict": verdict,
            "feed_action": feed_action,
            "phase1_reason": reason,
            "llm_model": llm_model,
            "prompt_version": prompt_version,
        })
    return rows
