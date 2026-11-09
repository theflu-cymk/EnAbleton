"""Apply the audio repairs a bounded PCM scan can support.

The scan reads the first 30 seconds of each Arrangement clip's source file.
Timestamps are source-file seconds, not Arrangement time, and warped playback
is not checked. Full-scale samples can lower clip gain by one modest step when
that gain is still at unity. DC offset can enable Utility's DC switch when this
Live build exposes exactly one of those parameters. Repeated level jumps load
one Compressor, with ratio, attack, release and threshold taken from the
measurement. Sparse jumps, dense clicks and silence gaps stay reported. A
limiter is not added, and clip fades are not written. Notes, Warp and track
faders stay.
"""

import math
import re
import time

from .align_safety import is_protected
from .assign_instruments import resolve_browser_item
from .audio_scan import scan_pcm

POLL_ATTEMPTS = 12
POLL_SECONDS = 0.15
SCAN_SECONDS = 30
# Live's Clip.gain at 0 dB is 0.4 on current Suite builds. The value is not dB.
UNITY_GAIN = 0.4
UNITY_TOLERANCE = 0.02
GAIN_STEP = 0.85
GAIN_FLOOR = 0.15
DC_NAMES = ("DC", "DC Filter", "Dc")
MIN_LEVEL_JUMPS = 3
ATTACK_MS_MIN = 0.01
ATTACK_MS_MAX = 1000.0
# Release samples measured on Live 12.2 Compressor2. The attack control is a pure
# log; release and the low end of Threshold are not, so they use this table.
RELEASE_CURVE = (
    (0.0, 1.0),
    (0.125, 19.2),
    (0.25, 82.6),
    (0.375, 220.0),
    (0.5, 459.0),
    (0.625, 828.0),
    (0.75, 1360.0),
    (0.875, 2070.0),
    (1.0, 3000.0),
)
# Above -14 dB the Threshold knob is 40 dB per native unit, ending at +6 dB.
THRESHOLD_CURVE = (
    (0.125, -44.6),
    (0.25, -28.8),
    (0.375, -19.2),
    (0.5, -14.0),
    (0.625, -9.0),
    (0.75, -4.0),
    (0.875, 1.0),
    (1.0, 6.0),
)
REPORTS = {
    "level_jump": (
        "Only a few level jumps were measured, so no compressor was added. "
        "They can be a musical change."
    ),
    "discontinuity": (
        "Click or seam stays reported. Clip properties cannot write a fade, and "
        "spectral repair is not available."
    ),
    "silence_gap": (
        "Silence stays reported. It can be a rest, and missing audio was not replaced."
    ),
}
DENSE_CLICKS = (
    "These sharp edges are dense, which fits percussion or a bright waveform. "
    "Clip properties cannot write a fade, and spectral repair is not available."
)
WINDOW_NOTE = (
    "The scan is the first 30 seconds of the source file, or less when the file "
    "is shorter. Timestamps are source-file seconds. Warped playback was not "
    "checked, and a longer file was not measured past that window."
)


def gain_decision(current):
    """One gain step from unity, or a report when the clip is already away from it."""

    if isinstance(current, bool) or not isinstance(current, (int, float)):
        raise ValueError("clip gain is missing")
    current = float(current)
    if not 0 <= current <= 1:
        raise ValueError("clip gain is outside 0..1")
    if current <= GAIN_FLOOR:
        return {
            "write": False,
            "status": "ready",
            "reason": "Clip gain is already very low. It was left unchanged.",
        }
    if abs(current - UNITY_GAIN) > UNITY_TOLERANCE:
        if current < UNITY_GAIN:
            reason = "Clip gain is already below unity. It was left unchanged."
        else:
            reason = "Clip gain is above unity and was left unchanged."
        return {
            "write": False,
            "status": "ready" if current < UNITY_GAIN else "review",
            "reason": reason + " Samples that already hit full scale are not restored.",
        }
    target = round(max(GAIN_FLOOR, current * GAIN_STEP), 6)
    return {
        "write": True,
        "status": "lower_gain",
        "gain": target,
        "reason": (
            "Lowered clip gain because samples hit full scale. "
            "This does not restore flattened peaks."
        ),
    }


