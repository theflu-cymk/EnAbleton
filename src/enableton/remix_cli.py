"""CLI adapters for the short-section build loop."""

import json
from pathlib import Path
import sys


def add_commands(commands):
    for name in ["remix-prepare", "remix-build", "remix-preview", "remix-compare", "remix-inspect"]:
        p = commands.add_parser(name, help="Bound remix build/render/compare workflow")
        p.add_argument("project_dir", type=Path)
        if name == "remix-prepare":
            p.add_argument("--config", type=Path, required=True)
            p.add_argument("--sources", type=Path, required=True)
            p.add_argument("--no-infer-vocals", action="store_true")
            p.add_argument("--refresh-pulses", action="store_true")
        if name == "remix-build":
            p.add_argument("--drum-kit", default="808 Core Kit")
            p.add_argument("--drum-map", type=Path)
        if name == "remix-preview":
            p.add_argument("--bars", type=int, default=8)
            p.add_argument("--no-lead-in", action="store_true")
        if name == "remix-compare":
            p.add_argument("reference")
            p.add_argument("variant")


def run(args):
    from .remix_assets import project, project_lock, read_json
    from .remix_live import build, inspect_project, prepare, worker
    from .remix_preview import capture

    try:
        if args.command == "remix-compare":
            root, _ = project(str(args.project_dir))
            with project_lock(root):
                result = worker("compare", root, reference=args.reference, variant=args.variant)
        else:
            from .server import dispatch

            if args.command == "remix-prepare":
                config = read_json(args.config)
                if isinstance(config.get("config"), dict):
                    config = config["config"]
                result = prepare(
                    dispatch,
                    config,
                    read_json(args.sources),
                    str(args.project_dir),
                    not args.no_infer_vocals,
                    args.refresh_pulses,
                )
            elif args.command == "remix-build":
                result = build(
                    dispatch,
                    str(args.project_dir),
                    args.drum_kit,
                    read_json(args.drum_map) if args.drum_map else None,
                )
            elif args.command == "remix-preview":
                result = capture(dispatch, str(args.project_dir), args.bars, not args.no_lead_in)
            else:
                result = inspect_project(dispatch, str(args.project_dir))
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, RuntimeError, OSError) as error:
        print(json.dumps(dict(error=str(error))), file=sys.stderr)
        return 2
