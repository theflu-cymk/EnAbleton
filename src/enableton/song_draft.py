"""Read-only 4/4 song sketches, plus one explicit apply step.

Dubstep, riddim and half-time stay on guide_halftime_remix_workflow. Drum
pitches are General MIDI guesses. Apply creates new Session clips in one undo
step and adds locators that are not already on those beats. It does not start
playback, delete Arrangement clips, or change the meter.
"""

from hashlib import sha256
import json

GENRES = ("house", "hip_hop", "pop", "melodic")
ENERGIES = ("low", "medium", "high")
REDIRECTS = {
    "dubstep": "guide_halftime_remix_workflow",
    "riddim": "guide_halftime_remix_workflow",
    "halftime": "guide_halftime_remix_workflow",
    "half_time": "guide_halftime_remix_workflow",
    "rock_dubstep": "guide_halftime_remix_workflow",
}
FORMS = {
    16: (("A", 8, False), ("B", 8, False)),
    32: (("Intro", 8, True), ("A", 8, False), ("B", 16, False)),
    64: (
        ("Intro", 8, True),
        ("A", 8, False),
        ("B", 16, False),
        ("Breakdown", 8, True),
        ("B2", 16, False),
        ("Outro", 8, True),
    ),
}
FEEDBACK = {
    "more_space": "Drop hats and shorten chords.",
    "more_energy": "Add hats and raise velocity.",
    "darker": "Drop the chord octave.",
    "brighter": "Raise the chord octave.",
    "shorter": "Use the 16-bar form.",
    "longer": "Step a 16-bar form to 32, or a 32-bar form to 64.",
}
MAJOR = ((0, False), (7, False), (9, True), (5, False))
MINOR = ((0, True), (8, False), (3, False), (10, False))
KICKS = {"house": (0, 1, 2, 3), "hip_hop": (0, 2.5), "pop": (0, 2), "melodic": (0, 2.5)}
PITCHES = {
    "C": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
}
FAMILIES = (
    {
        "name": "arrangement",
        "purpose": "Place, mark and read Arrangement material.",
        "tools": (
            "create_arrangement_audio_clip",
            "duplicate_to_arrangement",
            "create_audio_clip",
            "create_locator",
            "jump_to_cue",
            "delete_cue_point",
            "annotate_arrangement",
            "get_audio_clip_timing",
        ),
    },
    {
        "name": "racks_and_devices",
        "purpose": "Inspect racks and write named parameters or one blend macro.",
        "tools": (
            "inspect_rack",
            "map_rack_blend_macro",
            "insert_chain",
            "delete_chain",
            "get_sound_design_parameters",
            "set_sound_design_parameters",
            "get_nested_device_parameters",
            "set_nested_device_parameters",
            "list_plugin_aliases",
            "resolve_plugin_parameter",
            "set_plugin_parameter",
        ),
    },
    {
        "name": "song_draft",
        "purpose": "Sketch a 4/4 Session draft. Dubstep and riddim use the half-time guide.",
        "tools": (
            "guide_song_draft",
            "plan_song_draft",
            "refine_song_draft",
            "apply_song_draft",
            "guide_halftime_remix_workflow",
            "get_drum_pads",
        ),
    },
    {
        "name": "track_preparation",
        "purpose": "Name and color working tracks from their content, and mute the untouched originals.",
        "tools": ("plan_track_preparation", "apply_track_preparation"),
    },
    {
        "name": "instrument_assignment",
        "purpose": "Load a stock placeholder on a MIDI track that has notes and no instrument, so the part can be heard and replaced.",
        "tools": ("plan_instrument_assignment", "apply_instrument_assignment"),
    },
    {
        "name": "audio_repair",
        "purpose": "Lower unity clip gain for full-scale samples, enable Utility DC, and add a gentle Compressor when level jumps repeat.",
        "tools": ("plan_audio_repair", "apply_audio_repair"),
    },
    {
        "name": "track_alignment",
        "purpose": "Set each warped layer's Warp mode from its content. Markers, clip starts, and the mix stay.",
        "tools": ("plan_track_alignment", "apply_track_alignment"),
    },
)


def tool_families():
    return {
        "families": [
            {"name": row["name"], "purpose": row["purpose"], "tools": list(row["tools"])}
            for row in FAMILIES
        ],
        "note": "Registered tool names only. This is a map, not the full catalog.",
        "live_changes": False,
    }


