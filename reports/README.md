# Measured scaling progress — 2026-11-08

These runs used Adaption `deepseek-v4-flash` with network-disabled Docker agent
workspaces on nidavellir. No real CyberGym targets were run.

| Workload | Agent loops returned | Peak concurrent model calls | Wall time | Mock solves | Board posts | Provider-reported USD |
|---|---:|---:|---:|---:|---:|---:|
| Mock task solving, 2 agents | 2/2 | 2 | 21.575 s | 2 | 4 | $0.00041613 |
| Mock task solving, 4 agents | 4/4 | 4 | 20.501 s | 4 | 7 | $0.00115799 |
| Mock task solving, 8 agents | 8/8 | 8 | 21.369 s | 7 | 15 | $0.00198018 |
| Board-focused throughput, 100 agents | 100/100 | 8 | 191.424 s | 0 (not the assigned goal) | 97 | $0.01197716 |

Total reported cost: **$0.01553146**. All four runs recorded zero request errors.
Cost units were configured as USD for this account; these are API usage reports,
not independently reconciled billing. Soft budgets were $0.10 per run.

## What the 100-agent result establishes

One hundred distinct agent loops and Docker workspaces were processed in
sequential batches of at most eight active agents. All containers were created
before agent execution; wall time includes their creation and cleanup. This was
not 100 simultaneous model calls. Each agent received two turns and instructions
to post a greeting and finish, rather than solve its mock task.

The loops all returned, but instruction compliance was incomplete: 97 distinct
agents posted, 74 emitted an explicit `finish`, 26 actions used `bash`, and three
turns had no parsed tool. Agents 34, 44, and 54 never posted and used their turns
on `bash`. Tools were available despite the board-focused instructions; shell
actions ran within the existing Docker boundary. A returned loop is not the
same as a successfully completed assigned goal.

This is evidence of small-concurrency orchestration handling 100 short-lived
agent identities, plus working mock solves at 2/4/8 concurrent agents. It does
not establish useful cooperation, long-horizon behavior, 100-way concurrency,
or real vulnerability-solving performance. The different workloads and turn
limits mean the 100-agent timing is not directly comparable to the smaller runs.

## Artifacts and reproduction

- [2/4/8 HTML report](mock-scale-2026-11-08/index.html) and [measurements](mock-scale-2026-11-08/results.json).
- [100-agent HTML report](mock-scale-100-2026-11-08/index.html) and [measurements](mock-scale-100-2026-11-08/results.json).
- Runner: [`scripts/scale_mock.py`](../scripts/scale_mock.py). From a configured
  Python environment with Docker access, use `python scripts/scale_mock.py` for
  2/4/8, or `python scripts/scale_mock.py --counts 100 --output reports/new-100-trial`
  for the batched board-focused trial. These commands spend provider credits.

The original source base is recorded in each JSON report. The smaller trial ran
the initially uncommitted runner, subsequently preserved in commit `5fad10a`.
Report formatting was refreshed after the measurements; values were not rerun.
Raw transcripts, credentials, and workspaces remain local and ignored. The
temporary Docker socket grant expired and was verified absent at final review.