def dc_decision(parameters):
    """Enable a DC switch only when one allowlisted parameter is unambiguous."""

    matches = [item for item in parameters or [] if item.get("name") in DC_NAMES]
    if len(matches) != 1:
        return {
            "write": False,
            "status": "unavailable",
            "reason": "This Live build does not expose one DC parameter. No DC value was changed.",
        }
    param = matches[0]
    if int(param.get("automation_state") or 0) != 0:
        return {
            "write": False,
            "status": "unavailable",
            "reason": "The DC parameter is automated. No DC value was changed.",
        }
    if not param.get("is_quantized"):
        return {
            "write": False,
            "status": "unavailable",
            "reason": "The DC parameter is not a switch on this Live build. No DC value was changed.",
        }
    items = list(param.get("value_items") or [])
    ons = [index for index, item in enumerate(items) if str(item).casefold() == "on"]
    if len(ons) == 1:
        on_value = ons[0]
    elif not items and param.get("min", 0) <= 1 <= param.get("max", 1):
        on_value = 1
    else:
        return {
            "write": False,
            "status": "unavailable",
            "reason": "The DC switch values are ambiguous. No DC value was changed.",
        }
    if param.get("value") == on_value:
        return {"write": False, "status": "ready", "reason": "DC is already on."}
    return {
        "write": True,
        "status": "enable_dc",
        "name": param["name"],
        "value": on_value,
        "reason": "Enabled the DC filter because the source window has DC offset.",
    }


def _curve_native(curve, target):
    """Log-interpolate a measured native curve. The display values must increase."""

    if target <= curve[0][1]:
        return curve[0][0]
    if target >= curve[-1][1]:
        return curve[-1][0]
    for (left_native, left_value), (right_native, right_value) in zip(curve, curve[1:]):
        if left_value <= target <= right_value:
            span = math.log(right_value) - math.log(left_value)
            if span == 0:
                return left_native
            mix = (math.log(target) - math.log(left_value)) / span
            return left_native + (right_native - left_native) * mix
    raise ValueError("display target is outside the measured curve")


def threshold_native(db):
    """Native Threshold on this Live build. -14 dB and above use the linear region."""

    db = float(db)
    if not -36 <= db <= 6:
        raise ValueError("threshold is outside -36..6 dB")
    if db >= -14:
        return (db + 34.0) / 40.0
    points = tuple((native, displayed) for native, displayed in THRESHOLD_CURVE if displayed < 0)
    # dB is negative, so interpolate on the ascending native axis in linear dB.
    for (left_native, left_db), (right_native, right_db) in zip(points, points[1:]):
        if left_db <= db <= right_db:
            mix = (db - left_db) / (right_db - left_db)
            return left_native + (right_native - left_native) * mix
    return points[0][0]


def attack_native(ms):
    ms = float(ms)
    if not ATTACK_MS_MIN <= ms <= ATTACK_MS_MAX:
        raise ValueError("attack is outside 0.01..1000 ms")
    return math.log(ms / ATTACK_MS_MIN) / math.log(ATTACK_MS_MAX / ATTACK_MS_MIN)


def release_native(ms):
    ms = float(ms)
    if not 1 <= ms <= 3000:
        raise ValueError("release is outside 1..3000 ms")
    return _curve_native(RELEASE_CURVE, ms)


def compressor_values(settings):
    """Native Compressor2 values for one gentle level-jump repair."""

    ratio = float(settings["ratio"])
    knee = float(settings["knee_db"])
    if not 1.2 <= ratio <= 4:
        raise ValueError("ratio is outside 1.2..4")
    if not 0 <= knee <= 18:
        raise ValueError("knee is outside 0..18 dB")
    return {
        "Threshold": round(threshold_native(settings["threshold_db"]), 6),
        "Ratio": round(1.0 - 1.0 / ratio, 6),
        "Attack": round(attack_native(settings["attack_ms"]), 6),
        "Release": round(release_native(settings["release_ms"]), 6),
        "Knee": round(knee, 6),
    }


