# Join LLM Phase-1 output to messages by synthetic handle, not real `message_id`

**Status:** accepted
**Date:** 2026-06-21

## Context

`message_id` is **per-chat**, not globally unique — Telegram/WhatsApp number
messages within a chat, so two chats fetched in the same run can both carry id
`1424`. The LLM is given each message's real `message_id` (`util.py`,
`construct_message_object`) and echoes only that id back in `results` / `Events` /
`borderline`. Every result→message join then keyed on the bare id:

- `messages_found = [m for m in all_messages if m.message_id in message_ids]`
- `msg_by_id[message_id]` (built at `messageService.py:94`, read for borderline and
  events)
- `dialog_map[(source, message_id)]`

On a collision, the wrong `UnifiedMessage` is selected: borderline reports the
wrong `chat_title`, and — worse — a calendar event is built from the wrong message,
giving a wrong `dialog_id`, wrong source link, and a `calendar_events.event_id`
that points at an unrelated chat. The failure is silent (wrong data, not a crash)
and rare (ids are large and sparse), so it can sit undetected. The eval harness
never exposed it because `generate_random_metadata` mints unique random ids.

## Decision

Hand the LLM a **run-unique synthetic handle** (`"m{i}"`) in place of the real
`message_id`, and resolve results back to the real `UnifiedMessage` by handle.

1. **`service/llmJoin.py`** (new, pure, unit-tested):
   - `assign_handles(message_objects)` — overwrite each serialized object's
     `message_id` with `"m{i}"` in LLM-facing order.
   - `resolve_llm_results(messages, response) -> ResolvedResults` — handle `"m{i}"`
     maps to `messages[i]`; returns `matched` / `events` / `borderline` carrying real
     `UnifiedMessage` objects, with real ids **restored** into the result/event
     dicts at the seam (so calendar dedup and the planned `decision_log` see real
     ids). Tracks `recoveries` and `still_missing`.
2. **`MessageService.process_sources`** assigns handles before the LLM call, then
   replaces the bare-id join (and the buggy `msg_by_id`) with one call to
   `resolve_llm_results`. `dialog_map` re-keyed to the composite
   `(source, chat_id, message_id)`.
3. **Hallucination recovery kept**, now triggered by an invalid handle
   (non-`"m"`-prefixed, out of range, or a duplicate claim) → text-match against
   unclaimed messages, exactly as before but collision-safe.

## Why (the trade-offs)

- **Synthetic handle over "make the LLM also return `chat_id`."** The latter adds a
  field the model must reliably emit — and the very existence of the id-recovery
  path shows the model mangles ids. A handle changes nothing semantically; the model
  just parrots a token.
- **Prefixed `"m{i}"` over a bare int.** Visibly not a Telegram id, so a model prone
  to "correcting" ids is less likely to normalize it, and validation is unambiguous
  (`startswith("m")` + in range). A bare `"3"` could be silently rewritten to `"4"`.
- **`MessageService` owns the map.** The recovery loop, `dialog_map`, and result
  resolution already live there; keeping the map local leaves `findMessages` and the
  eval harness (`integration_tester.py`) signatures untouched.
- **Extracted a pure helper to make it testable.** The bug is in the join, so the
  join is tested in isolation (`tests/test_llm_join.py`): two chats sharing
  `message_id "1424"`, model echoes `"m0"`/`"m1"`, assert each resolves to the right
  chat and that event `event_id` restores to the real id. Deterministic, no API.

## Consequences

- The handle is internal: it never reaches calendar storage, the report, or the DB.
- Cross-run calendar dedup (`UNIQUE(dialog_id, event_id)`) is now correct — `event_id`
  is the real per-chat message id again.
- Independent of, but complementary to, the
  [[0004-decision-log-for-retrospective-fp-fn-detection]] composite identity
  `(source, chat_id, message_id)`.

## See also

`service/llmJoin.py`, `tests/test_llm_join.py`.
