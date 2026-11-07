"""Scoped source binding and repeatable new-lane Live builds.

All persistence is private project data; source tracks are never rewritten.
"""

from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
import sys

from .bass_recipes import get_recipe
from .bass_tools import _mutation_lock
from .live_reads import read_many
from .remix_assets import atomic_json, project, project_lock, read_json, save_project
from .remix_audio import digest, file_identity
from .remix_workflow import plan_halftime_remix


def worker(operation, root, **kwargs):
    request = dict(operation=operation, project_dir=str(root), **kwargs)
    try:
        r = subprocess.run(
            [sys.executable, "-m", "enableton.remix_worker"],
            input=json.dumps(request, allow_nan=False),
            text=True,
            capture_output=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Audio worker timed out; inspect project assets before retrying"
        ) from exc
    if len(r.stdout) > 8_000_000:
        raise RuntimeError("Worker result exceeds 8 MB")
    try:
        result = json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Audio worker failed: " + r.stderr[-1000:]) from exc
    if r.returncode or "error" in result:
        raise RuntimeError(result.get("error", "Audio worker failed"))
    return result


def batch(send, commands):
    if not commands:
        return []
    result = send("batch", dict(commands=commands))
    if result.get("executed") != len(commands):
        raise RuntimeError("Partial Live batch; inspect journal, never blindly replay")
    return [r["result"] for r in result["results"]]


def command(type, **params):
    return dict(type=type, params=params)


def target(value):
    if not isinstance(value, dict):
        raise ValueError("Source needs a target object")
    t = deepcopy(value)
    for key in ["track_index", "clip_index"]:
        if type(t.get(key)) is not int or t[key] < 0:
            raise ValueError("Source target needs nonnegative " + key)
    for key in ["expected_track_name", "expected_clip_name"]:
        if not isinstance(t.get(key), str) or not t[key]:
            raise ValueError("Source target requires " + key)
    t.setdefault("clip_view", "arrangement")
    if t["clip_view"] not in ["session", "arrangement"]:
        raise ValueError("Invalid clip_view")
    if t["clip_view"] == "arrangement" and (
        isinstance(t.get("expected_start_time"), bool)
        or not isinstance(t.get("expected_start_time"), (int, float))
        or not math.isfinite(t["expected_start_time"])
    ):
        raise ValueError("Arrangement source needs expected_start_time")
    return t


def simple_notes(notes):
    return [
        {k: n[k] for k in ["pitch", "start_time", "duration", "velocity", "mute"]} for n in notes
    ]


def note_hash(notes):
    return digest(
        sorted(
            (
                int(n["pitch"]),
                round(float(n["start_time"]), 5),
                round(float(n["duration"]), 5),
                round(float(n["velocity"]), 3),
                bool(n["mute"]),
            )
            for n in notes
        )
    )


