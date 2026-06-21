# Persist a per-message decision log to retrospectively detect false positives and false negatives

**Status:** accepted
**Date:** 2026-06-21

## Context

The presenting question: *do we collect all the data to retrospectively detect
both false positives and false negatives?* Answer at the time: **no.**

What persists in `messages.db` is the `dialogs` watermark, `calendar_events`, and
`run_history` (aggregate counts only). Per-run detail lives in `RunContext` and
**dies when the process exits** — and even there, matched messages are kept as a
60-char preview, not full text. Two consequences:

- **False positives** (junk Reported — see `CONTEXT.md`) are recoverable only by
  manually scrolling the Telegram Reported feed. No structured store, no full text,
  no query.
- **False negatives** (Relevant messages Skipped) are **undetectable**. Skipped
  messages are never recorded — only counted as `total_fetched - total_matched`.
  Once `update_last_processed_message` advances the watermark
  (`messageService.py:264`), they are never re-fetched. The only way to find one is
  to scroll the source chats by hand, outside the system.

[[0001-measure-precision-before-tuning]] already named the root cause — *"there is
no feedback loop … raw message text is not persisted"* — and bootstrapped a
**static** gold set (`tests/eval_set.yaml`, mined once via
`scratch/mine_eval_candidates.py`). [[0003-cheap-tier-model-and-prompt-tuning]]
then hit its ceiling against exactly this: a clean 1.00×3 on a 50-item set that was
*tuned against*, with "a larger labeled set" flagged as the highest-value next
investment. This ADR builds the mechanism that grows that set from production.

## Decision

Add a **`decision_log`** table to `messages.db` that records **every fetched
message** with the system's verdict, plus columns a later judge/human pass writes
back into. The log is the substrate; a hybrid offline loop turns it into confirmed
FP/FN labels that feed `eval_set.yaml`.

### 1. Capture — every fetched message (not just reported)

Write one row per message in the exact Phase-1 input set (`all_messages` after the
500-cap, `messageService.py:111`), at the point after hallucination-recovery
(~`:210`) and **before** the watermark advances (`:264`). Storing the Skipped
stream is the whole reason FN become detectable; volume is low (filtered community
chats, ≤500/run) so cost is not the constraint.

### 2. Four-field verdict model

A row's "what happened" spans four **independent** facts; one enum cannot carry the
loop:

- `phase1_verdict` — `reported` / `borderline` / `skipped` (system, always set)
- `feed_action` — `sent` / `dedup_skipped` (a *reported* message can still be
  suppressed from the feed at `messageService.py:220` — Phase-1 verdict ≠ feed action)
- `judge_verdict` — `relevant` / `not` / `null` (offline batch fills later)
- `human_label` — `relevant` / `not` / `null` (you confirm only judge↔phase1 diffs)

Definitions fall out directly:
- **FP** = `phase1_verdict = reported AND human_label = not`
- **FN** = `phase1_verdict = skipped AND human_label = relevant`

### 3. Hybrid detection, judge runs offline

Storage ≠ detection: a Skipped row isn't a known FN until something labels it wrong.

- **Offline judge = Claude (this assistant), not an LLM-API call.** `tools/review_decisions.py
  dump-judge` exports unjudged rows; Claude reads them in-session and fills
  `judge_verdict`; `apply-judge` writes them back. This removes the OpenRouter judge
  call entirely — no model pick, no API cost, no latency on the production path, and
  the judge is stronger than the production cheap-tier model by construction. Runs
  offline, re-runnable.
- **Human confirms only the disagreements** (`judge_verdict != phase1_verdict`,
  surfaced by `dump-confirm`), writing `human_label`. Cheap triage (Claude narrows) +
  human gold on the short list.

### 4. Config attribution

Stamp each row with `run_id`, `llm_model`, `prompt_version`. Without this, a
prompt/model change silently invalidates old rows and re-judging is meaningless;
with it, the log is a **regression record** — "these 3 FN appeared after prompt v4."

### 5. Identity is composite

`message_id` is **per-chat** and collides across chats. Row identity is
`(run_id, source, chat_id, message_id)`; the export dedups on
`(source, chat_id, message_id)`. (This also exposes a latent prod bug: `msg_by_id`
in `messageService.py:49,94` is keyed by bare `message_id` — tracked separately.)

### 6. Retention bounds the PII

The table is a growing plaintext store of private community chat. Therefore:
**do not store `sender_name`** (no classification value, pure liability), and
**TTL-purge `skipped` rows older than 90 days unless `judge_verdict` or
`human_label` is set.** Anything a judge/human touched is confirmed gold — keep
forever; it is the eval seed.

### 7. Close the loop to the gold set

An **export script** reads rows where `human_label` is set and emits `eval_set.yaml`
items (`label` = `human_label`, `predicted` = `phase1_verdict`, `system_reported`,
`text`, `chat_title`), deduped by `(source, chat_id, message_id)`. Run deliberately,
not auto-appended — respects the file's "frozen `predicted`" contract and keeps the
set curated.

## Why (the trade-offs)

- **Capture-all over sample.** Sampling the Skipped stream would leave most FN
  invisible; the whole point is that the Skipped majority is where FN hide. Storage
  is not the bottleneck at this volume.
- **Offline over inline judge.** Inline doubles LLM cost every run and couples prod
  to the judge model for no latency benefit. Production's job is *capture*, judgment
  is a separate, re-runnable concern.
- **Hybrid over pure-manual or pure-judge.** Manual review won't survive volume;
  a judge alone just relocates the misclassification problem (it has its own FP/FN).
  Judge-narrows-human-confirms gives scale *and* ground truth.
- **Drop `sender_name`.** Relevance is decided by event/place/time/intent, never by
  who sent it. Storing it is liability with no upside.
- **Silver→gold flywheel.** This generalizes [[0001-measure-precision-before-tuning]]'s
  one-shot hybrid labeling into a standing loop: prod captures → judge flags →
  human confirms → export grows gold → next eval scores the tuned prompt against
  *real past mistakes*, directly answering 0003's overfitting caveat.

## Caveats / open levers

- **Judge is Claude, run manually.** No automated schedule — detection happens when
  the review loop is run. Acceptable: the log accumulates regardless; judging is a
  deliberate batch pass, not a continuous service.
- **90-day TTL is a starting guess**, not a measured retention need; revisit once
  the review cadence is known.
- **Export dedup policy on relabeled rows** — when the same
  `(source, chat_id, message_id)` is labeled twice, keep the latest `human_label`.

## See also

`docs/design/retrospective-decision-log.design.md` (schema, capture point, flow).
