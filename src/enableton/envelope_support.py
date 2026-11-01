"""Bounded Session-clip automation. Called only on Live's main thread."""

import math

MAX_STEPS = 2048


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label + " must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(label + " must be finite")
    return value


def index(value, sequence, label):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < len(sequence):
        raise ValueError(label + " is out of range")
    return sequence[value]


def plan_steps(points, start, end, minimum, maximum, interpolation, resolution, quantized=False):
    """Validate the entire request before any Live mutation; values are native units."""
    if interpolation not in ("hold", "linear"):
        raise ValueError("interpolation must be hold or linear")
    resolution = number(resolution, "resolution")
    if resolution < 1.0 / 960 or resolution > 16:
        raise ValueError("resolution must be between 1/960 and 16 beats")
    if quantized and interpolation != "hold":
        raise ValueError("Quantized parameters require hold interpolation")
    if not isinstance(points, list) or not 1 <= len(points) <= MAX_STEPS:
        raise ValueError("Provide 1..2048 points")
    parsed = []
    for point in points:
        if not isinstance(point, dict) or set(point) != {"time", "value"}:
            raise ValueError("Each point needs exactly time and value")
        t, v = number(point["time"], "time"), number(point["value"], "value")
        if not start <= t <= end or not minimum <= v <= maximum:
            raise ValueError("Point is outside clip bounds or parameter range")
        if parsed and t <= parsed[-1][0]:
            raise ValueError("Point times must strictly increase")
        if quantized and v != round(v):
            raise ValueError("Quantized values must be whole numbers")
        parsed.append((t, v))
    if parsed[0][0] != start:
        raise ValueError("First point must be at clip loop_start")
    steps = []
    for i, (t, v) in enumerate(parsed):
        stop = parsed[i + 1][0] if i + 1 < len(parsed) else end
        if stop == t:
            continue
        count = (
            max(1, int(math.ceil((stop - t) / resolution)))
            if interpolation == "linear" and i + 1 < len(parsed)
            else 1
        )
        if len(steps) + count > MAX_STEPS:
            raise ValueError("Envelope exceeds 2048 steps; increase resolution")
        for k in range(count):
            a = t + (stop - t) * k / count
            b = t + (stop - t) * (k + 1) / count
            value = v
            if interpolation == "linear" and i + 1 < len(parsed):
                value += (parsed[i + 1][1] - v) * k / count
            steps.append((a, b - a, value))
    if not steps:
        raise ValueError("Envelope must have positive duration")
    return steps


class EnvelopeSupportMixin(object):
    def _envelope_target(self, args):
        track = index(args.get("track_index"), self._song.tracks, "track_index")
        slot = index(args.get("clip_index"), track.clip_slots, "clip_index")
        if not slot.has_clip:
            raise ValueError("Session slot is empty")
        clip = slot.clip
        if not clip.is_session_clip:
            raise ValueError("Envelope API supports Session clips only")
        for key, actual in (("expected_track_name", track.name), ("expected_clip_name", clip.name)):
            if args.get(key) is not None and args[key] != actual:
                raise ValueError(key + " no longer matches; refresh the set")
        target = args.get("target", "device")
        if target == "device":
            device = index(args.get("device_index"), track.devices, "device_index")
            param = index(args.get("parameter_index"), device.parameters, "parameter_index")
        elif target == "volume":
            param = track.mixer_device.volume
        elif target == "pan":
            param = track.mixer_device.panning
        elif target == "send":
            param = index(args.get("send_index"), track.mixer_device.sends, "send_index")
        else:
            raise ValueError("target must be device, volume, pan, or send")
        if not param.is_enabled:
            raise ValueError("Parameter is disabled")
        start, end = float(clip.loop_start), float(clip.loop_end)
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            raise ValueError("Clip has invalid loop bounds")
        metadata = {
            "track_name": track.name,
            "clip_name": clip.name,
            "parameter_name": param.name,
            "min": param.min,
            "max": param.max,
            "loop_start": start,
            "loop_end": end,
            "units": "native parameter values; times in clip beats",
        }
        return clip, param, metadata

    def _get_clip_envelope(self, args):
        clip, param, result = self._envelope_target(args)
        times = args.get("times", [])
        if not isinstance(times, list) or len(times) > MAX_STEPS:
            raise ValueError("times must contain at most 2048 sample positions")
        times = [number(t, "sample time") for t in times]
        if any(t < result["loop_start"] or t >= result["loop_end"] for t in times):
            raise ValueError("Sample times must be within [loop_start, loop_end)")
        envelope = clip.automation_envelope(param)
        result["exists"] = envelope is not None
        result["samples"] = (
            [{"time": t, "value": envelope.value_at_time(t)} for t in times]
            if envelope is not None
            else []
        )
        result["readback_kind"] = "samples, not an enumeration of breakpoints"
        return result

    def _write_clip_envelope(self, args):
        clip, param, result = self._envelope_target(args)
        if clip.is_recording:
            raise ValueError("Stop clip recording before writing automation")
        replace = args.get("replace", False)
        if not isinstance(replace, bool):
            raise ValueError("replace must be boolean")
        steps = plan_steps(
            args.get("points"),
            result["loop_start"],
            result["loop_end"],
            param.min,
            param.max,
            args.get("interpolation", "linear"),
            args.get("resolution", 0.0625),
            bool(param.is_quantized),
        )
        existing = clip.automation_envelope(param)
        if existing is not None and not replace:
            raise ValueError(
                "Parameter already has an envelope; read it first and set replace=true explicitly"
            )
        # Preflight API availability before removing any old automation.
        if not callable(getattr(clip, "create_automation_envelope", None)):
            raise RuntimeError("This Live version cannot create clip envelopes")
        if existing is not None and not callable(getattr(existing, "insert_step", None)):
            raise RuntimeError("This Live version cannot write envelope steps")
        self._song.begin_undo_step()
        try:
            if existing is not None:
                clip.clear_envelope(param)  # Never clear envelopes for other parameters.
            envelope = clip.create_automation_envelope(param)
            for t, duration, value in steps:
                envelope.insert_step(t, duration, value)
            samples = [
                {"time": t + duration / 2, "value": envelope.value_at_time(t + duration / 2)}
                for t, duration, value in steps
            ]
            tolerance = max(0.00001, (param.max - param.min) * 0.0001)
            verified = all(
                abs(sample["value"] - step[2]) <= tolerance for sample, step in zip(samples, steps)
            )
            if not verified:
                raise RuntimeError(
                    "Envelope readback differs from requested steps; write may be partial. Use Live Undo to revert"
                )
        except Exception as error:
            raise RuntimeError(
                "Envelope write failed; changes may be partial. Use Live Undo to revert: "
                + str(error)
            )
        finally:
            self._song.end_undo_step()
        result.update(
            {
                "steps_written": len(steps),
                "verified": True,
                "replaced_existing": existing is not None,
                "interpolation": args.get("interpolation", "linear"),
                "rendering": "positive-duration hold steps; linear curves are approximated",
                "verification_samples": [samples[0], samples[-1]],
            }
        )
        return result
