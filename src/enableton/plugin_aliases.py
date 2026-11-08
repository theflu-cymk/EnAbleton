"""Friendly names for parameters Live already exposes on a configured plugin.

The map is Serum only, and it names Live's short parameter strings. An exact
live name always wins. A friendly name is refused when that control was never
configured on the device. Values stay in the parameter's native range; this
module does not convert a 0..1 guess into Hertz or decibels.
"""

PROFILES = {
    "Serum": {
        "match": "serum",
        "aliases": {
            "wavetable position": "Osc A WT Pos",
            "wavetable position a": "Osc A WT Pos",
            "wavetable position b": "Osc B WT Pos",
            "osc a level": "Osc A Level",
            "osc b level": "Osc B Level",
            "osc a pan": "Osc A Pan",
            "osc b pan": "Osc B Pan",
            "osc a unison": "Osc A Unison",
            "osc b unison": "Osc B Unison",
            "osc a detune": "Osc A UniDet",
            "osc b detune": "Osc B UniDet",
            "osc a octave": "Osc A Oct",
            "osc b octave": "Osc B Oct",
            "osc a semi": "Osc A Semi",
            "osc b semi": "Osc B Semi",
            "osc a fine": "Osc A Fine",
            "osc b fine": "Osc B Fine",
            "filter cutoff": "Fil Cutoff",
            "filter resonance": "Fil Reso",
            "filter drive": "Fil Drive",
            "filter mix": "Fil Mix",
            "filter pan": "Fil Pan",
            "filter fat": "Fil Fat",
            "noise level": "Noise Level",
            "noise pan": "Noise Pan",
            "sub level": "Sub Level",
            "sub pan": "Sub Pan",
            "macro 1": "Macro 1",
            "macro 2": "Macro 2",
            "macro 3": "Macro 3",
            "macro 4": "Macro 4",
            "macro 5": "Macro 5",
            "macro 6": "Macro 6",
            "macro 7": "Macro 7",
            "macro 8": "Macro 8",
            "master volume": "Master Vol",
        },
        "categories": {
            "Oscillator A": ["Osc A"],
            "Oscillator B": ["Osc B"],
            "Filter": ["Fil "],
            "Noise": ["Noise"],
            "Sub": ["Sub "],
            "Envelope": ["Env "],
            "LFO": ["LFO"],
            "Macro": ["Macro"],
            "Effects": ["FX"],
            "Master": ["Master"],
        },
    }
}


def list_aliases(profiles=None):
    table = PROFILES if profiles is None else profiles
    return {
        "profiles": [
            {
                "name": name,
                "match": profile["match"],
                "aliases": dict(profile["aliases"]),
                "categories": {key: list(value) for key, value in profile["categories"].items()},
            }
            for name, profile in table.items()
        ],
        "note": (
            "Aliases name Live's configured parameter strings. "
            "Values stay in each parameter's native range."
        ),
    }


def matching_profiles(device_name, profiles=None):
    table = PROFILES if profiles is None else profiles
    folded = "" if device_name is None else str(device_name).casefold()
    hits = [name for name, profile in table.items() if profile["match"].casefold() in folded]
    if len(hits) > 1:
        raise ValueError("device name matches more than one plugin profile: " + ", ".join(hits))
    return hits


