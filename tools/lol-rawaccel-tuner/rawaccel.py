import copy
import json
import pathlib
import subprocess


class SynchronousParams:
    def __init__(self, syncSpeed, motivity, gamma, smooth):
        self.syncSpeed = max(1e-6, float(syncSpeed))
        self.motivity = float(motivity)
        self.gamma = max(1e-6, float(gamma))
        self.smooth = float(smooth)


class RawAccelController:
    def __init__(self, writer_path, base_settings_path, profile_index=0):
        self.writer_path = pathlib.Path(writer_path)
        self.base_settings_path = pathlib.Path(base_settings_path)
        self.profile_index = int(profile_index)
        self._base_obj = None

    def snapshot_base(self, dest_path):
        dest_path = pathlib.Path(dest_path)
        dest_path.write_bytes(self.base_settings_path.read_bytes())
        self._base_obj = json.loads(dest_path.read_text(encoding="utf-8"))

    def write_candidate_settings(self, candidate, dest_path):
        if self._base_obj is None:
            self._base_obj = json.loads(self.base_settings_path.read_text(encoding="utf-8"))

        obj = copy.deepcopy(self._base_obj)
        profiles = obj.get("profiles")
        if not isinstance(profiles, list) or not profiles:
            raise ValueError("settings.json missing profiles")
        if self.profile_index < 0 or self.profile_index >= len(profiles):
            raise ValueError("profile_index out of range")

        profile = profiles[self.profile_index]

        if not isinstance(candidate, dict):
            raise TypeError("candidate must be a dict")

        mode = candidate.get("mode")
        output_dpi = candidate.get("outputDpi")
        y_to_x_ratio = candidate.get("yToXRatio")

        if output_dpi is not None:
            profile["Output DPI"] = float(output_dpi)

        if y_to_x_ratio is not None:
            profile["Y/X output DPI ratio (vertical sens multiplier)"] = float(y_to_x_ratio)

        axis_sources = (
            ("argsX", "Whole or horizontal accel parameters"),
            ("argsY", "Vertical accel parameters"),
        )

        for internal_key, json_key in axis_sources:
            args = profile.get(json_key)
            if not isinstance(args, dict):
                args = profile.get(internal_key)
            if not isinstance(args, dict):
                raise ValueError(f"profile missing {json_key}")

            if mode is not None:
                args["mode"] = str(mode)

            for k in ("syncSpeed", "motivity", "gamma", "smooth"):
                if k not in candidate:
                    continue
                v = float(candidate[k])
                if k in ("syncSpeed", "gamma"):
                    v = max(1e-6, v)
                args[k] = v

            if json_key in profile and isinstance(profile.get(json_key), dict):
                profile[json_key] = args
            else:
                profile[internal_key] = args

        dest_path = pathlib.Path(dest_path)
        dest_path.write_text(json.dumps(obj, indent=2), encoding="utf-8")

    def apply_settings(self, settings_path):
        settings_path = pathlib.Path(settings_path)
        if not self.writer_path.exists():
            raise FileNotFoundError(str(self.writer_path))
        if not settings_path.exists():
            raise FileNotFoundError(str(settings_path))

        proc = subprocess.run(
            [str(self.writer_path), str(settings_path)],
            cwd=str(self.writer_path.parent),
        )
        return proc.returncode == 0
