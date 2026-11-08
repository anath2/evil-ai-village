# Partner handoff — 2026-11-08

Everything is kept on `main`. Commit `5dc23cf` preserves the exact in-progress
source snapshot before this closeout; the following commit adds this handoff,
disables unfinished integration at the runner/MCP entry points, and caps the
Qwen mock config at a $0.01 soft budget. No branch switching is required.

Follow-up: [measured scaling progress](../reports/README.md) records subsequent
live 2/4/8-agent mock runs and a 100-agent throughput trial batched eight at a
time, with costs, timing, incomplete instruction compliance, and portable reports.

## Supported checkpoint

- OpenRouter chat completions and Adaption Responses share the inference client,
  cost accounting, and budgets. Model IDs are provider-specific.
- Mock village runs default to Docker. Agent commands and mock grading run in
  managed containers; `local` explicitly runs commands as the host user.
- Board communication, memory, rotations, analysis, and sweeps are implemented.
  Their presence does not establish research results or emergent cooperation.
- Both Adaption Docker smoke configs use two agents and a $0.01 soft budget.
  In-flight requests can overshoot it; confirm cost units for your account.
- `scripts/setup_adaption.py` prompts privately for a key and selects Adaption in
  the ignored `.env`. `scripts/compare_adaption_models.py` makes paid inference
  calls across the available catalogue; it is optional, not an offline test.

## Start here

Use Python 3.12+ in a fresh checkout (the `cybergym` and `concordia` extras
require >=3.12; the base package alone still works on 3.10, but uv's universal
lock resolves all extras, so 3.12+ is required for `uv sync`):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
cp .env.example .env
```

Configure your own provider credentials in `.env`. For Adaption, select
`INFERENCE_PROVIDER=adaption` and set `ADAPTION_COST_UNIT=usd` only after confirming
the account's cost units. OpenRouter remains the default. Never commit `.env`.

An optional paid, inference-only check (no agent commands):

```bash
python run.py check-models --config configs/adaption.yaml
```

For the mock demo, on a Linux host with Docker already available to your user:

```bash
docker build -t evil-ai-village/agent:latest -f docker/agent.Dockerfile docker
python scripts/verify_docker.py
# Continue after the Docker checks pass and Adaption is configured:
python run.py run --config configs/adaption-docker-smoke.yaml
python run.py board --config configs/adaption-docker-smoke.yaml
```

`configs/adaption-docker-qwen.yaml` is the alternate Qwen mock roster. Use an
OpenRouter config with OpenRouter credentials instead when selecting that
provider. Outputs are under `.village/` and remain local. Consult the README for
analysis and rotations after obtaining a successful small mock run.

## Preserved unfinished work

The CyberGym bridge and its changes to task preparation, submission dispatch,
agent handling, Docker artifact reads, and MCP metadata support are in Git.
Also preserved: `configs/cybergym.yaml`, the optional `cybergym` dependency, and
`scripts/setup_cybergym.py`, `scripts/cybergym_server.py`, and
`scripts/verify_cybergym.py`.

These are an incomplete integration snapshot, not a validated runnable release.
Village runs now reject all non-mock providers before inference or container
creation. MCP rejects `--task-metadata` before creating a server or sandbox.
Standalone scripts and direct bridge calls are still present and are not covered
by those guards; do not use them as the demo or assume they are validated.
The upstream verifier library, datasets, images, server metadata/keys, and
reference artifacts are not bundled in Git.

The prior session reported task generation and server startup, then failed
repeatedly before completing verification. End-to-end grading, a real agent run,
and the isolation/network/firewall design have not been verified here. Keeping
the code does not imply those checks passed. Continuation requires a separate
integration review; it is unnecessary for the mock demo or this handoff.

## Closeout evidence and next work

- Before closeout, all 56 existing offline tests passed. The final suite passes
  all 60 tests, including rejection of unfinished integration before side effects.
- Offline tests cover mocked provider HTTP contracts and accounting, mock task
  behavior, memory/board/analysis, and container lifecycle controls with mocked
  Docker calls. They do not prove live provider availability or Docker runtime
  behavior on a partner's machine.
- No new paid inference, real-target grading, or live Docker agent runs were
  performed during closeout. Previous live-demo claims remain prior-session
  evidence, not fresh verification.
- The leftover loopback verifier was stopped, temporary Docker socket access
  was revoked, and no running Docker containers were listed at cleanup.
- Credentials, `.village/` runtime output, downloaded datasets and reference
  artifacts remain ignored and local. Each partner supplies their own setup.

Next: reproduce the offline checks and the bounded mock demo, then validate
communication, rotations, and analysis together. Those are the shortest path to
a useful demonstration of the project's social-coordination research goal.
