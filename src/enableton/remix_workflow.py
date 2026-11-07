"""Versioned half-time remix planning. Pure functions: no Live or file mutations."""

from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path


RECIPE_VERSION = "1.1.0"
FEEDBACK = {
    "too_guttural": "Keep the sub monophonic; remove low chord stacks from the mid layer.",
    "too_busy": "Reduce pulse/hat density; leave the hook and backbeat more space.",
    "vocal_masked": "Duck the mid layer around vocal phrases, preserving the clean sub.",
    "kick_sub_clash": "Dip sub gain briefly at actual kick positions; retain held notes.",
    "weak_transition": "Add a short pre-drop gap and compare the entrance at matched loudness.",
    "clicks": "Lengthen gain edges; inspect seams, gaps and modulation before compression.",
    "more_riddim": "Try the sparse repeating riddim starting pattern and contrasting answers.",
    "smoother": "Use slower rounded movement, a higher gain floor and gentler filtering.",
}


def remix_catalog():
    """Fresh copy of packaged, source-linked profiles; numbers are original exercises."""
    return json.loads(Path(__file__).with_name("remix_recipes.json").read_text(encoding="utf-8"))


def _number(value, name, minimum, maximum, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    if integer and value != int(value):
        raise ValueError(f"{name} must be an integer")
    return int(value) if integer else float(value)


def _patterns(value, name):
    if not isinstance(value, list) or not 1 <= len(value) <= 16:
        raise ValueError(f"{name} needs 1..16 bars of beat offsets")
    result = []
    for bar in value:
        if not isinstance(bar, list) or not 1 <= len(bar) <= 32:
            raise ValueError(f"{name} bars need 1..32 offsets")
        offsets = [_number(t, name, 0, 3.999999999) for t in bar]
        if offsets != sorted(set(offsets)):
            raise ValueError(f"{name} offsets must be unique and increasing")
        result.append(offsets)
    return result


def _notes(value):
    if not isinstance(value, list) or len(value) > 20000:
        raise ValueError("source_notes must contain at most 20000 note objects")
    result = []
    for n in value:
        if not isinstance(n, dict) or not {"pitch", "start_time", "duration"} <= n.keys():
            raise ValueError("Notes need pitch, start_time and duration in clip-relative beats")
        mute = n.get("mute", False)
        if not isinstance(mute, bool):
            raise ValueError("note mute must be boolean")
        result.append(
            {
                "pitch": _number(n["pitch"], "pitch", 0, 127, True),
                "start_time": _number(n["start_time"], "start_time", 0, 1000000),
                "duration": _number(n["duration"], "duration", 0.000001, 1000000),
                "velocity": _number(n.get("velocity", 90), "velocity", 1, 127),
                "mute": mute,
            }
        )
    return sorted(result, key=lambda n: (n["start_time"], n["pitch"]))


def _config(config):
    if not isinstance(config, dict):
        raise ValueError("config must be an object")
    allowed = {
        "schema_version",
        "recipe_version",
        "style",
        "tempo",
        "meter",
        "drop_bar",
        "drop_bars",
        "lead_in_bars",
        "source_section_start_beat",
        "source_notes",
        "source_roles",
        "source_mode",
        "riff_voice",
        "sub_octave_shift",
        "sub_range",
        "vocal_mode",
        "link_mode",
        "overrides",
        "feedback_history",
        "root_overrides",
        "vocal_regions",
        "phrase_variation",
        "bass_palette",
        "custom_pulses",
        "vocal_source_kind",
    }
    if config.keys() - allowed:
        raise ValueError(f"Unknown config fields: {sorted(config.keys() - allowed)}")
    c = deepcopy(config)
    if type(c.get("schema_version", 1)) is not int or c.get("schema_version", 1) != 1:
        raise ValueError("Unsupported schema_version")
    if c.get("recipe_version", RECIPE_VERSION) not in ("1.0.0", RECIPE_VERSION):
        raise ValueError("Unsupported recipe_version; migrate explicitly")
    if c.get("meter", [4, 4]) != [4, 4]:
        raise ValueError(
            "This recipe currently supports a 4/4 grid; half-time is not a 2/2 rewrite"
        )
    profiles = remix_catalog()["profiles"]
    style = c.setdefault("style", "rock_dubstep")
    if not isinstance(style, str) or style not in profiles:
        raise ValueError(f"style must be one of {sorted(profiles)}")
    c.update(schema_version=1, recipe_version=RECIPE_VERSION, meter=[4, 4])
    for field, default, low, high in [
        ("tempo", 140, 40, 300),
        ("drop_bar", 9, 1, 100000),
        ("drop_bars", 16, 1, 128),
        ("lead_in_bars", 4, 0, 32),
        ("source_section_start_beat", 0, 0, 1000000),
    ]:
        c[field] = _number(
            c.get(field, default), field, low, high, field.endswith("bar") or field.endswith("bars")
        )
    if c["lead_in_bars"] >= c["drop_bar"]:
        raise ValueError("lead_in_bars would start before bar 1; reduce it explicitly")
    for field, default, choices in [
        ("source_mode", "hybrid", {"audio_pulse", "midi_rebuild", "hybrid"}),
        ("riff_voice", "lowest_per_onset", {"lowest_per_onset", "all_notes"}),
        ("vocal_mode", "continuous", {"continuous", "chops", "none"}),
        ("link_mode", "rendered_gain", {"rendered_gain", "live_sidechain"}),
    ]:
        c.setdefault(field, default)
        if not isinstance(c[field], str) or c[field] not in choices:
            raise ValueError(f"{field} must be one of {sorted(choices)}")
    shift = _number(c.get("sub_octave_shift", -12), "sub_octave_shift", -48, 24, True)
    if shift % 12:
        raise ValueError(
            "sub_octave_shift must be a multiple of 12; exact pitch classes are retained"
        )
    c["sub_octave_shift"] = shift
    register = c.get("sub_range", [24, 47])
    if not isinstance(register, list) or len(register) != 2:
        raise ValueError("sub_range needs [minimum MIDI pitch, maximum MIDI pitch]")
    c["sub_range"] = [_number(x, "sub_range", 0, 127, True) for x in register]
    if register[1] - register[0] < 11:
        raise ValueError("sub_range must span at least twelve pitches to preserve pitch classes")
    c["source_notes"] = _notes(c.get("source_notes", []))
    roles = c.setdefault("source_roles", {})
    if not isinstance(roles, dict) or roles.keys() - {"riff", "vocal", "rock_context"}:
        raise ValueError("source_roles supports riff, vocal and rock_context labels")
    for role in roles.values():
        if not isinstance(role, str) or not role.strip() or len(role) > 500:
            raise ValueError(
                "Source role labels must be non-empty strings of at most 500 characters"
            )
    history = c.setdefault("feedback_history", [])
    if not isinstance(history, list) or len(history) > 100:
        raise ValueError("feedback_history must be a list of at most 100 iterations")
    overrides = c.setdefault("overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("overrides must be an object")
    settings = deepcopy(profiles[style]["settings"])
    if overrides.keys() - settings.keys():
        raise ValueError(f"Unknown overrides: {sorted(overrides.keys() - settings.keys())}")
    settings.update(overrides)
    limits = {
        "attack_ms": (1, 50),
        "release_ms": (5, 500),
        "floor": (0, 0.8),
        "pulse_duration": (0.05, 2),
        "wobble_beats": (0.25, 8),
        "hat_step": (0.25, 2),
        "hat_swing": (0, 0.12),
        "filter_low_hz": (80, 4000),
        "filter_high_hz": (100, 15000),
        "mid_highpass_hz": (50, 350),
        "kick_duck_db": (0, 12),
        "kick_duck_release_ms": (20, 300),
        "vocal_duck_db": (0, 9),
        "transition_gap_beats": (0, 2),
        "fill_every_bars": (0, 32),
    }
    for field, bounds in limits.items():
        settings[field] = _number(settings[field], field, *bounds, field == "fill_every_bars")
    if settings["filter_low_hz"] >= settings["filter_high_hz"]:
        raise ValueError("filter_low_hz must be below filter_high_hz")
    for field in ["pulse_patterns", "kick_patterns"]:
        settings[field] = _patterns(settings[field], field)
    from .remix_arrangement import validate_options

    validate_options(c)
    return c, settings


def pulse_gain_at(beat, pulses, tempo=140, attack_ms=8, release_ms=85, floor=0.13):
    """Continuous raised-cosine gain in LINEAR AMPLITUDE, never Live fader units."""
    beat = _number(beat, "beat", 0, 1000000)
    tempo = _number(tempo, "tempo", 40, 300)
    attack = _number(attack_ms, "attack_ms", 1, 50) * tempo / 60000
    release = _number(release_ms, "release_ms", 5, 500) * tempo / 60000
    floor = _number(floor, "floor", 0, 0.8)
    if not isinstance(pulses, list) or len(pulses) > 4096:
        raise ValueError("pulses must be a list of at most 4096 events")
    gain = floor
    for p in pulses:
        time = _number(p["time"], "pulse time", 0, 1000000)
        duration = _number(p["duration"], "pulse duration", 0.000001, 2)
        x = beat - time
        # A very short pulse must still finish its attack before its release.
        a = min(attack, duration)
        if 0 <= x < a:
            v = math.sin(math.pi * x / (2 * a)) ** 2
        elif a <= x < duration:
            v = 1
        elif duration <= x < duration + release:
            v = math.cos(math.pi * (x - duration) / (2 * release)) ** 2
        else:
            v = 0
        gain = max(gain, floor + (1 - floor) * v)
    return gain


def plan_halftime_remix(config):
    """Generate MIDI, pulse/duck recipes and an honest audio-link plan without editing Live."""
    c, s = _config(config)
    begin = (c["drop_bar"] - 1) * 4
    length = c["drop_bars"] * 4
    offset = c["source_section_start_beat"]
    active = [n for n in c["source_notes"] if not n["mute"]]
    riff = []
    for n in active:
        a = max(offset, n["start_time"])
        z = min(offset + length, n["start_time"] + n["duration"])
        if z > a:
            riff.append(dict(n, start_time=a - offset, duration=z - a))
    if c["riff_voice"] == "lowest_per_onset":
        lowest = {}
        for n in riff:
            if n["start_time"] not in lowest or n["pitch"] < lowest[n["start_time"]]["pitch"]:
                lowest[n["start_time"]] = n
        riff = list(lowest.values())
    sub, choices, missing = [], [], []
    for bar in range(c["drop_bars"]):
        time = offset + 4 * bar
        sounding = [n for n in active if n["start_time"] <= time < n["start_time"] + n["duration"]]
        incoming = [n for n in active if time <= n["start_time"] < time + 4]
        prior = [n for n in active if n["start_time"] < time]
        if sounding:
            chosen, reason = min(sounding, key=lambda n: n["pitch"]), "lowest_sounding_at_barline"
        elif incoming:
            chosen = min(incoming, key=lambda n: (n["start_time"], n["pitch"]))
            reason = "first_incoming_note_in_bar"
        elif prior:
            last = max(n["start_time"] for n in prior)
            chosen = min((n for n in prior if n["start_time"] == last), key=lambda n: n["pitch"])
            reason = "carry_previous_note_across_silence"
        else:
            missing.append(c["drop_bar"] + bar)
            continue
        pitch = chosen["pitch"] + c["sub_octave_shift"]
        requested = pitch
        low, high = c["sub_range"]
        while pitch < low:
            pitch += 12
        while pitch > high:
            pitch -= 12
        sub.append(dict(pitch=pitch, start_time=bar * 4, duration=4.0, velocity=100, mute=False))
        choices.append(
            dict(
                bar=c["drop_bar"] + bar,
                source_pitch=chosen["pitch"],
                sub_pitch=pitch,
                requested_pitch=requested,
                reason=reason,
                octave_adjusted_to_register=pitch != requested,
            )
        )
    drums, pulses, kicks = [], [], []

    def drum(pitch, time, velocity):
        drums.append(
            dict(
                pitch=pitch,
                start_time=time,
                duration=min(0.12, length - time),
                velocity=velocity,
                mute=False,
            )
        )

    for bar in range(c["drop_bars"]):
        time = bar * 4
        for h in s["pulse_patterns"][bar % len(s["pulse_patterns"])]:
            pulses.append(dict(time=time + h, duration=min(s["pulse_duration"], length - time - h)))
        for h in s["kick_patterns"][bar % len(s["kick_patterns"])]:
            kicks.append(time + h)
            drum(36, time + h, 114 if h == 0 else 94)
        drum(38, time + 2, 118)
        for j in range(math.ceil(4 / s["hat_step"])):
            hit = j * s["hat_step"] + (s["hat_swing"] if j % 2 else 0)
            if hit < 4:
                drum(42, time + hit, 68 if j % 2 == 0 else 46)
        if s["fill_every_bars"] and (bar + 1) % s["fill_every_bars"] == 0:
            for h in [3.5, 3.75]:
                drum(38, time + h, 64)
    warnings = [
        "Root selection is a MIDI heuristic, not chord recognition; audition inversions and passing notes.",
        "A full-mix riff sample can retain drums or vocals; do not call it an isolated guitar stem.",
        "Keep riff and singer at source pitch unless a measured musical mismatch justifies a shift.",
        "Compare the entire phrase at matched loudness; meter samples are not true peak or LUFS.",
    ]
    if missing:
        warnings.append(f"No root source for bars {missing}; no pitches were invented.")
    if c["vocal_mode"] != "none" and "vocal" not in c["source_roles"]:
        warnings.append("Choose an isolated vocal source before building the vocal layer.")
    if c["riff_voice"] == "lowest_per_onset":
        warnings.append(
            "Riff MIDI retains the lowest voice at each onset; upper chord notes are omitted explicitly."
        )
    if c["link_mode"] == "rendered_gain":
        link = "Shared pulse recipe drives rendered audio gain and MIDI-layer movement; MIDI edits require regeneration."
    else:
        link = "Requested live sidechain: probe current device input routing and verify a silent control path before wiring. Fall back to rendered_gain if unavailable."
    roles = [
        dict(
            id="rock_context",
            name="ROCK | Lead-In",
            start=begin - c["lead_in_bars"] * 4,
            end=begin,
            action="Copy the source phrase with its Warp map; fade its edge into the drop.",
        ),
        dict(
            id="riff_audio",
            name="RIFF | Original Audio Pulses",
            start=begin,
            end=begin + length,
            action="Use matching source phrases; do not repeat an intro across a different progression.",
        ),
        dict(
            id="midbass",
            name="MIDBASS | Riff + Wobble",
            start=begin,
            end=begin + length,
            action="Rebuild the selected MIDI voice, saturate/filter, and clear sub overlap.",
        ),
        dict(
            id="sub",
            name="SUB | Held Roots",
            start=begin,
            end=begin + length,
            action="One held root per bar; use short gain edges and actual kick-position dips.",
        ),
        dict(
            id="drums",
            name="DRUMS | Half-Time",
            start=begin,
            end=begin + length,
            action="Map the documented drum roles to the loaded kit; MIDI numbers are a proposed GM map.",
        ),
        dict(
            id="fx",
            name="FX | Phrase Answers",
            start=begin,
            end=begin + length,
            action="Place short responses in gaps; leave snare and vocal entrances clear.",
        ),
    ]
    if c["source_mode"] == "midi_rebuild":
        roles = [r for r in roles if r["id"] != "riff_audio"]
    elif c["source_mode"] == "audio_pulse":
        roles = [r for r in roles if r["id"] != "midbass"]
    if c["vocal_mode"] != "none":
        roles.append(
            dict(
                id="vocal",
                name="VOCAL | Isolated Chorus",
                start=begin,
                end=begin + length,
                action="Keep aligned lead phrases; put chops and wet tails in gaps on a separate lane.",
            )
        )
    fingerprint = sha256(json.dumps(c, sort_keys=True, allow_nan=False).encode()).hexdigest()
    result = dict(
        schema_version=1,
        recipe_version=RECIPE_VERSION,
        fingerprint=fingerprint,
        config=c,
        status="planned" if riff and not missing else "needs_source_notes",
        live_changes=False,
        grid=dict(
            tempo=c["tempo"],
            felt_backbeat_bpm=c["tempo"] / 2,
            meter=[4, 4],
            drop_start_beat=begin,
            drop_end_beat=begin + length,
            note_times="relative to drop start; source_notes are clip-relative",
        ),
        tracks=roles,
        midi=dict(
            riff=riff, sub=sub, drums=sorted(drums, key=lambda n: (n["start_time"], n["pitch"]))
        ),
        root_decisions=choices,
        missing_root_bars=missing,
        movement=dict(
            settings=s,
            pulses=pulses,
            boundary_fade_ms=5,
            units="linear amplitude for gain; displayed Hz/ms/dB for suggestions, never normalized Live fader values",
            kick_ducks=[
                dict(time=t, depth_db=s["kick_duck_db"], release_ms=s["kick_duck_release_ms"])
                for t in kicks
            ],
            audio_link=link,
        ),
        verification=[
            "Read fresh track/clip names, boundaries, source paths and Warp maps before writes.",
            "Build new lanes; preserve originals and avoid overlapping duplicate destinations.",
            "Verify loaded kit pad map and formatted parameter units before applying settings.",
            "Read back notes, bounds, envelopes, routing and backup mute/solo state.",
            "Check transport position after starting: this session's start_playback resumed a different marker.",
            "Audition transition and whole chorus; check mono low end, vocal clarity, seams and headroom.",
            "Check actual save support; if unavailable, save in Live and collect external audio.",
        ],
        warnings=warnings,
        sources=remix_catalog()["sources"],
        evidence="Deterministic generated plan; not a Live render, automatic transcription or an artist-session reconstruction.",
    )
    from .remix_arrangement import enrich

    return enrich(result)


def guide_halftime_remix(answers=None):
    """Return the next small decision group; caller can gather clip notes through existing Live reads."""
    answers = {} if answers is None else answers
    c, _ = _config(answers)
    groups = [
        [
            ("style", "Choose rock_dubstep, smooth_wobble or riddim."),
            ("tempo", "Keep the current grid tempo, or choose the target BPM?"),
            ("drop_bar", "At which bar should the half-time section begin?"),
        ],
        [
            ("drop_bars", "How many bars should the first drop cover?"),
            ("source_roles", "Which tracks/clips supply the riff, isolated vocal and lead-in?"),
            (
                "source_notes",
                "Read the chosen MIDI riff; obtain audio-to-MIDI manually if no transcription exists.",
            ),
        ],
        [
            ("source_section_start_beat", "What clip-relative beat aligns with the drop downbeat?"),
            ("source_mode", "Use original audio pulses, a MIDI rebuild, or a hybrid?"),
            ("vocal_mode", "Keep the chorus singing, use chops, or omit vocals?"),
        ],
    ]
    for stage, questions in enumerate(groups, 1):
        pending = [
            dict(field=f, question=q, suggested_default=c[f])
            for f, q in questions
            if f not in answers or (f in {"source_notes", "source_roles"} and not answers[f])
        ]
        if pending:
            return dict(
                stage=stage,
                status="gather_decisions",
                questions=pending,
                live_changes=False,
                defaults_are_not_answers=True,
                answers=deepcopy(answers),
                normalized_config=c,
                next_action="Gather only the missing decisions; read selected clips rather than scanning the entire set.",
            )
    plan = plan_halftime_remix(c)
    return dict(
        stage=4,
        status="review_and_build" if plan["status"] == "planned" else "needs_source_notes",
        questions=[],
        plan=plan,
        next_action="Use existing guarded Live tools to build new lanes, then audition and feed back specific problems.",
        live_changes=False,
    )


def refine_halftime_remix(config, feedback):
    """Return a new versioned config and plan from explicit listening feedback; no learning claim."""
    c, s = _config(config)
    if not isinstance(feedback, list) or not 1 <= len(feedback) <= len(FEEDBACK):
        raise ValueError("feedback needs 1..8 distinct supported issue names")
    if any(not isinstance(f, str) or f not in FEEDBACK for f in feedback) or len(
        set(feedback)
    ) != len(feedback):
        raise ValueError(f"feedback must be distinct names from {sorted(FEEDBACK)}")
    if len(c["feedback_history"]) >= 100:
        raise ValueError("Start a new revision lineage after 100 iterations")
    o = c["overrides"]
    for issue in feedback:
        if issue == "too_guttural":
            c["riff_voice"] = "lowest_per_onset"
            o["mid_highpass_hz"] = min(250, s["mid_highpass_hz"] + 25)
        elif issue == "too_busy":
            o.update(
                pulse_patterns=[bar[::2] for bar in s["pulse_patterns"]],
                hat_step=1,
                fill_every_bars=8,
            )
        elif issue == "vocal_masked":
            o["vocal_duck_db"] = min(9, s["vocal_duck_db"] + 3)
        elif issue == "kick_sub_clash":
            o.update(kick_duck_db=min(12, s["kick_duck_db"] + 3), kick_duck_release_ms=100)
        elif issue == "weak_transition":
            o["transition_gap_beats"] = 0.5
        elif issue == "clicks":
            o.update(attack_ms=max(8, s["attack_ms"]), release_ms=max(80, s["release_ms"]))
        elif issue == "more_riddim":
            c["style"] = "riddim"
            for f in ["pulse_patterns", "kick_patterns", "wobble_beats"]:
                o[f] = remix_catalog()["profiles"]["riddim"]["settings"][f]
        elif issue == "smoother":
            o.update(
                attack_ms=12,
                release_ms=100,
                floor=0.2,
                wobble_beats=2,
                filter_low_hz=250,
                filter_high_hz=1200,
            )
    c["feedback_history"].append(dict(recipe_version=RECIPE_VERSION, feedback=list(feedback)))
    plan = plan_halftime_remix(c)
    return dict(
        config=plan["config"],
        plan=plan,
        changes=[dict(issue=f, reason=FEEDBACK[f]) for f in feedback],
        live_changes=False,
        evidence="Explicit feedback rules, not automatic listening or self-training",
    )


def register_remix(mcp):
    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def plan_halftime_remix_workflow(config: dict) -> dict:
        """Plan a reusable rock/dubstep/riddim flip: source-relative riff MIDI, held roots,
        half-time drums, smooth pulses, audio-link choices and verification. No Live writes.
        Physical Hz/ms/dB suggestions are not native device values. Read docs/REMIX_WORKFLOW.md.
        """
        return plan_halftime_remix(config)

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def guide_halftime_remix_workflow(answers: dict | None = None) -> dict:
        """Guide remix creation in small decision groups. Select source clips, read their
        MIDI/timing, plan a drop, build through existing Live tools, audition, then refine.
        Returns pending decisions or a plan; never silently edits the set.
        """
        return guide_halftime_remix(answers)

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def refine_halftime_remix_workflow(config: dict, feedback: list[str]) -> dict:
        """Revise a remix plan using explicit listening feedback: too_guttural, too_busy,
        vocal_masked, kick_sub_clash, weak_transition, clicks, more_riddim, smoother.
        Returns a new config with revision history. No audio audition or Live changes.
        """
        return refine_halftime_remix(config, feedback)
