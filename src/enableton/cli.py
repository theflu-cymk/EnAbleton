"""EnAbleton command-line interface. Installation never edits a Live set."""

import argparse
import json
from pathlib import Path
import tempfile

from . import __version__


def main(argv=None):
    import sys

    from .prep import route

    argv = sys.argv[1:] if argv is None else list(argv)
    # prep.route answers every command it does not recognize with the nine-step
    # preparation screen, so a command this parser owns is dispatched before the
    # router sees it.
    routed = None if argv[:1] == ["client-config"] else route(argv)
    if routed is not None:
        return routed
    parser = argparse.ArgumentParser(prog="enableton", description=__doc__)
    parser.add_argument("--version", action="version", version=f"EnAbleton {__version__}")
    commands = parser.add_subparsers(dest="command", required=False)
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
    client_config = commands.add_parser(
        "client-config", help="Print an MCP client config; never edits client settings"
    )
    client_config.add_argument("client", choices=("claude-desktop", "cursor"))
    client_config.add_argument(
        "--output", type=Path, help="Write this entry to a new file instead of only printing it"
    )
    workflow = commands.add_parser("song-init", help="Apply a YAML song workflow. --plan previews")
    workflow.add_argument("workflow_args", nargs=argparse.REMAINDER)
    initiate = commands.add_parser(
        "initiate", help="Prepare or lint a song from the default initial-preparation preset"
    )
    initiate.add_argument("--song-root", required=True, help="Song folder parent directory")
    initiate.add_argument("--song-name", required=True)
    initiate.add_argument("--mode", choices=("lint", "prepare"), help="Ask by omitting this")
    initiate.add_argument("--song-folder-name")
    initiate_source = initiate.add_mutually_exclusive_group()
    initiate_source.add_argument("--snapshot", type=Path, help="Normalized JSON snapshot")
    initiate_source.add_argument("--live", action="store_true", help="Read the running Ableton set")
    initiate.add_argument("--include-session", action="store_true")
    initiate.add_argument("--fail-on", choices=("none", "info", "warning", "error"))
    initiate.add_argument("--report", type=Path, help="JSON report for the audit pass")
    initiate.add_argument("--keep-config", type=Path, help="Write the generated YAML here")
    initiate.add_argument(
        "--plan",
        action="store_true",
        help="Preview the prepare steps. The set is not changed",
    )
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
    if args.command == "client-config":
        import sys

        from .client_config import build_client_config, client_config_path, client_display

        try:
            raw = json.dumps(build_client_config(args.client), indent=2, allow_nan=False)
            if args.output:
                try:
                    with args.output.open("x", encoding="utf-8") as output:
                        output.write(raw + "\n")
                except FileExistsError as error:
                    raise ValueError(f"{args.output} already exists; choose a new path") from error
            print(raw)
            print(
                "enableton: add this entry to "
                f"{client_config_path(args.client)} and restart {client_display(args.client)}. "
                "Existing entries are not merged; review the file before saving.",
                file=sys.stderr,
            )
            return 0
        except (OSError, RuntimeError, ValueError) as error:
            print(json.dumps({"error": str(error)}), file=sys.stderr)
            return 2
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
    if args.command == "initiate":
        from . import initial_prep
        from .song_init import main as workflow_main

        if args.mode is None:
            phases = {}
            for item in initial_prep.describe():
                phases.setdefault(item["phase"], []).append(item["id"])
            print(
                json.dumps(
                    {
                        "song": {"name": args.song_name, "root": args.song_root},
                        "question": initial_prep.ENTRY_QUESTION,
                        "modes": {
                            "lint": "Read the set and report; no writes.",
                            "prepare": "Lint, then apply the enabled steps in phase order.",
                        },
                        "phases": phases,
                        "next": "Re-run with --mode lint or --mode prepare.",
                    },
                    indent=2,
                )
            )
            return 2
        if not (args.snapshot or args.live):
            parser.error("--live or --snapshot is required with --mode")
        if args.keep_config:
            config_path = args.keep_config
        else:
            config_path = Path(tempfile.mkdtemp(prefix="enableton-initiate-")) / "initiate.yaml"
        try:
            initial_prep.write_config(
                config_path,
                args.song_root,
                args.song_name,
                args.mode,
                args.song_folder_name,
            )
        except (OSError, ValueError) as error:
            print(json.dumps({"error": str(error)}))
            return 2
        common = [str(config_path)] + (
            ["--snapshot", str(args.snapshot)] if args.snapshot else ["--live"]
        )
        session = ["--include-session"] if args.include_session else []
        if args.mode == "lint":
            extra = ["--lint"] + session
            if args.fail_on:
                extra += ["--fail-on", args.fail_on]
            if args.report:
                extra += ["--report", str(args.report)]
            return workflow_main(common + extra)
        audit = ["--lint", "--fail-on", "none"] + session
        if args.report:
            audit += ["--report", str(args.report)]
        audit_code = workflow_main(common + audit)
        if audit_code not in (0, 1):
            return audit_code
        from .prep import process_exit, run_all

        if args.snapshot:
            source = json.loads(args.snapshot.read_text(encoding="utf-8"))
        else:
            from .server import dispatch

            source = dispatch
        results = run_all(source, {"plan": bool(args.plan)})
        print(json.dumps(results, indent=2, allow_nan=False))
        return process_exit(results)
    if args.command == "song-init":
        from .song_init import main as workflow_main

        return workflow_main(args.workflow_args)
    if args.command == "serve":
        from .server import mcp

        mcp.run()
        return 0
    if args.command == "build-bridge":
        from .bridge_builder import build as build_bridge

        print(json.dumps(build_bridge(args.output), indent=2))
        return 0
    if args.command is None:
        from .song_start import run

        return run(None)
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
