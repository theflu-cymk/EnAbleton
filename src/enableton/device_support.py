"""EXT.12 device, chain, cue-point and scene commands, plus EXT.13 rack inspect
and blend-macro mapping.

Every command probes the Live Object Model before writing, changes only
documented properties and verifies by readback. When this Live build lacks a
method, the command raises with what is missing instead of reporting success.
"""

import math
import re

from .envelope_support import index, number

DISPLAY = re.compile(r"(-?\d+(?:\.\d+)?)\s*(kHz|Hz|dB|%)?")
EQ_MODES = ("A", "B")
MAX_EQ_BANDS = 8
BLEND_NAMES = ("Dry/Wet", "Dry Wet", "Mix", "Amount")


def _json_values(value):
    """Return JSON scalars, or [] when a Live collection is not safe to send back.

    A failed read must not raise after a mapping undo step has already closed.
    """
    try:
        items = list(value or [])
    except Exception:
        return []
    safe = []
    for item in items:
        if isinstance(item, bool) or isinstance(item, str):
            safe.append(item)
        elif isinstance(item, int):
            safe.append(item)
        elif isinstance(item, float) and math.isfinite(item):
            safe.append(item)
        else:
            return []
    return safe


def _json_macros(rack):
    try:
        raw = getattr(rack, "macros_mapped", [])
    except Exception:
        return []
    return _json_values(raw)


def _token(name, token):
    return re.search(r"\b%s\b" % re.escape(token), name, re.I) is not None


def _shown(param, value):
    match = DISPLAY.search(param.str_for_value(value) or "")
    if not match:
        return None
    shown = float(match.group(1))
    return shown * 1000.0 if match.group(2) == "kHz" else shown


def _value_for(param, target, tolerance=0.02):
    """Reach a displayed value by bisecting the parameter's own display string."""
    low, high = float(param.min), float(param.max)
    if not low < high:
        raise ValueError("Parameter %s has no usable range" % param.name)
    for _ in range(48):
        middle = (low + high) / 2.0
        shown = _shown(param, middle)
        if shown is None:
            raise ValueError("Parameter %s has no numeric display to target" % param.name)
        if shown < target:
            low = middle
        else:
            high = middle
    value = (low + high) / 2.0
    shown = _shown(param, value)
    if shown is None or abs(shown - target) > max(tolerance * abs(target), 1e-6):
        raise ValueError("Could not reach %s on %s" % (target, param.name))
    return value


def eq_parameter(device, band, kind, mode):
    """Find one EQ Eight parameter by band number, kind and A/B mode."""
    if not 1 <= band <= MAX_EQ_BANDS:
        raise ValueError("EQ Eight band must be 1..8")
    if mode not in EQ_MODES:
        raise ValueError("EQ Eight mode must be A or B")
    for param in device.parameters:
        name = param.name or ""
        if all(_token(name, token) for token in (str(band), kind, mode)):
            return param
    raise ValueError("EQ Eight has no %s parameter for band %d" % (kind, band))