def compressor_settings(scan):
    """Gentle 2:1 settings when the window has repeated level jumps."""

    count = (scan.get("finding_counts") or {}).get("level_jump") or 0
    if count < MIN_LEVEL_JUMPS:
        return None
    levels = []
    for channel in scan.get("channels") or []:
        rms = channel.get("rms_dbfs")
        if isinstance(rms, bool) or not isinstance(rms, (int, float)):
            continue
        levels.append(float(rms))
    if levels:
        rms = max(levels)
        threshold = min(-8.0, max(-24.0, round(rms + 2.0, 1)))
        basis = f"Threshold is 2 dB above the scanned RMS ({rms:.1f} dB), limited to -24..-8 dB."
    else:
        threshold = -18.0
        basis = "RMS was missing, so the threshold starts at -18 dB."
    return {
        "threshold_db": threshold,
        "ratio": 2.0,
        "attack_ms": 20.0,
        "release_ms": 200.0,
        "knee_db": 10.0,
        "jump_count": count,
        "basis": basis,
    }


def parse_display(text):
    """First number in a Live display. Seconds become milliseconds. inf is None."""

    raw = str(text or "").strip()
    if "inf" in raw.casefold():
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", raw)
    if match is None:
        return None
    value = float(match.group(0))
    if re.search(r"\dms\b", raw, re.I):
        return value
    if re.search(r"\ds\b", raw, re.I):
        return value * 1000.0
    return value


def _dynamics(devices):
    found = []
    for device in devices or []:
        if isinstance(device, str):
            if device in {"Compressor", "Glue Compressor"}:
                found.append({"name": device, "index": None, "class_name": ""})
            continue
        if not isinstance(device, dict):
            continue
        name = str(device.get("name") or "")
        class_name = str(device.get("class_name") or "")
        if name in {"Compressor", "Glue Compressor"} or class_name in {
            "Compressor2",
            "GlueCompressor",
        }:
            found.append(device)
    return found


def _utilities(devices):
    found = []
    for device in devices or []:
        if isinstance(device, str):
            if device == "Utility":
                found.append({"name": "Utility", "index": None})
            continue
        if not isinstance(device, dict):
            continue
        if device.get("name") == "Utility" or device.get("class_name") == "StereoGain":
            found.append(device)
    return found


def _window(scan):
    coverage = scan.get("coverage") or {}
    return {
        "start_seconds": coverage.get("start_seconds"),
        "end_seconds": coverage.get("end_seconds"),
        "partial": coverage.get("partial"),
        "timestamps": coverage.get("timestamps")
        or "source-file seconds, not Arrangement or warped playback time",
    }


def _codes(scan):
    counts = scan.get("finding_counts") or {}
    return {code for code, count in counts.items() if count}


