"""Synthetic-handle join between LLM Phase-1 output and fetched messages.

The LLM echoes back only whatever id it is handed. Real `message_id`s are
per-chat and collide across chats, so handing the model real ids makes the
result->message join ambiguous. We instead hand it a run-unique synthetic
handle ("m0", "m1", ...) and resolve results back to the real `UnifiedMessage`
by handle. See docs/adr/0005 and the msg_by_id collision bug.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from model.unifiedMessage import UnifiedMessage

HANDLE_PREFIX = "m"


def make_handle(index: int) -> str:
    return f"{HANDLE_PREFIX}{index}"


def parse_handle(handle: Any, count: int) -> Optional[int]:
    """Return the in-range index for a handle, or None if invalid."""
    if not isinstance(handle, str) or not handle.startswith(HANDLE_PREFIX):
        return None
    raw = handle[len(HANDLE_PREFIX):]
    if not raw.isdigit():
        return None
    index = int(raw)
    return index if 0 <= index < count else None


def assign_handles(message_objects: List[dict]) -> List[dict]:
    """Overwrite each serialized message object's `message_id` with its handle.

    `message_objects` must be in the same order they are sent to the LLM, so
    handle "m{i}" maps back to messages[i] on resolve.
    """
    for i, obj in enumerate(message_objects):
        obj["message_id"] = make_handle(i)
    return message_objects


@dataclass
class ResolvedResults:
    matched: List[Tuple[UnifiedMessage, str]] = field(default_factory=list)
    events: List[Tuple[UnifiedMessage, dict]] = field(default_factory=list)
    borderline: List[Tuple[UnifiedMessage, str]] = field(default_factory=list)
    recoveries: int = 0
    still_missing: List[str] = field(default_factory=list)


def _recover_by_text(
    messages: List[UnifiedMessage], text: str, claimed: set
) -> Optional[Tuple[int, UnifiedMessage]]:
    """Match a result's echoed text to an unclaimed message (id-garble fallback)."""
    target = (text or "").strip()
    if not target:
        return None
    for i, m in enumerate(messages):
        if i in claimed:
            continue
        if m.text.strip() == target:
            return i, m
    return None


def resolve_llm_results(messages: List[UnifiedMessage], response: dict) -> ResolvedResults:
    """Resolve an LLM Phase-1 response against the messages it was given.

    `messages` is the exact list serialized to the LLM, in order; handle "m{i}"
    refers to `messages[i]`. Returns real `UnifiedMessage` objects with real ids.
    """
    resolved = ResolvedResults()
    count = len(messages)
    claimed: set = set()

    for r in response.get("results", []):
        index = parse_handle(r.get("message_id"), count)
        if index is not None and index not in claimed:
            claimed.add(index)
            resolved.matched.append((messages[index], r.get("reason", "")))
            continue
        # Bad/duplicate handle: fall back to text match (hallucination recovery).
        recovered = _recover_by_text(messages, r.get("text", ""), claimed)
        if recovered is not None:
            idx, message = recovered
            claimed.add(idx)
            resolved.recoveries += 1
            resolved.matched.append((message, r.get("reason", "")))
        else:
            resolved.still_missing.append(r.get("message_id"))

    for e in response.get("Events", []):
        index = parse_handle(e.get("message_id"), count)
        if index is None:
            continue
        message = messages[index]
        e["message_id"] = message.message_id  # restore real id for calendar/dedup
        resolved.events.append((message, e))

    for b in response.get("borderline", []):
        index = parse_handle(b.get("message_id"), count)
        if index is None:
            continue
        message = messages[index]
        resolved.borderline.append((message, b.get("exclusion_reason", "")))

    return resolved
