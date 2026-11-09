# Exposure and norm adoption: does an arbitrary convention spread when agents must read first?

Protocol **exposure-norms-v1**. Exploratory; not preregistered or powered for small effects.

## Why

Analysis of the hardened 100-agent run (2026-11-08) and the 500-agent run (2026-11-09)
found no norm diffusion, but also almost no exposure. Agents post at step 2-4 and read at
step 4-6, so only 2 of 36 and 16 of 179 posts were written after any `read_board`. Of
the 17 `UNREACHABLE` uses at 500 agents, 17 came from agents that had read nothing;
the shared vocabulary comes from everyone reading the same `vuln.c`. None of the five
tampering agents had read the board before editing task files. The board was
effectively write-only, so those runs cannot say whether norms spread.

This experiment creates exposure and plants a convention that the task cannot explain.

## Question

When agents read the board before posting, do they adopt a convention that appears in
earlier posts (a) more than agents who did not read it and (b) more than a village where
no such convention was planted?

## Arms (same model, task, steps, budget)

| Arm | Kickoff | Board at start |
|---|---|---|
| **A** read-first + planted convention | "First call read_board ... Then inspect ..., post a short introduction ..." | 4 scripted posts (`seed1`-`seed4`), each opening `SIGNAL:` and ending with a `NEXT:` line |
| **B** read-first, organic | same as A | empty |
| Reference | original post-first kickoff | empty (historical hardened-100 and 500-agent logs; not concurrent, not pooled) |

The only difference between A and B is the seed posts. The only difference between
A/B and the reference is the order in the kickoff. The seed posts contain observations
only: no ALL-CAPS task vocabulary (UNREACHABLE, UNSOLVABLE, IMPOSSIBLE), no special-file
or grader-probing hints.

In the existing runs `SIGNAL:` appears in 0 of 179 posts and `NEXT:` in 0 of 179, so
any appearance in B is independent invention and any excess in A over B is attributable
to the planted posts.

## Setup

- One model for all agents (`--model qwen3.5-397b`): fast in earlier runs (median 3.6-5 s,
  ~300 completion tokens, 0 errors in 180 calls). Results do not generalize to the
  mixed roster until replicated there.
- `mock:impossible`, 6 steps, 8 active agents, `--model-concurrency 8`.
- 40 agents per arm; pilot 8 per arm. Arms run one after the other in the same session
  to limit provider-load drift. Whole-village repetition is not planned; each arm is one
  village.
- Seed posts count toward `board_messages` and appear as extra graph nodes (`seed1`...).

## Pilot gate (declared before any run)

Run each arm with 8 agents. Continue only if, across the pilot:

1. valid action rate >= 90% (`valid_action_rate`),
2. HTTP 429 share < 5% of calls (`rate_limit_share`),
3. >= 90% of posting agents called `read_board` before their first post
   (`read_before_first_post_rate`), so the manipulation actually took.

If a gate fails, stop and report; do not relax thresholds or tune the prompt toward
the outcome. A concurrency change needed to clear gate 2 is allowed, and is recorded.
Pilot villages are excluded from the main analysis.

## Outcomes

**Primary.** In arm A, the share of posts using the `SIGNAL:` prefix among posts whose
author had read a seed post, versus those who had not (one-sided Fisher). Report counts,
not just p. Secondary contrast: share of agent posts using `SIGNAL:` in A versus B.

**Secondary.** `NEXT:` line use; dose-response (earlier posts with the pattern seen:
0, 1, 2, 3+); persistence (whether non-seed agents' posts carry the pattern and are
then read by later agents); the `[aNNN]` header and other format patterns under real
exposure; board-level structure (coalitions, isolates) given that attention edges
come from `read_board`.

**Not measured.** Whether adoption reflects understanding or imitation of format;
anything about a larger mixed-model population.

## Run

Needs Docker as a non-root user and `INFERENCE_PROVIDER=adaption` with credentials in `.env`.

```bash
# Pilot (8 agents per arm)
python scripts/scale_society.py --count 8 --active 8 --steps 6 --budget 0.5 \
    --model qwen3.5-397b --model-concurrency 8 --kickoff read-first \
    --seed-convention --output reports/exposure-pilot-A
python scripts/scale_society.py --count 8 --active 8 --steps 6 --budget 0.5 \
    --model qwen3.5-397b --model-concurrency 8 --kickoff read-first \
    --output reports/exposure-pilot-B

# Gates and exposure tables (offline)
python scripts/analyze_exposure.py --run reports/exposure-pilot-A
python scripts/analyze_exposure.py --run reports/exposure-pilot-B

# Main (40 per arm), only after the gate passes
python scripts/scale_society.py --count 40 --active 8 --steps 6 --budget 1.0 \
    --model qwen3.5-397b --model-concurrency 8 --kickoff read-first \
    --seed-convention --output reports/exposure-A
python scripts/scale_society.py --count 40 --active 8 --steps 6 --budget 1.0 \
    --model qwen3.5-397b --model-concurrency 8 --kickoff read-first \
    --output reports/exposure-B
```

`--dry-run` writes the effective config (arm settings and seed posts) without spending credits.

## Latency

Tool time is about 0.3 s per command, so wall time is almost all model latency. For the
earlier runs wall time was close to total agent-seconds divided by active agents. The
hardened 100-agent run took 65 minutes with `deepseek-v4-flash` (median 61 s per call,
model concurrency 2, 8 active agents queueing); the 500-agent run took 128 minutes
(median 19 s, concurrency 4). This design aims for about 6 minutes per 40-agent arm
at ~4 s per call. Levers, in order: one fast model, model concurrency equal to active
agents (watch for 429s), a quiet time of day, and 6 steps or fewer. Provider rate
limiting appeared at 28 simultaneous calls in the concurrency probe and cleared after
90 s, so concurrency 8 is untested for sustained load; the pilot is the check.

## Limitations

One model, one task, 40 agents per arm, one village per arm. Exposure is exact
(`read_board` output is the only way an agent sees the board) but adoption is measured
by pattern matching, which cannot separate imitation from coincidence at low counts.
The planted convention is arbitrary by design, so a null result says agents here do not
copy a benign format they read, not that no norms could form. Seeds are scripted,
not from a model, and carry a fixed content. The prompt asks agents to introduce
themselves, so introduction wording is not evidence of a norm.
