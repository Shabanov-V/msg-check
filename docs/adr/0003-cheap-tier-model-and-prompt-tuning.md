# Cheap-tier model pick (`deepseek-v4-flash`) and recall-focused prompt tuning

**Status:** accepted
**Date:** 2026-06-21

## Context

[[0002-no-claude-cli-in-production]] closed the free-model branch on reliability
and resolved the next step as the **cheap paid tier** (~$1–3/mo), pending the
user's go-ahead on the first paid OpenRouter call. The user authorized ~$0.50 for
a bake-off. This ADR records the bake-off, the model pick, and the prompt tuning
that followed. See [[0001-measure-precision-before-tuning]] for the eval method.

## The bake-off (4 cheap models, 50-item eval set, 2 runs each)

`scratch/bakeoff.py` reproduces the exact production Phase-1 call (system =
`base_phase1.prompt`, user = messages JSON, `PHASE1_SCHEMA`, `temperature=0`) but
with `max_retries=0` + a 120s per-call timeout so failures **surface** instead of
hanging in the 10×/30s tenacity loop. Same seeded batch across all models.

| Model | Run 1 | Run 2 | Latency | Verdict |
|---|---|---|---|---|
| **deepseek/deepseek-v4-flash** | P67 R57 F1 .62 | P83 R71 F1 .77 | 35–51s | ✅ no failures, fastest, balanced |
| z-ai/glm-4.7-flash | P83 R71 F1 .77 | ❌ empty response | 149–164s | ❌ hard failure + slow |
| qwen/qwen3-235b-a22b-2507 | P100 R71 F1 .83 | P14 R86 F1 .24 (37 FP) | 144–356s | ⚠️ best ceiling, catastrophic variance |
| openai/gpt-5-nano | P100 R43 F1 .60 | P100 R57 F1 .73 | 91–142s | ✅ perfect precision, weak recall |

Total bake-off spend ≈ **$0.03** (of the $0.50 authorized).

### Findings

1. **Cost is no longer the constraint.** Every model lands at sub-cent per 50-msg
   batch (a few cents even at production's 500-msg scale). The cost anxiety that
   drove the `claude -p` and free-model detours is fully resolved — *any* of these
   is effectively free. The real constraint is **reliability + quality**.
2. **Variance dominates, even at `temperature=0`.** In just two runs each, two of
   four models broke: glm returned an empty response; qwen swung from best (F1 .83)
   to meltdown (37 false positives, F1 .24). OpenRouter is almost certainly routing
   to different providers/quantizations per call. **Single-run scoring is
   misleading** — this justifies the 2-runs-each method.
3. Only **deepseek-v4-flash** and **gpt-5-nano** were failure-free across both runs.

## Decision

**Production model = `deepseek/deepseek-v4-flash`** (`.env: LLM_MODEL`). It is the
only failure-free model that is also fast (3–7× faster than the rest) and balanced.
gpt-5-nano's perfect precision was rejected because its recall (43–57%) misses half
the events — and the user set **recall as the priority**: for an "alert me to
events" tool, a missed appointment is the failure that defeats it; a stray entry is
a smaller cost.

## Recall-focused prompt tuning

Diagnosing deepseek's misses (`scratch/probe_fn.py`) showed the recall gap was
**two narrow prompt/label mismatches**, not broad over-strictness — deepseek
already kept every promotional event post (concerts, quizzes, theater):

1. **Sports rule too blunt.** Criterion 5's blanket exclusion of "regular sports
   events" was killing a one-off *"кто-то бежит? будем рады компании"* run invite
   that the gold set labels relevant. → Narrowed to *recurring team-sport*
   activities, with an explicit exception for one-off sports outings carrying a
   direct invitation.
2. **Terse direct invitations slipped through.** A short *"Кто хочет …?"* outing
   invite with no venue/time didn't register as an event. → Added that concrete
   short invitations count.

A user domain call settled the last item ([4], a guided hike to **Aneto**, a
Pyrenees peak ~400km away): **community trips count even when the destination is
outside Madrid.** Added a location exception — but scoped to **nature/outdoor**
destinations only, explicitly NOT urban events physically in Barcelona/Catalonia,
after a first, looser version leaked Barcelona-orbit false positives (a Castelldefels
tapas route, a brand pop-up, a contentless "party today" one-liner).

### Result (3 runs each, deepseek)

| Prompt | Precision | Recall | F1 |
|---|---|---|---|
| Live (baseline) | 67–83% | 57–71% | .62–.77 |
| Tuned, loose location/invite | 78–88% | 100% | .88–.93 |
| **Tuned, tightened (promoted)** | **100% ×3** | **100% ×3** | **1.00 ×3** |

The tightened prompt is now live in `base_phase1.prompt`.

## Caveats / open levers

- **Overfitting risk.** A clean 1.00 ×3 is on a **50-item / 7-positive set that was
  tuned against**. The added clauses are generalizable, but this is not a claim of
  100% in production. The real validation is a **larger labeled set** — the highest-
  value next investment, not more prompt iteration on this set.
- **Provider-pinning is the remaining reliability lever.** The bake-off variance is
  a routing artifact. Production determinism would come from pinning a single
  OpenRouter provider via `extra_body={"provider": {...}}` in
  `service/textAnalyzer.py`. Untested; deepseek showed no hard failures, so this is
  a hardening step, not a blocker.
- **Batch size (500 msgs) untested.** All measurements are on the 50-msg eval
  (~1/10th production). qwen's meltdown and nemotron's earlier choke suggest weak
  models destabilize at scale; deepseek should be re-checked on a full-size batch.
