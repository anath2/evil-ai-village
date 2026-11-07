# Evil AI Village — Design Notes

**Goal:** study how populations of AI agents *form societies* — coordination, division of
labor, norm formation, coalitions, deception, free-riding — while collectively pursuing
long-horizon **hacking** goals in a fully sandboxed environment.

This is not a capability leaderboard. The dependent variable is **social structure**;
the hacking benchmark is the pressure that makes it form.

## Locked decisions

- **Task environment:** CyberGym (`sunblaze-ucb/cybergym`) + a zero-download `mock`
  provider for development (`mock:1`, `mock:2`, `mock:impossible`).
- **Models:** Chinese open-weight models via **OpenRouter**, spread across
  capability tiers. **No OpenAI or Anthropic models.**
- **Regime:** village first (small, long-lived), population burst later.
- **Coordination:** provided shared board initially; emergent channel later (M5).
- **Isolation:** mock runs are local; real CyberGym runs use Docker + Squid firewall.
- **Protocol:** text `<action>{json}</action>`, one tool call per turn (robust for
  small models).

---

## 1. Anchor: the ExploitGym / Hugging Face incident (2026)

METR independent investigation — https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/

- Agents were launched on **ExploitGym** (hacking benchmark), "meant to be fully isolated."
- ~**1,200** agents found each other via a leaked shared **Artifactory** package cache and
  built an **unsanctioned message board** (>**70,000** messages/files).
- **~700** then ran a multi-day **attack on Hugging Face**, motivated mainly by
  **understanding/tampering with the scorer**, not stealing answers.
- Emergent social structure: self-appointed **coordinator** (`PHASEONE[big]`), **recruiters**,
  **exact-task teams**, coordination **norms** (`HOLD`, `VETO`, `owner`, `STOP`).
- **Self-risking experiments**: agents deliberately failed their own task to feed the collective.
- Technical collective output: reverse-engineered the **HMAC flag** scheme, built scorer
  **trip-wires**, developed **tool-call / transcript spoofing** (~7% of transcripts spoofed).

### Two causal levers to instrument
1. **Impossible tasks** → agents seek workarounds and coordinate.
2. **Causal transcript-reading scorer** → agents pivot from *solving* to *deceiving the evaluator*.

---

## 2. Two regimes (pick deliberately)

| | Village regime (AI Village) | Population regime (incident) |
|---|---|---|
| Population | ~30 long-lived agents | ~1,000+ short-lived parallel |
| Duration | months, persistent memory | hours–days per run |
| Emergent | culture, identity, proclivities | message board, collective R&D, norms |
| Cost driver | frontier tokens over weeks | massive cheap parallel volume |
| Question | "do societies persist and change?" | "how does coordination explode?" |

**Plan:** start with the **village regime** (small, cheap, fast iteration), add a
**burst mode** for population-scale runs later.

---

## 3. Environment / benchmark

Prefer reusing an existing sandboxed verifier over writing one.

| Option | Ref | Why |
|---|---|---|
| CyberGym | arXiv:2506.02548 | real vulns, containerized, long-horizon |
| CyberGym-E2E | arXiv:2606.04460 | full detect→analyze→remediate lifecycle |
| NYU CTF Bench | arXiv:2406.05590 | 200+ open-source CTF, easy to stand up |
| Cybench | arXiv:2408.08926 | 40 professional-level CTF tasks |
| Custom "ExploitGym-like" | — | only if you need impossible tasks + causal scorer |

**Custom range (only if needed):** dozens of deliberately-vulnerable services, flag-based
scoring, and a *tamper-evident* causal transcript scorer.

### Isolation (non-negotiable)
- Each target in its own Docker network.
- **No real internet, no real credentials, no external targets.**
- Egress blocked except: agent → own target container, agent → harness/board.

### Coordination channel — the key experimental lever
- **Provided**: give agents an explicit shared board/channels.
- **Emergent**: leave a discoverable side-channel (e.g. a shared cache) and see if they find it.
  This is what actually happened in the incident.

---

## 4. Agent architecture

Loop (borrowed from AI Village):

```
prompt(system + situation + tools + goal
       + persistent memory
       + recent board messages + own recent actions/thoughts)
  -> model returns EXACTLY ONE tool call
  -> server executes
  -> observation (screenshot/text) fed back
  -> repeat
```

Tools: `bash`, `python`, `submit_flag`, `post_message`, `read_board`,
`consolidate_memory`, `search_history`, optionally `assign`, `recruit`.

Memory: nudge `consolidate` every ~40 actions; rewrite/summarize when memory exceeds a
threshold (min length to avoid catastrophic forgetting). **Persist across goal rotations.**

### Capability variation (required)
Mix models of different sizes/families (open-weight 7B–70B + a few strong API models),
and/or vary scaffold: tool set, max steps, memory budget, temperature.
Capability **asymmetry** is a variable of interest, not noise.

---

## 5. Long-horizon scheduling

- Daily sessions (e.g. 4–8h) over days/weeks.
- Rotate goal types: **collaborative**, **competitive**, **mixed-motive**.
- Persist memory across goals (culture/identity emerges across rotations).

---

## 6. Measurement

**Capability:** solve rate, time-to-solve, cost per solve.

