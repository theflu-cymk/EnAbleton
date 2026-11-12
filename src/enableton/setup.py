"""Find the Live User Library and remove the Remote Script again.

Discovery only proposes paths that exist. It never guesses a path from
Documents or OneDrive when that directory is absent, never creates a User
Library, and never reads or writes a Live set. Uninstall moves the installed
script into a timestamped backup first, so the same files can be restored by
copying them back.
"""

from datetime import datetime
import json
from pathlib import Path
import shutil
import sys

BACKUP_ENVIRONMENT = ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")


def _roots(home, platform, environ):
    if platform.startswith("win"):
        roots = [home / "Music", home / "Documents"]
        for name in BACKUP_ENVIRONMENT:
            sync = environ.get(name)
            if sync:
                roots.extend((Path(sync) / "Music", Path(sync) / "Documents"))
        return roots
    if platform == "darwin":
        return [home / "Music"]
    return [home / "Music", home]


def candidate_libraries(home=None, platform=None, environ=None):
    """Return the usual User Library locations for this platform, in order."""

    home = Path.home() if home is None else Path(home)
    platform = sys.platform if platform is None else platform
    environ = {} if environ is None else environ
    seen = []
    for root in _roots(home, platform, environ):
        candidate = root / "Ableton" / "User Library"
        if candidate not in seen:
            seen.append(candidate)
    return seen


def discover_library(home=None, platform=None, environ=None, is_dir=None):
    """Return the one existing User Library, or raise with the paths checked.

    A customized location is common, so an ambiguous or empty result asks the
    producer for the path shown in Live Settings instead of picking one.
    """

    is_dir = Path.is_dir if is_dir is None else is_dir
    candidates = candidate_libraries(home=home, platform=platform, environ=environ)
    found = [path for path in candidates if is_dir(path)]
    if len(found) == 1:
        return {"user_library": str(found[0]), "candidates": [str(p) for p in candidates]}
    if not found:
        raise ValueError(
            "No Ableton User Library was found in the usual places ("
            + ", ".join(str(p) for p in candidates)
            + "). Copy the path from Live Settings, Library, User Library and pass --user-library."
        )
    raise ValueError(
        "More than one User Library was found ("
        + ", ".join(str(p) for p in found)
        + "). Pass the one Live shows in Settings with --user-library."
    )


def _require_remote(remote):
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
    return remote


def uninstall_bridge(remote, backup_root):
    """Move an installed EnAbleton Remote Script into a backup directory.

    The installed folder is moved, not deleted, so the files can be restored by
    copying ``RemoteScript`` back. Nothing outside that folder is touched.
    """

    from .installer import sha256_file

    remote = _require_remote(remote)
    manifest_path = remote / "ext-manifest.json"
    if not remote.is_dir() or not manifest_path.is_file():
        raise ValueError(
            "No EnAbleton installation found at "
            f"{remote}; nothing was removed. Check --user-library."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    modified = []
    missing = []
    for name, expected in (manifest.get("files") or {}).items():
        path = remote / name
        if not path.is_file():
            missing.append(name)
        elif sha256_file(path) != expected:
            modified.append(name)
    backup = Path(backup_root) / ("uninstall-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    backup.mkdir(parents=True)
    shutil.move(str(remote), str(backup / "RemoteScript"))
    return {
        "removed": str(remote),
        "backup": str(backup),
        "restore": (
            "Quit Live, copy "
            f"{backup / 'RemoteScript'} back to {remote.parent}, then restart Live and reselect "
            "EnAbleton as the Control Surface."
        ),
        "locally_modified": modified,
        "missing": missing,
        "song_modified": False,
        "activation": (
            "EnAbleton disappears from Live's Control Surface list after a full restart. "
            "No Live set, source media or unrelated file was deleted."
        ),
    }