def _genre(value):
    if not isinstance(value, str):
        raise ValueError("genre must be house, hip_hop, pop or melodic")
    text = "_".join(value.strip().casefold().replace("-", " ").split())
    if text in REDIRECTS:
        return text
    if text not in GENRES:
        raise ValueError(
            "genre must be house, hip_hop, pop or melodic. "
            "Dubstep, riddim and half-time use guide_halftime_remix_workflow."
        )
    return text


def _redirect(genre):
    tool = REDIRECTS.get(genre)
    if tool is None:
        return None
    return {
        "status": "use_halftime_guide",
        "redirect_tool": tool,
        "reason": "Dubstep, riddim and half-time sketches belong to the half-time remix guide.",
        "questions": [],
        "live_changes": False,
        "playback_started": False,
    }


def _energy(value):
    if not isinstance(value, str) or value.strip().casefold() not in ENERGIES:
        raise ValueError("energy must be low, medium or high")
    return value.strip().casefold()


def _bars(value):
    if value is None:
        return 32
    if isinstance(value, bool) or not isinstance(value, int) or value not in FORMS:
        raise ValueError("bars must be 16, 32 or 64")
    return value


def _key(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("key must look like C, Am, F#m or Bb")
    raw = value.strip().replace("♯", "#").replace("♭", "b")
    minor = raw.casefold().endswith("m") and len(raw) > 1
    token = raw[:-1] if minor else raw
    pitch_class = PITCHES.get(token.upper())
    if pitch_class is None:
        raise ValueError("key must look like C, Am, F#m or Bb")
    return {
        "name": token[:1].upper() + token[1:] + ("m" if minor else ""),
        "pitch_class": pitch_class,
        "minor": minor,
        "mode": "minor" if minor else "major",
    }


def _tempo(value):
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 20 <= float(value) <= 999
    ):
        raise ValueError("tempo must be a BPM from 20 to 999")
    return float(value)


def _changes(value):
    if value is None:
        return []
    if not isinstance(value, list) or any(
        not isinstance(item, str) or item not in FEEDBACK for item in value
    ):
        raise ValueError("changes must be names from %s" % sorted(FEEDBACK))
    if len(set(value)) != len(value):
        raise ValueError("changes must be distinct")
    return list(value)


def _config(raw):
    if not isinstance(raw, dict):
        raise ValueError("config must be an object")
    genre = _genre(raw.get("genre"))
    redirected = _redirect(genre)
    if redirected is not None:
        return None, redirected
    tempo = _tempo(raw.get("tempo"))
    apply_tempo = raw.get("apply_tempo", False)
    if apply_tempo is not False and apply_tempo is not True:
        raise ValueError("apply_tempo must be true or false")
    if apply_tempo and tempo is None:
        raise ValueError("apply_tempo requires tempo")
    locked = raw.get("locked_sections") or []
    if not isinstance(locked, list) or any(
        not isinstance(item, str) or not item for item in locked
    ):
        raise ValueError("locked_sections must be section names")
    return {
        "genre": genre,
        "energy": _energy(raw.get("energy")),
        "key": raw.get("key"),
        "bars": _bars(raw.get("bars")),
        "tempo": tempo,
        "apply_tempo": apply_tempo,
        "changes": _changes(raw.get("changes")),
        "locked_sections": list(dict.fromkeys(locked)),
    }, None


def _note(pitch, start, duration, velocity):
    if duration <= 0:
        return None
    return {
        "pitch": int(pitch),
        "start_time": float(start),
        "duration": float(duration),
        "velocity": int(velocity),
        "mute": False,
    }


def _groove(energy, changes):
    hats = energy != "low"
    hat_step = 0.5 if energy == "high" else 1.0
    velocity = {"low": 78, "medium": 96, "high": 112}[energy]
    chord_beats = 4.0
    chord_shift = 0
    for change in changes:
        if change == "more_space":
            hats = False
            chord_beats = 1.0
        elif change == "more_energy":
            hats = True
            hat_step = 0.5
            velocity = min(124, velocity + 16)
        elif change == "darker":
            chord_shift = -12
        elif change == "brighter":
            chord_shift = 12
    return {
        "hats": hats,
        "hat_step": hat_step,
        "velocity": velocity,
        "chord_beats": chord_beats,
        "chord_shift": chord_shift,
    }


def _placed(key_pc, interval, center, shift):
    return center + ((key_pc + interval) % 12) + shift


def _triad(root, minor):
    third = 3 if minor else 4
    return (root, root + third, root + 7)


