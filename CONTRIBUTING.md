# Contributing

Open an issue describing the musical task, target Live version and expected
read/write behavior. Avoid attaching copyrighted samples or private sets.

Use a feature branch and a pull request. Preserve target guards, capability
checks, bounded work, original-preserving warp previews and explicit evidence
labels. A timeout must not trigger a blind retry of a write.

Install development dependencies with `uv sync --locked`, then run the checks
listed in README.md. Add tests for new behavior and failure cases. New tools
need accurate read-only/destructive annotations and documentation. Regenerate
the tool catalog after changing the registry. Keep recipes/source attributions
and packed JSON in sync. Never claim audio audition or Live runtime verification
from unit tests alone.

See docs/RELEASING.md before changing versions or making release assets.
