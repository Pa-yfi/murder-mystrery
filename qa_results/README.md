# Recorded audit evidence

The committed run is `20260920-081824`: 184 existing tests passed, one skipped;
1,262 new contract cases passed and 63 failed. See `../audit-results.md`.

That run includes source hashes, a credential-free source snapshot, logs, JUnit
XML, and per-family counts. It describes the captured source, not later working
tree changes. `post-audit-worktree.json` records changes observed after testing.

`repository_leak_scan.json` is a narrow, redacted signature scan of the recorded
Git HEAD and reachable text history. It does not certify that every possible
secret or runtime information leak is absent.

Run `python tools/run_quality_audit.py` from the repository root to produce fresh
results. Timestamped runs other than the reviewed snapshot are ignored here so
routine local runs do not accidentally add duplicate source trees to Git.

The quality contracts intentionally fail for documented unmet requirements.
Review this work as an audit and remediation starting point, not a release with
all tests passing. No production credentials or live database belong here.
