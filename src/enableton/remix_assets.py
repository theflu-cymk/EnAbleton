"""Private project journals and immutable, content-checked rendered assets."""

from array import array
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import os
from uuid import uuid4

from .remix_audio import (
    activity_regions,
    aligned_source,
    decode_window,
    digest,
    fade_edges,
    file_identity,
    process_values,
    write_wave,
)
from .remix_workflow import plan_halftime_remix


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def project(path, create=False):
    raw = Path(path).expanduser()
    if not raw.is_absolute():
        raise ValueError("Use an absolute private remix project directory")
    root = raw.resolve()
    marker = root / "remix-project.json"
    if create and not marker.exists():
        if root.exists() and any(root.iterdir()):
            raise ValueError("Refuse nonempty unmarked project directory")
        root.mkdir(parents=True, exist_ok=True)
        atomic_json(marker, dict(schema_version=1, project_id=uuid4().hex, state="new", tracks={}))
    if not marker.is_file():
        raise ValueError("Not a remix project directory")
    data = read_json(marker)
    if data.get("schema_version") != 1 or len(data.get("project_id", "")) != 32:
        raise ValueError("Unsupported remix project manifest")
    return root, data


@contextmanager
def project_lock(root):
    path = Path(root) / "operation.lock"
    try:
        with path.open("x", encoding="utf-8") as f:
            f.write(json.dumps(dict(pid=os.getpid())))
    except FileExistsError as exc:
        raise RuntimeError(
            "Project operation already running, or interrupted lock needs inspection"
        ) from exc
    try:
        yield
    finally:
        path.unlink()


def save_project(root, data):
    atomic_json(Path(root) / "remix-project.json", data)


def cached_asset(root, key, producer):
    folder = Path(root) / "assets"
    folder.mkdir(exist_ok=True)
    path = folder / (key + ".wav")
    metadata = folder / (key + ".json")
    if metadata.exists():
        info = read_json(metadata)
        current = file_identity(path)
        if current["sha256"] != info["file"]["sha256"]:
            raise ValueError(
                "Cached audio changed externally; preserve it and prepare in a new project"
            )
        return dict(info, cached=True)
    if path.exists():
        raise ValueError("Orphaned rendered audio without metadata; inspect before recovery")
    values, sr, ch = producer()
    write_wave(path, values, sr, ch)
    info = dict(
        path=str(path),
        sample_rate=sr,
        channels=ch,
        frames=len(values) // ch,
        file=file_identity(path),
        cached=False,
    )
    atomic_json(metadata, info)
    return info


def render_assets(root, plan, bindings, infer_vocals=True):
    root = Path(root)
    assets = {}
    references = {}
    tempo = plan["grid"]["tempo"]
    length = plan["config"]["drop_bars"] * 4
    for role, binding in bindings.items():
        if role not in {"riff", "vocal", "rock_context"}:
            continue
        if role == "vocal" and plan["config"]["vocal_mode"] == "none":
            continue
        if file_identity(binding["timing"]["file_path"]) != binding["file"]:
            raise ValueError(f"{role} source changed before render")
        beats = plan["config"]["lead_in_bars"] * 4 if role == "rock_context" else length
        if not beats:
            continue
        key = "source-" + digest(dict(binding=binding, tempo=tempo, beats=beats, renderer=2))
        references[role] = cached_asset(
            root, key, lambda b=binding, n=beats: aligned_source(b, tempo, n)
        )
    if (
        "vocal" in references
        and infer_vocals
        and not plan["config"]["vocal_regions"]
        and plan["config"]["vocal_source_kind"] == "isolated"
    ):
        ref = references["vocal"]
        v, sr, ch = decode_window(ref["path"], 0, ref["frames"] / ref["sample_rate"])
        config = deepcopy(plan["config"])
        config["vocal_regions"] = activity_regions(v, sr, ch, tempo)
        plan = plan_halftime_remix(config)
        plan["vocal_activity_evidence"] = (
            "Level-based activity windows; not words, lyric recognition or guaranteed clean-vocal detection"
        )
    for role, ref in references.items():
        s = plan["movement"]["settings"]
        if role == "riff":
            dependencies = dict(
                pulses=plan["movement"]["pulses"],
                settings={k: s[k] for k in ["attack_ms", "release_ms", "floor", "vocal_duck_db"]},
                vocal_regions=plan["config"]["vocal_regions"],
            )
        elif role == "vocal":
            dependencies = dict(
                chops=plan["arrangement"]["vocal_chops"], mode=plan["config"]["vocal_mode"]
            )
        else:
            dependencies = dict(gap=s["transition_gap_beats"])
        key = "render-" + digest(
            dict(role=role, source=ref["file"]["sha256"], dependencies=dependencies, renderer=2)
        )

        def render(ref=ref, role=role):
            v, sr, ch = decode_window(ref["path"], 0, ref["frames"] / ref["sample_rate"])
            return process_values(v, sr, ch, plan, role), sr, ch

        assets[role] = cached_asset(root, key, render)
    if plan["arrangement"]["fx"] and "riff" in references:
        ref = references["riff"]
        key = "fx-" + digest(
            dict(source=ref["file"]["sha256"], events=plan["arrangement"]["fx"], tempo=tempo)
        )

        def render_fx():
            v, sr, ch = decode_window(ref["path"], 0, ref["frames"] / ref["sample_rate"])
            out = array("h", [0]) * len(v)
            for event in plan["arrangement"]["fx"]:
                a = round(event["start"] * 60 / tempo * sr)
                b = round(event["end"] * 60 / tempo * sr)
                # Reverse sample frames, preserving channel order.
                piece = array("h")
                for i in range(b - 1, a - 1, -1):
                    piece.extend(v[i * ch : (i + 1) * ch])
                fade_edges(piece, sr, ch, 10)
                out[a * ch : b * ch] = piece
            return out, sr, ch

        assets["fx"] = cached_asset(root, key, render_fx)
    for role, binding in bindings.items():
        if role in references and file_identity(binding["timing"]["file_path"]) != binding["file"]:
            raise ValueError(f"{role} source changed during render")
    return dict(plan=plan, assets=assets, references=references)


def worker_job(request):
    root, manifest = project(request["project_dir"])
    op = request["operation"]
    if op == "render":
        return render_assets(
            root, request["plan"], request["bindings"], request.get("infer_vocals", True)
        )
    if op == "measure":
        from .remix_audio import measure

        return measure(request["path"])
    if op == "compare":
        from .remix_audio import compare

        return compare(request["reference"], request["variant"], root / "comparisons")
    if op == "extract":
        from .remix_audio import measure

        key = "preview-" + digest(
            dict(
                source=file_identity(request["path"]),
                start=request["start_seconds"],
                duration=request["duration"],
            )
        )

        def render():
            v, sr, ch = decode_window(
                request["path"], request["start_seconds"], request["duration"]
            )
            fade_edges(v, sr, ch, 5)
            return v, sr, ch

        result = cached_asset(root, key, render)
        result["measurements"] = measure(result["path"])
        from .audio_scan import scan_pcm

        result["problem_scan"] = scan_pcm(result["path"], max_seconds=min(120, request["duration"]))
        return result
    raise ValueError("Unknown remix worker operation")
