# Measure Phase-1 precision before changing the prompt or model

**Status:** accepted

## Context

The presenting complaint was "too many hallucinations and undesirable output."
Grilling reframed it: the real pain is **junk in the Telegram feed** — Phase 1
false positives (irrelevant messages reported as relevant). The calendar / Phase 2
event extraction and `message_id` recovery are explicitly out of scope for now.

Every prior prompt/model change has been a blind guess because **there is no
feedback loop**: output is never reviewed against ground truth, raw message text
is not persisted in `messages.db`, and the only eval is 11 hand-made fixtures
checking a per-message boolean — far too few to measure precision.

## Decision

Build a measured baseline *before* touching the prompt or model:

1. **Mine a labeled eval set from the logs.** Raw messages aren't in the DB, but
   `output.txt` holds ~1,868 real production batches and `calendar_events` holds
   ~2,517 produced positives. Sample from these, oversampling reported (positive)
   messages so precision is measurable.
2. **Hybrid labeling.** A strong model pre-labels each candidate Relevant/Not with
   a reason; the user does a fast accept/reject pass (~50 items). The user judges
   rather than labels from scratch.
3. **Upgrade `tests/integration_tester.py`** to report **precision and recall**
   (and a confusion matrix), not accuracy — accuracy is misleading on a corpus
   that is mostly irrelevant.
4. **Then** test levers against the baseline: a stronger (paid) model — the prime
   suspect, since the default is `google/gemini-2.0-flash-exp:free` — prompt
   tightening, and batch-size/structure changes.

## Why (the trade-offs)

- **Target = precision-rescue, recall as guardrail.** The user's *principle* is
  recall-first (never miss a meetup), but the *operational* priority is cutting
  junk to a tolerable level without going blind. Optimize precision subject to not
  dropping recall.
- **Paid model is on the table.** The user will pay for quality if the eval shows
  a stronger model cuts junk; this is the single biggest lever.
- **Hybrid labels are "silver," not gold.** Accepted deliberately: a fully
  hand-labeled set was judged too tedious given the user does not review output.
  Risk is shared blind spots between grader and graded; mitigated by user review.
