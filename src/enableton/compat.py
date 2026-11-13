"""Refuse Live calls when the session reports a Live version below the floor.

`docs/LIMITATIONS.md` and `docs/INSTALLATION.md` already state Ableton Live 12 as
the requirement. This module enforces that stated floor instead of assuming it:
the generated bridge reports the Live build it is running inside, and a build
below it is refused before any command reaches Live.

Only the floor is claimed. Which editions and which 12.x builds work remains
unapproved decision D-2; an unknown or unreadable version is reported as
unverified rather than called unsupported.
"""

MINIMUM_LIVE = (12, 0, 0)
MINIMUM_LIVE_TEXT = "12.0"

REFUSAL = (
    "Ableton Live {reported} is below the supported Live {minimum}. No command "
    "was sent and no set was changed. Update Ableton Live before using the Live "
    "tools; the catalog, recipe and offline tools work without Live."
)


def parse_live_version(value):
    """Return a comparable tuple for ``"12.2.5"``, or None when unreadable."""

    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    numbers = []
    for part in text.split(".")[:3]:
        if not part.isdigit():
            return None
        numbers.append(int(part))
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers)


def evaluate(live_version):
    """Report the floor, what Live said and whether it clears the floor.

    ``supported`` is None when the version is unknown, so a caller never reads
    "not supported" from a value it never received.
    """

    parsed = parse_live_version(live_version)
    return {
        "reported": live_version if isinstance(live_version, str) else "",
        "minimum": MINIMUM_LIVE_TEXT,
        "supported": None if parsed is None else parsed >= MINIMUM_LIVE,
    }


def require_supported(live_version):
    """Raise before a Live call when the reported version is below the floor."""

    if evaluate(live_version)["supported"] is False:
        raise RuntimeError(REFUSAL.format(reported=live_version, minimum=MINIMUM_LIVE_TEXT))
