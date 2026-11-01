"""Write SHA-256 checksums for built wheel/sdist assets; never bundles user files."""

import hashlib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
folder = root / "dist"
assets = sorted(folder.glob("*.whl")) + sorted(folder.glob("*.tar.gz"))
if not assets:
    raise SystemExit("Run uv build first")
lines = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in assets]
(folder / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Checksummed", len(assets), "release assets.")
