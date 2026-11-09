# Remote evidence closeout

This supplements the earlier evidence snapshots and completed-run export.
`manifest.json` maps every selected local run file to its exact preserved Git
path and SHA-256; identical files are referenced rather than copied again.

Includes interrupted fast runs, the paused six-turn fast run, failed Ajit-settings
setup, final run workspace evidence, launch/source-hash/coordinator records,
original-run retirement and host-relief records. Do not execute model-generated
commands or recovery scripts without checking current host state and the handoff.
Small synthetic PoC inputs may be binary data; generated executables are excluded.

The final command-settings repeat is complete. The faster run is still frozen;
448 inactive-agent containers were stopped, one active container was Docker-paused,
and its coordinator is separately SIGSTOP-held. Recovery metadata is preserved,
but process memory and live container state cannot be restored from Git alone.
The original run is retired, not resumable. The temporary old controller retains
Docker access for remaining work. Large/generated omissions remain local and
are explicitly listed. Credentials, private chat and unrelated files are excluded.

Read `docs/handoff-2026-11-09.md` and `reports/run-status-2026-11-09.json` for
context; final metrics and grading caveats are in
`reports/ajit-settings-repeat-2026-11-09/` and `reports/matching-settings-case-a283/`.