def bind_sources(send, config, sources):
    if not isinstance(sources, dict) or sources.keys() - {
        "riff_midi",
        "riff",
        "vocal",
        "rock_context",
    }:
        raise ValueError("Sources supports riff_midi, riff, vocal and rock_context")
    if "riff_midi" in sources and "source_section_start_beat" not in config:
        raise ValueError(
            "Supply the explicit clip-relative source_section_start_beat; do not guess MIDI offsets"
        )
    config = deepcopy(config)
    plan = plan_halftime_remix(config)
    bound = {}
    timing_references = {}
    reads = []
    roles = []
    for role, spec in sources.items():
        if not isinstance(spec, dict):
            raise ValueError("Source binding needs target and optional source_start")
        t = target(spec.get("target"))
        reads.append(command("get_track_info", track_index=t["track_index"]))
        reads.append(
            command("get_access_notes" if role == "riff_midi" else "get_audio_clip_timing", **t)
        )
        roles.append((role, spec, t))
    results = read_many(send, reads)
    if any(error for _, error in results):
        raise ValueError("Source read failed: " + str(next(error for _, error in results if error)))
    config.setdefault("source_roles", {})
    for k, (role, spec, t) in enumerate(roles):
        track = results[k * 2][0]
        data = results[k * 2 + 1][0]
        if track["name"] != t["expected_track_name"]:
            raise ValueError("Source track moved or renamed")
        if role == "riff_midi":
            if not track["is_midi_track"]:
                raise ValueError("riff_midi must refer to MIDI")
            notes = simple_notes(data["notes"])
            config["source_notes"] = notes
            props = send("read_access_object", dict(t, object_type="clip"))["properties"]
            if props.get("looping") and (
                config["source_section_start_beat"] < data.get("loop_start", 0)
                or config["source_section_start_beat"] + config.get("drop_bars", 16) * 4
                > data.get("loop_end", 0) + 1e-5
            ):
                raise ValueError(
                    "Selected MIDI range crosses loop braces; flatten/extend the transcription first"
                )
            bound[role] = dict(
                target=t,
                notes_hash=note_hash(notes),
                loop_start=data.get("loop_start"),
                loop_end=data.get("loop_end"),
                looping=props.get("looping"),
            )
            config["source_roles"]["riff"] = track["name"] + " / " + t["expected_clip_name"]
        else:
            if not track["is_audio_track"]:
                raise ValueError(role + " must refer to audio")
            native_timing = deepcopy(data)
            reference = None
            if spec.get("timing_reference") is not None:
                rt = target(spec["timing_reference"])
                key = digest(rt)
                if key not in timing_references:
                    ref = send("get_audio_clip_timing", rt)
                    if not ref["warping"]:
                        raise ValueError("Shared stem timing reference must be warped")
                    timing_references[key] = dict(
                        target=rt, timing=ref, file=file_identity(ref["file_path"])
                    )
                reference = timing_references[key]
                ref = reference["timing"]
                if all(k in d for d in [ref, data] for k in ["sample_length", "sample_rate"]):
                    if (
                        abs(
                            ref["sample_length"] / ref["sample_rate"]
                            - data["sample_length"] / data["sample_rate"]
                        )
                        > 0.25
                    ):
                        raise ValueError(
                            "Stem/reference lengths differ; confirm offsets before sharing timing"
                        )
                for field in [
                    "warping",
                    "warp_mode",
                    "warp_markers",
                    "start_marker",
                    "end_marker",
                    "loop_start",
                    "loop_end",
                    "looping",
                    "arrangement_start",
                    "arrangement_end",
                ]:
                    if field in ref:
                        data[field] = deepcopy(ref[field])
            role_start = plan["grid"]["drop_start_beat"] - (
                config.get("lead_in_bars", 4) * 4 if role == "rock_context" else 0
            )
            beats = (
                config.get("lead_in_bars", 4) * 4
                if role == "rock_context"
                else config.get("drop_bars", 16) * 4
            )
            if "source_start" in spec:
                start = spec["source_start"]
                if (
                    isinstance(start, bool)
                    or not isinstance(start, (int, float))
                    or not math.isfinite(start)
                    or start < 0
                ):
                    raise ValueError("Invalid source_start")
            elif t["clip_view"] == "arrangement":
                if (
                    data["arrangement_start"] > role_start + 1e-5
                    or data["arrangement_end"] < role_start + beats - 1e-5
                ):
                    raise ValueError(
                        role
                        + " clip does not cover the section; select a covering clip or explicit source_start"
                    )
                start = data["start_marker"] + (role_start - data["arrangement_start"]) * (
                    1 if data["warping"] else 60 / plan["grid"]["tempo"]
                )
            else:
                start = data["start_marker"]
            offset = spec.get("source_offset_seconds", 0)
            if (
                isinstance(offset, bool)
                or not isinstance(offset, (int, float))
                or not math.isfinite(offset)
                or abs(offset) > 2
            ):
                raise ValueError(
                    "source_offset_seconds must be a measured offset within +/-2 seconds"
                )
            if offset:
                if data["warping"]:
                    data["warp_markers"] = [
                        dict(m, sample_time=m["sample_time"] + offset) for m in data["warp_markers"]
                    ]
                else:
                    start += offset
            props = send("read_access_object", dict(t, object_type="clip"))["properties"]
            bound[role] = dict(
                target=t,
                timing=data,
                source_start=start,
                clip_gain=props.get("gain", 0.4),
                file=file_identity(data["file_path"]),
                native_timing=native_timing,
                timing_reference=reference,
            )
            config["source_roles"][role if role != "riff" else "riff"] = (
                track["name"] + " / " + t["expected_clip_name"]
            )
    plan = plan_halftime_remix(config)
    if plan["status"] != "planned":
        raise ValueError("Source MIDI does not cover the drop; supply notes or root overrides")
    if config.get("source_mode", "hybrid") in ["hybrid", "audio_pulse"] and "riff" not in bound:
        raise ValueError("Audio/hybrid mode requires a bound riff audio clip")
    if config.get("vocal_mode", "continuous") != "none" and "vocal" not in bound:
        raise ValueError("Select a vocal clip or choose vocal_mode=none")
    return plan, bound


def prepare(send, config, sources, project_dir, infer_vocals=True, refresh_pulses=False):
    root, manifest = project(project_dir, create=True)
    with _mutation_lock, project_lock(root):
        if refresh_pulses:
            owned = manifest.get("tracks", {}).get("control")
            if not owned:
                raise ValueError("Build the control MIDI lane before refreshing its notes")
            info = send("get_track_info", dict(track_index=owned["index"]))
            if info["name"] != owned["name"]:
                raise ValueError("Control track moved or renamed")
            ns = send(
                "get_access_notes",
                dict(
                    track_index=owned["index"],
                    clip_index=0,
                    clip_view="session",
                    expected_track_name=owned["name"],
                    expected_clip_name="RMX | Pulse Input",
                ),
            )["notes"]
            config = deepcopy(config)
            config["custom_pulses"] = [
                dict(time=n["start_time"], duration=n["duration"]) for n in ns if not n["mute"]
            ]
        plan, bound = bind_sources(send, config, sources)
        seconds = (
            (plan["config"]["drop_bars"] + plan["config"]["lead_in_bars"])
            * 4
            * 60
            / plan["grid"]["tempo"]
        )
        if seconds > 120:
            raise ValueError("Build a short section <=120 seconds before expanding")
        rendered = worker("render", root, plan=plan, bindings=bound, infer_vocals=infer_vocals)
        # Re-read actual sources after DSP, not just the old preview/config hash.
        _, fresh = bind_sources(send, plan["config"], sources)
        if digest(fresh) != digest(bound):
            raise ValueError("Sources changed during preparation; discard this preview")
        old = manifest.get("prepared")
        if old:
            manifest.setdefault("history", []).append(
                dict(fingerprint=old["plan"]["fingerprint"], assets=old["assets"])
            )
        manifest["history"] = manifest.get("history", [])[-20:]
        manifest["prepared"] = dict(**rendered, bindings=bound, sources=deepcopy(sources))
        manifest["state"] = "prepared"
        save_project(root, manifest)
        atomic_json(root / "plan.json", rendered["plan"])
    return dict(
        project_dir=str(root),
        state="prepared",
        fingerprint=rendered["plan"]["fingerprint"],
        rendered={
            k: dict(path=v["path"], cached=v["cached"]) for k, v in rendered["assets"].items()
        },
        root_reviews=[
            r["bar"] for r in rendered["plan"]["root_decisions"] if r["needs_root_review"]
        ],
        live_changes=False,
    )