def plan_repairs(tracks):
    """Turn completed scans into gain, DC, compressor and report rows. No Live calls."""

    if not isinstance(tracks, list):
        raise ValueError("tracks must be a list")
    actions = []
    reports = []
    skipped = []
    dc_tracks = set()
    compressor_tracks = set()
    for track in tracks:
        name = str(track.get("name") or "")
        index = track.get("index")
        if is_protected(name):
            skipped.append({"index": index, "name": name, "reason": "already an original"})
            continue
        if track.get("is_return") or track.get("is_master") or track.get("is_group"):
            skipped.append({"index": index, "name": name, "reason": "return, main or group"})
            continue
        if track.get("type") not in (None, "audio"):
            skipped.append({"index": index, "name": name, "reason": "not an audio track"})
            continue
        clips = [
            clip
            for clip in track.get("clips") or []
            if clip.get("type") in (None, "audio") and clip.get("view") in (None, "arrangement")
        ]
        if not clips:
            skipped.append({"index": index, "name": name, "reason": "no arrangement audio"})
            continue
        track_dc = False
        jump_sources = []
        pending_reports = []
        for clip in clips:
            label = clip.get("name") or ""
            if clip.get("scan_error"):
                skipped.append(
                    {
                        "index": index,
                        "name": name,
                        "clip": label,
                        "reason": clip["scan_error"],
                    }
                )
                continue
            scan = clip.get("scan")
            if not isinstance(scan, dict):
                skipped.append(
                    {
                        "index": index,
                        "name": name,
                        "clip": label,
                        "reason": "clip was not scanned",
                    }
                )
                continue
            if clip.get("start_beats") is None:
                skipped.append(
                    {
                        "index": index,
                        "name": name,
                        "clip": label,
                        "reason": "arrangement start is missing",
                    }
                )
                continue
            codes = _codes(scan)
            window = _window(scan)
            counts = scan.get("finding_counts") or {}
            if "near_full_scale" in codes:
                actions.append(
                    {
                        "status": "lower_gain",
                        "track_index": index,
                        "track_name": name,
                        "clip_index": clip.get("index", 0),
                        "clip_name": label,
                        "clip_view": clip.get("view") or "arrangement",
                        "start_beats": clip.get("start_beats"),
                        "window": window,
                        "message": (
                            "Lower clip gain because samples hit full scale. "
                            "This does not restore flattened peaks."
                        ),
                    }
                )
            if "dc_offset" in codes:
                track_dc = True
            settings = compressor_settings(scan) if "level_jump" in codes else None
            if settings is not None:
                jump_sources.append((clip, settings, window))
            for code, message in REPORTS.items():
                if code not in codes:
                    continue
                if code == "level_jump" and settings is not None:
                    continue
                count = counts.get(code) or 0
                if code == "discontinuity" and count >= 20:
                    message = DENSE_CLICKS
                first = next(
                    (
                        item.get("start_seconds")
                        for item in scan.get("findings") or []
                        if item.get("code") == code
                    ),
                    None,
                )
                row = {
                    "track_index": index,
                    "track_name": name,
                    "clip_name": label,
                    "code": code,
                    "count": count,
                    "start_seconds": first,
                    "window": window,
                    "message": message,
                }
                pending_reports.append(row)
        if jump_sources and index not in compressor_tracks:
            compressor_tracks.add(index)
            clip, settings, window = max(jump_sources, key=lambda item: item[1]["jump_count"])
            actions.append(
                {
                    "status": "level_compressor",
                    "track_index": index,
                    "track_name": name,
                    "clip_name": clip.get("name") or "",
                    "window": window,
                    "threshold_db": settings["threshold_db"],
                    "ratio": settings["ratio"],
                    "attack_ms": settings["attack_ms"],
                    "release_ms": settings["release_ms"],
                    "knee_db": settings["knee_db"],
                    "jump_count": settings["jump_count"],
                    "message": (
                        "Load one Compressor at 2:1, 20 ms attack, 200 ms release and a "
                        "10 dB knee. "
                        + settings["basis"]
                        + " Makeup stays off, so the track can get quieter. "
                        "This uses the scanned window, not the whole song."
                    ),
                }
            )
            reports.extend(row for row in pending_reports if row["code"] != "level_jump")
        else:
            reports.extend(pending_reports)
        if track_dc and index not in dc_tracks:
            dc_tracks.add(index)
            utilities = _utilities(track.get("devices"))
            actions.append(
                {
                    "status": "dc_filter",
                    "track_index": index,
                    "track_name": name,
                    "utility_count": len(utilities),
                    "message": (
                        "Enable Utility's DC switch when this Live build exposes one "
                        "DC, DC Filter, or Dc parameter."
                    ),
                }
            )
    return {
        "method": "repair-audio",
        "live_changes": False,
        "playback_started": False,
        "window": WINDOW_NOTE,
        "session_clips": "Session clips are not scanned.",
        "writes": [
            "lower clip gain by about 15 percent when samples hit full scale and gain is still at unity",
            "load one Utility and enable its DC switch when the source has DC offset and Live exposes that parameter",
            "load one Compressor when a clip has at least 3 level jumps, and set a gentle 2:1 repair",
        ],
        "leaves_unchanged": [
            "notes",
            "warp",
            "track faders",
            "limiters",
            "fades",
            "existing compressors",
        ],
        "not_fixed": [REPORTS["discontinuity"], REPORTS["silence_gap"], DENSE_CLICKS],
        "actions": actions,
        "reports": reports,
        "skipped": skipped,
    }


