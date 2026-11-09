"""Interactive start screen. The nine operations come from prep.OPS."""

import argparse
import json
import sys

from .prep import OPS, handoff, probe_live, process_exit, resolve, run, run_all

PROMPT = "> "


def menu_lines(connected):
    """The screen a person sees. One status line, nine ops, then a prompt."""

    status = (
        "Live: connected" if connected else "Live: not connected (open Live and select EnAbleton)"
    )
    lines = [
        "EnAbleton - prepare or edit the open set",
        "",
        status,
        "",
        "  all   Run every step below, in order",
    ]
    for number, op in enumerate(OPS, start=1):
        mark = "writes" if op["writes"] else "read-only"
        lines.append(f"  {number}  {op['id']:<7} {op['words']:<46} {mark}")
    lines.extend(["", 'Type a number, a step id, "all", or just say what you want.'])
    return lines


def menu_text(connected):
    return "\n".join(menu_lines(connected))


def payload(connected):
    return {
        "method": "start",
        "live": "connected" if connected else "not connected",
        "live_changes": False,
        "playback_started": False,
        "all": "Run every step below, in order",
        "options": [
            {
                "number": number,
                "id": op["id"],
                "title": op["title"],
                "words": op["words"],
                "writes": op["writes"],
                "phase": op["phase"],
            }
            for number, op in enumerate(OPS, start=1)
        ],
    }


def _screen_parser(argv):
    parser = argparse.ArgumentParser(prog="enableton start", add_help=False)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--choice")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--snapshot")
    parser.add_argument("--plan", action="store_true")
    return parser.parse_args(argv)


def _run_choice(choice, args):
    """Run one op, or all, against Live or a snapshot. Free text is a handoff."""

    selected = resolve(choice)
    if selected is None:
        return handoff(choice)
    from .prep import _options_from, _parser, _source_from

    if args is None or not (getattr(args, "snapshot", None) or getattr(args, "live", False)):
        from .server import dispatch

        source = dispatch
        options = {}
    else:
        namespace = _parser().parse_args([])
        namespace.snapshot = getattr(args, "snapshot", None)
        namespace.plan = bool(getattr(args, "plan", False))
        namespace.live = bool(getattr(args, "live", False))
        source = _source_from(namespace)
        options = _options_from(namespace)
    if selected == "all":
        payload_rows = run_all(source, options)
    else:
        payload_rows = run(selected, source, options)
    print(json.dumps(payload_rows, indent=2, allow_nan=False))
    return process_exit(payload_rows)


def run(args=None, reader=input, is_tty=None, probe=None):
    """Print the screen, or JSON when stdin is not a terminal. Return an exit code."""

    if isinstance(args, list):
        try:
            args = _screen_parser(args)
        except SystemExit as escaped:
            return int(escaped.code or 2)
    as_json = bool(getattr(args, "json", False)) if args is not None else False
    choice = getattr(args, "choice", None) if args is not None else None
    tty = sys.stdin.isatty() if is_tty is None else bool(is_tty() if callable(is_tty) else is_tty)
    connected = (probe_live if probe is None else probe)()
    if choice:
        if as_json:
            print(json.dumps(payload(connected), indent=2))
        selected = resolve(choice)
        if selected is None:
            print("Unknown choice. Use a number or a step id.", file=sys.stderr)
            return 2
        if getattr(args, "snapshot", None) or getattr(args, "live", False):
            return _run_choice(choice, args)
        op = next(item for item in OPS if item["id"] == selected) if selected != "all" else None
        if op is None:
            print("all   Run every step below, in order")
        else:
            mark = "writes" if op["writes"] else "read-only"
            print(f"{op['id']:<7} {op['words']:<46} {mark}")
        return 0
    if as_json or not tty:
        print(json.dumps(payload(connected), indent=2))
        return 0
    print(menu_text(connected))
    try:
        picked = reader(PROMPT)
    except (EOFError, KeyboardInterrupt):
        return 0
    if picked is None:
        return 0
    picked = str(picked).strip()
    if picked.casefold() in {"", "q", "quit"}:
        return 0
    if resolve(picked) is None:
        return handoff(picked)
    try:
        return _run_choice(picked, args)
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