def resolve_name(device_name, requested, live_names, profiles=None):
    """Resolve one requested name against the live parameter list."""
    if not isinstance(requested, str) or not requested.strip():
        raise ValueError("parameter name is required")
    if not isinstance(live_names, list):
        raise ValueError("live parameter names are required")
    folded = {}
    for name in live_names:
        if isinstance(name, str):
            folded.setdefault(name.casefold(), []).append(name)
    exact = folded.get(requested.casefold(), [])
    if len(exact) > 1:
        raise ValueError("parameter name is ambiguous: " + requested)
    if len(exact) == 1:
        return {
            "requested": requested,
            "resolved": exact[0],
            "source": "exact",
            "profile": None,
        }
    hits = matching_profiles(device_name, profiles)
    if not hits:
        raise ValueError(
            "No alias profile matches this device, and no live parameter is named %r. "
            "Use the name shown by get_sound_design_parameters." % requested
        )
    table = PROFILES if profiles is None else profiles
    real = None
    for friendly, target in table[hits[0]]["aliases"].items():
        if friendly.casefold() == requested.casefold():
            real = target
            break
    if real is None:
        raise ValueError(
            "No alias or live parameter is named %r. "
            "Use the name shown by get_sound_design_parameters." % requested
        )
    present = folded.get(real.casefold(), [])
    if len(present) != 1:
        raise ValueError(
            "Alias %r maps to %r, which is not configured on this device. "
            "Open the plugin, click Configure, and add that control." % (requested, real)
        )
    return {
        "requested": requested,
        "resolved": present[0],
        "source": "alias",
        "profile": hits[0],
    }


def _native_value(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value must be the parameter's native number; aliases do not convert 0..1")
    return value


def resolve_live_alias(
    dispatch,
    track_index,
    device_index,
    parameter,
    expected_track_name=None,
    expected_device_name=None,
):
    report = dispatch(
        "get_sound_design_parameters",
        {
            "track_index": track_index,
            "device_index": device_index,
            "expected_track_name": expected_track_name,
            "expected_device_name": expected_device_name,
        },
    )
    names = [row.get("name") for row in report.get("parameters", [])]
    resolved = resolve_name(report.get("device_name"), parameter, names)
    return {
        "track_name": report.get("track_name"),
        "device_name": report.get("device_name"),
        "resolution": resolved,
        "live_changes": False,
    }


def apply_plugin_parameter(
    dispatch,
    track_index,
    device_index,
    parameter,
    value,
    expected_track_name,
    expected_device_name,
):
    if not isinstance(expected_track_name, str) or not expected_track_name:
        raise ValueError("expected_track_name is required")
    if not isinstance(expected_device_name, str) or not expected_device_name:
        raise ValueError("expected_device_name is required")
    native = _native_value(value)
    resolved = resolve_live_alias(
        dispatch,
        track_index,
        device_index,
        parameter,
        expected_track_name,
        expected_device_name,
    )
    written = dispatch(
        "set_sound_design_parameters",
        {
            "track_index": track_index,
            "device_index": device_index,
            "parameters": {resolved["resolution"]["resolved"]: native},
            "expected_track_name": expected_track_name,
            "expected_device_name": expected_device_name,
        },
    )
    written = dict(written)
    written["alias"] = resolved["resolution"]
    written["native_value"] = native
    return written


def register_plugin_aliases(mcp, dispatch):
    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def list_plugin_aliases() -> dict:
        """List the Serum friendly-name map. These are Live parameter strings, not
        stock Ableton device names, and they do not change a value by themselves.
        """
        return list_aliases()

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def resolve_plugin_parameter(
        track_index: int,
        device_index: int,
        parameter: str,
        expected_track_name: str | None = None,
        expected_device_name: str | None = None,
    ) -> dict:
        """Resolve a friendly or exact parameter name against the live device.
        An exact live name wins. A Serum alias is used only when that configured
        control is actually present. Read-only. No 0..1 conversion.
        """
        return resolve_live_alias(
            dispatch,
            track_index,
            device_index,
            parameter,
            expected_track_name,
            expected_device_name,
        )

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def set_plugin_parameter(
        track_index: int,
        device_index: int,
        parameter: str,
        value: float,
        expected_track_name: str,
        expected_device_name: str,
    ) -> dict:
        """Set one plugin parameter by friendly or exact name. The value is the
        parameter's native number from get_sound_design_parameters, not a guessed
        0..1 amount. Resolves the live name, then uses the guarded parameter batch:
        range check, readback and rollback. One Live Undo step.
        """
        return apply_plugin_parameter(
            dispatch,
            track_index,
            device_index,
            parameter,
            value,
            expected_track_name,
            expected_device_name,
        )
