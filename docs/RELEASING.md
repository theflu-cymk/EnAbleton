# Release numbering and checklist

Use Semantic Versioning for GitHub tags and PEP 440 for Python distribution versions:

| Meaning | Git tag / GitHub release | Python version |
| --- | --- | --- |
| First beta | `v0.1.0-beta.1` | `0.1.0b1` |
| Next beta | `v0.1.0-beta.2` | `0.1.0b2` |
| Release candidate | `v0.1.0-rc.1` | `0.1.0rc1` |
| Stable | `v0.1.0` | `0.1.0` |

During 0.x, increase the minor version for incompatible changes; use patch
versions for compatible fixes. Do not move published tags. A 1.0 release needs
a documented real-Live compatibility/repair test matrix.

The Python distribution version, pinned upstream `1.8.1`, and legacy bridge
protocol `1.8.1-ext.8` are distinct. `ext.6` adds note insert/delete; earlier
`ext.5` installs lack those commands and report a lower capability count. `ext.7` adds Warp writes and track
monitoring; `ext.8` exposes clip `warp_mode` in object reads. The generated bridge also reports the
EnAbleton distribution version; doctor checks that it matches the client.

Before a release:

1. Update `pyproject.toml`, `src/enableton/__init__.py`, changelog and catalogs.
2. Update the lock file deliberately; run all unit/transport tests and Ruff.
3. Build wheel/sdist with `uv build`; verify packaged JSON and license files.
4. Run CLI help/version, generate a temporary bridge, and test an installation
   into a temporary User Library. Do not test installation over a user's song.
5. Scan tracked files and wheel/sdist for secrets, local paths and user media.
6. Build SHA-256 checksums for release assets; create an annotated immutable tag.
7. Create a GitHub prerelease for beta/RC tags. Upload wheel, sdist and checksums.
8. Document exactly which Live tests were completed, deferred or unsupported.

CI validates code and packaging; it does not run Ableton or publish automatically.
No PyPI publication is configured. Review the wheel and source before upload.
