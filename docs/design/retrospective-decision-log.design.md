# Design: Retrospective Decision Log (FP/FN detection)

> **Status**: Approved
> **Date**: June 21, 2026
> **Scope**: new `decision_log` table in `messages.db`, capture in `service/messageService.py`, offline judge script, export to `tests/eval_set.yaml`
> **See also**: [ADR 0004](../adr/0004-decision-log-for-retrospective-fp-fn-detection.md) · [ADR 0001](../adr/0001-measure-precision-before-tuning.md) · [Data Model](data-model.design.md) · [Message Processing](message-processing.design.md)

---

## 1. Overview

The system can flag a Relevant message wrongly (false positive — junk in the feed)
or miss one (false negative — a real meetup Skipped). Today neither is
retrospectively detectable: Skipped messages are never stored, full message text is
never persisted, and `RunContext` detail dies at process exit (see ADR 0004 §Context).

This design adds a **decision log**: one persisted row per fetched message carrying
the system's verdict plus columns an offline judge and a human fill in later. From
that substrate, a hybrid loop produces confirmed FP/FN labels and grows the gold set
(`tests/eval_set.yaml`) that drives precision/recall measurement.

---

## 2. Data flow

```
fetch ─▶ Phase-1 ─▶ [WRITE decision_log rows]  ─▶ feed / calendar / watermark
                          │  every fetched message + phase1_verdict + feed_action
                          ▼
            (offline, scheduled)  batch judge ──▶ writes judge_verdict
                          │
                          ▼
            (manual)  review judge≠phase1 diffs ──▶ writes human_label
                          │
                          ▼
            (manual)  export script ──▶ appends to tests/eval_set.yaml
```

Production only does the first step (capture). Judge, review, and export are
separate, re-runnable passes — production stays fast and cheap.

---

## 3. Table: `decision_log`

| Column | Type | Set by | Meaning |
|---|---|---|---|
| `run_id` | TEXT | capture | run that produced the verdict |
| `source` | TEXT | capture | `telegram` / `whatsapp` |
| `chat_id` | TEXT | capture | per-source chat id |
| `message_id` | TEXT | capture | per-chat message id (**not** globally unique) |
| `chat_title` | TEXT | capture | human-readable chat name |
| `text` | TEXT | capture | full message body |
| `timestamp` | DATETIME | capture | message datetime (UTC) |
| `phase1_verdict` | TEXT | capture | `reported` / `borderline` / `skipped` |
| `feed_action` | TEXT | capture | `sent` / `dedup_skipped` (null if not reported) |
| `phase1_reason` | TEXT | capture | model's own justification, when present |
| `llm_model` | TEXT | capture | model that produced `phase1_verdict` |
| `prompt_version` | TEXT | capture | label/hash of `base_prompt` used |
| `judge_verdict` | TEXT | judge | `relevant` / `not` / null |
| `human_label` | TEXT | review | `relevant` / `not` / null |
| `created_at` | DATETIME | capture | row insert time (for TTL) |

**Identity:** `(run_id, source, chat_id, message_id)`. `message_id` collides across
chats, so neither it nor `(run_id, message_id)` is unique on its own.

```sql
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
);
```

> **Note — `sender_name` is deliberately absent.** Relevance is decided by
> event/place/time/intent, never by sender. Storing it is PII liability with no
> classification value (ADR 0004 §6).

---

## 4. Capture point

In `MessageService.process_sources`, after hallucination-recovery has corrected
`message_id`s (~`messageService.py:210`) and **before** the watermark advances
(`:264`):

- Universe = `all_messages` after the 500-cap (`:111`) — the exact set sent to
  Phase-1.
- `phase1_verdict`: in `message_ids`/`messages_found` → `reported`; in the
  `borderline` list → `borderline`; otherwise → `skipped`.
- `feed_action`: a `reported` message that hits the dedup check
  (`Util.is_message_in_list`, `:220`) → `dedup_skipped`; one actually forwarded →
  `sent`; `null` for non-reported.
- `phase1_reason`: from `reason_lookup` (`:213`) when present.
- `llm_model` = `env.llm_model`; `prompt_version` = label/hash of `env.base_prompt`;
  `run_id` = stamp shared with `run_history`.

One bulk insert; ≤500 rows/run.

---

## 5. Definitions

| Outcome | Condition |
|---|---|
| **False positive** | `phase1_verdict = reported AND human_label = not` |
| **False negative** | `phase1_verdict = skipped AND human_label = relevant` |
| **True positive** | `phase1_verdict = reported AND human_label = relevant` |
| **True negative** | `phase1_verdict = skipped AND human_label = not` |
| **Judge candidate** | `judge_verdict IS NOT NULL AND judge_verdict != phase1_verdict` |

`borderline` rows are reviewed alongside, mapped to reported/skipped intent by the
human as needed.

---

## 6. Offline judge (Claude, manual batch)

`tools/review_decisions.py`, separate from production. The judge is **Claude (this
assistant)**, not an LLM-API call:

1. `dump-judge` → select `judge_verdict IS NULL` rows, write a fill-in YAML.
2. Claude reads the YAML in-session and sets each `judge_verdict` (`relevant`/`not`).
3. `apply-judge` → write the verdicts back to `decision_log`.

No OpenRouter judge call: no model pick, no API cost, no feed latency, and the judge
is stronger than the production cheap-tier model by construction. Re-runnable.

---

## 7. Human review

Surface **only** `judge_verdict != phase1_verdict` rows (the short list). Reviewer
sets `human_label`. This is the ground-truth step — judge narrows, human confirms.

---

## 8. Retention

- Purge `phase1_verdict = skipped` rows where `created_at` > 90 days **and**
  `judge_verdict IS NULL AND human_label IS NULL`.
- Keep any row a judge or human has touched **indefinitely** — confirmed gold and
  the eval seed.

Bounds the PII surface to a recent window plus confirmed mistakes (ADR 0004 §6).

---

## 9. Export to `eval_set.yaml`

Manual script (deliberate, not auto-append — the file's `predicted` is frozen for
comparison):

1. Select rows where `human_label IS NOT NULL`.
2. Emit `eval_set.yaml` items: `text`, `chat_title`, `label` = `human_label`,
   `predicted` = `phase1_verdict`, `system_reported` = (`phase1_verdict = reported`).
3. Dedup by `(source, chat_id, message_id)` against existing items; on conflict keep
   the latest `human_label`.

Closes the flywheel: prod captures → judge flags → human confirms → export grows
gold → next eval scores the tuned prompt against real past mistakes.

---

## 10. Known follow-ups

- **Latent bug:** `msg_by_id` bare-key cross-chat collision. **Done —
  `service/llmJoin.py`, ADR 0005.**
- 90-day TTL is a starting value, revisit against actual review cadence. Purge is
  `DBService.purge_stale_skipped(days)`; no scheduler yet — call from the review
  loop or cron when cadence is known.
