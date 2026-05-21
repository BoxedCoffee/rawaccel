import math


def synchronous_gain(speed, sync_speed, motivity, gamma, smooth):
    speed = max(1e-9, float(speed))
    sync_speed = max(1e-9, float(sync_speed))
    motivity = max(1e-9, float(motivity))
    gamma = max(1e-9, float(gamma))
    smooth = float(smooth)

    log_motivity = math.log(motivity)
    gamma_const = gamma / log_motivity if log_motivity != 0 else 0.0
    log_syncspeed = math.log(sync_speed)

    sharpness = 16.0 if smooth == 0 else 0.5 / max(1e-9, smooth)
    use_linear_clamp = sharpness >= 16.0
    sharpness_recip = 1.0 / sharpness

    minimum_sens = 1.0 / motivity
    maximum_sens = motivity

    if use_linear_clamp:
        log_space = gamma_const * (math.log(speed) - log_syncspeed)
        if log_space < -1.0:
            return minimum_sens
        if log_space > 1.0:
            return maximum_sens
        return math.exp(log_space * log_motivity)

    if speed == sync_speed:
        return 1.0

    log_diff = math.log(speed) - log_syncspeed
    if log_diff > 0:
        log_space = gamma_const * log_diff
        exponent = math.pow(math.tanh(math.pow(log_space, sharpness)), sharpness_recip)
        return math.exp(exponent * log_motivity)

    log_space = -gamma_const * log_diff
    exponent = -math.pow(math.tanh(math.pow(log_space, sharpness)), sharpness_recip)
    return math.exp(exponent * log_motivity)


def curve_points(sync_speed, motivity, gamma, smooth, speeds=None):
    if speeds is None:
        speeds = [10 ** (a / 20.0) for a in range(-20, 61)]
    pts = []
    for s in speeds:
        pts.append((float(s), float(synchronous_gain(s, sync_speed, motivity, gamma, smooth))))
    return pts
