"""Canonical layer naming and colour convention.

Every audio layer gets one role, one short label and one colour index, so that
track names, clip names and colours stay predictable across songs:

    role        label        colour   example track name
    drums       Drums             6   01 Drums
    bass        Bass             20   02 Bass
    guitar      Guitar           22   03 Guitar
    keys        Keys             24   04 Keys
    percussion  Perc             26   05 Perc
    strings     Strings          28   06 Strings
    synth       Synth            30   07 Synth
    woodwinds   Winds            32   08 Winds
    lead_vox    Lead Vox         11   09 Lead Vox
    bg_vox      BG Vox           13   10 BG Vox
    other       Other            60   11 Other

Names are ``NN Label``: two-digit order from 1, a space, then the label. Clips
inherit the label of their track. Colours are Live colour indexes (0..69) and
are unique per role so a glance at the Arrangement groups the layers.
"""

ROLE_LABELS = {
    "drums": "Drums",
    "bass": "Bass",
    "guitar": "Guitar",
    "keys": "Keys",
    "percussion": "Perc",
    "strings": "Strings",
    "synth": "Synth",
    "woodwinds": "Winds",
    "lead_vox": "Lead Vox",
    "bg_vox": "BG Vox",
    "other": "Other",
}

ROLE_COLORS = {
    "drums": 6,
    "bass": 20,
    "guitar": 22,
    "keys": 24,
    "percussion": 26,
    "strings": 28,
    "synth": 30,
    "woodwinds": 32,
    "lead_vox": 11,
    "bg_vox": 13,
    "other": 60,
}

# Longest/most specific match first: "Backing Vocals" must beat "Vocals".
KEYWORDS = (
    ("bg_vox", ("backing", "bgv", "bg vox", "harmon")),
    ("lead_vox", ("lead", "vocal", "vox")),
    ("percussion", ("perc", "shaker", "tamb", "hat")),
    ("woodwinds", ("wind", "flute", "sax", "clarinet")),
    ("strings", ("string", "violin", "cello", "viola")),
    ("drums", ("drum", "kick", "snare", "clap")),
    ("bass", ("bass", "sub")),
    ("guitar", ("guitar", "gtr")),
    ("keys", ("key", "piano", "organ", "rhodes")),
    ("synth", ("synth", "pad", "arp")),
)


def infer_role(name, track_type="audio"):
    """Best-effort role from a track name; unknown audio falls back to ``other``."""

    key = (name or "").casefold()
    for role, words in KEYWORDS:
        if any(word in key for word in words):
            return role
    return "other"


def layer_label(role):
    return ROLE_LABELS.get(role, ROLE_LABELS["other"])


def layer_color(role):
    return ROLE_COLORS.get(role, ROLE_COLORS["other"])


def layer_name(role, index):
    """``index`` starts at 1, giving ``01 Drums`` style names."""

    return f"{int(index):02d} {layer_label(role)}"


def clip_name(role, source_name, index):
    """Clips keep their own identity but gain the ordered layer prefix."""

    label = layer_label(role)
    source = (source_name or "").strip()
    if source and source.casefold() != label.casefold():
        return f"{int(index):02d} {label} | {source}"
    return f"{int(index):02d} {label}"


def plan(tracks):
    """Deterministic rename/colour plan for regular audio tracks, in order."""

    plan_rows = []
    order = 0
    for track in tracks:
        if track.get("is_group") or track.get("is_return") or track.get("is_master"):
            continue
        if track.get("type") != "audio":
            continue
        if not track.get("clips"):
            continue
        order += 1
        role = infer_role(track.get("name"), track.get("type", "audio"))
        plan_rows.append(
            {
                "id": track["id"],
                "role": role,
                "name": layer_name(role, order),
                "color_index": layer_color(role),
            }
        )
    return plan_rows