def _scan_cached(scan, path, cache):
    if path not in cache:
        try:
            cache[path] = ("ok", scan(path, 0, SCAN_SECONDS))
        except (OSError, RuntimeError, ValueError) as error:
            cache[path] = ("error", str(error))
    return cache[path]


def tracks_from_capture(state, scan=None):
    """Attach a bounded source scan to each Arrangement audio clip."""

    scan = scan or scan_pcm
    cache = {}
    rows = []
    for track in state.get("tracks") or []:
        clips = []
        for clip in track.get("clips") or []:
            if clip.get("protected") or clip.get("view") not in (None, "arrangement"):
                continue
            locator = clip.get("locator") or {}
            row = {
                "name": clip.get("name") or "",
                "view": clip.get("view") or "arrangement",
                "index": locator.get("clip_index", 0),
                "start_beats": clip.get("start_beats"),
                "type": clip.get("type"),
                "audio_path": clip.get("audio_path"),
            }
            if row["type"] == "audio":
                path = row.get("audio_path")
                if not path:
                    row["scan_error"] = "no source file"
                else:
                    kind, payload = _scan_cached(scan, path, cache)
                    if kind == "ok":
                        row["scan"] = payload
                    else:
                        row["scan_error"] = payload
            clips.append(row)
        rows.append(
            {
                "index": track.get("index"),
                "name": track.get("name") or "",
                "type": track.get("type"),
                "is_group": bool(track.get("is_group")),
                "is_return": bool(track.get("is_return")),
                "is_master": bool(track.get("is_master")),
                "devices": track.get("devices") or [],
                "clips": clips,
            }
        )
    return rows


def _require_stopped(send):
    session = send("get_session_info", {})
    if session.get("is_playing") or session.get("record_mode"):
        raise ValueError("Stop playback and recording before repairing audio")