def verify_sources(send, prepared):
    _, current = bind_sources(send, prepared["plan"]["config"], prepared["sources"])
    if digest(current) != digest(prepared["bindings"]):
        raise ValueError("Stale sources: prepare again before building")
    for asset in prepared["assets"].values():
        if file_identity(asset["path"])["sha256"] != asset["file"]["sha256"]:
            raise ValueError("Prepared audio was changed externally")


def _track(send, owned):
    t = send("get_track_info", dict(track_index=owned["index"]))
    if t["name"] != owned["name"]:
        raise ValueError("Owned track moved/renamed; refuse stale track indices")
    return t


def _resolve(send, name, category):
    result = send("search_browser", dict(query=name, category=category, max_results=50))
    items = result.get("matches", result.get("results", result.get("items", [])))
    matches = [
        i
        for i in items
        if i.get("is_loadable", True)
        and i["name"].removesuffix(".adg").removesuffix(".adv") == name
    ]
    if len(matches) != 1:
        raise ValueError("Missing/ambiguous native device or kit: " + name)
    return matches[0]["uri"]


def _device_matches(device, name):
    classes = {
        "Operator": {"Operator"},
        "Saturator": {"Saturator"},
        "Auto Filter": {"AutoFilter", "AutoFilter2"},
        "EQ Eight": {"Eq8"},
        "Utility": {"StereoGain"},
    }
    return device["name"].removesuffix(".adg") == name or device.get("class_name") in classes.get(
        name, set()
    )


def _restore_arms(send, manifest):
    errors = []
    rows = manifest.get("original_arms", [])
    observed = read_many(
        send, [command("get_track_info", track_index=row["index"]) for row in rows]
    )
    changes = []
    for row, (info, error) in zip(rows, observed):
        if error or info["name"] != row["name"]:
            errors.append("Original track identity unavailable during arm restoration")
        elif info["arm"] != row["arm"]:
            changes.append(command("set_track_arm", track_index=row["index"], arm=row["arm"]))
    if changes:
        try:
            batch(send, changes)
        except Exception as error:
            errors.append(str(error))
        observed = read_many(
            send, [command("get_track_info", track_index=row["index"]) for row in rows]
        )
    for row, (info, error) in zip(rows, observed):
        if error or info["name"] != row["name"] or info["arm"] != row["arm"]:
            errors.append("Original arm state failed final readback")
    return errors


def _parameters(send, owned, dindex, values):
    p = send(
        "get_sound_design_parameters",
        dict(track_index=owned["index"], device_path=[dindex], expected_track_name=owned["name"]),
    )
    names = {v["name"] for v in p["parameters"]}
    if values.keys() - names:
        raise ValueError("Native device lacks required controls: " + str(values.keys() - names))
    send(
        "set_sound_design_parameters",
        dict(
            track_index=owned["index"],
            device_path=[dindex],
            expected_track_name=owned["name"],
            expected_device_name=p["device_name"],
            parameters=values,
        ),
    )
    return p


def _clip_target(owned, index, name, view="session", start=None):
    t = dict(
        track_index=owned["index"],
        clip_index=index,
        clip_view=view,
        expected_track_name=owned["name"],
        expected_clip_name=name,
    )
    if view == "arrangement":
        t["expected_start_time"] = start
    return t


def _envelope(send, owned, slot, name, dindex, pindex, points):
    args = dict(
        track_index=owned["index"],
        clip_index=slot,
        device_index=dindex,
        parameter_index=pindex,
        expected_track_name=owned["name"],
        expected_clip_name=name,
        target="device",
    )
    existing = send("get_clip_envelope", dict(args, times=[0]))
    send(
        "write_clip_envelope",
        dict(
            args, points=points, interpolation="hold", resolution=1 / 96, replace=existing["exists"]
        ),
    )


