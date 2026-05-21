def default_micro():
    return {
        "trials": 18,
        "timeout_ms": 1600,
        "start_gate": True,
        "distances_px": [80, 120, 160],
        "radii_px": [8, 10, 12],
    }


def default_flick():
    return {
        "trials": 18,
        "timeout_ms": 2200,
        "start_gate": True,
        "distances_px": [220, 340, 520],
        "radii_px": [12, 16, 22],
    }


def default_dual_config():
    return {
        "enabled": False,
        "weights": {"micro": 0.6, "flick": 0.4},
        "micro_floor": 0.95,
        "micro": default_micro(),
        "flick": default_flick(),
    }


def clamp01(x):
    x = float(x)
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def norm_weights(weights):
    w_micro = float(weights.get("micro", 0.6))
    w_flick = float(weights.get("flick", 0.4))
    s = w_micro + w_flick
    if s <= 0:
        return {"micro": 0.5, "flick": 0.5}
    return {"micro": w_micro / s, "flick": w_flick / s}
