import math
import random
import time
import tkinter as tk


def run_task_block(root, trials, distances_px, radii_px, seed=None, timeout_ms=None, start_gate=False):
    rng = random.Random(seed)

    win = tk.Toplevel(root)
    win.title("Target Task")

    width = int(win.winfo_screenwidth())
    height = int(win.winfo_screenheight())
    win.geometry(f"{width}x{height}+0+0")
    win.attributes("-fullscreen", True)
    win.grab_set()
    win.focus_force()

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
        "prev_sample_pos": None,
        "prev_sample_t": None,
        "path_length": 0.0,
        "overshoots": 0,
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
        state["target_start"] = now
        state["prev_sample_pos"] = start_pos
        state["prev_sample_t"] = now
        state["path_length"] = 0.0
        state["overshoots"] = 0
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

        def path_eff(a):
            d = float(a["distance"])
            pl = float(a["path_length"])
            if d <= 0:
                return 1.0
            return d / max(pl, d)

        avg_path_eff = (sum(path_eff(a) for a in hits) / float(len(hits))) if hits else 0.0
        avg_overshoots = (sum(a["overshoots"] for a in hits) / float(len(hits))) if hits else 0.0
        avg_reaccels = (sum(a["reaccels"] for a in hits) / float(len(hits))) if hits else 0.0

        state["result"] = {
            "throughput": float(throughput),
            "miss_rate": float(miss_rate),
            "avg_error_px": float(avg_error),
            "avg_path_eff": float(avg_path_eff),
            "avg_overshoots": float(avg_overshoots),
            "avg_reaccels": float(avg_reaccels),
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

        state["misses"] += 1
        state["attempts"].append(
            {
                "hit": False,
                "movement_time": float(mt),
                "width": float(width_px),
                "distance": float(distance_px),
                "endpoint_error": float(endpoint_error),
                "path_length": float(state["path_length"]),
                "overshoots": int(state["overshoots"]),
                "reaccels": int(state["reaccels"]),
                "max_perp_dev": float(state["max_perp_dev"]),
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
        if perp_len > state["max_perp_dev"]:
            state["max_perp_dev"] = perp_len

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
                "path_length": float(state["path_length"]),
                "overshoots": int(state["overshoots"]),
                "reaccels": int(state["reaccels"]),
                "max_perp_dev": float(state["max_perp_dev"]),
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

    def sample_loop():
        if not win.winfo_exists():
            return
        if state["started"] and not state["done"] and state["target"] is not None:
            sample_position(get_mouse_pos(), time.perf_counter())
        win.after(16, sample_loop)

    sample_loop()

    root.wait_window(win)
    return state["result"]
