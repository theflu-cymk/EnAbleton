# Working on EnAbleton

Preserve source-linked recipe provenance and stable IDs. Distinguish measured
audio, heuristic estimates, fake-Live tests, and actual Live readback/audition.
Never claim literal access to every Live UI function or hidden plug-in control.

Run `uv run python -m unittest discover -s tests/unit -p "test_*.py"`,
`uv run python tests/integration/test_transport.py`, `uv run ruff check .`, and
`uv run ruff format --check .` for code changes. Run `uv build` and verify the
wheel's packaged JSON/resources before release. Keep `uv.lock` in version control.

Read fresh track/device/clip targets and use identity/name/start guards before
Live writes. Refuse stale previews. After a timeout, inspect state before retrying.
Warp repairs preserve originals and operate on non-overlapping duplicates.
Do not use UI accessibility automation against this user's Ableton installation:
it has repeatedly crashed Live. Installation must never edit the user's song.

Do not commit credentials, local configuration, Live sets, presets, commercial
samples, user session snapshots, or reports. Keep release assets source-only.
Respect upstream license notices. Document compatibility and release limitations.

Use SemVer Git tags (`v0.1.0-beta.1`) and PEP 440 package versions (`0.1.0b1`).
The upstream package version and bridge protocol version are separate concerns.
Update the changelog and capability catalog when adding tools.

## Performance for Live work

For edits to named tracks, prefer collect_live(..., track_indices=[...]) or
bounded native read batches over full-set captures. Keep fresh identity guards,
backups and readback; do not cache write preconditions. Reuse audio analysis only
when its source/window/Warp fingerprints still match. Reserve full audits for
whole-set requests. Bundle necessary scoped work into fewer shell/tool calls;
never bypass approval review. See docs/PERFORMANCE.md for measured scope/limits.

## User-requested fast editing

The user explicitly requests fewer editing safeguards and less latency. Routine
Live edits are authorized by the requested task; do not ask again to apply them.
Use one scoped fresh read, one guarded native write batch where practical, and
one affected-object readback. Do not repeat compatibility checks, scan unrelated
tracks, rerun whole-set lint, export MIDI, or copy source media for every edit.
Prefer native Undo and a compact pre-edit state record over repeated full backups.
Keep original media intact when preparing replacement audio. Do not remove the
single target-identity check or final verification; they prevent wrong-track edits
at little cost when batched. Ask only for genuinely missing targets or unresolved
ambiguity. Never bypass platform permissions or automatic approval review.
