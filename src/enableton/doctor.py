"""Read-only doctor for the deliberately extended 1.8.1 Remote Script."""

import hashlib
import json
from pathlib import Path
import sys
from ableton_live_mcp.connection import get_ableton_connection, disconnect_ableton
from . import __version__


def main(folder):
    folder = Path(folder)
    try:
        manifest = json.loads((folder / "ext-manifest.json").read_text())
    except (OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "package_version": __version__,
                    "installation_error": str(error),
                    "next": "Run enableton install with the correct --user-library path.",
                },
                indent=2,
            )
        )
        return 1
    result = {
        "package_version": __version__,
        "installed_matches": (folder / "__init__.py").is_file()
        and hashlib.sha256((folder / "__init__.py").read_bytes()).hexdigest()
        == manifest["generated_sha256"],
    }
    if manifest.get("files"):
        result["installed_matches"] = result["installed_matches"] and all(
            (folder / name).is_file()
            and hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest
            for name, digest in manifest["files"].items()
        )
    try:
        connection = get_ableton_connection()
        info = connection.send_command("get_script_info", {})
        result["running_version"] = info.get("version")
        result["running_enableton_version"] = info.get("enableton_version")
        result["running_matches"] = (
            info.get("upstream_version") == "1.8.1"
            and info.get("version") == manifest["extension_version"]
            and info.get("enableton_version") == __version__
        )
        if result["running_matches"]:
            session = connection.send_command("get_session_info", {})
            result["session"] = {
                k: session.get(k) for k in ("tempo", "tracks", "track_count") if k in session
            }
        result["ok"] = result["installed_matches"] and result["running_matches"]
    except Exception as error:
        result.update(ok=False, connection_error=str(error))
    finally:
        disconnect_ableton()
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
