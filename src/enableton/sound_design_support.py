"""Main-thread parameter batches for the bass toolkit."""

from .envelope_support import index, number


class SoundDesignSupportMixin(object):
    def _inspect_master_chain(self, args):
        """Bounded read-only recursion, executed by the upstream main-thread dispatcher."""
        track = self._access_track(args) if args.get("track_type") else self._song.master_track
        budget = [256]

        def devices(items, path, depth):
            if depth > 8:
                raise ValueError("Master rack nesting exceeds inspection limit")
            result = []
            for i, device in enumerate(items):
                budget[0] -= 1
                if budget[0] < 0:
                    raise ValueError("Master chain exceeds 256-device inspection limit")
                node = {
                    "index": i,
                    "path": path + [i],
                    "name": device.name,
                    "class_name": device.class_name,
                    "parameters": [
                        self._sound_design_parameter_info(p, j)
                        for j, p in enumerate(device.parameters)
                    ],
                }
                if getattr(device, "can_have_chains", False):
                    node["chains"] = [
                        {
                            "index": ci,
                            "name": chain.name,
                            "mute": bool(chain.mute),
                            "solo": bool(chain.solo),
                            "volume": self._sound_design_parameter_info(
                                chain.mixer_device.volume, 0
                            ),
                            "devices": devices(chain.devices, path + [i, ci], depth + 1),
                        }
                        for ci, chain in enumerate(device.chains)
                    ]
                result.append(node)
            return result

        return {
            "track_name": track.name,
            "volume": self._sound_design_parameter_info(track.mixer_device.volume, 0),
            "devices": devices(track.devices, [], 0),
            "read_only": True,
            "limits": "Parameter inspection only; no measured loudness, true peak or gain reduction.",
        }

    def _sound_design_target(self, args):
        track = self._access_track(args)
        path = args.get("device_path", [args.get("device_index")])
        if not isinstance(path, list) or not 1 <= len(path) <= 17 or len(path) % 2 != 1:
            raise ValueError(
                "device_path must alternate device, chain, device indexes; max depth 8"
            )
        device = index(path[0], track.devices, "device_path[0]")
        for position in range(1, len(path), 2):
            chain = index(path[position], device.chains, "chain index")
            device = index(path[position + 1], chain.devices, "device index")
        for key, actual in [
            ("expected_track_name", track.name),
            ("expected_device_name", device.name),
        ]:
            if args.get(key) is not None and args[key] != actual:
                raise ValueError(key + " no longer matches")
        return track, device

    def _access_track(self, args):
        kind = args.get("track_type", "track")
        if kind == "master":
            track = self._song.master_track
        elif kind in ("track", "return"):
            track = index(
                args.get("track_index", 0),
                self._song.tracks if kind == "track" else self._song.return_tracks,
                "track_index",
            )
        else:
            raise ValueError("track_type must be track, return, or master")
        if (
            args.get("expected_track_name") is not None
            and track.name != args["expected_track_name"]
        ):
            raise ValueError("expected_track_name no longer matches")
        return track

    def _sound_design_parameter_info(self, param, i):
        def display(value):
            try:
                return str(param.str_for_value(value))
            except (AttributeError, RuntimeError):
                return str(value)

        try:
            options = list(param.value_items) if param.is_quantized else []
        except (AttributeError, RuntimeError):
            options = []
        return {
            "index": i,
            "name": param.name,
            "value": param.value,
            "display_value": display(param.value),
            "min": param.min,
            "max": param.max,
            "display_min": display(param.min),
            "display_max": display(param.max),
            "is_quantized": bool(param.is_quantized),
            "is_enabled": bool(param.is_enabled),
            "value_items": options,
            "automation_state": int(getattr(param, "automation_state", 0)),
        }

    def _get_sound_design_parameters(self, args):
        track, device = self._sound_design_target(args)
        return {
            "track_name": track.name,
            "device_name": device.name,
            "class_name": device.class_name,
            "parameters": [
                self._sound_design_parameter_info(p, i) for i, p in enumerate(device.parameters)
            ],
        }

    def _set_sound_design_parameters(self, args):
        track, device = self._sound_design_target(args)
        changes = args.get("parameters")
        if not isinstance(changes, dict) or not 1 <= len(changes) <= 64:
            raise ValueError(
                "parameters must contain 1..64 exact parameter names and native numeric values"
            )
        names = {}
        for i, param in enumerate(device.parameters):
            names.setdefault(param.name, []).append((i, param))
        planned = []
        for name, raw in changes.items():
            candidates = names.get(name, [])
            if len(candidates) != 1:
                raise ValueError("Missing or ambiguous parameter: " + str(name))
            i, param = candidates[0]
            value = number(raw, name)
            if not param.min <= value <= param.max:
                raise ValueError(name + " is outside its native range")
            if param.is_quantized and value != round(value):
                raise ValueError(name + " requires an integer")
            if int(getattr(param, "automation_state", 0)) != 0:
                raise ValueError(
                    name + " has automation; use an envelope rather than overriding it"
                )
            # Some controls are disabled until an earlier enable/mode control in
            # this batch is applied. Range and existence still validate upfront.
            planned.append((i, param, value, param.value))
        self._song.begin_undo_step()
        applied = []
        try:
            for i, param, value, before in planned:
                if not param.is_enabled:
                    raise ValueError(
                        param.name + " is disabled; enable its device/oscillator/filter first"
                    )
                applied.append((param, before))
                param.value = value
                tolerance = max(1e-5, (param.max - param.min) * 1e-5)
                if abs(param.value - value) > tolerance:
                    raise ValueError(
                        param.name
                        + " snapped to a different value; use coarse/fine tuning separately"
                    )
        except Exception as error:
            failures = []
            for param, before in reversed(applied):
                try:
                    param.value = before
                except Exception:
                    failures.append(param.name)
            if failures:
                raise RuntimeError(
                    "Parameter batch failed and rollback was partial; use Live Undo: "
                    + ", ".join(failures)
                ) from error
            raise RuntimeError(
                "Parameter batch failed; previous values restored: " + str(error)
            ) from error
        finally:
            self._song.end_undo_step()
        return {
            "track_name": track.name,
            "device_name": device.name,
            "verified": True,
            "parameters": [
                self._sound_design_parameter_info(param, i) for i, param, value, before in planned
            ],
        }
