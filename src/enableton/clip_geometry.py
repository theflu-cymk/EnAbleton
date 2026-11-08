"""Arrangement clip geometry: pure functions, shared by bridge and host.

Units are beats for MIDI and warped audio. Unwarped audio uses seconds, so the
caller must refuse it rather than mixing units.
"""


def overlaps(a_start, a_end, b_start, b_end, tolerance=1e-6):
    """Half-open interval overlap; touching edges are not an overlap."""

    if a_end < a_start or b_end < b_start:
        raise ValueError("span end must not precede its start")
    return a_start < b_end - tolerance and b_start < a_end - tolerance


def plan_move(start, end, destination):
    """Validate a whole-clip move and return the destination span."""

    if destination < 0:
        raise ValueError("destination must be >= 0")
    length = end - start
    if length <= 1e-6:
        raise ValueError("clip has no length to move")
    return destination, destination + length, length


def plan_split(start, end, split_at):
    """Validate a split point and return the two abutting spans."""

    if not start + 1e-6 < split_at < end - 1e-6:
        raise ValueError("split point must fall strictly inside the clip")
    return (start, split_at), (split_at, end)


def conflicts(destination_start, destination_end, spans, ignore_index):
    """Indices of clips the destination span would overwrite."""

    return [
        index
        for index, (other_start, other_end) in enumerate(spans)
        if index != ignore_index
        and overlaps(destination_start, destination_end, other_start, other_end)
    ]
