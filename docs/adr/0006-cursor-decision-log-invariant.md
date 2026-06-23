# Cursor advances iff a decision_log row is written; findMessages raises on failure

**Status:** accepted
**Date:** 2026-06-23

## Context

[[0004-decision-log-for-retrospective-fp-fn-detection]] §1 promised "one row per
fetched message ... **before** the watermark advances." That guarantee was never
actually enforced.

`TextAnalyzer.findMessages` returned `None` for **two opposite outcomes**:

1. **Batch all-irrelevant** — Phase 1 LLM succeeded and returned `found=false`
   (`textAnalyzer.py:210-211`, before any row could be built).
2. **LLM/parse failure** — the call failed after 10 retries
   (`textAnalyzer.py:203-205` swallowed the error and returned `None`).

`MessageService.process_sources` wrapped the **entire** results + decision_log
block in `if response is not None:` (`:136`), but the cursor update
(`update_last_processed_message`, `:245`) sat **outside** that guard. So a `None`
from *either* cause skipped all audit rows yet still advanced the watermark.

Observed impact: on 2026-06-23, runs 15:00–18:00 each made one successful LLM call
returning `found=false`, wrote **zero** decision_log rows, reported nothing, and
advanced every chat's cursor — a whole afternoon of traffic became a **Silent
skip** (see `CONTEXT.md`). The same path means a transient LLM outage *also*
silently burns the cursor with `errors_count = 0`.

## Decision

1. **Invariant — a chat's cursor advances iff a decision_log row exists for every
   message it passed.** The watermark advance and the row write move together or
   not at all.

2. **`findMessages` contract — raise on failure, return an empty-but-valid dict on
   no-hits.** Failure propagates (the existing `except` in `process_sources:124`
   already returns *before* the cursor update — freezing it and recording the
   error). `found=false` returns `{results: [], Events: [], borderline, _meta}`,
   which flows through `resolve_llm_results` / `build_decision_rows` to produce a
   `skipped` row per message and a normal cursor advance. The `None` sentinel —
   the thing that conflated the two cases — is deleted.

3. **Control flow keys off `results`, not `found`.** `found` is redundant with
   `len(results) > 0` and is no longer load-bearing; at most it is a sanity-check
   log when `found != (len(results) > 0)`.

## Why (the trade-offs)

- **Raise vs. None sentinel.** A third return state (`None`) was a permanent
  invitation to misread "succeeded, nothing relevant" as "failed." Raising reuses
  the existing failure path that already does the right thing (freeze cursor,
  alert, count the error). Deleting the sentinel kills the bug *class*, not just
  this instance.
- **Freeze cursor on failure.** Re-fetching the same batch next run costs a
  duplicate LLM call but never loses a message; dedup guards double-reports.
  Advancing on failure trades a cent of compute for silent, unrecoverable loss —
  wrong trade.
- **Stop trusting `found`.** Keeping a redundant control field invites the LLM to
  contradict itself (`found=false` with non-empty results would drop real hits).

## Caveats / open levers

- One **combined** LLM call covers all chats, so a raise freezes **every** chat's
  cursor that run — correct (all-or-nothing batch) but a total stall during an LLM
  outage.
- Persistent outage ⇒ every run re-processes a growing backlog and re-alerts.
  Intended (retry + nag); noise reduction is a separate, deferred change.
- **No recovery of already-lost messages.** The 2026-06-23 afternoon backlog stays
  cursor-advanced; this ADR is fix-forward only.

## See also

[[0004-decision-log-for-retrospective-fp-fn-detection]] (the guarantee this
restores), `CONTEXT.md` → "Silent skip".