def _sections(bars):
    cursor = 0
    rows = []
    for name, length, thin in FORMS[bars]:
        rows.append(
            {
                "name": name,
                "bars": length,
                "start_beat": cursor,
                "thin": thin,
                "end_beat": cursor + length * 4,
            }
        )
        cursor += length * 4
    return rows


def _chords_for(key, groove):
    pattern = MINOR if key["minor"] else MAJOR
    return [(root, _triad(root, minor), groove["chord_shift"]) for root, minor in pattern]


def _render(config, key):
    groove = _groove(config["energy"], config["changes"])
    sections = _sections(config["bars"])
    drums, bass, chords, lead = [], [], [], []
    progression = _chords_for(key, groove)
    for section in sections:
        _section_notes(config, key, groove, section, progression, drums, bass, chords, lead)
    tracks = [
        {"name": "Drums", "role": "drums", "notes": drums},
        {"name": "Bass", "role": "bass", "notes": bass},
        {"name": "Chords", "role": "chords", "notes": chords},
    ]
    if config["energy"] == "high":
        tracks.append({"name": "Lead", "role": "lead", "notes": lead})
    return sections, tracks, groove


def _section_notes(config, key, groove, section, progression, drums, bass, chords, lead):
    genre = config["genre"]
    start = section["start_beat"]
    total = section["end_beat"] - start
    kicks = (0,) if section["thin"] else KICKS[genre]
    for bar in range(section["bars"]):
        origin = start + bar * 4
        for offset in kicks:
            drums.append(_note(36, origin + offset, 0.25, groove["velocity"]))
        if section["thin"]:
            continue
        for offset in (1, 3):
            drums.append(_note(38, origin + offset, 0.25, max(1, groove["velocity"] - 8)))
        if groove["hats"]:
            step = groove["hat_step"]
            cursor = 0.0
            while cursor < 4 - 1e-9:
                drums.append(_note(42, origin + cursor, 0.25, max(1, groove["velocity"] - 18)))
                cursor += step
    slot = total if section["thin"] else 8
    position = 0
    index = 0
    while position < total - 1e-9:
        root, tones, shift = progression[index % len(progression)]
        width = min(slot, total - position)
        duration = min(groove["chord_beats"], width)
        origin = start + position
        for tone in tones:
            chords.append(
                _note(
                    _placed(key["pitch_class"], tone, 60, shift),
                    origin,
                    duration,
                    groove["velocity"],
                )
            )
        if config["energy"] == "high" and not section["thin"]:
            lead.append(
                _note(
                    _placed(key["pitch_class"], root, 72, shift),
                    origin,
                    duration,
                    groove["velocity"],
                )
            )
        if section["thin"]:
            bass.append(
                _note(
                    _placed(key["pitch_class"], root, 36, 0),
                    origin,
                    min(2.0, width),
                    groove["velocity"],
                )
            )
        else:
            for hit_start, hit_length in _bass_hits(genre, origin, width):
                bass.append(
                    _note(
                        _placed(key["pitch_class"], root, 36, 0),
                        hit_start,
                        hit_length,
                        groove["velocity"],
                    )
                )
        position += width
        index += 1


def _bass_hits(genre, origin, width):
    if genre == "house":
        hits = []
        cursor = 0.5
        while cursor < width:
            hits.append((origin + cursor, min(0.5, width - cursor)))
            cursor += 1.0
        return hits
    if genre == "hip_hop":
        return [(origin, min(1.5, width)), (origin + width / 2.0, min(1.0, width / 2.0))]
    if genre == "pop":
        return [(origin, min(1.5, width))]
    return [(origin, min(3.5, width))]


def _body(plan):
    return {
        "apply_tempo": plan["apply_tempo"],
        "bars": plan["bars"],
        "changes": plan["changes"],
        "cues": plan["cues"],
        "energy": plan["energy"],
        "genre": plan["genre"],
        "key": plan["key"],
        "locked_sections": plan["locked_sections"],
        "tempo": plan["tempo"],
        "tracks": plan["tracks"],
    }


