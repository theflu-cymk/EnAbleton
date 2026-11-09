"""YAML pipeline scaffold: pure planners, guarded adapter boundary, local song folders."""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import unicodedata
from uuid import uuid4

import yaml

REGISTRY = {}


@dataclass
class Result:
    changes: list = field(default_factory=list)
    notices: list = field(default_factory=list)


def register(name):
    """A process receives (normalized state, merged params, target) and returns Result."""

    def decorate(function):
        if name in REGISTRY:
            raise ValueError(f"Duplicate process: {name}")
        REGISTRY[name] = function
        return function

    return decorate


def load_config(path):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    validate(data)
    return data


def validate(config):
    if not isinstance(config, dict) or type(config.get("schemaVersion")) is not int:
        raise ValueError("schemaVersion: 1 is required")
    if config["schemaVersion"] != 1:
        raise ValueError("Unsupported schemaVersion")
    allowed = {"schemaVersion", "song", "defaults", "steps", "lint"}
    if set(config) - allowed:
        raise ValueError("Unknown top-level config keys")
    for key in ("defaults", "song", "lint"):
        if key in config and not isinstance(config[key], dict):
            raise ValueError(f"{key} must be an object")
    if not isinstance(config.get("steps"), list):
        raise ValueError("steps must be an ordered list")
    if set(config.get("defaults", {})) - {"processes"}:
        raise ValueError("Unknown defaults keys")
    processes = config.get("defaults", {}).get("processes", {})
    if not isinstance(processes, dict) or any(not isinstance(v, dict) for v in processes.values()):
        raise ValueError("defaults.processes must map names to parameter objects")
    if set(config.get("song", {})) - {"name", "root", "folderName", "onExists", "subfolders"}:
        raise ValueError("Unknown song folder keys")
    seen = set()
    for step in config["steps"]:
        if not isinstance(step, dict) or set(step) - {
            "id",
            "process",
            "enabled",
            "params",
            "target",
            "when",
        }:
            raise ValueError("Invalid step keys")
        if not isinstance(step.get("id"), str) or not step["id"] or step["id"] in seen:
            raise ValueError("Step IDs must be non-empty and unique")
        seen.add(step["id"])
        if step.get("process") not in REGISTRY:
            raise ValueError(f"Unregistered process: {step.get('process')}")
        if type(step.get("enabled")) is not bool or not isinstance(step.get("params"), dict):
            raise ValueError("Each step requires boolean enabled and object params")
        target = step.get("target", {})
        if not isinstance(target, dict) or set(target) - {"trackIds", "clipIds", "types"}:
            raise ValueError("Unknown target selector")
        if any(
            not isinstance(v, list) or any(not isinstance(x, str) for x in v)
            for v in target.values()
        ):
            raise ValueError("Target selectors must be lists of strings")
        when = step.get("when", {})
        if not isinstance(when, dict) or set(when) - {"hasMidi", "hasAudio", "minTracks"}:
            raise ValueError("Unknown when predicate; expressions are not evaluated")
        for key in ("hasMidi", "hasAudio"):
            if key in when and type(when[key]) is not bool:
                raise ValueError(f"{key} must be boolean")
        if "minTracks" in when and (type(when["minTracks"]) is not int or when["minTracks"] < 0):
            raise ValueError("minTracks must be a non-negative integer")


def selected(state, target):
    for track in state.get("tracks", []):
        if track.get("is_master") or track.get("is_return"):
            continue
        if "trackIds" in target and track["id"] not in target["trackIds"]:
            continue
        if "types" in target and track["type"] not in target["types"]:
            continue
        if "clipIds" in target and not any(
            c["id"] in target["clipIds"] for c in track.get("clips", [])
        ):
            continue
        yield track


def clips(state, target):
    for track in selected(state, target):
        for clip in track.get("clips", []):
            if "clipIds" not in target or clip["id"] in target["clipIds"]:
                yield track, clip


def condition(state, when):
    tracks = state.get("tracks", [])
    for field, kind in (("hasMidi", "midi"), ("hasAudio", "audio")):
        if field in when and any(t["type"] == kind for t in tracks) != when[field]:
            return False
    return len(tracks) >= when.get("minTracks", 0)


