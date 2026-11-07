"""Explicit musical corrections and phrase events; no audio-recognition claims."""

import math


def validate_options(c):
    length = c["drop_bars"] * 4
    c.setdefault("vocal_source_kind", "isolated")
    if c["vocal_source_kind"] not in ["isolated", "full_mix"]:
        raise ValueError("vocal_source_kind must be isolated or full_mix")
    overrides = c.setdefault("root_overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("root_overrides must map absolute bar numbers to source MIDI pitches")
    for bar, pitch in overrides.items():
        if not isinstance(bar, str) or not bar.isdecimal() or str(int(bar)) != bar:
            raise ValueError("Root override keys must be canonical absolute bar numbers")
        if not c["drop_bar"] <= int(bar) < c["drop_bar"] + c["drop_bars"]:
            raise ValueError("Root override outside drop")
        if type(pitch) is not int or not 0 <= pitch <= 127:
            raise ValueError("Root override pitch must be MIDI 0..127")
    regions = c.setdefault("vocal_regions", [])
    if not isinstance(regions, list) or len(regions) > 256:
        raise ValueError("vocal_regions needs at most 256 drop-relative activity windows")
    previous = -1
    for region in regions:
        if not isinstance(region, dict) or set(region) != {"start", "end"}:
            raise ValueError("Vocal windows need exactly start and end beats")
        a, b = region["start"], region["end"]
        if any(
            isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t)
            for t in [a, b]
        ):
            raise ValueError("Vocal window times must be finite")
        if not 0 <= a < b <= length or a < previous:
            raise ValueError("Vocal windows must be ordered, non-overlapping and inside the drop")
        previous = b
    c.setdefault("phrase_variation", True)
    if not isinstance(c["phrase_variation"], bool):
        raise ValueError("phrase_variation must be boolean")
    palette = c.setdefault("bass_palette", ["wobble", "growl"])
    if (
        not isinstance(palette, list)
        or not 1 <= len(palette) <= 4
        or any(x not in ["wobble", "growl", "smooth", "riff"] for x in palette)
    ):
        raise ValueError("bass_palette supports 1..4 wobble/growl/smooth/riff gestures")
    pulses = c.setdefault("custom_pulses", None)
    if pulses is not None:
        if not isinstance(pulses, list) or len(pulses) > 4096:
            raise ValueError("custom_pulses must contain at most 4096 events")
        previous = -1
        for p in pulses:
            if not isinstance(p, dict) or set(p) != {"time", "duration"}:
                raise ValueError("Pulse events need time and duration")
            t, d = p["time"], p["duration"]
            if any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in [t, d]
            ):
                raise ValueError("Pulse values must be finite")
            if (
                not 0 <= t < length
                or not 0.000001 <= d <= 2
                or t + d > length + 1e-6
                or t < previous
            ):
                raise ValueError("Custom pulses must be ordered and inside the drop")
            previous = t


def enrich(plan):
    c = plan["config"]
    length = c["drop_bars"] * 4
    if c["custom_pulses"] is not None:
        plan["movement"]["pulses"] = c["custom_pulses"]
    notes = [n for n in c["source_notes"] if not n["mute"]]
    choices = {x["bar"]: x for x in plan["root_decisions"]}
    subs = {int(n["start_time"] / 4) + c["drop_bar"]: n for n in plan["midi"]["sub"]}
    for bar in range(c["drop_bar"], c["drop_bar"] + c["drop_bars"]):
        time = c["source_section_start_beat"] + 4 * (bar - c["drop_bar"])
        weights = {}
        for n in notes:
            overlap = max(
                0, min(time + 4, n["start_time"] + n["duration"]) - max(time, n["start_time"])
            )
            if overlap:
                weights[n["pitch"] % 12] = (
                    weights.get(n["pitch"] % 12, 0) + overlap * n["velocity"] / 127
                )
        total = sum(weights.values()) or 1
        candidates = [
            dict(pitch_class=p, support=round(w / total, 4))
            for p, w in sorted(weights.items(), key=lambda x: (-x[1], x[0]))[:3]
        ]
        if str(bar) in c["root_overrides"]:
            source = c["root_overrides"][str(bar)]
            requested = source + c["sub_octave_shift"]
            pitch = requested
            low, high = c["sub_range"]
            while pitch < low:
                pitch += 12
            while pitch > high:
                pitch -= 12
            subs[bar] = dict(
                pitch=pitch,
                start_time=(bar - c["drop_bar"]) * 4,
                duration=4.0,
                velocity=100,
                mute=False,
            )
            choices[bar] = dict(
                bar=bar,
                source_pitch=source,
                sub_pitch=pitch,
                requested_pitch=requested,
                reason="explicit_root_override",
                octave_adjusted_to_register=pitch != requested,
            )
        if bar in choices:
            choices[bar]["alternatives"] = candidates
            choices[bar]["needs_root_review"] = choices[bar][
                "reason"
            ] != "explicit_root_override" and (
                not candidates
                or candidates[0]["support"] < 0.6
                or choices[bar]["source_pitch"] % 12 != candidates[0]["pitch_class"]
            )
    plan["midi"]["sub"] = [subs[b] for b in sorted(subs)]
    plan["root_decisions"] = [choices[b] for b in sorted(choices)]
    plan["missing_root_bars"] = [
        b for b in range(c["drop_bar"], c["drop_bar"] + c["drop_bars"]) if b not in subs
    ]
    plan["status"] = (
        "planned"
        if plan["midi"]["riff"] and not plan["missing_root_bars"]
        else "needs_source_notes"
    )

    def busy(a, b):
        return any(r["start"] < b and r["end"] > a for r in c["vocal_regions"])

    phrases = []
    fx = []
    chops = []
    for a in range(0, length, 8):
        b = min(length, a + 8)
        i = a // 8
        kind = c["bass_palette"][i % len(c["bass_palette"])]
        phrases.append(
            dict(
                start=a,
                end=b,
                role="call" if i % 2 == 0 else "response",
                bass=kind if c["phrase_variation"] else c["bass_palette"][0],
                vocal_active=busy(a, b),
            )
        )
        if c["phrase_variation"] and i % 2 and not busy(b - 1, b):
            fx.append(dict(start=b - 1, end=b, kind="reverse_tail", source="riff"))
    if c["vocal_mode"] == "chops":
        for r in c["vocal_regions"]:
            a = r["end"]
            b = min(length, a + 0.5)
            if b > a and not busy(a, b):
                chops.append(dict(start=a, end=b, source_start=max(r["start"], r["end"] - 0.5)))
    plan["arrangement"] = dict(
        phrases=phrases,
        fx=fx,
        vocal_chops=chops,
        vocal_regions=c["vocal_regions"],
        root_support_is_not_chord_probability=True,
        transition_gap=dict(
            start=max(
                0,
                plan["grid"]["drop_start_beat"]
                - plan["movement"]["settings"]["transition_gap_beats"],
            ),
            end=plan["grid"]["drop_start_beat"],
        ),
    )
    if c["vocal_source_kind"] == "full_mix":
        for track in plan["tracks"]:
            if track["id"] == "vocal":
                track["name"] = "SOURCE | Chorus Vocal Context"
                track["action"] = (
                    "Retain full-mix context; original drums/instruments remain. Replace with stems for a clean remix."
                )
        plan["warnings"].append(
            "Full-mix vocal context is not an isolated singer; original rhythm remains audible."
        )
    plan["warnings"].append(
        "Root alternatives describe duration/velocity support, not calibrated chord-root confidence."
    )
    return plan