def _fingerprint(plan):
    encoded = json.dumps(_body(plan), sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def plan_draft(raw):
    config, redirected = _config(raw)
    if redirected is not None:
        return redirected
    key = _key(config["key"])
    sections, tracks, groove = _render(config, key)
    cues = [{"name": section["name"], "time": section["start_beat"]} for section in sections]
    names = [track["name"] for track in tracks]
    plan = {
        "schema_version": 1,
        "status": "planned",
        "live_changes": False,
        "playback_started": False,
        "genre": config["genre"],
        "energy": config["energy"],
        "key": key,
        "bars": config["bars"],
        "meter": [4, 4],
        "tempo": config["tempo"],
        "apply_tempo": config["apply_tempo"],
        "changes": config["changes"],
        "locked_sections": config["locked_sections"],
        "length_beats": config["bars"] * 4,
        "sections": sections,
        "cues": cues,
        "tracks": tracks,
        "config": config,
        "drum_pitches": {
            "kick": 36,
            "snare": 38,
            "hat": 42,
            "evidence": "General MIDI guesses. Confirm the kit with get_drum_pads before trusting these pitches.",
        },
        "brief": {
            "genre": config["genre"],
            "mood": config["energy"],
            "bpm": config["tempo"],
            "key": key["name"],
            "mode": key["mode"],
            "form": [section["name"] for section in sections],
            "section_lengths_bars": [section["bars"] for section in sections],
            "instruments": names,
            "vocal_plan": "No vocal lane in this sketch.",
            "mix_target": "Leave headroom. This sketch does not set mixer levels.",
            "groove": groove,
            "constraints": [
                "4/4 only.",
                "Do not start playback unless the user asks.",
                "Do not delete or overwrite Arrangement clips.",
                "Do not change the time signature.",
                "Confirm drum pitches with get_drum_pads.",
            ],
        },
    }
    plan["fingerprint"] = _fingerprint(plan)
    return plan


def guide_draft(answers=None):
    """Ask at most three questions, then return a plan. No Live writes."""
    answers = {} if answers is None else answers
    if not isinstance(answers, dict):
        raise ValueError("answers must be an object")
    if "genre" in answers:
        genre = _genre(answers.get("genre"))
        redirected = _redirect(genre)
        if redirected is not None:
            redirected["answers"] = dict(answers)
            return redirected
    pending = []
    if "genre" not in answers:
        pending.append(
            {
                "field": "genre",
                "question": "Which sketch should this be: house, hip_hop, pop, or melodic?",
                "choices": list(GENRES),
            }
        )
    if "energy" not in answers:
        pending.append(
            {
                "field": "energy",
                "question": "What energy should the sketch use: low, medium, or high?",
                "choices": list(ENERGIES),
            }
        )
    if "key" not in answers:
        pending.append(
            {
                "field": "key",
                "question": "What key should the sketch use? Examples: C, Am, F#m, Bb.",
                "choices": ["C", "Am", "F#m", "Bb"],
            }
        )
    if pending:
        return {
            "status": "gather_decisions",
            "questions": pending[:3],
            "answers": dict(answers),
            "live_changes": False,
            "playback_started": False,
            "next_action": "Answer the missing fields. bars is optional: 16, 32 or 64, and 32 is the default.",
        }
    plan = plan_draft(answers)
    return {
        "status": plan["status"],
        "questions": [],
        "plan": plan,
        "answers": dict(answers),
        "live_changes": False,
        "playback_started": False,
        "next_action": (
            "apply_song_draft writes this sketch. It refuses playback and does not start "
            "the transport. Pass confirm=false to preview. Check drum pitches with get_drum_pads."
        ),
    }


def _section_map(plan):
    return {section["name"]: section for section in plan["sections"]}


def _keep_locked(previous, revised):
    locked = previous.get("locked_sections") or []
    if not locked:
        return revised
    old = _section_map(previous)
    new = _section_map(revised)
    for name in locked:
        if name not in old or name not in new:
            raise ValueError("locked section %s is not in the revised form; unlock it first" % name)
        before, after = old[name], new[name]
        if before["start_beat"] != after["start_beat"] or before["bars"] != after["bars"]:
            raise ValueError("locked section %s moved; unlock it before changing the form" % name)
        start, end = before["start_beat"], before["end_beat"]
        for old_track, new_track in zip(previous["tracks"], revised["tracks"], strict=True):
            if old_track["role"] != new_track["role"]:
                raise ValueError("locked section %s cannot be kept across a role change" % name)
            kept = [note for note in old_track["notes"] if start <= note["start_time"] < end]
            rest = [note for note in new_track["notes"] if not start <= note["start_time"] < end]
            new_track["notes"] = sorted(
                kept + rest, key=lambda note: (note["start_time"], note["pitch"])
            )
    revised["locked_sections"] = list(locked)
    revised["fingerprint"] = _fingerprint(revised)
    return revised


def refine_draft(plan, feedback):
    if not isinstance(plan, dict) or plan.get("status") != "planned":
        raise ValueError("refine a planned song draft")
    if not isinstance(feedback, list) or not 1 <= len(feedback) <= len(FEEDBACK):
        raise ValueError("feedback needs 1..%d supported names" % len(FEEDBACK))
    if any(not isinstance(item, str) or item not in FEEDBACK for item in feedback) or len(
        set(feedback)
    ) != len(feedback):
        raise ValueError("feedback must be distinct names from %s" % sorted(FEEDBACK))
    config = dict(plan["config"])
    bars = config["bars"]
    kept = list(config.get("changes") or [])
    for issue in feedback:
        if issue == "shorter":
            bars = 16
        elif issue == "longer":
            bars = 64 if bars >= 32 else 32
        elif issue in kept:
            continue
        else:
            kept.append(issue)
    config["bars"] = bars
    config["changes"] = kept
    config["locked_sections"] = list(plan.get("locked_sections") or [])
    revised = plan_draft(config)
    revised = _keep_locked(plan, revised)
    revised["refined_from"] = plan.get("fingerprint")
    revised["live_changes"] = False
    return {
        "config": revised["config"],
        "plan": revised,
        "changes": [dict(issue=issue, reason=FEEDBACK[issue]) for issue in feedback],
        "live_changes": False,
        "playback_started": False,
        "evidence": "Explicit sketch rules. This does not listen to audio or train on the set.",
    }


def _check_notes(plan):
    if plan.get("fingerprint") != _fingerprint(plan):
        raise ValueError("plan was edited; plan again before applying")
    if plan.get("meter") != [4, 4]:
        raise ValueError("song drafts are 4/4 only")
    length = plan["length_beats"]
    for track in plan["tracks"]:
        if track["name"] not in {"Drums", "Bass", "Chords", "Lead"}:
            raise ValueError("unexpected draft track name")
        for note in track["notes"]:
            pitch = note.get("pitch")
            start = note.get("start_time")
            duration = note.get("duration")
            if isinstance(pitch, bool) or not isinstance(pitch, int) or not 0 <= pitch <= 127:
                raise ValueError("note pitch is outside 0..127")
            if not isinstance(start, (int, float)) or not isinstance(duration, (int, float)):
                raise ValueError("note times must be beats")
            if start < 0 or start + duration > length + 1e-6:
                raise ValueError("a draft note falls outside the clip")


def _track_count(session):
    count = session.get("track_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise RuntimeError("get_session_info returned no track_count; inspect Live before retrying")
    return count


def _track_commands(track, index, length):
    """Commands cannot read earlier results inside one batch, so the index is predicted."""
    return [
        {"type": "create_midi_track", "params": {"index": -1}},
        {"type": "set_track_name", "params": {"track_index": index, "name": track["name"]}},
        {
            "type": "create_clip",
            "params": {"track_index": index, "clip_index": 0, "length": length},
        },
        {
            "type": "set_clip_name",
            "params": {"track_index": index, "clip_index": 0, "name": track["name"]},
        },
        {
            "type": "add_notes_to_clip",
            "params": {"track_index": index, "clip_index": 0, "notes": track["notes"]},
        },
    ]


def _revert_batch(dispatch):
    try:
        dispatch("undo", {})
    except Exception as error:
        raise RuntimeError(
            "song draft apply failed and undo did not complete; inspect Live"
        ) from error


def _created_tracks(batch, commands, plan, predicted):
    results = batch.get("results") if isinstance(batch, dict) else None
    if not isinstance(results, list) or len(results) != len(commands):
        raise RuntimeError("song draft batch returned no results; inspect Live")
    expected = [command["type"] for command in commands]
    made = []
    for item, kind in zip(results, expected, strict=True):
        if not isinstance(item, dict) or item.get("type") != kind:
            raise RuntimeError("song draft batch returned no results; inspect Live")
        if kind != "create_midi_track":
            continue
        result = item.get("result")
        index = result.get("index") if isinstance(result, dict) else None
        if isinstance(index, bool) or not isinstance(index, int):
            index = result.get("track_index") if isinstance(result, dict) else None
        if isinstance(index, bool) or not isinstance(index, int):
            raise RuntimeError("create_midi_track returned no track index; the apply was undone")
        made.append(index)
    if made != predicted:
        raise RuntimeError(
            "create_midi_track index did not match the predicted end of the song; "
            "the apply was undone"
        )
    return [
        {"track_index": index, "name": track["name"], "notes": len(track["notes"])}
        for track, index in zip(plan["tracks"], made, strict=True)
    ]


def _locator_times(payload):
    rows = payload.get("locators") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("get_locators did not return locators; inspect Live")
    times = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        beat = row.get("time")
        if isinstance(beat, bool) or not isinstance(beat, (int, float)):
            continue
        times.append(float(beat))
    return times


def _locator_exists(times, beat):
    return any(abs(time - beat) < 1e-3 for time in times)


def apply_draft(dispatch, plan, confirm=True):
    if confirm is not True:
        return {"applied": False, "live_changes": False, "playback_started": False}
    if not isinstance(plan, dict) or plan.get("status") != "planned":
        raise ValueError("only a planned song draft can be applied")
    _check_notes(plan)
    session = dispatch("get_session_info", {})
    if session.get("is_playing") or session.get("record_mode"):
        raise ValueError("Stop playback before applying a song draft")
    if [session.get("signature_numerator"), session.get("signature_denominator")] != [4, 4]:
        raise ValueError("song drafts do not change the meter; set the song to 4/4 first")
    if session.get("scene_count", 1) < 1:
        raise ValueError("Add a Session scene before applying a song draft")
    track_count = _track_count(session)
    commands = []
    if plan.get("apply_tempo"):
        commands.append({"type": "set_tempo", "params": {"tempo": plan["tempo"]}})
    predicted = []
    for offset, track in enumerate(plan["tracks"]):
        index = track_count + offset
        predicted.append(index)
        commands.extend(_track_commands(track, index, plan["length_beats"]))
    try:
        batch = dispatch("batch", {"commands": commands})
        created = _created_tracks(batch, commands, plan, predicted)
    except Exception:
        # The bridge closes the batch undo step without reverting it. Another
        # client can still land a command between this failure and the undo.
        _revert_batch(dispatch)
        raise
    previous = session.get("current_song_time", 0)
    occupied = _locator_times(dispatch("get_locators", {}))
    locators = []
    skipped = []
    try:
        for cue in plan["cues"]:
            beat = float(cue["time"])
            if _locator_exists(occupied, beat):
                skipped.append(beat)
                continue
            dispatch("set_current_song_time", {"time": beat})
            locators.append(dispatch("create_locator", {"name": cue["name"]}))
    finally:
        if isinstance(previous, (int, float)) and not isinstance(previous, bool):
            dispatch("set_current_song_time", {"time": previous})
    return {
        "applied": True,
        "playback_started": False,
        "live_changes": True,
        "tracks": created,
        "locators": locators,
        "locators_skipped": skipped,
        "tempo_changed": bool(plan.get("apply_tempo")),
        "drum_pitches": plan["drum_pitches"],
        "undo": (
            "Tracks, clips and notes are one undo step. "
            "Locators are separate commands and are not locked against another client."
        ),
    }


def register_song_draft(mcp, dispatch):
    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def describe_tool_families() -> dict:
        """Group the arrangement, rack, plugin-alias and song-draft tools with the
        existing names. Read-only map, not a full catalog and not a rename.
        """
        return tool_families()

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def guide_song_draft(answers: dict | None = None) -> dict:
        """Ask at most three questions (genre, energy, key), then return a 4/4 sketch.
        Genres are house, hip_hop, pop and melodic. Dubstep, riddim and half-time
        redirect to guide_halftime_remix_workflow. No Live writes and no playback.
        """
        return guide_draft(answers)

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def plan_song_draft(config: dict) -> dict:
        """Optional preview of a 16, 32 or 64 bar Session sketch in 4/4. Role tracks
        are Drums, Bass, Chords, and Lead when energy is high. Drum pitches are
        General MIDI guesses: check them with get_drum_pads. No Live writes.
        """
        return plan_draft(config)

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def refine_song_draft(plan: dict, feedback: list[str]) -> dict:
        """Revise a sketch: more_space, more_energy, darker, brighter, shorter, longer.
        Locked sections keep their notes when the form still holds them. Read-only.
        """
        return refine_draft(plan, feedback)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def apply_song_draft(plan: dict, confirm: bool = True) -> dict:
        """Create the planned MIDI tracks at the end of the song, one Session clip
        each, and Arrangement locators that are not already within 0.001 beats.
        Writes unless confirm is false. Refuses while the transport plays or the
        meter is not 4/4. Does not start playback, delete Arrangement clips, rename
        an existing locator, or change the meter. Tempo changes only when the plan
        sets apply_tempo. Tracks, clips and notes are one undo step. Locators
        are separate commands.
        """
        return apply_draft(dispatch, plan, confirm)
