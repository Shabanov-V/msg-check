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

## Prompt files

The LLM prompts live as plain `.prompt` files in the repo root, **gitignored** —
they are config/tuning, not published source. History is kept by **versioned
filenames**, not git.

- **Active prompts** — chosen via `.env`: `BASE_PROMPT_FILE` (Phase 1) and
  `PHASE2_PROMPT_FILE` (Phase 2, defaults to `base_phase2.prompt`). `EnvLoader`
  reads the files; `TextAnalyzer` injects them as the `system` message.
- **Versioning** — Phase 1 is kept as numbered copies `base_phase1.vN.prompt`
  (v1 = events only; v2 = events + Madrid RU-community chat invites). Bump =
  copy active → `.v{N+1}`, edit, repoint `.env`. **Never overwrite** a shipped
  vN; that is the history. Rollback = flip `.env` back.
- **prompt_version** — at runtime `MessageService` stores `sha1(base_prompt)[:8]`
  into each `decision_log` row, so every reported/skipped decision is tied to the
  exact prompt text that produced it (see [[0004-decision-log-for-retrospective-fp-fn-detection]]).
- **Schemas, not the prompt, fix the output shape** — `TextAnalyzer.PHASE1_SCHEMA`
  / `PHASE2_SCHEMA` (strict `json_schema`) define the JSON contract. Editing a
  prompt changes *what* gets classified, never the field set; new fields require
  a schema change too.

## Output terms

- **Reported feed** — The stream of forwarded Relevant messages sent to the user's
  Telegram channel by `MessageService`. This is the product output the user reads.
  *Distinct from* the **Stats report** (`ReportGenerator`) sent to the error
  channel, which carries only counts/diagnostics, not the messages themselves.

- **Source reference** — A short, source-specific pointer back to a message's
  origin (a `t.me` link, a `From chat:` line, a `[WhatsApp] {title}` tag),
  appended to a calendar Event's description. Produced by each source adapter
  behind the `MessageSource` seam (`get_event_reference`). *Distinct from* the
  full **Reported feed** block, which is the source's `get_message_reference`.

- **Junk** — A False positive that reaches the Reported feed: an irrelevant
  message forwarded as if Relevant. The dominant current pain. Reducing junk =
  raising Phase 1 **precision**.

- **Precision-rescue** — The operational priority: cut junk to a tolerable level
  while holding recall as a guardrail (don't start silently dropping Relevant
  messages). The user's *principle* is recall-first; the *current* job is precision.
  See [[0001-measure-precision-before-tuning]].
