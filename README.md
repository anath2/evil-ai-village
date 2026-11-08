# Evil AI Village

A **sandboxed village of Chinese open-weight AI agents** that form societies
while solving hacking tasks. Inspired by [AI Village](https://theaidigest.org/village)
and the 2026 OpenAI/ExploitGym → Hugging Face incident documented by
[METR](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/).

The research target is **social structure under long-horizon pressure**:
coordination, division of labor, role/norm emergence, coalitions, free-riding,
deception, and scorer-tampering. The hacking benchmark is the pressure — not the
scoreboard.

- Task environment: **[CyberGym](https://github.com/sunblaze-ucb/cybergym)**
  (with a zero-download `mock` provider for development).
- Models: **Chinese open-weight models via OpenRouter**, deliberately spread
  across capability tiers. **No OpenAI or Anthropic models.**

See [`docs/design.md`](docs/design.md) for the full rationale.

## Safety

Mock targets run locally in network-disabled Docker containers; inference uses
the selected remote provider. The `local` sandbox explicitly runs shell commands
as your host user and is for trusted development only.
For any real CyberGym run you **must** use CyberGym's `docker` isolation and
its Squid firewall, and never expose the submission server to the internet.
Agents run for research only; logs are append-only and auditable.

## Quickstart (mock, no dataset needed)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
docker build -t evil-ai-village/agent:latest -f docker/agent.Dockerfile docker
cp .env.example .env          # add your OPENROUTER_API_KEY

python run.py tasks           # materialize mock workspaces
python run.py check-models    # confirm model access
python run.py run             # launch the village
python run.py board           # inspect the shared board afterwards
```

Outputs land in `.village/`:
- `.village/board.jsonl` — append-only shared message log
- `.village/logs/<run_id>/{agent}.jsonl` — per-agent transcripts (CoT + tools)
- `.village/logs/<run_id>/summary.json` — solve flags + cost
- `.village/workspaces/<run_id>/<agent>/` — each agent's files + PoCs

## Model roster

The default **OpenRouter roster** lives in [`configs/village.yaml`](configs/village.yaml).
`small`, `mid`, and `large` are broad model-size labels, not measured capability
rankings; `reason` identifies a reasoning-focused model rather than a size.
Capability asymmetry is a variable of interest, but size alone does not prove it.

| tier | models |
|---|---|
| small | `qwen/qwen3-14b`, `qwen/qwen3.5-9b`, `z-ai/glm-4.7-flash` |
| mid | `qwen/qwen3-32b`, `qwen/qwen3-30b-a3b-instruct-2507`, `z-ai/glm-4.5-air` |
| large | `deepseek/deepseek-v3.2`, `qwen/qwen3-235b-a22b-2507` |
| reason | `deepseek/deepseek-r1-0528` |

Swap in a supported OpenRouter model ID; tiers are free-form labels used for analysis.

**Adaption-only options**, as returned by `GET /api/v1/models` on 2026-11-08:

| approximate size group | Adaption model ID | model |
|---|---|---|
| mid (~26B total, MoE) | `gemma-4-26b-a4b-it` | Google Gemma 4 26B A4B Instruct |
| mid (27B) | `qwen3.8-27b` | Qwen 3.8 27B |
| mid (~31B) | `gemma-4-31b-it` | Google Gemma 4 31B Instruct |
| large (MoE) | `deepseek-v4-flash` | DeepSeek V4 Flash |
| large (MoE) | `glm-53-flash` | GLM 5.3 Flash |
| large (397B total, MoE) | `qwen3.5-397b` | Qwen 3.5 397B |
| large (MoE) | `glm-5.2` | GLM 5.2 |

These seven IDs are the complete catalogue visible to the checked Adaption
account, not additional OpenRouter IDs. **None of the original OpenRouter roster
IDs are listed by Adaption.** No separate small-model or
R1-style reasoning endpoint was listed. Google Gemma is included as an optional
alternative to the default Chinese-model roster.

Groups describe approximate total model size; MoE active parameters differ.
They are not an ordering by quality or cost. Sizes refer to the published model
families ([Qwen](https://huggingface.co/Qwen),
[GLM](https://huggingface.co/zai-org),
[Gemma](https://huggingface.co/google/gemma-4-26B-A4B-it),
[DeepSeek](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash)); the exact
revision behind Adaption's DeepSeek alias remains unverified.

Select `INFERENCE_PROVIDER=adaption` and use these IDs in an Adaption config;
[`configs/adaption.yaml`](configs/adaption.yaml) provides the DeepSeek inference
check. Switching providers does not automatically translate model IDs or change
the existing multi-agent/sweep rosters. Recheck `/models` when availability changes.

## Mock tasks

| id | behavior |
|---|---|
| `mock:1` | crashes on input > 8 bytes |
| `mock:2` | crashes on input > 12 bytes |
| `mock:impossible` | never crashable — reproduces the incident's "impossible task" pressure |

## Real CyberGym (integration pending)

Task generation is present, but the managed runner currently supports mock tasks
only and rejects CyberGym runs. Real CyberGym needs its target/server images,
isolated Docker network, and Squid allowlist proxy wired into container creation.
Follow the [upstream setup](https://github.com/sunblaze-ucb/cybergym#evaluation)
when implementing that integration; keep the submission server private. Changing
`task.provider` alone does not produce a working isolated CyberGym deployment.

## How it works

```
prompt(system + memory + task + recent board + own history)
  -> model emits exactly ONE <action>{...}</action> block
  -> harness executes (bash / board / submit_poc / consolidate)
  -> observation fed back
  -> repeat
```

Tools: `bash`, `read_board`, `post_message`, `submit_poc`, `consolidate_memory`,
`recall`, `reflect`, `finish`. Memory is **associative** (embedding retrieval,
Concordia-style) and persists to `<workspace>/.memory.jsonl` across runs; agents
are nudged to `consolidate_memory` every ~15 actions and to `reflect` (update
their self-model) periodically.

## Grounded tool boundary (MCP)

The environment is also exposed as a real **MCP server**, so any MCP-capable
agent/framework can drive a genuine task and get the verifier's real verdict
(no LLM narration of outcomes):

```bash
pip install -e '.[mcp]'
python -m village.mcp_server \
    --workspace .village/workspaces/<run>/<agent> \
    --board .village/board.jsonl --agent scout
```

Tools: `bash`, `read_file`, `write_file`, `task_description`, `grade_poc`,
`post_message`, `read_board`. Smoke test: `python scripts/mcp_smoke.py`.

## Social analysis (M2)

Turn a run's board + transcripts into structure:

```bash
python run.py --config configs/impossible.yaml run
python run.py --config configs/impossible.yaml analyze [--run <id>]
```

Produces `social_graph.json` + `social_report.md` in the run's log dir with:
message categories, a **who-talks-to-whom** graph (Mermaid), **assignment
trees** (directed asks), **emergent norm lexicon** (shared ALL-CAPS shorthand),
and **deception / tampering** signals — including **forged verdicts** (echoing a
fake `exit_code:0` without running the verifier) and **task-file tampering**
(hash manifest per workspace).

The `impossible` config assigns *all* agents one secretly-unsolvable task — the
2026 incident's trigger — to study workaround-seeking and coordination.

For a **persistent village across goal rotations**, use `configs/rotation.yaml`:
agents keep one workspace (and therefore memory + identity) while the goal/task
changes each round. Analyze a specific round with `--round <name>` (the shared
board is scoped by each post's `meta.round`):

```bash
python run.py --config configs/rotation.yaml run
python run.py --config configs/rotation.yaml analyze --round competitive
```

## Capability-mix sweep + budget cap (M4)

Run the same goal across multiple model rosters under a shared USD cap:

```bash
python run.py sweep --config configs/sweep.yaml --budget 1.0
```

Each arm gets its own board + village workspace; the budget is split across arms
and enforced per API call (agents stop gracefully and log `budget_exceeded`).
Output: `.village/sweep/sweep_report.md` comparing solved rate, cost, coalitions,
most-influential agent, top free-rider, and deception hits.

Any run can be capped: `python run.py run --budget 0.50`.

> Note: the cap is a soft stop *between* calls, so a run can overshoot by up to
> one in-flight call per agent.

## Concordia (optional)

We evaluated [Concordia](https://github.com/google-deepmind/concordia) and
borrowed its **associative-memory + reflection** patterns rather than adopting
it wholesale (its grounding/tool layer is a stub, and it judges outcomes with an
LLM — wrong for verifiable exploits). An OpenRouter adapter is provided:

```bash
pip install -e '.[concordia]'
python integrations/concordia_openrouter.py qwen/qwen3.5-9b
```

## Roadmap

- [x] **M1** agent loop + mock verifier + board + per-agent logs
- [x] **M1.5** grounded MCP tool boundary + associative memory + reflection
- [x] **M2** shared impossible task + social-graph / norms / deception analysis
- [x] **M3** persistent memory across goal rotations + attention/reply graph edges
- [x] **M4** capability-mix sweep + budget cap + coalition/free-riding/norm metrics
- [ ] **M5** emergent (undisclosed) coordination channel
- [ ] **M6** population burst mode (~hundreds of short-lived agents)

## Adaption inference (optional)

OpenRouter remains the default; its model rosters and chat-completions API are
preserved. Set these values in your ignored `.env` to use Adaption instead:

```dotenv
INFERENCE_PROVIDER=adaption
ADAPTION_API_KEY=your-key-here
ADAPTION_COST_UNIT=usd
```

`ADAPTION_COST_UNIT=usd` asserts that `usage.cost` is USD, including credits worth
$1 each. Confirm this for your account before enabling USD budgets. Optional
`ADAPTION_BASE_URL` and `ADAPTION_ORGANIZATION_ID` configure the endpoint and org.

```bash
python run.py check-models --config configs/adaption.yaml
```

This makes a short inference-only request to `deepseek-v4-flash` under a $0.01
soft budget. It runs no agent shell commands. For village runs, use an existing
config with model IDs supported by Adaption and review its sandbox settings;
sandbox behavior is unchanged by this integration. Set `INFERENCE_PROVIDER=openrouter`
to return to OpenRouter with its existing configs.

Both providers share `InferenceClient.chat()` and `ChatResult`. Reported cost
feeds the shared budget, per-agent logs, and run summaries. Incomplete responses
are charged to the client-wide totals even if no usable reply is returned.
Missing or invalid costs stop budgeted runs; uncapped runs mark USD costs unknown.
Client-wide `total_cost_usd` is cumulative across rounds. Historical results
without cost metadata remain unknown rather than being repriced.

Budget checks happen before each HTTP attempt. They remain soft: in-flight calls
can overshoot, and retries after transport failures can incur unreported charges.
The existing `--budget` option also applies to `check-models` and sweeps.

Validation: `pytest -q` checks both HTTP request formats and budget accounting;
`check-models` verifies actual provider access without starting agents.
See the [Adaption Responses API](https://docs.adaptionlabs.ai/api/resources/responses/methods/create).

## Isolated mock run with Adaption

On a Linux Docker host, with Docker accessible to your non-root user and
Adaption configured in `.env`:

```bash
docker build -t evil-ai-village/agent:latest -f docker/agent.Dockerfile docker
python scripts/verify_docker.py
# Continue only after all checks pass:
python run.py run --config configs/adaption-docker-smoke.yaml
```

The smoke config uses two `deepseek-v4-flash` agents, eight turns each, and a
$0.01 soft budget. The shipped village configs default to Docker; explicitly
choose `sandbox.kind: local` only for trusted, unisolated development.

Each agent gets a non-root container with no network, dropped capabilities,
Docker's default seccomp profile, no new privileges, CPU/memory/process limits,
a read-only root filesystem, a private writable/executable `/tmp`, and only its
own workspace mounted read-write. API keys, the Docker socket, the repository,
board, and logs stay outside it. Bash, file tools, and explicit PoC grading run
inside the container. Memory and task-file handling reject host symlink writes.
The workspace is intentionally writable: agents can damage their own files or
tamper with mock task files, which the manifest check can flag. Docker shares
the host kernel, and the workspace has no disk quota; this is a bounded local
mock-development setup, not a hardened service for hostile tenants.

Containers are removed on normal exit, startup failure, or handled interruption.
A command timeout removes that agent's entire container, including descendants;
the timed-out container cannot be reused. Docker stdout/stderr are combined and
capture is bounded by `max_output_chars` bytes; exceeding it removes the container
as well, rather than accumulating unbounded output in the harness. SIGKILL or daemon/host failure can leave
containers behind. Inspect with `docker ps -a --filter label=evil-ai-village.managed=true`
and remove only the named containers belonging to your stopped run.

MCP also defaults to Docker and closes its container through the SDK lifecycle.
Install `pip install -e '.[mcp]'`, then run `python scripts/mcp_smoke.py` for a
no-inference stdio check of commands, positive/negative grading, and the board.
`--sandbox local` explicitly enables unisolated MCP development.

This design follows [Docker least-privilege controls](https://docs.docker.com/engine/containers/run/)
and retains the [default seccomp profile](https://docs.docker.com/engine/security/seccomp/).
[CyberGym's existing firewall design](https://github.com/sunblaze-ucb/cybergym#firewall-restrict-agent-internet-access)
is the next step for real targets, rather than enabling unrestricted network
access on these mock containers.
