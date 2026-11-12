"""One read-only first-run check: what is installed and what to do next.

The check builds nothing, copies nothing and launches nothing. It reports the
User Library it was given, whether the installed Remote Script still matches its
manifest, and the exact commands that finish setup. Hashing uses the installer's
manifest format, so this result cannot disagree with `doctor`.
"""

import json
from pathlib import Path

from .installer import sha256_file

ACTIVATION = (
    "In Live Settings, Tempo & MIDI, select EnAbleton as a Control Surface with "
    "Input and Output set to None, then fully quit and restart Live."
)
NOTHING_CHANGED = (
    "This check builds, copies and launches nothing. It does not start Live, "
    "select a Control Surface or edit a set."
)


def inspect_installation(remote):
    """Return the on-disk state of the installed script; never import or run it."""

    remote = Path(remote)
    result = {
        "path": str(remote),
        "state": "missing",
        "modified_files": [],
        "missing_files": [],
    }
    manifest_path = remote / "ext-manifest.json"
    if not manifest_path.is_file():
        return result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        result["state"] = "unreadable"
        return result
    result["installed_upstream_version"] = manifest.get("upstream_version")
    result["installed_extension_version"] = manifest.get("extension_version")
    for name, expected in (manifest.get("files") or {}).items():
        path = remote / name
        if not path.is_file():
            result["missing_files"].append(name)
        elif sha256_file(path) != expected:
            result["modified_files"].append(name)
    result["state"] = (
        "modified" if result["missing_files"] or result["modified_files"] else "installed"
    )
    return result


def report(library, client=None):
    """Describe setup state and the remaining commands for one User Library."""

    library = Path(library)
    install = inspect_installation(library / "Remote Scripts" / "EnAbleton")
    quoted = f'"{library}"'
    if install["state"] == "modified":
        install_step = f"enableton install --user-library {quoted} --replace"
    elif install["state"] == "installed":
        install_step = None
    else:
        install_step = f"enableton install --user-library {quoted}"
    next_steps = [step for step in (install_step,) if step]
    next_steps.append(f"enableton doctor --user-library {quoted}")
    if client:
        next_steps.append(f"enableton client-config {client}")
    payload = {
        "user_library": str(library),
        "remote_script": install,
        "ready": install["state"] == "installed",
        "next": next_steps,
        "activation": ACTIVATION,
        "writes": NOTHING_CHANGED,
        "song_modified": False,
    }
    if client:
        from .client_config import build_client_config

        payload["client_config"] = {"client": client, "entry": build_client_config(client)}
    return payload
