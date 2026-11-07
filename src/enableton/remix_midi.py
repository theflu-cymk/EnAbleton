"""Conservative transcription cleanup; edits are proposed, never applied to originals."""

from copy import deepcopy
import math


def clean_transcription(notes, policy=None):
    policy = {} if policy is None else deepcopy(policy)
    allowed = {
        "minimum_duration",
        "monophonic_lowest",
        "register",
        "snap_grid",
        "snap_tolerance",
        "snap_strength",
    }
    if not isinstance(policy, dict) or policy.keys() - allowed:
        raise ValueError("Unknown MIDI cleanup policy")
    minimum = policy.get("minimum_duration", 1 / 64)
    grid = policy.get("snap_grid", 1 / 16)
    tolerance = policy.get("snap_tolerance", 0.03)
    strength = policy.get("snap_strength", 0.5)
    for value, low, high in [
        (minimum, 0, 0.25),
        (grid, 1 / 192, 1),
        (tolerance, 0, 0.125),
        (strength, 0, 1),
    ]:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not low <= value <= high
        ):
            raise ValueError("Invalid MIDI cleanup timing controls")
    mono = policy.get("monophonic_lowest", False)
    if not isinstance(mono, bool):
        raise ValueError("monophonic_lowest must be boolean")
    register = policy.get("register")
    if register is not None and (
        not isinstance(register, list)
        or len(register) != 2
        or any(type(n) is not int or not 0 <= n <= 127 for n in register)
        or register[1] - register[0] < 11
    ):
        raise ValueError("Register must span at least twelve MIDI pitches")
    from .remix_workflow import _notes

    source = _notes(notes)
    working = []
    seen = set()
    report = dict(
        input_notes=len(source),
        duplicates_removed=0,
        short_removed=0,
        same_pitch_overlaps_trimmed=0,
        timing_adjustments=0,
        octave_adjustments=0,
        monophonic_reduction=False,
        limitations="No key snapping, chord recognition or automatic wrong-note correction. Basic notes only, without MPE curves. Audition the proposed copy.",
    )
    for n in source:
        if n["mute"]:
            working.append(dict(n))
            continue
        key = (n["pitch"], n["start_time"], n["duration"])
        if key in seen:
            report["duplicates_removed"] += 1
            continue
        seen.add(key)
        if n["duration"] < minimum:
            report["short_removed"] += 1
            continue
        working.append(dict(n))
    if mono:
        import heapq

        active = [(i, n) for i, n in enumerate(working) if not n["mute"]]
        starts = {}
        for i, n in active:
            starts.setdefault(n["start_time"], []).append((i, n))
        events = sorted(
            {t for _, n in active for t in [n["start_time"], n["start_time"] + n["duration"]]}
        )
        reduced = []
        last_id = None
        heap = []
        for a, b in zip(events, events[1:]):
            for i, n in starts.get(a, []):
                heapq.heappush(
                    heap, (n["pitch"], -n["velocity"], i, n["start_time"] + n["duration"], n)
                )
            while heap and heap[0][3] <= a + 1e-8:
                heapq.heappop(heap)
            if not heap:
                last_id = None
                continue
            _, _, i, _, n = heap[0]
            if (
                reduced
                and i == last_id
                and abs(reduced[-1]["start_time"] + reduced[-1]["duration"] - a) < 1e-7
            ):
                reduced[-1]["duration"] = b - reduced[-1]["start_time"]
            else:
                reduced.append(dict(n, start_time=a, duration=b - a))
            last_id = i
        working = reduced + [dict(n) for n in working if n["mute"]]
        report["monophonic_reduction"] = True
    for n in working:
        if n["mute"]:
            continue
        a = n["start_time"]
        b = a + n["duration"]
        sa = round(a / grid) * grid
        sb = round(b / grid) * grid
        if abs(sa - a) <= tolerance:
            a += strength * (sa - a)
            report["timing_adjustments"] += int(strength > 0 and sa != n["start_time"])
        if abs(sb - b) <= tolerance:
            b += strength * (sb - b)
        n.update(start_time=max(0, a), duration=max(1e-6, b - max(0, a)))
        if register:
            pitch = n["pitch"]
            while n["pitch"] < register[0]:
                n["pitch"] += 12
            while n["pitch"] > register[1]:
                n["pitch"] -= 12
            report["octave_adjustments"] += int(pitch != n["pitch"])
    working.sort(key=lambda n: (n["start_time"], n["pitch"], n["duration"]))
    following = {}
    for n in reversed(working):
        if n["mute"]:
            continue
        key = None if mono else n["pitch"]
        if key in following and following[key] < n["start_time"] + n["duration"] - 1e-7:
            n["duration"] = max(0, following[key] - n["start_time"])
            report["same_pitch_overlaps_trimmed"] += 1
        following[key] = n["start_time"]
    result = []
    for n in working:
        if not n["mute"] and n["duration"] < minimum:
            report["short_removed"] += 1
        else:
            result.append(n)
    report["output_notes"] = len(result)
    return dict(notes=result, report=report, policy=policy, original_unchanged=True)


def register_midi_cleanup(mcp, dispatch):
    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def plan_remix_midi_cleanup(target: dict, policy: dict | None = None) -> dict:
        """Propose transcription cleanup on a guarded MIDI clip: exact duplicates,
        short fragments, overlaps, gentle nearby-grid correction and optional lowest
        monophonic voice/octave register. Never key-snap or edit the original. Returns
        proposed notes and counts for building a separate copy; rechecks source notes.
        """
        from .remix_live import target as checked_target, note_hash, simple_notes

        t = checked_target(target)
        before = dispatch("get_access_notes", t)
        result = clean_transcription(simple_notes(before["notes"]), policy)
        after = dispatch("get_access_notes", t)
        if note_hash(before["notes"]) != note_hash(after["notes"]):
            raise ValueError("MIDI source changed during cleanup preview")
        return dict(
            result,
            source_target=t,
            source_fingerprint=note_hash(before["notes"]),
            live_changes=False,
        )
