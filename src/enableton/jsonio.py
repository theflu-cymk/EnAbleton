"""One atomic JSON reader/writer for every local journal and cache file."""

import json
import os
from pathlib import Path
import tempfile


def read_json(path):
    """Read UTF-8 JSON, tolerating a byte-order mark from external editors."""
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def atomic_json(path, value, *, indent=2):
    """Write JSON via a fsynced temporary file, then replace the target atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, indent=indent, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
