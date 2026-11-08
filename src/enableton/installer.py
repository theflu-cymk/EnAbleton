"""Recoverable installation of generated Remote Scripts; never edits a Live set."""

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_stage(stage):
    stage = Path(stage)
    manifest = json.loads((stage / "ext-manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("files") or "__init__.py" not in manifest["files"]:
        raise ValueError("Incomplete stage manifest")
    for name, expected in manifest["files"].items():
        if Path(name).name != name or not name.endswith(".py"):
            raise ValueError("Unsafe manifest filename")
        path = stage / name
        if path.is_symlink() or not path.is_file() or sha256_file(path) != expected:
            raise ValueError("Staged file mismatch: " + name)
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    return manifest


def atomic_copy(source, destination):
    destination = Path(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(Path(source).read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def install_bridge(stage, remote, backup_root, replace=False):
    stage = Path(stage).resolve()
    remote = Path(remote)
    if (
        not remote.is_absolute()
        or remote.name != "EnAbleton"
        or remote.parent.name != "Remote Scripts"
    ):
        raise ValueError("Destination must be an absolute Remote Scripts/EnAbleton directory")
    for path in (remote, remote.parent, remote.parent.parent):
        if path.is_symlink():
            raise ValueError("Symlink destinations are not supported")
    manifest = validate_stage(stage)
    existed = remote.exists()
    if existed and any(remote.iterdir()) and not replace:
        raise ValueError(
            "Existing EnAbleton files: review them, then use --replace to back up and update"
        )
    if (remote / "ext-manifest.json").exists():
        old = json.loads((remote / "ext-manifest.json").read_text(encoding="utf-8"))
        for name, expected in old.get("files", {}).items():
            if (
                Path(name).name != name
                or not (remote / name).is_file()
                or sha256_file(remote / name) != expected
            ):
                raise ValueError(
                    "Installed bridge has local changes; review before overwriting: " + name
                )
    backup = Path(backup_root) / ("install-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    backup.mkdir(parents=True)
    if existed:
        shutil.copytree(remote, backup / "RemoteScript")
    remote.mkdir(parents=True, exist_ok=True)
    applied = []
    try:
        for name in (*manifest["files"], "ext-manifest.json"):
            destination = remote / name
            applied.append(destination)
            atomic_copy(stage / name, destination)
            if sha256_file(stage / name) != sha256_file(destination):
                raise RuntimeError("Installed hash mismatch: " + name)
    except Exception as error:
        failures = []
        for destination in reversed(applied):
            original = backup / "RemoteScript" / destination.name
            try:
                if original.exists():
                    atomic_copy(original, destination)
                else:
                    if destination.parent.resolve() != remote.resolve():
                        raise RuntimeError("Rollback escaped destination")
                    destination.unlink(missing_ok=True)
            except Exception:
                failures.append(str(destination))
        status = (
            "rollback incomplete: " + ", ".join(failures)
            if failures
            else "previous installation restored"
        )
        raise RuntimeError(f"Install failed; {status}. Backup: {backup}. {error}") from error
    report = {
        "version": manifest.get("enableton_version"),
        "bridge_protocol": manifest["extension_version"],
        "backup": str(backup),
        "installed_files_verified": len(applied),
        "activation": "Save and fully restart Live. Select EnAbleton only; disable the previous AbletonMCP row. Input/Output: None.",
        "song_modified": False,
    }
    (backup / "installation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