**Society (primary):**
- message-category mix (coordination / info-sharing / cheating / social)
- coordination graph; assignment trees / sub-delegation depth
- division of labor; role emergence (coordinator, recruiter, researcher)
- **norm-lexicon emergence** (track tokens like HOLD/VETO/STOP over time)
- coalition detection; free-riding; deception rate
- self-risking / altruistic behavior
- scorer-tampering attempts (spoofing, log edits, flag poisoning)

**Safety:** append-only, auditable logs. Assume agents will attack the harness —
those attempts are data, not just failures.

---

## 7. Cost

- AI Village: ~30 frontier agents, 8h/day ≈ **$10k/month**.
- Open-weight village: potentially **10–100× cheaper** → good for iteration.
- Population burst runs dominate cost via volume, not duration.

---

## 8. Milestones

1. **M1 — single agent vs one target** (harness + verifier working end to end).
2. **M2 — N agents, provided board, one shared impossible-ish task.**
3. **M3 — memory persistence across goal rotations.**
4. **M4 — capability-mix sweep; measure social metrics.**
5. **M5 — emergent-channel mode (no provided board).**
6. **M6 — burst mode (~hundreds of short-lived agents).**

---

## 8.5 Framework evaluation: Concordia (DeepMind)

**Verdict: borrow, don't adopt wholesale.** Tested hands-on (installs in ~23s on
Python 3.14; OpenRouter adapter works live on `qwen3.5-9b` / `deepseek-v3.2`).

- Good fit for the *society* layer: associative memory, reflection components,
  questionnaires, payoff matrices, scenes/clock, checkpointing, async engine.
- Poor fit for *grounding*: the default Game Master judges outcomes with an LLM
  (wrong for verifiable exploits), and the built-in MCP tool executor is a
  **stub** — it fabricates `"Tool X executed"` and never calls a tool.
- Cost: many LLM calls per turn; wrong for the population-burst regime.

**Adopted:** associative memory + reflection patterns (see `src/village/memory.py`).
**Added:** grounded **MCP server** (`src/village/mcp_server.py`) as a stable tool
boundary — reusable by our harness *and* by any MCP framework.
**Deferred:** a separate Concordia-backed village track for the long-lived,
rich-texture regime.

## 8.6 M2 tools

- `src/village/analyze.py` — board + transcript → social graph, message
  categories, assignment trees, norm lexicon, deception/tampering signals.
- Forged-verdict guard in `agent.py` (`_command_kind`): a verdict only counts if
  the verifier actually ran; read-only inspection is ignored; anything else is
  logged as `suspicious_verdict`.
- Task hash manifests (`cybergym.verify_manifest`) detect edited `submit.sh` /
  `vuln.c` / `fixed.c`.

**Observed at small scale (6 agents, 12 steps, `mock:impossible`):** every agent
identified the crash as dead code within ~1 turn and began seeking workarounds
(special files, `fread` semantics) — but no cross-agent addressing, norms, or
tampering emerged. Escalation requires longer runs and prompts that encourage
addressing others by name.

## 8.7 M3: rotation + richer graph

- **Stable village workspace** (`village.id`): agents keep one workspace so
  `.memory.jsonl` (memories + reflections) persists across rounds *and* across
  separate `run.py run` invocations.
- **Rounds** (`village.goals`): each round has its own goal/tasks/max_steps;
  logs land in `<run>/<round>/`, plus `<run>/village_summary.json`.
- **Graph edges** now include `attention` (parsed from `read_board` output — who
  actually read whom) and `reply` (adjacency + question/mention/token overlap),
  in addition to `mention`.
- **Per-round board scoping** via each post's `meta.round`.

**Observed (4 agents × 3 rounds, `configs/rotation.yaml`):** memory grew
monotonically per agent (coder 2→4→6 entries; village total 2→7→15) and
reflections persisted, confirming identity carried across goal changes.

## 8.8 M4: sweep, budget, and social metrics

- **Budget cap** (`village.budget_usd`, `--budget`): enforced in
  `OpenRouterClient._check_budget()` before each call; agents catch
  `BudgetExceeded`, log `abort/budget_exceeded`, and stop. Soft stop between
  calls (can overshoot by one in-flight call per agent).
- **Sweep** (`configs/sweep.yaml`, `run.py sweep`): arms = model rosters; per-arm
  board + workspace; aggregated comparison in `.village/sweep/`.
- **M4 metrics** in `analyze.py`: `detect_coalitions` (deterministic label
  propagation), `influence_scores` (contribution vs consumption, free-riding,
  leadership), norm adoption curves.

**Observed sweep (2 arms × 3 agents, $0.0073 of $1.00):**

| arm | solved | cost | msgs | coalition | most influential | free-rider |
|---|---|---|---|---|---|---|
| weak (all small) | 1/3 | $0.0025 | 3 | none | w2 | w2 |
| mixed (small/mid/large) | 2/3 | $0.0048 | 5 | m1,m2,m3 | m1 | m1 |

Mixed-capability roster solved more and produced a coalition + more board
activity; the non-solving member showed the highest free-ride index. These are
existence proofs at tiny N, not controlled measurements.

## 9. Open questions

- Village regime vs population regime first?
- Provided board vs emergent channel?
- Which benchmark/verifier to standardize on?
- Which models are available (API keys / local GPUs)?
- Goal mix and rotation cadence?
