import math
import random
import time
import tkinter as tk


def run_task_block(root, trials, distances_px, radii_px, seed=None, timeout_ms=None, start_gate=False, dir_bins=16):
    rng = random.Random(seed)

    win = tk.Toplevel(root)
    win.title("Target Task")

    width = int(win.winfo_screenwidth())
    height = int(win.winfo_screenheight())
    win.geometry(f"{width}x{height}+0+0")
    win.attributes("-fullscreen", True)
    win.attributes("-topmost", True)
    win.grab_set()
    win.focus_force()

    try:
        win.protocol("WM_DELETE_WINDOW", lambda: None)
    except Exception:
        pass

    canvas = tk.Canvas(win, bg="#0b0f14", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    def get_mouse_pos():
        return (
            float(win.winfo_pointerx() - win.winfo_rootx()),
            float(win.winfo_pointery() - win.winfo_rooty()),
        )

    state = {
        "width": float(width),
        "height": float(height),
        "started": False,
        "trial": 0,
        "misses": 0,
        "sum_id": 0.0,
        "sum_mt": 0.0,
        "prev": (width / 2.0, height / 2.0),
        "attempts": [],
        "start_pos": None,
        "target_start": None,
        "first_move_t": None,
        "first_enter_t": None,
        "prev_sample_pos": None,
        "prev_sample_t": None,
        "path_length": 0.0,
        "overshoots": 0,
        "perp_area": 0.0,
        "perp_time": 0.0,
        "max_perp_dev": 0.0,
        "line_unit": (1.0, 0.0),
        "has_line_unit": False,
        "last_sign": 0,
        "reaccels": 0,
        "below_low_speed_while_far": False,
        "t0": None,
        "target": None,
        "done": False,
        "result": None,
        "dir_bins": int(max(4, dir_bins)),
        "dir_angle_deg": None,
        "dir_bin": None,
    }

    text_id = canvas.create_text(
        width / 2,
        height / 2,
        fill="#d9e2ef",
        font=("Segoe UI", 16),
        text=(
            "Click the center dot to start\nClick targets as fast and accurate as possible\nESC to abort"
            if start_gate
            else "Press SPACE to start\nClick targets as fast and accurate as possible\nESC to abort"
        ),
        justify="center",
    )

    gate_id = None
    if start_gate:
        gx = state["width"] / 2.0
        gy = state["height"] / 2.0
        r = 18.0
        gate_id = canvas.create_oval(gx - r, gy - r, gx + r, gy + r, fill="#2563eb", outline="")
        canvas.create_oval(gx - 2, gy - 2, gx + 2, gy + 2, fill="#0b0f14", outline="")

    state["awaiting_gate"] = bool(start_gate)
    state["timeout_job"] = None

    def draw_target():
        canvas.delete("target")
        start_x, start_y = state["prev"]

        w = state["width"]
        h = state["height"]

        dist = float(rng.choice(distances_px))
        r = float(rng.choice(radii_px))
        angle = rng.random() * math.tau

        x = start_x + dist * math.cos(angle)
        y = start_y + dist * math.sin(angle)

        x = max(r + 8, min(w - r - 8, x))
        y = max(r + 8, min(h - r - 8, y))

        canvas.create_oval(x - r, y - r, x + r, y + r, fill="#2dd4bf", outline="", tags="target")
        canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="#0b0f14", outline="", tags="target")

        state["target"] = (x, y, r, dist)
        now = time.perf_counter()
        start_pos = get_mouse_pos()
        dx = x - start_pos[0]
        dy = y - start_pos[1]
        length = math.hypot(dx, dy)
        if length > 1e-6:
            state["line_unit"] = (dx / length, dy / length)
            state["has_line_unit"] = True
        else:
            state["line_unit"] = (1.0, 0.0)
            state["has_line_unit"] = False

        state["start_pos"] = start_pos
        state["target_vec"] = (float(x - start_pos[0]), float(y - start_pos[1]))

        angle_deg = (math.degrees(math.atan2(float(state["target_vec"][1]), float(state["target_vec"][0]))) + 360.0) % 360.0
        bin_w = 360.0 / float(max(1, int(state.get("dir_bins", 16))))
        state["dir_angle_deg"] = float(angle_deg)
        state["dir_bin"] = int(angle_deg // bin_w) % int(max(1, int(state.get("dir_bins", 16))))
        state["target_start"] = now
        state["first_move_t"] = None
        state["first_enter_t"] = None
        state["prev_sample_pos"] = start_pos
        state["prev_sample_t"] = now
        state["path_length"] = 0.0
        state["overshoots"] = 0
        state["perp_area"] = 0.0
        state["perp_time"] = 0.0
        state["max_perp_dev"] = 0.0
        state["last_sign"] = 0
        state["reaccels"] = 0
        state["below_low_speed_while_far"] = False
        state["t0"] = now

        if timeout_ms is not None and timeout_ms > 0:
            if state["timeout_job"] is not None:
                try:
                    win.after_cancel(state["timeout_job"])
                except Exception:
                    pass
            state["timeout_job"] = win.after(int(timeout_ms), on_timeout)

        canvas.delete(text_id)

    def finish():
        if state["done"]:
            return
        state["done"] = True

        attempts = state["attempts"]
        hits = [a for a in attempts if a["hit"]]
        miss_rate = 1.0 - (len(hits) / float(len(attempts))) if attempts else 1.0

        id_sum = 0.0
        mt_sum = 0.0
        for a in hits:
            mt = float(a["movement_time"])
            w = float(a["width"])
            d = float(a["distance"])
            if mt <= 0 or w <= 0:
                continue
            id_sum += math.log2(d / w + 1.0)
            mt_sum += mt

        throughput = id_sum / mt_sum if mt_sum > 0 else 0.0
        avg_error = (sum(a["endpoint_error"] for a in attempts) / float(len(attempts))) if attempts else 0.0

        errors = sorted(float(a["endpoint_error"]) for a in attempts) if attempts else []

        horiz = [a for a in attempts if a.get("axis") == "h"]
        vert = [a for a in attempts if a.get("axis") == "v"]
        horiz_errors = sorted(float(a["endpoint_error"]) for a in horiz) if horiz else []
        vert_errors = sorted(float(a["endpoint_error"]) for a in vert) if vert else []

        def pct(vals, q):
            if not vals:
                return 0.0
            if q <= 0:
                return float(vals[0])
            if q >= 1:
                return float(vals[-1])
            i = q * (len(vals) - 1)
            lo = int(math.floor(i))
            hi = int(math.ceil(i))
            if lo == hi:
                return float(vals[lo])
            t = i - lo
            return float(vals[lo] * (1.0 - t) + vals[hi] * t)

        def path_eff(a):
            d = float(a["distance"])
            pl = float(a["path_length"])
            if d <= 0:
                return 1.0
            return d / max(pl, d)

        avg_path_eff = (sum(path_eff(a) for a in hits) / float(len(hits))) if hits else 0.0
        avg_overshoots = (sum(a["overshoots"] for a in hits) / float(len(hits))) if hits else 0.0
        avg_reaccels = (sum(a["reaccels"] for a in hits) / float(len(hits))) if hits else 0.0
        avg_time_to_move_ms = (
            (
                sum(float(a.get("time_to_move")) for a in hits if a.get("time_to_move") is not None)
                / float(sum(1 for a in hits if a.get("time_to_move") is not None))
                * 1000.0
            )
            if any(a.get("time_to_move") is not None for a in hits)
            else 0.0
        )
        avg_correction_ms = (
            (
                sum(float(a.get("correction_time")) for a in hits if a.get("correction_time") is not None)
                / float(sum(1 for a in hits if a.get("correction_time") is not None))
                * 1000.0
            )
            if any(a.get("correction_time") is not None for a in hits)
            else 0.0
        )
        avg_bias_x = (sum(float(a.get("bias_x", 0.0)) for a in attempts) / float(len(attempts))) if attempts else 0.0
        avg_bias_y = (sum(float(a.get("bias_y", 0.0)) for a in attempts) / float(len(attempts))) if attempts else 0.0
        avg_perp_dev = (
            sum(float(a.get("avg_perp_dev", 0.0)) for a in hits) / float(len(hits)) if hits else 0.0
        )

        bins = int(state.get("dir_bins", 0))
        dir_bins_obj = None
        dir_summary = None
        if bins > 0 and attempts:
            bin_w = 360.0 / float(bins)
            speeds_all = sorted(float(a.get("speed_px_s", 0.0)) for a in attempts)
            speed_p33 = float(pct(speeds_all, 1.0 / 3.0)) if speeds_all else 0.0
            speed_p66 = float(pct(speeds_all, 2.0 / 3.0)) if speeds_all else 0.0
            rows = []
            for i in range(bins):
                group = [a for a in attempts if int(a.get("dir_bin", -1)) == i]
                if group:
                    group_errors = sorted(float(a.get("endpoint_error", 0.0)) for a in group)
                    group_hits = [a for a in group if a.get("hit")]
                    miss_rate_i = 1.0 - (len(group_hits) / float(len(group))) if group else 1.0

                    bp = [float(a.get("bias_parallel", 0.0)) for a in group]
                    bperp = [float(a.get("bias_perp", 0.0)) for a in group]
                    spd = [float(a.get("speed_px_s", 0.0)) for a in group]
                    bias_parallel_mean = (sum(bp) / float(len(bp))) if bp else 0.0
                    bias_perp_mean = (sum(bperp) / float(len(bperp))) if bperp else 0.0
                    speed_mean = (sum(spd) / float(len(spd))) if spd else 0.0

                    correction_ms = [float(a.get("correction_time")) * 1000.0 for a in group_hits if a.get("correction_time") is not None]
                    move_ms = [float(a.get("time_to_move")) * 1000.0 for a in group_hits if a.get("time_to_move") is not None]

                    avg_correction_ms = (sum(correction_ms) / float(len(correction_ms))) if correction_ms else 0.0
                    avg_time_to_move_ms = (sum(move_ms) / float(len(move_ms))) if move_ms else 0.0
                else:
                    group_errors = []
                    miss_rate_i = 1.0
                    avg_correction_ms = 0.0
                    avg_time_to_move_ms = 0.0
                    bias_parallel_mean = 0.0
                    bias_perp_mean = 0.0
                    speed_mean = 0.0

                deg0 = float(i) * bin_w
                deg1 = float(i + 1) * bin_w
                rows.append(
                    {
                        "bin": int(i),
                        "deg0": float(deg0),
                        "deg1": float(deg1),
                        "n": int(len(group_errors)),
                        "miss_rate": float(miss_rate_i),
                        "p90_error_px": float(pct(group_errors, 0.9)),
                        "avg_correction_ms": float(avg_correction_ms),
                        "avg_time_to_move_ms": float(avg_time_to_move_ms),
                        "bias_parallel_mean": float(bias_parallel_mean),
                        "bias_perp_mean": float(bias_perp_mean),
                        "speed_mean": float(speed_mean),
                    }
                )

            dir_bins_obj = {
                "bins": int(bins),
                "rows": rows,
                "speed_p33": float(speed_p33),
                "speed_p66": float(speed_p66),
            }

            rows2 = [r for r in rows if int(r.get("n", 0)) > 0]
            worst_miss = sorted(rows2, key=lambda r: (float(r.get("miss_rate", 0.0)), float(r.get("p90_error_px", 0.0))), reverse=True)[:4]
            worst_p90 = sorted(rows2, key=lambda r: (float(r.get("p90_error_px", 0.0)), float(r.get("miss_rate", 0.0))), reverse=True)[:4]
            dir_summary = {
                "bins": int(bins),
                "speed_p33": float(speed_p33),
                "speed_p66": float(speed_p66),
                "worst_miss": worst_miss,
                "worst_p90": worst_p90,
            }

        state["result"] = {
            "throughput": float(throughput),
            "miss_rate": float(miss_rate),
            "avg_error_px": float(avg_error),
            "p50_error_px": float(pct(errors, 0.5)),
            "p90_error_px": float(pct(errors, 0.9)),
            "avg_path_eff": float(avg_path_eff),
            "avg_perp_dev": float(avg_perp_dev),
            "avg_overshoots": float(avg_overshoots),
            "avg_reaccels": float(avg_reaccels),
            "avg_time_to_move_ms": float(avg_time_to_move_ms),
            "avg_correction_ms": float(avg_correction_ms),
            "avg_bias_x": float(avg_bias_x),
            "avg_bias_y": float(avg_bias_y),
            "h_miss_rate": float(1.0 - (sum(1 for a in horiz if a["hit"]) / float(len(horiz)))) if horiz else float(miss_rate),
            "v_miss_rate": float(1.0 - (sum(1 for a in vert if a["hit"]) / float(len(vert)))) if vert else float(miss_rate),
            "h_p90_error_px": float(pct(horiz_errors, 0.9)),
            "v_p90_error_px": float(pct(vert_errors, 0.9)),
            "dir_bins": dir_bins_obj,
            "dir_summary": dir_summary,
        }

        canvas.delete("all")
        canvas.create_text(
            state["width"] / 2,
            state["height"] / 2,
            fill="#d9e2ef",
            font=("Segoe UI", 16),
            text=(
                f"Done\n\nThroughput: {throughput:.3f} bits/s\nMiss rate: {miss_rate:.3f}"
                f"\nPath eff: {avg_path_eff:.3f}"
                f"\nOvershoots: {avg_overshoots:.2f}"
                f"\nReaccels: {avg_reaccels:.2f}"
                f"\nErr p50/p90: {pct(errors, 0.5):.1f}/{pct(errors, 0.9):.1f}px"
                f"\n\nPress ENTER to continue"
            ),
            justify="center",
        )

    def abort():
        state["result"] = None
        win.destroy()

    def on_timeout():
        if not state["started"] or state["done"] or state["target"] is None:
            return

        now = time.perf_counter()
        mx, my = get_mouse_pos()
        tx, ty, r, _ = state["target"]
        sample_position((mx, my), now)

        mt = float(timeout_ms) / 1000.0
        width_px = max(2.0, 2.0 * r)
        start_pos = state["start_pos"]
        distance_px = math.hypot(tx - start_pos[0], ty - start_pos[1])
        endpoint_error = math.hypot(mx - tx, my - ty)
        bias_x = mx - tx
        bias_y = my - ty

        time_to_move = None
        if state["first_move_t"] is not None:
            time_to_move = float(state["first_move_t"] - state["t0"])

        correction_time = None
        if state["first_enter_t"] is not None:
            correction_time = float(now - state["first_enter_t"])

        avg_perp_dev = float(state["perp_area"] / state["perp_time"]) if state["perp_time"] > 0 else 0.0

        state["misses"] += 1
        state["attempts"].append(
            {
                "hit": False,
                "movement_time": float(mt),
                "width": float(width_px),
                "distance": float(distance_px),
                "endpoint_error": float(endpoint_error),
                "bias_x": float(bias_x),
                "bias_y": float(bias_y),
                "path_length": float(state["path_length"]),
                "overshoots": int(state["overshoots"]),
                "reaccels": int(state["reaccels"]),
                "time_to_move": float(time_to_move) if time_to_move is not None else None,
                "correction_time": float(correction_time) if correction_time is not None else None,
                "avg_perp_dev": float(avg_perp_dev),
                "max_perp_dev": float(state["max_perp_dev"]),
                "axis": "h" if abs(float(state.get("target_vec", (0.0, 0.0))[0])) >= abs(float(state.get("target_vec", (0.0, 0.0))[1])) else "v",
                "dir_bin": int(state.get("dir_bin", 0)),
                "dir_angle_deg": float(state.get("dir_angle_deg", 0.0)),
            }
        )

        state["prev"] = (mx, my)
        state["trial"] += 1

        if state["trial"] >= trials:
            finish()
        else:
            draw_target()

    def sample_position(pos, t):
        prev_pos = state["prev_sample_pos"]
        prev_t = state["prev_sample_t"]
        if prev_pos is None or prev_t is None:
            state["prev_sample_pos"] = pos
            state["prev_sample_t"] = t
            return

        dt = t - prev_t
        if dt <= 0:
            state["prev_sample_pos"] = pos
            state["prev_sample_t"] = t
            return

        dx = pos[0] - prev_pos[0]
        dy = pos[1] - prev_pos[1]
        delta_len = math.hypot(dx, dy)

        if state["first_move_t"] is None and delta_len >= 2.0:
            state["first_move_t"] = t
        state["path_length"] += delta_len
        state["prev_sample_pos"] = pos
        state["prev_sample_t"] = t

        if not state["has_line_unit"] or state["target"] is None:
            return

        tx, ty, r, _ = state["target"]
        ux, uy = state["line_unit"]

        to_x = pos[0] - state["start_pos"][0]
        to_y = pos[1] - state["start_pos"][1]
        parallel = to_x * ux + to_y * uy
        perp_x = to_x - ux * parallel
        perp_y = to_y - uy * parallel
        perp_len = math.hypot(perp_x, perp_y)
        state["perp_area"] += perp_len * dt
        state["perp_time"] += dt
        if perp_len > state["max_perp_dev"]:
            state["max_perp_dev"] = perp_len

        if state["first_enter_t"] is None:
            if (pos[0] - tx) ** 2 + (pos[1] - ty) ** 2 <= r ** 2:
                state["first_enter_t"] = t

        signed = (pos[0] - tx) * ux + (pos[1] - ty) * uy
        if abs(signed) > r:
            sign = 1 if signed > 0 else -1
            if state["last_sign"] != 0 and sign != state["last_sign"]:
                state["overshoots"] += 1
            state["last_sign"] = sign

        remaining = (tx - pos[0]) * ux + (ty - pos[1]) * uy
        delta_along = dx * ux + dy * uy
        speed_toward = delta_along / dt
        if speed_toward < 0:
            speed_toward = 0.0

        low_speed = 120.0
        high_speed = 260.0
        if remaining > r * 1.5:
            if not state["below_low_speed_while_far"] and speed_toward < low_speed:
                state["below_low_speed_while_far"] = True

            if state["below_low_speed_while_far"] and speed_toward > high_speed:
                state["reaccels"] += 1
                state["below_low_speed_while_far"] = False
        else:
            state["below_low_speed_while_far"] = False

    def on_configure(event):
        state["width"] = float(max(1, event.width))
        state["height"] = float(max(1, event.height))
        if not state["started"]:
            state["prev"] = (state["width"] / 2.0, state["height"] / 2.0)
            canvas.coords(text_id, state["width"] / 2.0, state["height"] / 2.0)

    def on_click(event):
        if state["done"]:
            win.destroy()
            return

        if state.get("awaiting_gate"):
            gx = state["width"] / 2.0
            gy = state["height"] / 2.0
            if (float(event.x) - gx) ** 2 + (float(event.y) - gy) ** 2 <= 18.0 ** 2:
                state["awaiting_gate"] = False
                state["started"] = True
                if gate_id is not None:
                    canvas.delete(gate_id)
                draw_target()
            return

        if not state["started"]:
            state["started"] = True
            draw_target()
            return

        if not state["started"] or state["done"]:
            return

        x, y = float(event.x), float(event.y)
        tx, ty, r, dist = state["target"]

        now = time.perf_counter()
        sample_position((x, y), now)

        mt = now - state["t0"]
        hit = (x - tx) ** 2 + (y - ty) ** 2 <= r ** 2

        width_px = max(2.0, 2.0 * r)
        start_pos = state["start_pos"]
        distance_px = math.hypot(tx - start_pos[0], ty - start_pos[1])
        endpoint_error = math.hypot(x - tx, y - ty)
        bias_x = x - tx
        bias_y = y - ty

        time_to_move = None
        if state["first_move_t"] is not None:
            time_to_move = float(state["first_move_t"] - state["t0"])

        correction_time = None
        if state["first_enter_t"] is not None:
            correction_time = float(now - state["first_enter_t"])

        avg_perp_dev = float(state["perp_area"] / state["perp_time"]) if state["perp_time"] > 0 else 0.0

        if hit:
            state["sum_mt"] += max(1e-3, mt)
        else:
            state["misses"] += 1

        if state["timeout_job"] is not None:
            try:
                win.after_cancel(state["timeout_job"])
            except Exception:
                pass
            state["timeout_job"] = None

        state["attempts"].append(
            {
                "hit": bool(hit),
                "movement_time": float(mt),
                "width": float(width_px),
                "distance": float(distance_px),
                "endpoint_error": float(endpoint_error),
                "bias_x": float(bias_x),
                "bias_y": float(bias_y),
                "path_length": float(state["path_length"]),
                "overshoots": int(state["overshoots"]),
                "reaccels": int(state["reaccels"]),
                "time_to_move": float(time_to_move) if time_to_move is not None else None,
                "correction_time": float(correction_time) if correction_time is not None else None,
                "avg_perp_dev": float(avg_perp_dev),
                "max_perp_dev": float(state["max_perp_dev"]),
                "axis": "h" if abs(float(state.get("target_vec", (0.0, 0.0))[0])) >= abs(float(state.get("target_vec", (0.0, 0.0))[1])) else "v",
                "dir_bin": int(state.get("dir_bin", 0)),
                "dir_angle_deg": float(state.get("dir_angle_deg", 0.0)),
            }
        )

        state["prev"] = (x, y)
        state["trial"] += 1

        if state["trial"] >= trials:
            finish()
        else:
            draw_target()

    def on_key(event):
        if event.keysym == "Escape":
            abort()
            return

        if event.keysym == "space" and not state["started"] and not state.get("awaiting_gate"):
            state["started"] = True
            draw_target()
            return

        if event.keysym == "Return" and state["done"]:
            win.destroy()
            return

    win.bind("<Button-1>", on_click)
    win.bind("<Key>", on_key)
    win.bind("<Configure>", on_configure)

    def on_focus_out(event):
        if not win.winfo_exists() or state.get("done"):
            return
        try:
            win.focus_force()
            win.grab_set()
        except Exception:
            pass

    win.bind("<FocusOut>", on_focus_out)

    def sample_loop():
        if not win.winfo_exists():
            return
        if state["started"] and not state["done"] and state["target"] is not None:
            sample_position(get_mouse_pos(), time.perf_counter())
        win.after(16, sample_loop)

    sample_loop()

    root.wait_window(win)
    return state["result"]
