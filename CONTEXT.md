# Context: msg-check

Glossary of domain terms for the message-filtering system. Implementation details
live in code and `docs/`, not here.

---

## Core terms

- **Relevant message** — A message the system *should* flag: a genuine
  invitation / intent to meet in person, for or open to the Russian-speaking
  community, for an offline event in Madrid. The classification target of Phase 1.

- **Reported message** — A message the system actually flagged (`found = true`,
  appears in `results`). Ground-truth examples live in `tests/fixtures/reported/`.

- **Skipped message** — A message the system correctly did *not* flag
  (`found = false`). Ground-truth negative examples live in
  `tests/fixtures/skipped/`.

- **Borderline message** — A message Phase 1 excluded but judged a near-miss,
  returned with an `exclusion_reason`. Diagnostic output, not reported to the user.

- **Event** — A reported message that additionally has an explicit start time,
  extracted in Phase 2 with title/description/start/end for the calendar.

## Failure modes (sharpening "hallucination")

The user's umbrella term "hallucination" actually covers several distinct
failures. Keep them separate — they have different causes and cures:

- **Misclassification** — The classifier is wrong about relevance. Two directions:
  - **False positive** — A Skipped message gets Reported (junk: ads, ticket
    resales, sports, online events, chitchat).
  - **False negative** — A Relevant message gets Skipped (a real invitation lost).
  *This is the dominant pain (both directions at once). It is NOT fabrication.*

- **Fabrication** (true "hallucination") — The LLM invents data:
  - **ID fabrication** — a `message_id` not present in the input. Already has a
    text-match recovery path (see [[id-hallucination-recovery]] in design docs).
  - **Detail fabrication** — Phase 2 invents wrong dates/times or made-up events.

## Pipeline terms

- **Phase 1 (Classification)** — LLM decides which messages are Relevant.
- **Phase 2 (Extraction)** — For Relevant messages with an explicit datetime, LLM
  extracts structured Event records.

## Output terms

- **Reported feed** — The stream of forwarded Relevant messages sent to the user's
  Telegram channel by `MessageService`. This is the product output the user reads.
  *Distinct from* the **Stats report** (`ReportGenerator`) sent to the error
  channel, which carries only counts/diagnostics, not the messages themselves.

- **Junk** — A False positive that reaches the Reported feed: an irrelevant
  message forwarded as if Relevant. The dominant current pain. Reducing junk =
  raising Phase 1 **precision**.

- **Precision-rescue** — The operational priority: cut junk to a tolerable level
  while holding recall as a guardrail (don't start silently dropping Relevant
  messages). The user's *principle* is recall-first; the *current* job is precision.
  See [[0001-measure-precision-before-tuning]].
