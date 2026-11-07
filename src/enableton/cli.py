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
    workflow = commands.add_parser("song-init", help="Lint Live or plan a YAML song workflow")
    workflow.add_argument("workflow_args", nargs=argparse.REMAINDER)
    lint = commands.add_parser("lint", help="Read and lint the current Live set")
    lint.add_argument("workflow_args", nargs=argparse.REMAINDER)
    scan = commands.add_parser(
        "scan-audio", help="Scan PCM WAV and suggest targeted repairs; no audio edits"
    )
    scan.add_argument("path", type=Path)
    scan.add_argument("--start-seconds", type=float, default=0)
    scan.add_argument("--max-seconds", type=float, default=30)
    scan.add_argument("--report", type=Path, help="Write a new JSON report; never overwrite")
    for name in ("remix-plan", "remix-guide", "remix-refine"):
        remix = commands.add_parser(name, help="Plan or refine a half-time remix; no Live writes")
        remix.add_argument("config", type=Path, nargs="?" if name == "remix-guide" else None)
        remix.add_argument("--output", type=Path, help="Create a new JSON result; never overwrite")
        if name == "remix-refine":
            remix.add_argument("--feedback", nargs="+", required=True)
    from .remix_cli import add_commands

    add_commands(commands)
    args = parser.parse_args(argv)
    if args.command in {
        "remix-prepare",
        "remix-build",
        "remix-preview",
        "remix-compare",
        "remix-inspect",
    }:
        from .remix_cli import run

        return run(args)
    if args.command in {"remix-plan", "remix-guide", "remix-refine"}:
        import sys
        from .remix_workflow import (
            plan_halftime_remix,
            guide_halftime_remix,
            refine_halftime_remix,
        )

        try:
            config = json.loads(args.config.read_text(encoding="utf-8-sig")) if args.config else {}
            if isinstance(config, dict) and isinstance(config.get("config"), dict):
                config = config["config"]
            if args.command == "remix-guide":
                result = guide_halftime_remix(config)
            elif args.command == "remix-refine":
                result = refine_halftime_remix(config, args.feedback)
            else:
                result = plan_halftime_remix(config)
            raw = json.dumps(result, indent=2, allow_nan=False)
            if args.output:
                with args.output.open("x", encoding="utf-8") as output:
                    output.write(raw + "\n")
            print(raw)
            return 0
        except (ValueError, OSError) as error:
            print(json.dumps({"error": str(error)}), file=sys.stderr)
            return 2
    if args.command == "scan-audio":
        import sys
        from .audio_scan_tools import scan_audio_file

        try:
            report = scan_audio_file(
                str(args.path.expanduser().resolve()), args.start_seconds, args.max_seconds
            )
            raw = json.dumps(report, indent=2, allow_nan=False)
            if args.report:
                with args.report.open("x", encoding="utf-8") as output:
                    output.write(raw + "\n")
            print(raw)
            return 1 if report["finding_counts"] else 0
        except (ValueError, RuntimeError, OSError) as error:
            print(json.dumps({"error": str(error)}), file=sys.stderr)
            return 2
    if args.command in {"song-init", "lint"}:
        from .song_init import main as workflow_main

        return workflow_main(args.workflow_args + (["--lint"] if args.command == "lint" else []))
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
