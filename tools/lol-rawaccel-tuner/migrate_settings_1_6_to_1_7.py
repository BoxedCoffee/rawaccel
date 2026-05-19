import json
import pathlib


DPI_16_KEY = "DPI (normalizes sens to 1000dpi and converts input speed unit: counts/ms -> in/s)"
DPI_17_KEY = "DPI (normalizes input speed unit: counts/ms -> in/s)"

DEFAULT_TIME_MIN = 1000.0 / 8000.0 / 2.0
DEFAULT_TIME_MAX = 100.0

PROFILE_MODE_KEY_X = "Whole or horizontal accel parameters"
PROFILE_MODE_KEY_Y = "Vertical accel parameters"

COMBINE_KEY = "Whole/combined accel (set false for 'by component' mode)"
INPUT_SPEED_ARGS_KEY = "Input speed calculation parameters"

IN_SMOOTH_KEY = "Time in ms after which an input is weighted at half its original value."
SCALE_SMOOTH_KEY = "Time in ms after which scale is weighted at half its original value."
OUT_SMOOTH_KEY = "Time in ms after which an output is weighted at half its original value."

SENS_MULT_KEY = "Sensitivity multiplier"
YX_SENS_KEY = "Y/X sensitivity ratio (vertical sens multiplier)"
LR_SENS_KEY = "L/R sensitivity ratio (left sens multiplier)"
UD_SENS_KEY = "U/D sensitivity ratio (up sens multiplier)"

OUTPUT_DPI_KEY = "Output DPI"
YX_OUTPUT_DPI_KEY = "Y/X output DPI ratio (vertical sens multiplier)"
LR_OUTPUT_DPI_KEY = "L/R output DPI ratio (left sens multiplier)"
UD_OUTPUT_DPI_KEY = "U/D output DPI ratio (up sens multiplier)"

ACCEL_DEFAULTS = {
    "Gain / Velocity": True,
    "inputOffset": 0.0,
    "outputOffset": 0.0,
    "acceleration": 0.005,
    "decayRate": 0.1,
    "gamma": 1.0,
    "motivity": 1.5,
    "exponentClassic": 2.0,
    "scale": 1.0,
    "exponentPower": 0.05,
    "limit": 1.5,
    "syncSpeed": 5.0,
    "smooth": 0.5,
    "Cap / Jump": {"x": 15.0, "y": 1.5},
    "Cap mode": "output",
    "data": [],
}


def migrate_profile(profile: dict) -> dict:
    combine = bool(profile.get(COMBINE_KEY, True))
    lp_norm = float(profile.get("lpNorm", 2.0))

    input_speed_args = profile.get(INPUT_SPEED_ARGS_KEY)
    if not isinstance(input_speed_args, dict):
        input_speed_args = {
            COMBINE_KEY: combine,
            "lpNorm": lp_norm,
            IN_SMOOTH_KEY: 0.0,
            SCALE_SMOOTH_KEY: 0.0,
            OUT_SMOOTH_KEY: 0.0,
        }
    else:
        input_speed_args.setdefault(COMBINE_KEY, combine)
        input_speed_args.setdefault("lpNorm", lp_norm)
        input_speed_args.setdefault(IN_SMOOTH_KEY, 0.0)
        input_speed_args.setdefault(SCALE_SMOOTH_KEY, 0.0)
        input_speed_args.setdefault(OUT_SMOOTH_KEY, 0.0)

    sensitivity_multiplier = profile.get(SENS_MULT_KEY)
    if sensitivity_multiplier is None:
        output_dpi = profile.get(OUTPUT_DPI_KEY)
    else:
        output_dpi = 1000.0 * float(sensitivity_multiplier)

    if output_dpi is None:
        output_dpi = 1000.0

    profile = dict(profile)
    profile[INPUT_SPEED_ARGS_KEY] = input_speed_args
    profile[OUTPUT_DPI_KEY] = float(profile.get(OUTPUT_DPI_KEY, output_dpi))

    if YX_SENS_KEY in profile and YX_OUTPUT_DPI_KEY not in profile:
        profile[YX_OUTPUT_DPI_KEY] = float(profile[YX_SENS_KEY])
    if LR_SENS_KEY in profile and LR_OUTPUT_DPI_KEY not in profile:
        profile[LR_OUTPUT_DPI_KEY] = float(profile[LR_SENS_KEY])
    if UD_SENS_KEY in profile and UD_OUTPUT_DPI_KEY not in profile:
        profile[UD_OUTPUT_DPI_KEY] = float(profile[UD_SENS_KEY])

    profile.pop(SENS_MULT_KEY, None)
    profile.pop(YX_SENS_KEY, None)
    profile.pop(LR_SENS_KEY, None)
    profile.pop(UD_SENS_KEY, None)

    for axis_key in (PROFILE_MODE_KEY_X, PROFILE_MODE_KEY_Y, "argsX", "argsY"):
        args = profile.get(axis_key)
        if not isinstance(args, dict):
            continue

        for k, v in ACCEL_DEFAULTS.items():
            args.setdefault(k, v)

        if isinstance(args.get("Cap / Jump"), dict):
            cap = dict(ACCEL_DEFAULTS["Cap / Jump"])
            cap.update(args["Cap / Jump"])
            args["Cap / Jump"] = cap

        mode = args.get("mode")
        if mode == "motivity":
            args["mode"] = "natural"

        if mode == "lookup":
            args["mode"] = "lut"

        profile[axis_key] = args

    return profile


def migrate_settings(obj: dict) -> dict:
    obj = dict(obj)

    default_cfg = dict(obj.get("defaultDeviceConfig") or {})
    if DPI_16_KEY in default_cfg and DPI_17_KEY not in default_cfg:
        default_cfg[DPI_17_KEY] = default_cfg.pop(DPI_16_KEY)

    default_cfg.setdefault("setExtraInfo", False)
    default_cfg.setdefault("Use constant time interval based on polling rate", False)
    default_cfg.setdefault("minimumTime", DEFAULT_TIME_MIN)
    default_cfg.setdefault("maximumTime", DEFAULT_TIME_MAX)
    obj["defaultDeviceConfig"] = default_cfg

    profiles = obj.get("profiles")
    if isinstance(profiles, list):
        obj["profiles"] = [migrate_profile(p) if isinstance(p, dict) else p for p in profiles]

    return obj


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()

    obj = json.loads(args.input.read_text(encoding="utf-8"))
    out = migrate_settings(obj)
    args.output.write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
