"""Bounded, read-only bridge batches with fault isolation and no timeout storms."""

READS = {
    "get_session_info",
    "get_track_info",
    "get_group_info",
    "get_arrangement_clips",
    "get_access_notes",
    "get_audio_clip_timing",
}


def read_many(call, commands, batch_size=48):
    """Return (value, error) per command; never replay writes or hide failed reads."""
    if not 1 <= batch_size <= 48:
        raise ValueError("Read batch size must be 1..48")
    if any(c.get("type") not in READS for c in commands):
        raise ValueError("Only allowlisted read commands may be batched here")

    def chunk(rows):
        if len(rows) == 1:
            try:
                return [(call(rows[0]["type"], rows[0]["params"]), None)]
            except Exception as error:
                return [(None, error)]
        try:
            response = call("batch", {"commands": rows})
        except Exception as error:
            # Lost transports/timeouts must not become N more failing round trips.
            if isinstance(error, (ConnectionError, TimeoutError, OSError)) or type(
                error
            ).__name__ in {
                "AbletonTimeoutError",
                "AbletonConnectionLostError",
                "AbletonNotConnectedError",
            }:
                return [(None, error)] * len(rows)
            # A native batch stops at the first command error. Isolate only reads.
            middle = len(rows) // 2
            return chunk(rows[:middle]) + chunk(rows[middle:])
        results = response.get("results", [])
        if (
            len(results) != len(rows)
            or response.get("executed", len(rows)) != len(rows)
            or any(not isinstance(r, dict) or "result" not in r for r in results)
        ):
            return [(None, ValueError("Incomplete bridge read batch"))] * len(rows)
        return [(r["result"], None) for r in results]

    output = []
    for first in range(0, len(commands), batch_size):
        output.extend(chunk(commands[first : first + batch_size]))
    return output
