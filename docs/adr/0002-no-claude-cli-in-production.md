# Don't use `claude -p` (Claude Code CLI) as the production classifier

**Status:** accepted

## Context

The only motivation for shelling out to the Claude Code CLI in production was
**cost** — reusing the existing Claude subscription instead of paying an LLM
provider. Grilling showed the cost motive actually argues *against* it.

## Decision

Production keeps calling models through the OpenAI SDK against OpenRouter
(`service/textAnalyzer.py`). `claude -p` is rejected for the production pipeline.

## Why (the cost motive is self-defeating)

At ~11M tokens/month, the cheapest *safe* option is already near-free:

- Genuinely free OpenRouter models (e.g. `nvidia/nemotron-3-super-120b-a12b:free`,
  `qwen/qwen3-next-80b-a3b-instruct:free`) cost **$0/mo** *and* keep strict
  `json_schema` structured output *and* carry no ToS exposure. This strictly
  dominates `claude -p` on every axis.
- Cheap paid structured-output models land at **~$1–3/mo**; the Claude quality
  anchor (`anthropic/claude-haiku-4.5`) is **~$18/mo** — the same model `claude -p`
  would use, but via a clean API contract.

`claude -p`'s "$0" is also illusory: it draws down the **same Claude Code
subscription quota** the user pays for to do dev work, competing with interactive
usage and the plan's rolling/weekly caps. And it loses the strict-schema
guarantee (would parse free text) and uses a personal subscription for unattended
automation (ToS gray area).

## Consequence

For a pure-cost goal the right lever is **test the free OpenRouter models first**
(see the bake-off against `tests/eval_set.yaml`). `claude -p` only re-enters
consideration if *every* free model fails the precision bar **and** the user also
refuses to spend ~$1–3/mo. Claude in production, if chosen for quality, goes
through `anthropic/claude-haiku-4.5` on OpenRouter, not the CLI.
See [[0001-measure-precision-before-tuning]].

## Update (2026-06-20): the free models failed the workload

Bake-off result on the 50-item eval set (1/10th of production's 500-message
batch): **both genuinely-free models are unusable before precision can even be
scored.**

- `nvidia/nemotron-3-super-120b-a12b:free` — took **442s** on the 50-msg batch and
  then returned **malformed JSON** (broke the strict schema). A single 1-message
  call works in 15s, so it scales catastrophically; production's ~70k-token batch
  is hopeless.
- `qwen/qwen3-next-80b-a3b-instruct:free` — instant **429, rate-limited upstream**.

So the "free model" branch is closed on **throughput/reliability**, not quality.
This does **not** reopen `claude -p`: that path shares the *worse* version of the
same reliability problem (no strict schema, subscription quota/rate caps). The
resolved next step is the **cheap paid tier** (~$1–3/mo: `deepseek-v4-flash`,
`z-ai/glm-4.7-flash`, `qwen3-235b`, `gpt-5-nano`), pending the user's go-ahead on
the first paid OpenRouter call.
