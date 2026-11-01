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
