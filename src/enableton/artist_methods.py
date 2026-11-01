"""Artist research with explicit separation between evidence and original patches."""

from copy import deepcopy
import json
from pathlib import Path

DATA = json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8-sig"))
ALIASES = {
    "all": "all",
    "alleycvt": "alleycvt",
    "alleycat": "alleycvt",
    "subtronics": "subtronics",
    "vulper": "vulper",
    "volpetron": "ray-volpe",
    "ray volpe": "ray-volpe",
    "ray-volpe": "ray-volpe",
    "ray_volpe": "ray-volpe",
    "rayvolpe": "ray-volpe",
}


def catalog(artist="all"):
    if not isinstance(artist, str) or artist.strip().lower() not in ALIASES:
        raise ValueError(
            "Unknown artist. Choose ALLEYCVT, Subtronics, VULPER, Ray Volpe / Volpetron, or all."
        )
    selected = ALIASES[artist.strip().lower()]
    profiles = [
        deepcopy(p) for key, p in DATA["artists"].items() if selected == "all" or key == selected
    ]
    from .bass_recipes import get_recipe

    for profile in profiles:
        profile["native_recipes"] = [
            get_recipe(key) for key, p in DATA["patches"].items() if p["artist"] == profile["id"]
        ]
    return {
        "artists": profiles,
        "sources": deepcopy(DATA["sources"]),
        "limits": "Artist interviews establish only the documented findings. All native patches, numeric starting points and example procedures are original adaptations, not artist presets or track reconstructions. No audio was auditioned or analyzed.",
        "execution": "Read-only catalog. Native patches can be built separately with create_native_bass. Manual workflows do not automatically create vocal chops, audio resampling, delays, granular routing or arrangement.",
    }
