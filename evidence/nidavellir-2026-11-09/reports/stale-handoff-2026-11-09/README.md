# Stale-handoff pilot: incomplete, no treatment-effect conclusion

The [protocol](../../docs/experiments/stale-handoff.md) tests whether task-bound
verifier receipts change how workers handle stale peer success claims. It uses
independent/plain-board/receipt-board arms and fresh/stale handoff controls.

The v3 run used frozen commit `2a0c6b3`, Adaption `deepseek-v4-flash`, a 2048-token
output cap, a 180-second timeout and one HTTP attempt. It stopped after a response
failure under its predefined stopping rule. **16 episodes completed, one was
incomplete, and 19 of the scheduled 36 were never started.** The incomplete
episode was seed 3, stale handoff, plain board, at worker 3. The saved error is
`RuntimeError / provider_or_runtime_error`; its precise cause was not retained.

There were 50 valid worker reports across the recorded episodes, with no false
success claims among those reports. This partial, small sample does not establish
that receipts help, that the conditions are equivalent, or that the system is
safe. The checksum task is deliberately simple and may not expose the hypothesized
failure. A correct answer without a receipt is not a false success.

Provider-reported v3 cost was **$0.003497615456**, over 1365.989 seconds. This is not
reconciled billing; transport failures can incur unreported charges.

Two earlier calibration runs remain local and are not pooled with v3:

- V1 (`217c6e9`): 512-token cap; three complete and two incomplete episodes.
  A diagnostic replay confirmed output truncation.
- V2 (`d60eef9`): 2048-token cap, 45-second timeout; two complete and one
  incomplete episode. A diagnostic replay confirmed a read timeout.

[metrics.json](metrics.json) preserves the v3 manifest, source hashes, exact
schedule, per-condition counts, uncertainty and missingness. Raw synthetic
prompts/replies remain under `.village/stale-handoff-pilot-v3-2026-11-09/`, in
accordance with the repository's curated-summary-only reporting convention.
This is a research checkpoint, not a completed hackathon PDF or submission.

## Next decision

The remote branch has since added inference retries, concurrency controls and
changed handling of incomplete generations. Those changes were **not** loaded
by this running process. Before another study, review their effect on the frozen
protocol and record a new execution version; do not silently append new observations
to this run. First validate provider reliability on a small fixed set, then decide
whether a harder benign task is needed. Do not scale agent counts or claim a
behavioral improvement from this incomplete pilot.
