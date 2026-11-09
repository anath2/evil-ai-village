# Communication study: calibration stopped main launch

The final technical pilot completed, but its frozen launch gate failed.
**The planned 48-village / 288-agent main comparison did not start.**

Protocol: `communication-impossibility-v4`, execution commit
`7209b2f0f9a6abce128a2f6b354599c3abcfe0aa`. Two DeepSeek villages
(six agents each, seed 96) tested shared versus private prepared findings.
These are excluded calibration runs, not the planned behavioral comparison.

Of 62 returned action replies, 52 were valid actions: **83.9%**, below the
required 90%. All 68 model calls completed without recorded model-call errors;
that denominator includes six initial finding calls. HTTP attempts are recorded
separately and are not an extra count of agent decisions. Reported pilot cost:
**$0.013089629088**, based on provider usage rather than reconciled billing.

Every other launch check passed: peer exposure in the shared condition,
private isolation, matched initial notes and task hashes, note authorship,
frozen source hashes, and dispatch pacing. Increasing the action output
allowance to 8,192 tokens did not establish adequate action-format reliability.
The gate did not inspect primary task-change outcomes when deciding to launch.
No thresholds were relaxed after this failure and no main run was launched.

This establishes a measurement limitation in this toy setup. It provides no
estimate of communication's behavioral effect, no cross-model behavioral
replication, and no claim about real vulnerability solving or the Hugging Face
incident. Additional credits do not resolve the failed measurement check.

[Machine-readable checks and provenance](metrics.json) contain counts and hashes
only. Raw model replies, notes and workspace data remain local. Earlier pilots
are retained locally and are not pooled into an effect estimate. See the
[protocol](../../docs/experiments/communication-impossibility.md) for their
operational amendments and the predeclared quality criteria.
