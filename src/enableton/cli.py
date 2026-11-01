"""EnAbleton command-line interface. Installation never edits a Live set."""

import argparse
import json
from pathlib import Path
import tempfile

from . import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(prog="enableton", description=__doc__)
    parser.add_argument("--version", action="version", version=f"EnAbleton {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Run the stdio MCP server")
    build = commands.add_parser("build-bridge", help="Generate the pinned Live Remote Script")
    build.add_argument("--output", type=Path, required=True)
    install = commands.add_parser(
        "install", help="Install the EnAbleton Remote Script with backups"
    )
    install.add_argument("--user-library", type=Path, required=True)
    install.add_argument(
        "--replace", action="store_true", help="Allow a reviewed existing script to be replaced"
    )
    doctor = commands.add_parser("doctor", help="Read-only installation and running-version check")
    doctor.add_argument("--user-library", type=Path, required=True)
    doctor.add_argument("--json", action="store_true", help="Emit JSON (the default)")
    args = parser.parse_args(argv)
    if args.command == "serve":
        from .server import mcp

        mcp.run()
        return 0
    if args.command == "build-bridge":
        from .bridge_builder import build as build_bridge

        print(json.dumps(build_bridge(args.output), indent=2))
        return 0
    library = args.user_library.expanduser().resolve()
    if not library.is_dir():
        parser.error(
            "--user-library must point to the existing User Library shown in Live Settings"
        )
    remote = library / "Remote Scripts" / "EnAbleton"
    if args.command == "doctor":
        from .doctor import main as doctor_main

        return doctor_main(remote)
    from .bridge_builder import build as build_bridge
    from .installer import install_bridge

    with tempfile.TemporaryDirectory(prefix="enableton-stage-") as temp:
        stage = Path(temp) / "EnAbleton"
        build_bridge(stage)
        print(
            json.dumps(
                install_bridge(
                    stage, remote, Path.home() / ".enableton" / "backups", replace=args.replace
                ),
                indent=2,
            )
        )
    return 0