def song_folder(params):
    raw_root = params.get("root", "")
    if not isinstance(raw_root, str):
        raise ValueError("song.root must be a path string")
    root = Path(raw_root).expanduser()
    if not root.is_absolute():
        raise ValueError("song.root must be an absolute user-defined directory")
    title = params.get("name", "")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("song.name is required")
    raw = params.get("folderName")
    if raw is None:
        raw = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
        raw = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw).strip("-_").lower()
    if (
        not isinstance(raw, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]+(?: [A-Za-z0-9_-]+)*", raw)
        or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", raw)
    ):
        raise ValueError("folderName must be one safe, non-reserved directory component")
    root = root.resolve()
    destination = (root / raw).resolve()
    if not destination.is_relative_to(root):
        raise ValueError("Song folder escapes song.root")
    subdirs = params.get(
        "subfolders", ["audio", "midi", "originals", "exports", "reports", "configs"]
    )
    if not isinstance(subdirs, list) or any(
        not isinstance(s, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", s) for s in subdirs
    ):
        raise ValueError("subfolders must be safe single directory components")
    for sub in subdirs:
        if not (destination / sub).resolve().is_relative_to(destination):
            raise ValueError("Subfolder resolves outside song folder")
    policy = params.get("onExists", "error")
    if policy not in {"error", "reuse"}:
        raise ValueError("onExists must be error or reuse")
    if destination.exists():
        if not destination.is_dir() or policy == "error":
            raise ValueError(f"Song folder already exists: {destination}")
        manifest = destination / "song.json"
        if manifest.exists():
            existing = json.loads(manifest.read_text(encoding="utf-8"))
            if existing.get("name") != title:
                raise ValueError("Existing folder belongs to a different song")
        elif any(destination.iterdir()):
            raise ValueError("Refusing to reuse an unrelated non-empty folder")
    return {
        "path": str(destination),
        "name": title,
        "subfolders": subdirs,
        "onExists": policy,
        "root": str(root),
    }


def create_folder(change):
    # Revalidate at execution time, including symlink containment and reuse policy.
    checked = song_folder(dict(change, folderName=Path(change["path"]).name))
    dest = Path(checked["path"])
    dest.mkdir(parents=True, exist_ok=checked["onExists"] == "reuse")
    for sub in checked["subfolders"]:
        (dest / sub).mkdir(exist_ok=True)
    manifest = dest / "song.json"
    if not manifest.exists():
        manifest.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "name": checked["name"],
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return dest


def project(state, change):
    """Project supported change lists in memory; never invoke a writer during dry run."""
    kind = change["kind"]
    patch = deepcopy(change.get("patch", {}))
    if kind == "create_song_folder":
        state["workspace"] = {"path": change["path"], "name": change["name"]}
    elif kind == "set_session":
        state.setdefault("session", {}).update(patch)
    elif kind in {"set_track", "delete_track"}:
        for track in list(state.get("tracks", [])):
            if track["id"] == change["target"]:
                if kind == "delete_track":
                    state["tracks"].remove(track)
                else:
                    track.update(patch)
    elif kind in {"set_clip", "replace_midi", "delete_clip", "resize_clip", "set_warp"}:
        for track in state.get("tracks", []):
            for clip in list(track.get("clips", [])):
                if clip["id"] == change["target"]:
                    if kind == "delete_clip":
                        track["clips"].remove(clip)
                    else:
                        clip.update(patch)


class UnsupportedOperations(RuntimeError):
    pass


class SnapshotAdapter:
    """Read-only planning adapter. It deliberately never pretends to edit Live.

    Production adapters implement snapshot(), supports(change), apply(change).
    apply MUST re-read and check change['before'] against the current target,
    use name/start/identity guards, then verify the write. Target IDs must stay
    stable across steps; track/clip indexes alone are not stable identifiers.
    """

    def __init__(self, state):
        self.state = deepcopy(state)

    def snapshot(self):
        return deepcopy(self.state)

    def supports(self, change):
        return False

    def apply(self, change):
        raise UnsupportedOperations(f"Live adapter needed for {change['kind']}")


def run_pipeline(config, adapter, *, dry_run=True, only=None, song_overrides=None, strict=False):
    """Run with injectable MCP adapter; no filesystem/Live writes during dry run."""
    validate(config)
    only = set(only or [])
    unknown = only - {s["id"] for s in config["steps"]}
    if unknown:
        raise ValueError(f"Unknown step IDs: {sorted(unknown)}")
    song = dict(config.get("song", {}), **(song_overrides or {}))
    active = [s for s in config["steps"] if s["enabled"] and (not only or s["id"] in only)]
    defaults = config.get("defaults", {}).get("processes", {})

    def plan(step, state):
        params = dict(defaults.get(step["process"], {}), **step["params"])
        if step["process"] == "create_song_folder":
            params = dict(song, **params)
            params.update(song_overrides or {})
        return REGISTRY[step["process"]](state, params, step.get("target", {}))

    # Preflight every selected planner, even conditional ones: no folder is made
    # before discovering a missing writer, unknown process or invalid parameter.
    initial = adapter.snapshot()
    previews = []
    preview_state = deepcopy(initial)
    for step in active:
        result = plan(step, preview_state)
        previews.append((step, result, deepcopy(preview_state)))
        if condition(preview_state, step.get("when", {})):
            for ch in result.changes:
                project(preview_state, ch)
    unsupported = {}
    for step, result, prior in previews:
        if not condition(prior, step.get("when", {})):
            continue
        for ch in result.changes:
            if ch["kind"] == "create_song_folder" or adapter.supports(ch):
                continue
            explain = getattr(adapter, "reason", None)
            unsupported[ch["kind"]] = (
                explain(ch) if callable(explain) else "no guarded writer for " + ch["kind"]
            )
    # Only strict mode aborts the run. The default applies everything the bridge
    # can do and reports the rest, so one unavailable Live API cannot block a step.
    if not dry_run and strict and unsupported:
        raise UnsupportedOperations(
            "Missing guarded adapter helpers: " + ", ".join(sorted(unsupported))
        )
    records = []
    destination = None
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]

    def current_state():
        snapshot = adapter.snapshot()
        if destination is not None:
            snapshot["workspace"] = {"path": str(destination), "name": song.get("name")}
        return snapshot

    try:
        for step, preview, projected_before in previews:
            before = current_state() if not dry_run else deepcopy(projected_before)
            record = {
                "id": step["id"],
                "process": step["process"],
                "before": before,
                "status": "skipped",
                "after": before,
            }
            records.append(record)
            if not condition(before, step.get("when", {})):
                continue
            result = preview if dry_run else plan(step, before)
            record.update(changes=result.changes, notices=result.notices)
            if dry_run:
                after = deepcopy(before)
                for ch in result.changes:
                    project(after, ch)
                record.update(status="planned", after=after, projected=True)
                continue
            record["status"] = "applying"
            skipped = []
            applied = 0
            for change in result.changes:
                if change["kind"] == "create_song_folder":
                    destination = create_folder(change)
                    applied += 1
                    continue
                if not adapter.supports(change):
                    explain = getattr(adapter, "reason", None)
                    skipped.append(
                        {
                            "kind": change["kind"],
                            "target": change["target"],
                            "reason": explain(change)
                            if callable(explain)
                            else "no guarded writer for " + change["kind"],
                        }
                    )
                    continue
                adapter.apply(change)
                applied += 1
            if skipped:
                record["skipped"] = skipped
            record.update(status="complete" if applied else "reported", after=current_state())
    except Exception as error:
        if records:
            records[-1].update(status="failed", error=str(error), after=current_state())
        raise
    finally:
        if not dry_run and destination is not None:
            report_dir = destination / "reports"
            report_dir.mkdir(exist_ok=True)
            (report_dir / f"{run_id}.json").write_text(
                json.dumps(records, indent=2), encoding="utf-8"
            )
            config_dir = destination / "configs"
            config_dir.mkdir(exist_ok=True)
            resolved = deepcopy(config)
            resolved["song"] = song
            (config_dir / f"{run_id}.yaml").write_text(
                yaml.safe_dump(resolved, sort_keys=False), encoding="utf-8"
            )
    return {
        "dryRun": dry_run,
        "steps": records,
        "missingAdapterHelpers": sorted(unsupported),
        "unsupportedReasons": unsupported,
        "songFolder": str(destination) if destination else None,
    }


