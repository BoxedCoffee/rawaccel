import math
import random
import time
import tkinter as tk


def run_task_block(root, trials, distances_px, radii_px, seed=None):
    rng = random.Random(seed)

    win = tk.Toplevel(root)
    win.title("Target Task")
    win.resizable(False, False)

    width = 1000
    height = 700

    win.geometry(f"{width}x{height}")
    win.grab_set()
    win.focus_force()

    canvas = tk.Canvas(win, width=width, height=height, bg="#0b0f14", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    state = {
        "started": False,
        "trial": 0,
        "misses": 0,
        "sum_id": 0.0,
        "sum_mt": 0.0,
        "prev": (width / 2.0, height / 2.0),
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
        text="Press SPACE to start\nClick targets as fast and accurate as possible\nESC to abort",
        justify="center",
    )

    def draw_target():
        canvas.delete("target")
        start_x, start_y = state["prev"]

        dist = float(rng.choice(distances_px))
        r = float(rng.choice(radii_px))
        angle = rng.random() * math.tau

        x = start_x + dist * math.cos(angle)
        y = start_y + dist * math.sin(angle)

        x = max(r + 8, min(width - r - 8, x))
        y = max(r + 8, min(height - r - 8, y))

        canvas.create_oval(x - r, y - r, x + r, y + r, fill="#2dd4bf", outline="", tags="target")
        canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="#0b0f14", outline="", tags="target")

        state["target"] = (x, y, r, dist)
        state["t0"] = time.perf_counter()

        canvas.delete(text_id)

    def finish():
        if state["done"]:
            return
        state["done"] = True

        miss_rate = state["misses"] / float(trials)
        throughput = state["sum_id"] / state["sum_mt"] if state["sum_mt"] > 0 else 0.0

        state["result"] = {
            "throughput": float(throughput),
            "miss_rate": float(miss_rate),
        }

        canvas.delete("all")
        canvas.create_text(
            width / 2,
            height / 2,
            fill="#d9e2ef",
            font=("Segoe UI", 16),
            text=(
                f"Done\n\nThroughput: {throughput:.3f} bits/s\nMiss rate: {miss_rate:.3f}\n\nPress ENTER to continue"
            ),
            justify="center",
        )

    def abort():
        state["result"] = None
        win.destroy()

    def on_click(event):
        if not state["started"] or state["done"]:
            return

        x, y = float(event.x), float(event.y)
        tx, ty, r, dist = state["target"]

        mt = time.perf_counter() - state["t0"]
        hit = (x - tx) ** 2 + (y - ty) ** 2 <= r ** 2

        w = max(2.0, 2.0 * r)
        d = math.hypot(tx - state["prev"][0], ty - state["prev"][1])
        d = max(1.0, d)
        idx = math.log2(d / w + 1.0)

        if hit:
            state["sum_id"] += idx
            state["sum_mt"] += max(1e-3, mt)
        else:
            state["misses"] += 1

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

        if event.keysym == "space" and not state["started"]:
            state["started"] = True
            draw_target()
            return

        if event.keysym == "Return" and state["done"]:
            win.destroy()
            return

    win.bind("<Button-1>", on_click)
    win.bind("<Key>", on_key)

    root.wait_window(win)
    return state["result"]