def _calibrate_db(send, owned, dindex, parameter, targets):
    import re

    info = send(
        "get_sound_design_parameters",
        dict(track_index=owned["index"], device_path=[dindex], expected_track_name=owned["name"]),
    )
    p = next(v for v in info["parameters"] if v["name"] == parameter)
    if p.get("is_quantized"):
        raise ValueError("Gain calibration requires a continuous native parameter")
    low, high = p["min"], p["max"]
    probes = [low + (high - low) * i / 64 for i in range(65)]

    def sample(values):
        rows = batch(
            send,
            [
                command(
                    "set_device_parameter",
                    track_index=owned["index"],
                    device_index=dindex,
                    parameter=parameter,
                    value=float(v),
                )
                for v in values
            ],
        )
        found = []
        for row in rows:
            text = row.get("display", "")
            if (
                "inf" in text.lower()
                or "ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã¢â‚¬Â¹ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾" in text
            ):
                continue
            match = re.fullmatch(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*dB\s*", text, re.I)
            if not match:
                raise ValueError("Native parameter does not expose dB readback")
            found.append((float(row["value"]), float(match.group(1))))
        return found

    observed = sample(probes)
    outputs = {}
    tolerance = 0.6 if parameter == "Volume" else 0.15
    for _ in range(8):
        observed = sorted(dict(observed).items())
        if any(y < x for (_, x), (_, y) in zip(observed, observed[1:])):
            raise ValueError("Non-monotonic native dB mapping")
        pending = []
        for db in targets:
            nearest = min(observed, key=lambda item: abs(item[1] - db))
            if abs(nearest[1] - db) <= tolerance:
                outputs[db] = nearest[0]
                continue
            lower = [item for item in observed if item[1] < db]
            upper = [item for item in observed if item[1] > db]
            if not lower or not upper:
                raise ValueError("Requested dB value outside observed finite range")
            left, right = lower[-1], upper[0]
            pending.append((left[0] + right[0]) / 2)
        if not pending:
            return p["index"], [outputs[db] for db in targets]
        observed.extend(sample(sorted(set(pending))))
    raise ValueError("Native dB mapping could not be calibrated reliably")


def _set_display(send, owned, dindex, parameter, value):
    info = send(
        "get_sound_design_parameters",
        dict(track_index=owned["index"], device_path=[dindex], expected_track_name=owned["name"]),
    )
    p = next(v for v in info["parameters"] if v["name"] == parameter)
    if (
        isinstance(value, str)
        and value.endswith(" dB")
        and any(
            x in str(p.get("display_min", "")).lower()
            for x in ["inf", "ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã¢â‚¬Â¹ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾"]
        )
    ):
        _, values = _calibrate_db(send, owned, dindex, parameter, [float(value.split()[0])])
        value = values[0]
    return send(
        "set_device_parameter",
        dict(track_index=owned["index"], device_index=dindex, parameter=parameter, value=value),
    )


def _gain_map(send, owned, dindex, depth=24):
    # Numeric probes bypass the upstream display converter's unsupported -inf endpoint.
    result = _calibrate_db(send, owned, dindex, "Gain", list(range(-depth, 1)))
    send(
        "set_device_parameter",
        dict(
            track_index=owned["index"], device_index=dindex, parameter="Gain", value=result[1][-1]
        ),
    )
    return result


def _native_gain(db, mapping):
    x = max(0, min(len(mapping) - 1, db + len(mapping) - 1))
    i = int(x)
    j = min(i + 1, len(mapping) - 1)
    return mapping[i] + (mapping[j] - mapping[i]) * (x - i)


def _gain_points(plan, first, length, mapping, role):
    from .remix_audio import gain_curve

    # Envelope samples use a native device's gain curve; audio rendering itself is sample-continuous.
    tempo = plan["grid"]["tempo"]
    rate = 2240
    count = round(plan["config"]["drop_bars"] * 4 * 60 / tempo * rate)
    if role == "midbass":
        curve = gain_curve(plan, rate, count, "riff")
    else:
        from array import array

        curve = array("f", [1]) * count
        for e in plan["movement"]["kick_ducks"]:
            a = round(e["time"] * 60 / tempo * rate)
            n = max(1, round(e["release_ms"] * rate / 1000))
            low = 10 ** (-e["depth_db"] / 20)
            for i in range(a, min(count, a + n)):
                g = low + (1 - low) * math.sin((i - a) / n * math.pi / 2) ** 2
                curve[i] = min(curve[i], g)
    points = []
    for i in range(math.ceil(length * 96)):
        beat = i / 96
        index = min(count - 1, round((first + beat) * 60 / tempo * rate))
        g = max(1e-8, curve[index])
        points.append(dict(time=beat, value=_native_gain(20 * math.log10(g), mapping)))
    return points


def _verify_owned_content(send, manifest, allow_control_edits=True):
    owned_rows = list(manifest.get("tracks", {}).items())
    commands = []
    for role, owned in owned_rows:
        commands += [
            command("get_track_info", track_index=owned["index"]),
            command("get_arrangement_clips", track_index=owned["index"]),
        ]
    observed = read_many(send, commands)
    if any(error for _, error in observed):
        raise ValueError("Owned track reads failed")
    note_reads = []
    accepted_hashes = []
    for k, (role, owned) in enumerate(owned_rows):
        t = observed[k * 2][0]
        clips = observed[k * 2 + 1][0]["clips"]
        if t["name"] != owned["name"]:
            raise ValueError("Owned track moved/renamed; refresh identities")
        if owned.get("devices") is not None and [
            (d["name"], d.get("class_name")) for d in t["devices"]
        ] != [tuple(d) for d in owned["devices"]]:
            raise ValueError("Owned device chain changed; rebind rather than overwrite it")
        pending = owned.get("pending_content")
        allowed = [tuple(c) for c in (pending["clips"] if pending else owned.get("clips", []))]
        actual = [(c["name"], round(c["start_time"], 5), round(c["end_time"], 5)) for c in clips]
        if actual != allowed[: len(actual)] or (not pending and len(actual) != len(allowed)):
            raise ValueError("Owned Arrangement changed; refuse to overwrite edits")
        if t["is_midi_track"]:
            for i, clip in enumerate(clips):
                old = owned.get("note_hashes", [])
                accepted = {old[i]} if i < len(old) else set()
                if pending and i < len(pending["note_hashes"]):
                    accepted.add(pending["note_hashes"][i])
                note_reads.append(
                    command(
                        "get_access_notes",
                        **_clip_target(owned, i, clip["name"], "arrangement", clip["start_time"]),
                    )
                )
                accepted_hashes.append(accepted)
        if role == "control" and not allow_control_edits:
            raise ValueError("Unexpected control edit policy")
    for (result, error), accepted in zip(read_many(send, note_reads), accepted_hashes):
        if error or note_hash(result["notes"]) not in accepted:
            raise ValueError(
                "Owned MIDI was edited; copy edits to the bound source before rebuilding"
            )


def build(send, project_dir, drum_kit="808 Core Kit", drum_map=None):
    root, manifest = project(project_dir)
    with _mutation_lock, project_lock(root):
        prepared = manifest.get("prepared")
        if not prepared:
            raise ValueError("Prepare sources before building")
        session = send("get_session_info", {})
        if session["is_playing"] or session.get("record_mode"):
            raise ValueError("Stop playback/recording before building")
        plan = prepared["plan"]
        tempo = plan["grid"]["tempo"]
        if abs(session["tempo"] - tempo) > 0.001 or [
            session["signature_numerator"],
            session["signature_denominator"],
        ] != [4, 4]:
            raise ValueError(
                "Set tempo/meter does not match the prepared plan; no global tempo changes are automatic"
            )
        region = [
            plan["grid"]["drop_start_beat"],
            plan["grid"]["drop_end_beat"],
            plan["config"]["lead_in_bars"],
        ]
        if manifest.get("built_region") and manifest["built_region"] != region:
            raise ValueError("Use a new remix project when changing section boundaries")
        if math.ceil(plan["config"]["drop_bars"] / 4) > session["scene_count"]:
            raise ValueError("Add enough Session scenes before building this section")
        verify_sources(send, prepared)
        _verify_owned_content(send, manifest)
        specs = {
            "midbass": get_recipe("dubstep_wobble")["chain"],
            "sub": get_recipe("clean_sub")["chain"],
        }
        # Dedicated Utility controls own gain automation without changing source levels.
        for role in specs:
            if specs[role][-1]["name"] != "Utility":
                specs[role].append(dict(name="Utility", category="audio_effects", parameters={}))
        needed = {
            (d["name"], d["category"])
            for role, chain in specs.items()
            if not manifest["tracks"].get(role, {}).get("devices_ready")
            for d in chain
        }
        if not manifest["tracks"].get("drums", {}).get("devices_ready"):
            needed.add((drum_kit, "drums"))
        uris = {(name, category): _resolve(send, name, category) for name, category in needed}
        roles = ["midbass", "sub", "drums", "control"] + list(prepared["assets"])
        if plan["config"]["source_mode"] == "audio_pulse":
            roles.remove("midbass")
        if plan["config"]["source_mode"] == "midi_rebuild" and "riff" in roles:
            roles.remove("riff")
        if manifest.get("pending_create"):
            raise RuntimeError(
                "Uncertain earlier track creation; inspect pending_create before retrying"
            )
        owned_indices = {t["index"] for t in manifest["tracks"].values()}
        rows = read_many(
            send,
            [
                command("get_track_info", track_index=i)
                for i in range(session["track_count"])
                if i not in owned_indices
            ],
        )
        if any(error for _, error in rows):
            raise ValueError("Cannot snapshot original arm state")
        manifest["original_arms"] = [
            {k: row[k] for k in ["index", "name", "arm"]} for row, _ in rows
        ]
        manifest.pop("last_error", None)
        manifest["state"] = "building"
        save_project(root, manifest)
        try:
            for role in roles:
                owned = manifest["tracks"].get(role)
                if owned is None:
                    before = send("get_session_info", {})["track_count"]
                    name = f"RMX {manifest['project_id'][:8]} | {role.upper()}"
                    manifest["pending_create"] = dict(index=before, name=name, role=role)
                    save_project(root, manifest)
                    created = send(
                        "create_midi_track"
                        if role in ["midbass", "sub", "drums", "control"]
                        else "create_audio_track",
                        dict(index=-1),
                    )
                    index = created.get("index", created.get("track_count", before + 1) - 1)
                    fresh = send("get_track_info", dict(track_index=index))
                    if any(s["has_clip"] for s in fresh["clip_slots"]) or fresh["devices"]:
                        raise RuntimeError(
                            "New-track readback is not empty; inspect pending_create"
                        )
                    send("set_track_name", dict(track_index=index, name=name))
                    owned = dict(index=index, name=name, clips=[], note_hashes=[])
                    manifest["tracks"][role] = owned
                    manifest.pop("pending_create")
                    save_project(root, manifest)
                    _track(send, owned)
                    send("set_track_arm", dict(track_index=index, arm=False))
                    send("set_track_mute", dict(track_index=index, mute=True))
                    send("set_track_volume", dict(track_index=index, volume=0.75))
                fresh = _track(send, owned)
                chain = specs.get(role, [])
                if role == "drums":
                    chain = [dict(name=drum_kit, category="drums", parameters={})]
                if role in prepared["assets"] and role in ["riff", "vocal", "fx"]:
                    chain = [dict(name="Auto Filter", category="audio_effects", parameters={})]
                    if ("Auto Filter", "audio_effects") not in uris:
                        uris[("Auto Filter", "audio_effects")] = _resolve(
                            send, "Auto Filter", "audio_effects"
                        )
                if fresh["arm"]:
                    send("set_track_arm", dict(track_index=owned["index"], arm=False))
                if not owned.get("devices_ready"):
                    if len(fresh["devices"]) > len(chain):
                        raise ValueError("Unexpected partial device chain")
                    for dindex, spec in enumerate(chain):
                        fresh = _track(send, owned)
                        if len(fresh["devices"]) == dindex:
                            send(
                                "load_browser_item",
                                dict(
                                    track_index=owned["index"],
                                    item_uri=uris[(spec["name"], spec["category"])],
                                ),
                            )
                        loaded = _track(send, owned)
                        if len(loaded["devices"]) <= dindex or not _device_matches(
                            loaded["devices"][dindex], spec["name"]
                        ):
                            raise ValueError(
                                "Loaded device readback differs from the resolved device"
                            )
                        if spec["parameters"]:
                            _parameters(send, owned, dindex, spec["parameters"])
                    if role in ["midbass", "sub"]:
                        _parameters(
                            send,
                            owned,
                            0,
                            {"Ae Attack": 0.3, "Ae Sustain": 1, "Ae Release": 0.35557},
                        )
                        _set_display(
                            send, owned, 0, "Volume", "-15 dB" if role == "sub" else "-18 dB"
                        )
                    if role in ["riff", "vocal", "fx"]:
                        send(
                            "get_sound_design_parameters",
                            dict(
                                track_index=owned["index"],
                                device_path=[0],
                                expected_track_name=owned["name"],
                            ),
                        )
                        for parameter, value in [
                            ("Type", "High-pass"),
                            ("Frequency", f"{95 if role == 'vocal' else 120} Hz"),
                        ]:
                            send(
                                "set_device_parameter",
                                dict(
                                    track_index=owned["index"],
                                    device_index=0,
                                    parameter=parameter,
                                    value=value,
                                ),
                            )
                    owned["devices_ready"] = True
                    owned["devices"] = [
                        (d["name"], d.get("class_name")) for d in _track(send, owned)["devices"]
                    ]
                    save_project(root, manifest)
            # Map the selected rack's real occupied pads rather than assuming GM.
            drum = manifest["tracks"]["drums"]
            pads = send("get_drum_pads", dict(track_index=drum["index"], device_index=0))
            pads = pads.get("pads", pads.get("drum_pads", []))
            occupied = {p.get("note", p.get("midi_note")): p for p in pads}
            if drum_map is None:
                import re

                drum_map = {}
                for role, pattern in [
                    ("kick", r"kick|bass.?drum"),
                    ("snare", r"snare"),
                    ("hat", r"closed.*(hat|hh)|(hat|hh).*closed"),
                ]:
                    found = [n for n, p in occupied.items() if re.search(pattern, p["name"], re.I)]
                    if len(found) != 1:
                        raise ValueError("Choose an explicit kit pad map for " + role)
                    drum_map[role] = found[0]
            if set(drum_map) != {"kick", "snare", "hat"} or any(
                type(n) is not int or n not in occupied for n in drum_map.values()
            ):
                raise ValueError("drum_map must select occupied kick/snare/hat MIDI pads")
            length = plan["config"]["drop_bars"] * 4
            start = plan["grid"]["drop_start_beat"]
            for role in roles:
                owned = manifest["tracks"][role]
                _track(send, owned)
                if role in prepared["assets"]:
                    content_key = digest(dict(asset=prepared["assets"][role]["file"]["sha256"]))
                else:
                    content_key = digest(
                        dict(
                            role=role,
                            notes=plan["midi"].get("riff" if role == "midbass" else role),
                            movement=plan["movement"]
                            if role in ["midbass", "sub", "control"]
                            else None,
                            phrases=plan["arrangement"]["phrases"] if role == "midbass" else None,
                            drum_map=drum_map if role == "drums" else None,
                        )
                    )
                if owned.get("content_key") == content_key:
                    continue
                if role in ["midbass", "sub", "drums", "control"]:
                    notes = deepcopy(plan["midi"].get("riff" if role == "midbass" else role, []))
                    if role == "drums":
                        mapping = {36: drum_map["kick"], 38: drum_map["snare"], 42: drum_map["hat"]}
                        for n in notes:
                            n["pitch"] = mapping[n["pitch"]]
                    if role == "control":
                        notes = [
                            dict(
                                pitch=60,
                                start_time=p["time"],
                                duration=p["duration"],
                                velocity=100,
                                mute=False,
                            )
                            for p in plan["movement"]["pulses"]
                        ]
                    if role == "control":
                        chunks = [(0, length)]
                    else:
                        chunks = [(b, min(16, length - b)) for b in range(0, length, 16)]
                    if len(chunks) > len(_track(send, owned)["clip_slots"]):
                        raise ValueError("Add enough empty Session scenes for this section")
                    proposed = []
                    proposed_hashes = []
                    for k, (first, size) in enumerate(chunks):
                        if role == "control":
                            continue
                        label = f"RMX | {role} | {k + 1}"
                        proposed.append(
                            (label, round(start + first, 5), round(start + first + size, 5))
                        )
                        part = [
                            dict(
                                n,
                                start_time=max(first, n["start_time"]) - first,
                                duration=min(first + size, n["start_time"] + n["duration"])
                                - max(first, n["start_time"]),
                            )
                            for n in notes
                            if min(first + size, n["start_time"] + n["duration"])
                            > max(first, n["start_time"])
                        ]
                        proposed_hashes.append(note_hash(part))
                    owned["pending_content"] = dict(clips=proposed, note_hashes=proposed_hashes)
                    save_project(root, manifest)
                    gain_index = mapping = None
                    if role in ["midbass", "sub"]:
                        if "gain_map" not in owned:
                            gain_index, mapping = _gain_map(send, owned, len(specs[role]) - 1)
                            owned["gain_map"] = [gain_index, mapping]
                            save_project(root, manifest)
                        gain_index, mapping = owned["gain_map"]
                    if role == "midbass":
                        _parameters(
                            send,
                            owned,
                            2,
                            {
                                "LFO Wave": 0,
                                "LFO T Mode": 5,
                                "LFO 16th": 4 * plan["movement"]["settings"]["wobble_beats"],
                            },
                        )
                        _track(send, owned)
                        send(
                            "set_device_parameter",
                            dict(
                                track_index=owned["index"],
                                device_index=2,
                                parameter="Frequency",
                                value=f"{math.sqrt(plan['movement']['settings']['filter_low_hz'] * plan['movement']['settings']['filter_high_hz'])} Hz",
                            ),
                        )
                        send(
                            "set_device_parameter",
                            dict(
                                track_index=owned["index"],
                                device_index=3,
                                parameter="1 Frequency A",
                                value=f"{plan['movement']['settings']['mid_highpass_hz']} Hz",
                            ),
                        )
                    observed = []
                    hashes = []
                    for k, (first, size) in enumerate(chunks):
                        name = (
                            "RMX | Pulse Input" if role == "control" else f"RMX | {role} | {k + 1}"
                        )
                        slot = k
                        fresh = _track(send, owned)["clip_slots"][slot]
                        ns = []
                        for n in notes:
                            a = max(first, n["start_time"])
                            b = min(first + size, n["start_time"] + n["duration"])
                            if b > a:
                                ns.append(dict(n, start_time=a - first, duration=b - a))
                        if fresh["has_clip"]:
                            if fresh["clip"]["name"] != name:
                                raise ValueError("Owned Session slot contains a foreign clip")
                        else:
                            send(
                                "create_clip",
                                dict(track_index=owned["index"], clip_index=slot, length=size),
                            )
                        send(
                            "set_clip_name",
                            dict(track_index=owned["index"], clip_index=slot, name=name),
                        )
                        send(
                            "add_notes_to_clip",
                            dict(track_index=owned["index"], clip_index=slot, notes=ns),
                        )
                        send(
                            "write_access_object",
                            dict(
                                _clip_target(owned, slot, name),
                                object_type="clip",
                                properties={"looping": False},
                            ),
                        )
                        actual = send("get_access_notes", _clip_target(owned, slot, name))["notes"]
                        if note_hash(actual) != note_hash(ns):
                            raise RuntimeError("New MIDI content failed readback")
                        if gain_index is not None:
                            _envelope(
                                send,
                                owned,
                                slot,
                                name,
                                len(specs[role]) - 1,
                                gain_index,
                                _gain_points(plan, first, size, mapping, role),
                            )
                        if role == "midbass":
                            p = send(
                                "get_sound_design_parameters",
                                dict(
                                    track_index=owned["index"],
                                    device_path=[2],
                                    expected_track_name=owned["name"],
                                ),
                            )
                            byname = {v["name"]: v for v in p["parameters"]}
                            # Native sine LFO provides smooth modulation between phrase changes.
                            points = []
                            for phrase in plan["arrangement"]["phrases"]:
                                a = max(first, phrase["start"])
                                b = min(first + size, phrase["end"])
                                if b > a:
                                    points.append(
                                        dict(
                                            time=a - first,
                                            value={
                                                "smooth": 0.3,
                                                "wobble": 0.5,
                                                "growl": 0.65,
                                                "riff": 0.2,
                                            }[phrase["bass"]],
                                        )
                                    )
                            _envelope(
                                send, owned, slot, name, 2, byname["LFO Amount"]["index"], points
                            )
                        if role != "control":
                            send(
                                "duplicate_session_clip_to_arrangement",
                                dict(
                                    track_index=owned["index"],
                                    clip_index=slot,
                                    destination_time=start + first,
                                ),
                            )
                            observed.append(
                                (name, round(start + first, 5), round(start + first + size, 5))
                            )
                            hashes.append(note_hash(ns))
                    owned["clips"] = observed
                    owned["note_hashes"] = hashes
                else:
                    asset = prepared["assets"][role]
                    name = "RMX | " + role
                    fresh = _track(send, owned)["clip_slots"][0]
                    if fresh["has_clip"]:
                        if fresh["clip"]["name"] != name:
                            raise ValueError("Owned audio Session slot contains a foreign clip")
                        send("delete_clip", dict(track_index=owned["index"], clip_index=0))
                    send(
                        "create_audio_clip",
                        dict(track_index=owned["index"], clip_index=0, path=asset["path"]),
                    )
                    send("set_clip_name", dict(track_index=owned["index"], clip_index=0, name=name))
                    send(
                        "read_access_object", dict(_clip_target(owned, 0, name), object_type="clip")
                    )
                    send(
                        "write_access_object",
                        dict(
                            _clip_target(owned, 0, name),
                            object_type="clip",
                            properties={"warping": False, "looping": False},
                        ),
                    )
                    destination = (
                        start - plan["config"]["lead_in_bars"] * 4
                        if role == "rock_context"
                        else start
                    )
                    send(
                        "duplicate_session_clip_to_arrangement",
                        dict(
                            track_index=owned["index"], clip_index=0, destination_time=destination
                        ),
                    )
                    end = destination + asset["frames"] / asset["sample_rate"] * tempo / 60
                    owned["clips"] = [(name, round(destination, 5), round(end, 5))]
                    owned["note_hashes"] = []
                actual = send("get_arrangement_clips", dict(track_index=owned["index"]))["clips"]
                observed = [
                    (c["name"], round(c["start_time"], 5), round(c["end_time"], 5)) for c in actual
                ]
                if observed != [tuple(c) for c in owned["clips"]]:
                    raise RuntimeError("Arrangement bounds failed readback")
                owned["content_key"] = content_key
                save_project(root, manifest)
                owned.pop("pending_content", None)
                save_project(root, manifest)
            for role, owned in manifest["tracks"].items():
                if role not in roles:
                    _track(send, owned)
                    send("set_track_mute", dict(track_index=owned["index"], mute=True))
            manifest["state"] = "built"
            manifest["built_region"] = region
            manifest["active_roles"] = roles
            manifest["built_fingerprint"] = plan["fingerprint"]
            save_project(root, manifest)
            return dict(
                project_dir=str(root),
                state="built",
                tracks=manifest["tracks"],
                muted_on_creation=True,
                original_sources_preserved=True,
                evidence="Live command readback; musical audition still required",
            )
        except Exception as error:
            manifest["state"] = "partial"
            manifest["last_error"] = str(error)
            save_project(root, manifest)
            raise RuntimeError(
                "Partial build journal saved; inspect before resuming: " + str(error)
            ) from error
        finally:
            errors = _restore_arms(send, manifest)
            manifest["arm_restore_errors"] = errors
            if errors:
                manifest["state"] = "needs_recovery"
            save_project(root, manifest)
            if errors:
                raise RuntimeError("Original arm state needs recovery: " + str(errors))


def inspect_project(send, project_dir):
    root, manifest = project(project_dir)
    observations = []
    for role, owned in manifest.get("tracks", {}).items():
        try:
            info = _track(send, owned)
            clips = send("get_arrangement_clips", dict(track_index=owned["index"]))["clips"]
            observations.append(
                dict(
                    role=role,
                    index=owned["index"],
                    name=info["name"],
                    clip_count=len(clips),
                    identity_matches=True,
                )
            )
        except Exception as error:
            observations.append(dict(role=role, identity_matches=False, error=str(error)))
    source_error = None
    if manifest.get("prepared"):
        try:
            verify_sources(send, manifest["prepared"])
        except Exception as error:
            source_error = str(error)
    return dict(
        project_dir=str(root),
        state=manifest["state"],
        tracks=observations,
        pending_create=manifest.get("pending_create"),
        last_error=manifest.get("last_error"),
        sources_current=source_error is None,
        source_error=source_error,
        live_changes=False,
        recovery="Never replay uncertain creates. Inspect pending track identity; preserve originals and recover from the private journal.",
    )