def main(argv=None):
    import argparse
    from . import song_processes  # Explicit registration

    parser = argparse.ArgumentParser(
        description="Apply a song workflow. --plan previews. --lint stays read-only"
    )
    parser.add_argument("config", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--snapshot", type=Path, help="Normalized JSON snapshot for offline use")
    source.add_argument(
        "--live", action="store_true", help="Read the running Ableton set and apply the workflow"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--plan",
        action="store_true",
        help="Preview the workflow. No set or folder writes except an explicit --report",
    )
    mode.add_argument("--fix", action="store_true", help="Explicit Live lint metadata fixes only")
    parser.add_argument(
        "--lint", action="store_true", help="Run diagnostic rules independently of cleanup steps"
    )
    parser.add_argument(
        "--rules", action="append", default=[], help="Comma-separated lint rule names"
    )
    parser.add_argument(
        "--track",
        action="append",
        default=[],
        help="Lint capture track ID; repeat to select several",
    )
    parser.add_argument(
        "--clip", action="append", default=[], help="Lint capture clip ID; repeat to select several"
    )
    parser.add_argument("--fail-on", choices=["none", "info", "warning", "error"])
    parser.add_argument(
        "--include-session",
        action="store_true",
        help="Also inspect Session; ORIGINAL backups protected",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Explicit JSON report destination; existing files are never overwritten",
    )
    parser.add_argument("--only", action="append", default=[], help="Legacy workflow step IDs")
    parser.add_argument("--song-root")
    parser.add_argument("--song-name")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Abort before writing when any selected step needs an unavailable Live API",
    )
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        lint_mode = bool(args.lint or args.fix or args.rules or args.track or args.clip)
        if not lint_mode and args.fail_on:
            raise ValueError("Lint options require --lint")
        if lint_mode:
            from .song_lint import run_lint, write_report

            if args.only:
                raise ValueError(
                    "Lint uses --fix and --rules; --plan and --only are workflow flags"
                )
            if args.song_root or args.song_name:
                raise ValueError(
                    "Live lint does not create folders; song-root/name are workspace workflow options"
                )
            if args.report and (not args.report.parent.is_dir() or args.report.exists()):
                raise ValueError("Report parent must exist and report path must be new")
            snapshot = (
                json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else None
            )
            report = run_lint(
                config,
                snapshot=snapshot,
                live=args.live,
                fix=args.fix,
                selected_rules=[v for group in args.rules for v in group.split(",")] or None,
                fail_on=args.fail_on,
                include_session=args.include_session,
                target=dict(
                    {"trackIds": args.track} if args.track else {},
                    **({"clipIds": args.clip} if args.clip else {}),
                ),
            )
            if args.report:
                write_report(args.report, report)
            print(json.dumps(report, indent=2))
            return report["exitCode"]
        overrides = {}
        for key, value in (("root", args.song_root), ("name", args.song_name)):
            if value is not None:
                overrides[key] = value
        only = [v for item in args.only for v in item.split(",")]
        if args.live:
            from .server import dispatch
            from .song_apply import LiveAdapter
            from .song_lint import collect_live

            adapter = LiveAdapter(dispatch, collect_live(include_session=True))
            report = run_pipeline(
                config,
                adapter,
                dry_run=args.plan,
                only=only,
                song_overrides=overrides,
                strict=args.strict,
            )
            print(json.dumps(report, indent=2))
            return 0
        adapter = SnapshotAdapter(json.loads(args.snapshot.read_text(encoding="utf-8")))
        report = run_pipeline(
            config,
            adapter,
            dry_run=args.plan,
            only=only,
            song_overrides=overrides,
        )
        print(json.dumps(report, indent=2))
    except (ValueError, OSError, RuntimeError, UnsupportedOperations, yaml.YAMLError) as error:
        parser.error(str(error))
    return 0


# Load after register exists. Do not read prep.OPS here: this import can run
# while prep itself is still loading.
from . import prep as _prep

del _prep