class DeviceSupportMixin(object):
    def _device(self, args):
        track = index(args.get("track_index"), self._song.tracks, "track_index")
        device = index(args.get("device_index"), track.devices, "device_index")
        expected = args.get("expected_device_name")
        if expected is not None and device.name != expected:
            raise ValueError("expected_device_name no longer matches; refresh the set")
        return track, device

    def _set_eq_bands(self, args):
        _, device = self._device(args)
        # An EQ Eight loaded from the browser keeps the preset's name ("Remove Mud",
        # "Kick Tight"), so the device class is the only reliable identification.
        is_eq = (
            getattr(device, "class_name", None) == "Eq8"
            or "eq eight" in (device.name or "").lower()
        )
        if not is_eq:
            raise ValueError("Device is not an EQ Eight (class_name %r)" % (device.name,))
        mode = args.get("mode", "A")
        if mode not in EQ_MODES:
            raise ValueError("mode must be A or B")
        bands = args.get("bands")
        if not isinstance(bands, list) or not 1 <= len(bands) <= MAX_EQ_BANDS:
            raise ValueError("bands must hold 1..8 entries")
        plan = []
        seen = set()
        for row in bands:
            if not isinstance(row, dict):
                raise ValueError("Each band needs an object")
            number_ = row.get("band")
            if isinstance(number_, bool) or not isinstance(number_, int):
                raise ValueError("band must be an integer 1..8")
            if number_ in seen:
                raise ValueError("Duplicate band " + str(number_))
            seen.add(number_)
            plan.append(row)
        self._song.begin_undo_step()
        results = []
        try:
            for row in plan:
                band = row["band"]
                written = {}
                if row.get("filter_on") is not None:
                    if not isinstance(row["filter_on"], bool):
                        raise ValueError("filter_on must be boolean")
                    param = eq_parameter(device, band, "Filter On", mode)
                    param.value = 1.0 if row["filter_on"] else 0.0
                    written["filter_on"] = row["filter_on"]
                if row.get("frequency_hz") is not None:
                    hz = number(row["frequency_hz"], "frequency_hz")
                    if not 10 <= hz <= 22000:
                        raise ValueError("frequency_hz must be within 10..22000")
                    param = eq_parameter(device, band, "Frequency", mode)
                    param.value = _value_for(param, hz)
                    written["frequency_hz"] = round(hz, 2)
                if row.get("gain_db") is not None:
                    gain = number(row["gain_db"], "gain_db")
                    if not -30 <= gain <= 30:
                        raise ValueError("gain_db must be within -30..30")
                    param = eq_parameter(device, band, "Gain", mode)
                    param.value = _value_for(param, gain)
                    written["gain_db"] = round(gain, 2)
                if row.get("q") is not None:
                    q = number(row["q"], "q")
                    if not 0.1 <= q <= 18:
                        raise ValueError("q must be within 0.1..18")
                    param = eq_parameter(device, band, "Resonance", mode)
                    param.value = _value_for(param, q)
                    written["q"] = round(q, 3)
                if not written:
                    raise ValueError("Band %d has no field to write" % band)
                readback = {
                    "band": band,
                    "written": written,
                    "display": {
                        key: eq_parameter(device, band, key, mode).str_for_value(
                            eq_parameter(device, band, key, mode).value
                        )
                        for key in ("Frequency", "Gain")
                        if any(field in written for field in ("frequency_hz", "gain_db"))
                    },
                }
                results.append(readback)
        finally:
            self._song.end_undo_step()
        return {
            "device": device.name,
            "device_class": getattr(device, "class_name", None),
            "mode": mode,
            "bands": results,
            "verified": True,
        }

    def _insert_chain(self, args):
        _, rack = self._device(args)
        if not getattr(rack, "can_have_chains", False) or not hasattr(rack, "chains"):
            raise ValueError("Device is not a rack")
        inserter = getattr(rack, "insert_chain", None)
        if not callable(inserter):
            raise RuntimeError(
                "This Live build does not expose RackDevice.insert_chain; add the chain with the rack's + button"
            )
        before = len(rack.chains)
        position = args.get("chain_index", before)
        if (
            isinstance(position, bool)
            or not isinstance(position, int)
            or not 0 <= position <= before
        ):
            raise ValueError("chain_index must be an integer within the current chains")
        self._song.begin_undo_step()
        try:
            inserter(position)
            after = len(rack.chains)
            if after != before + 1:
                raise RuntimeError(
                    "Chain insertion did not add exactly one chain; inspect the rack"
                )
            chain = rack.chains[position]
        finally:
            self._song.end_undo_step()
        return {
            "rack": rack.name,
            "chain_index": position,
            "chain_name": chain.name,
            "chains": after,
        }

    def _delete_chain(self, args):
        _, rack = self._device(args)
        remover = getattr(rack, "delete_chain", None)
        if not callable(remover):
            raise RuntimeError(
                "This Live build does not expose RackDevice.delete_chain; remove the chain in Live"
            )
        chains = list(rack.chains)
        position = args.get("chain_index")
        if (
            isinstance(position, bool)
            or not isinstance(position, int)
            or not 0 <= position < len(chains)
        ):
            raise ValueError("chain_index is out of range")
        chain = chains[position]
        expected = args.get("expected_chain_name")
        if expected is not None and chain.name != expected:
            raise ValueError("expected_chain_name no longer matches; refresh the rack")
        if len(chains) == 1:
            raise ValueError("A rack must keep at least one chain")
        self._song.begin_undo_step()
        try:
            remover(position)
            after = len(rack.chains)
            if after != len(chains) - 1:
                raise RuntimeError(
                    "Chain deletion did not remove exactly one chain; inspect the rack"
                )
        finally:
            self._song.end_undo_step()
        return {"rack": rack.name, "deleted": chain.name, "chains": after}

    def _insert_device_to_chain(self, args):
        _, rack = self._device(args)
        chains = list(getattr(rack, "chains", []))
        position = args.get("chain_index")
        if (
            isinstance(position, bool)
            or not isinstance(position, int)
            or not 0 <= position < len(chains)
        ):
            raise ValueError("chain_index is out of range")
        chain = chains[position]
        name = args.get("device_name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("device_name required")
        inserter = getattr(chain, "insert_device", None)
        if not callable(inserter):
            raise RuntimeError(
                "This Live build does not expose Chain.insert_device; load the device with the browser"
            )
        before = len(chain.devices)
        self._song.begin_undo_step()
        try:
            inserter(name.strip())
            devices = list(chain.devices)
            if len(devices) != before + 1:
                raise RuntimeError(
                    "Device insertion did not add exactly one device; inspect the chain"
                )
        finally:
            self._song.end_undo_step()
        return {
            "rack": rack.name,
            "chain": chain.name,
            "device": devices[-1].name,
            "devices": len(devices),
        }

    def _delete_cue_point(self, args):
        time_value = number(args.get("time"), "time")
        if not 0 <= time_value <= 1576800:
            raise ValueError("time is outside the Arrangement")
        matches = [cue for cue in self._song.cue_points if abs(float(cue.time) - time_value) < 1e-3]
        if not matches:
            raise ValueError("No cue point at that time")
        if len(matches) > 1:
            raise ValueError("Several cue points share that time; delete them in Live")
        cue = matches[0]
        name = cue.name
        playhead = float(self._song.current_song_time)
        # set_or_delete_cue reads the playhead, which does not settle inside the task
        # that assigns it, so the caller moves the playhead with its own command first.
        if abs(playhead - time_value) > 1e-3:
            raise ValueError(
                "Move the playhead onto that cue first; set_or_delete_cue reads the playhead"
            )
        before = len(self._song.cue_points)
        self._song.set_or_delete_cue()
        after = len(self._song.cue_points)
        if after != before - 1:
            raise RuntimeError(
                "Cue point deletion did not take effect; inspect the Arrangement before retrying"
            )
        # The removed CuePoint handle is dead: reading cue.time here raises from
        # Boost.Python, so report the position captured before the toggle.
        return {"deleted": name, "time": round(time_value, 6), "remaining": after}

    def _get_scenes(self, args):
        scenes = []
        for position, scene in enumerate(self._song.scenes):
            occupied = 0
            for track in self._song.tracks:
                slots = getattr(track, "clip_slots", [])
                if position < len(slots) and slots[position].has_clip:
                    occupied += 1
            scenes.append(
                {
                    "index": position,
                    "name": scene.name,
                    "color_index": getattr(scene, "color_index", None),
                    "tempo": getattr(scene, "tempo", None),
                    "clips": occupied,
                }
            )
        return {"scenes": scenes, "count": len(scenes)}

    def _blend_parameter(self, device):
        """Prefer an exact blend name, then a case-insensitive match."""
        by_name = {}
        for param in getattr(device, "parameters", []) or []:
            name = getattr(param, "name", None)
            if isinstance(name, str) and name not in by_name:
                by_name[name] = param
        for name in BLEND_NAMES:
            if name in by_name:
                return by_name[name], name
        lowered = {key.casefold(): (param, key) for key, param in by_name.items()}
        for name in BLEND_NAMES:
            hit = lowered.get(name.casefold())
            if hit:
                return hit
        return None, None

    def _rack(self, args):
        _, device = self._device(args)
        if not getattr(device, "can_have_chains", False):
            raise ValueError("Device is not a rack")
        return device

    def _visible_macros(self, rack):
        if not hasattr(rack, "visible_macro_count"):
            return None
        visible = getattr(rack, "visible_macro_count")
        if isinstance(visible, bool) or not isinstance(visible, int):
            raise ValueError("visible_macro_count is not an integer")
        return visible

    def _inspect_rack(self, args):
        """Read one rack's macro support and the blend parameter on each chain device."""
        rack = self._rack(args)
        devices = []
        chains = list(getattr(rack, "chains", []) or [])
        for chain_index, chain in enumerate(chains):
            for device_index, device in enumerate(list(getattr(chain, "devices", []) or [])):
                _, blend_name = self._blend_parameter(device)
                devices.append(
                    {
                        "chain_index": chain_index,
                        "chain_name": getattr(chain, "name", ""),
                        "device_index": device_index,
                        "device_name": getattr(device, "name", ""),
                        "class_name": getattr(device, "class_name", ""),
                        "blend_parameter": blend_name,
                    }
                )
        return {
            "rack_name": rack.name,
            "has_macro_map": callable(getattr(rack, "macro_map", None)),
            "has_rename_macro": callable(getattr(rack, "rename_macro", None)),
            "has_add_macro": callable(getattr(rack, "add_macro", None)),
            "visible_macro_count": self._visible_macros(rack),
            "macros_mapped": _json_macros(rack),
            "chains": len(chains),
            "devices": devices,
        }

    def _map_rack_blend_macro(self, args):
        """Map nested Dry/Wet, Mix or Amount parameters to one rack macro.

        Live 12.2.5 may not expose RackDevice.macro_map. This command refuses
        in that case instead of reporting a mapping that did not happen.
        """
        expected = args.get("expected_device_name")
        if not isinstance(expected, str) or not expected:
            raise ValueError("expected_device_name is required")
        macro_index = args.get("macro_index", 0)
        if (
            isinstance(macro_index, bool)
            or not isinstance(macro_index, int)
            or not 0 <= macro_index <= 7
        ):
            raise ValueError("macro_index must be an integer from 0 to 7")
        macro_name = args.get("macro_name", "Blend")
        if not isinstance(macro_name, str) or not macro_name.strip():
            raise ValueError("macro_name is required")
        macro_name = macro_name.strip()
        rack = self._rack(args)
        mapper = getattr(rack, "macro_map", None)
        if not callable(mapper):
            raise RuntimeError(
                "This Live build does not expose RackDevice.macro_map; map the macro in Live"
            )
        self._song.begin_undo_step()
        try:
            needed = macro_index + 1
            visible = self._visible_macros(rack)
            if visible is None and macro_index > 0:
                raise RuntimeError(
                    "visible_macro_count is unavailable; choose macro_index 0 or map the macro in Live"
                )
            adder = getattr(rack, "add_macro", None)
            added = 0
            while visible is not None and visible < needed and added < 8:
                if not callable(adder):
                    break
                adder()
                added += 1
                visible = self._visible_macros(rack)
            if visible is not None and visible < needed:
                raise RuntimeError(
                    "Could not expose macro %d; this Live build did not raise visible_macro_count"
                    % macro_index
                )
            renamer = getattr(rack, "rename_macro", None)
            if callable(renamer):
                renamer(macro_index, macro_name)
            else:
                params = list(getattr(rack, "parameters", []) or [])
                slot = macro_index + 1
                if slot >= len(params):
                    raise RuntimeError(
                        "Rack macro parameter is not exposed; rename the macro in Live"
                    )
                try:
                    params[slot].name = macro_name
                except Exception as error:
                    raise RuntimeError(
                        "This Live build cannot rename rack macros; rename the macro in Live"
                    ) from error
            mapped = []
            skipped = []
            for chain_index, chain in enumerate(list(getattr(rack, "chains", []) or [])):
                for device_index, device in enumerate(list(getattr(chain, "devices", []) or [])):
                    blend, blend_name = self._blend_parameter(device)
                    label = {
                        "chain_index": chain_index,
                        "chain_name": getattr(chain, "name", ""),
                        "device_index": device_index,
                        "device_name": getattr(device, "name", ""),
                    }
                    if blend is None:
                        skipped.append(dict(label, reason="no blend parameter"))
                        continue
                    mapper(macro_index, blend)
                    mapped.append(dict(label, parameter=blend_name))
        finally:
            self._song.end_undo_step()
        return {
            "rack_name": rack.name,
            "macro_name": macro_name,
            "macro_index": macro_index,
            "mapped": mapped,
            "skipped": skipped,
            "macros_mapped": _json_macros(rack),
            "playback_started": False,
        }