def _index(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(label + " is missing")
    return value


def _clip_target(action):
    return {
        "object_type": "clip",
        "track_index": _index(action.get("track_index"), "track index"),
        "clip_index": _index(action.get("clip_index"), "clip index"),
        "clip_view": action.get("clip_view") or "arrangement",
        "expected_track_name": action.get("track_name"),
        "expected_clip_name": action.get("clip_name") or "",
        "expected_start_time": action.get("start_beats"),
    }


def _load_utility(send, track_index, track_name, before_count, sleeper):
    uri = resolve_browser_item(send, "audio_effects", "Utility")
    if not uri:
        return None
    send("load_browser_item", {"track_index": track_index, "item_uri": uri})
    for _attempt in range(POLL_ATTEMPTS):
        seen = send("get_track_info", {"track_index": track_index})
        if seen.get("name") != track_name:
            raise RuntimeError("Track changed while loading Utility. Inspect it before retrying.")
        devices = seen.get("devices") or []
        if len(devices) == before_count + 1 and devices[-1].get("name") == "Utility":
            return devices[-1]
        sleeper(POLL_SECONDS)
    raise RuntimeError(
        "Utility was not confirmed on "
        + track_name
        + ". Inspect that track before loading it again. Earlier repairs in this "
        "apply may already have changed; each write is its own undo."
    )


def _apply_gain(send, action):
    target = _clip_target(action)
    fresh = send("get_track_info", {"track_index": target["track_index"]})
    if fresh.get("name") != action.get("track_name"):
        raise RuntimeError("track changed before the gain change")
    read = send("read_access_object", target)
    properties = read.get("properties") or {}
    if "gain" in (read.get("unavailable") or []) or "gain" not in properties:
        return {
            "status": "unavailable",
            "wrote": False,
            "track_name": action.get("track_name"),
            "clip_name": action.get("clip_name"),
            "reason": "Clip gain is not exposed on this Live build. No value was changed.",
        }
    decision = gain_decision(properties["gain"])
    result = {
        "status": decision["status"],
        "wrote": False,
        "track_index": target["track_index"],
        "track_name": action.get("track_name"),
        "clip_name": action.get("clip_name"),
        "reason": decision["reason"],
    }
    if not decision["write"]:
        return result
    send("write_access_object", {**target, "properties": {"gain": decision["gain"]}})
    result["wrote"] = True
    result["gain"] = decision["gain"]
    return result


def _apply_dc(send, action, sleeper):
    index = _index(action.get("track_index"), "track index")
    track_name = action.get("track_name")
    fresh = send("get_track_info", {"track_index": index})
    if fresh.get("name") != track_name:
        raise RuntimeError("track changed before the DC change")
    utilities = _utilities(fresh.get("devices"))
    loaded = False
    if len(utilities) > 1:
        return {
            "status": "unavailable",
            "wrote": False,
            "utility_loaded": False,
            "track_name": track_name,
            "reason": "More than one Utility is on this track. No DC value was changed.",
        }
    if not utilities:
        device = _load_utility(send, index, track_name, len(fresh.get("devices") or []), sleeper)
        if device is None:
            return {
                "status": "unavailable",
                "wrote": False,
                "utility_loaded": False,
                "track_name": track_name,
                "reason": "Utility is not available in the browser. No DC value was changed.",
            }
        loaded = True
        utilities = [device]
    device = utilities[0]
    device_index = device.get("index")
    if device_index is None:
        device_index = len(fresh.get("devices") or []) if loaded else None
    if isinstance(device_index, bool) or not isinstance(device_index, int):
        return {
            "status": "unavailable",
            "wrote": False,
            "utility_loaded": loaded,
            "track_name": track_name,
            "reason": "Utility's device index could not be read. No DC value was changed.",
        }
    data = send(
        "get_sound_design_parameters",
        {
            "track_index": index,
            "device_index": device_index,
            "expected_track_name": track_name,
            "expected_device_name": "Utility",
        },
    )
    decision = dc_decision(data.get("parameters"))
    result = {
        "status": decision["status"],
        "wrote": False,
        "utility_loaded": loaded,
        "track_index": index,
        "track_name": track_name,
        "reason": decision["reason"],
    }
    if not decision["write"]:
        return result
    send(
        "set_sound_design_parameters",
        {
            "track_index": index,
            "device_index": device_index,
            "parameters": {decision["name"]: decision["value"]},
            "expected_track_name": track_name,
            "expected_device_name": data.get("device_name") or "Utility",
        },
    )
    result["wrote"] = True
    result["parameter"] = decision["name"]
    return result


_COMPRESSOR_TARGETS = ("Threshold", "Ratio", "Attack", "Release", "Knee")
_COMPRESSOR_TOLERANCE = {
    "Threshold": 0.75,
    "Ratio": 0.08,
    "Attack": 2.0,
    "Release": 40.0,
    "Knee": 0.6,
}


def _load_named_device(send, track_index, track_name, category, device_name, before_count, sleeper):
    uri = resolve_browser_item(send, category, device_name)
    if not uri:
        return None
    send("load_browser_item", {"track_index": track_index, "item_uri": uri})
    for _attempt in range(POLL_ATTEMPTS):
        seen = send("get_track_info", {"track_index": track_index})
        if seen.get("name") != track_name:
            raise RuntimeError(
                "Track changed while loading " + device_name + ". Inspect it before retrying."
            )
        devices = seen.get("devices") or []
        if len(devices) == before_count + 1 and devices[-1].get("name") == device_name:
            return devices[-1]
        sleeper(POLL_SECONDS)
    raise RuntimeError(
        device_name
        + " was not confirmed on "
        + track_name
        + ". Inspect that track before loading it again. Earlier repairs in this "
        "apply may already have changed; each write is its own undo."
    )


def _parameter_rows(send, track_index, device_index, track_name, device_name):
    data = send(
        "get_sound_design_parameters",
        {
            "track_index": track_index,
            "device_index": device_index,
            "expected_track_name": track_name,
            "expected_device_name": device_name,
        },
    )
    return data.get("parameters") or []


def _write_parameters(send, track_index, device_index, track_name, device_name, values):
    send(
        "set_sound_design_parameters",
        {
            "track_index": track_index,
            "device_index": device_index,
            "parameters": values,
            "expected_track_name": track_name,
            "expected_device_name": device_name,
        },
    )


def _refine_parameter(send, track_index, device_index, track_name, name, target, native):
    """Move one monotonic knob until its display is close. Each try is an undo."""

    low, high = 0.0, 1.0
    if name == "Knee":
        low, high = 0.0, 18.0
    shown = None
    for _step in range(5):
        rows = _parameter_rows(send, track_index, device_index, track_name, "Compressor")
        current = next((row for row in rows if row.get("name") == name), None)
        shown = parse_display(current.get("display_value")) if current else None
        tolerance = _COMPRESSOR_TOLERANCE[name]
        if shown is not None and abs(shown - target) <= tolerance:
            return native, shown, True
        if shown is None:
            break
        if shown < target:
            low = native
        else:
            high = native
        native = round((low + high) / 2.0, 6)
        _write_parameters(send, track_index, device_index, track_name, "Compressor", {name: native})
    rows = _parameter_rows(send, track_index, device_index, track_name, "Compressor")
    current = next((row for row in rows if row.get("name") == name), None)
    shown = parse_display(current.get("display_value")) if current else shown
    matched = shown is not None and abs(shown - target) <= _COMPRESSOR_TOLERANCE[name]
    return native, shown, matched


def _apply_compressor(send, action, sleeper):
    index = _index(action.get("track_index"), "track index")
    track_name = action.get("track_name")
    fresh = send("get_track_info", {"track_index": index})
    if fresh.get("name") != track_name:
        raise RuntimeError("track changed before the compressor change")
    present = _dynamics(fresh.get("devices"))
    if present:
        return {
            "status": "ready",
            "wrote": False,
            "compressor_loaded": False,
            "track_index": index,
            "track_name": track_name,
            "reason": "A compressor is already on this track and was left unchanged.",
        }
    try:
        values = compressor_values(action)
    except (KeyError, TypeError, ValueError) as error:
        return {
            "status": "unavailable",
            "wrote": False,
            "compressor_loaded": False,
            "track_name": track_name,
            "reason": str(error),
        }
    device = _load_named_device(
        send,
        index,
        track_name,
        "audio_effects",
        "Compressor",
        len(fresh.get("devices") or []),
        sleeper,
    )
    if device is None:
        return {
            "status": "unavailable",
            "wrote": False,
            "compressor_loaded": False,
            "track_name": track_name,
            "reason": "Compressor is not available in the browser. No dynamics device was loaded.",
        }
    device_index = device.get("index")
    if isinstance(device_index, bool) or not isinstance(device_index, int):
        device_index = len(fresh.get("devices") or [])
    rows = _parameter_rows(send, index, device_index, track_name, "Compressor")
    names = [row.get("name") for row in rows]
    if any(names.count(name) != 1 for name in _COMPRESSOR_TARGETS):
        return {
            "status": "unavailable",
            "wrote": False,
            "compressor_loaded": True,
            "track_index": index,
            "track_name": track_name,
            "reason": (
                "This Live build does not expose the expected Compressor controls. "
                "No compressor value was changed. Undo removes the loaded device."
            ),
        }
    automated = [
        row["name"]
        for row in rows
        if row.get("name") in values and int(row.get("automation_state") or 0) != 0
    ]
    if automated:
        return {
            "status": "unavailable",
            "wrote": False,
            "compressor_loaded": True,
            "track_name": track_name,
            "reason": "Automated compressor controls were left unchanged: " + ", ".join(automated),
        }
    try:
        _write_parameters(send, index, device_index, track_name, "Compressor", values)
    except RuntimeError as error:
        return {
            "status": "unavailable",
            "wrote": False,
            "compressor_loaded": True,
            "track_name": track_name,
            "reason": "Compressor was loaded, but the parameter write failed: " + str(error),
        }
    rows = _parameter_rows(send, index, device_index, track_name, "Compressor")
    targets = {
        "Threshold": action["threshold_db"],
        "Ratio": action["ratio"],
        "Attack": action["attack_ms"],
        "Release": action["release_ms"],
        "Knee": action["knee_db"],
    }
    displays = {}
    verified = True
    for name, target in targets.items():
        current = next(row for row in rows if row.get("name") == name)
        shown = parse_display(current.get("display_value"))
        if shown is None or abs(shown - target) > _COMPRESSOR_TOLERANCE[name]:
            _native, shown, matched = _refine_parameter(
                send, index, device_index, track_name, name, target, values[name]
            )
            verified = verified and matched
        displays[name] = shown
    return {
        "status": "level_compressor" if verified else "review",
        "wrote": True,
        "compressor_loaded": True,
        "verified": verified,
        "track_index": index,
        "track_name": track_name,
        "displays": displays,
        "reason": action.get("message") or "Loaded a gentle Compressor for repeated level jumps.",
    }


def apply_plan(send, plan, confirm=True, sleeper=None):
    """Write the planned gain, DC and compressor changes. Clicks and silence are not rewritten."""

    if confirm is not True:
        preview = dict(plan)
        preview["applied"] = False
        preview["live_changes"] = False
        preview["playback_started"] = False
        return preview
    if sleeper is None:
        sleeper = time.sleep
    _require_stopped(send)
    results = []
    for action in plan.get("actions") or []:
        _require_stopped(send)
        if action.get("status") == "lower_gain":
            results.append(_apply_gain(send, action))
        elif action.get("status") == "dc_filter":
            results.append(_apply_dc(send, action, sleeper))
        elif action.get("status") == "level_compressor":
            results.append(_apply_compressor(send, action, sleeper))
    return {
        "method": "repair-audio",
        "applied": True,
        "live_changes": any(
            row.get("wrote") or row.get("utility_loaded") or row.get("compressor_loaded")
            for row in results
        ),
        "playback_started": False,
        "window": plan.get("window") or WINDOW_NOTE,
        "results": results,
        "reports": plan.get("reports") or [],
        "skipped": plan.get("skipped") or [],
        "undo": (
            "Each clip-gain change, device load, and parameter change is its own "
            "undo step, from the last write backward."
        ),
    }


def plan_live(send, scan=None):
    from .song_lint import collect_live

    state = collect_live(include_session=False)
    plan = plan_repairs(tracks_from_capture(state, scan=scan))
    plan["captured_tracks"] = len(state.get("tracks") or [])
    plan["capture_errors"] = state.get("capture_errors") or []
    return plan


def apply_live(send, confirm=True):
    if confirm is not True:
        plan = plan_live(send)
        plan["applied"] = False
        plan["live_changes"] = False
        return plan
    _require_stopped(send)
    applied = apply_plan(send, plan_live(send), confirm=True)
    applied["method"] = "repair-audio"
    return applied


def register_audio_repair(mcp, dispatch):
    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def plan_audio_repair() -> dict:
        """Optional preview of repairs for the first 30 seconds of each Arrangement
        audio clip's source WAV. Full-scale samples can lower clip gain. DC offset
        can enable Utility's DC switch when Live exposes it. Three or more level
        jumps can add one gentle Compressor. Clicks and silence gaps are listed.
        Does not write or start playback.
        """
        return plan_live(dispatch)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def apply_audio_repair(confirm: bool = True) -> dict:
        """Lower unity clip gain, enable Utility DC, and load one gentle Compressor
        where the measurement supports it. Writes unless confirm is false. Refuses
        while playing or recording. Does not add a limiter, write fades, or change
        notes, Warp, track faders, or a compressor that is already loaded. A missing
        parameter is left unset.
        """
        return apply_live(dispatch, confirm=confirm)
