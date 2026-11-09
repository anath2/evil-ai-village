# Partial checkpoint: Ajit command-settings repeat

**RUNNING CHECKPOINT, NOT FINAL RESULTS.** Snapshot at 2026-11-09T10:03:30.446735+00:00.
54/500 agent loops have end records; 62 have start records.
Execution source `c40f9cc239ce902e7f10a35860dc4b5c20ed3342` is frozen; this export cannot change it.

This repeats the supplied CLI settings (500 agents, six turns, eight active,
$3 cap, 120-second requests, five attempts, four requests/model, 1,800-second
agent budget). Ajit's original source revision is unverified, so this is not
a proven exact-code replication. Host startup overhead affects wall time.

See settings.json and manifest.json for configuration, hashes and coverage.
The raw logs include malformed actions and failures; do not interpret every
returned loop as six useful actions. The board contains untrusted model text.
No credentials or environment files are included.
