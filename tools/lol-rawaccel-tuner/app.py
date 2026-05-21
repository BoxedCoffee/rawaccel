import json
import math
import os
import pathlib
import random
import subprocess
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import statistics

from optimizer import CemTuner
from rawaccel import RawAccelController
from task import run_task_block
import drills
import curve_preview
import report

APP_DIR = pathlib.Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
RUNS_DIR = APP_DIR / "runs"


def _default_config():
    return {
        "writer_path": "",
        "settings_path": "",
        "profile_index": 0,
        "task": {
            "trials": 28,
            "penalty": 2.0,
            "timeout_ms": 2200,
            "start_gate": True,
            "distances_px": [140, 240, 360],
            "radii_px": [10, 14, 20],
        },
        "dual_drills": drills.default_dual_config(),
        "sensitivity": {
            "bounds": {
                "outputDpi": [200.0, 800.0],
            },
            "fine_pct": 0.05,
        },
        "search": {
            "population": 5,
            "elite": 2,
            "generations": 8,
            "seed": 1337,
            "repeats": 2,
            "bounds": {
                "syncSpeed": [0.5, 25.0],
                "motivity": [1.1, 2.4],
                "gamma": [0.6, 1.8],
                "smooth": [0.2, 0.8],
            },
        },
        "ai": {
            "enabled": True,
            "max_iters": 18,
            "confidence_threshold": 0.85,
            "history_limit": 12,
            "temperature": 0.2,
        },
    }


def _load_config():
    if not CONFIG_PATH.exists():
        return _default_config()

    def merge(base, override):
        if not isinstance(base, dict) or not isinstance(override, dict):
            return override
        out = dict(base)
        for k, v in override.items():
            if isinstance(out.get(k), dict) and isinstance(v, dict):
                out[k] = merge(out[k], v)
            else:
                out[k] = v
        return out

    return merge(_default_config(), json.loads(CONFIG_PATH.read_text(encoding="utf-8")))


def _save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LoL RawAccel Tuner")
        self.resizable(False, False)

        self.cfg = _load_config()

        self.writer_var = tk.StringVar(value=self.cfg.get("writer_path", ""))
        self.settings_var = tk.StringVar(value=self.cfg.get("settings_path", ""))

        self.trials_var = tk.IntVar(value=int(self.cfg["task"]["trials"]))
        self.penalty_var = tk.DoubleVar(value=float(self.cfg["task"]["penalty"]))
        self.timeout_var = tk.IntVar(value=int(self.cfg["task"].get("timeout_ms", 2200)))
        self.start_gate_var = tk.BooleanVar(value=bool(self.cfg["task"].get("start_gate", True)))

        dual_cfg = self.cfg.get("dual_drills")
        if not isinstance(dual_cfg, dict):
            dual_cfg = drills.default_dual_config()
        self.dual_enabled_var = tk.BooleanVar(value=bool(dual_cfg.get("enabled", False)))
        weights = drills.norm_weights(dual_cfg.get("weights", {}))
        self.weight_micro_var = tk.DoubleVar(value=float(weights["micro"]))
        self.weight_flick_var = tk.DoubleVar(value=float(weights["flick"]))
        self.micro_floor_var = tk.DoubleVar(value=float(dual_cfg.get("micro_floor", 0.95)))

        sens_bounds = self.cfg.get("sensitivity", {}).get("bounds", {}).get("outputDpi", [200.0, 800.0])
        self.dpi_min = tk.DoubleVar(value=float(sens_bounds[0]))
        self.dpi_max = tk.DoubleVar(value=float(sens_bounds[1]))

        bounds = self.cfg["search"]["bounds"]
        self.sync_min = tk.DoubleVar(value=float(bounds["syncSpeed"][0]))
        self.sync_max = tk.DoubleVar(value=float(bounds["syncSpeed"][1]))
        self.mot_min = tk.DoubleVar(value=float(bounds["motivity"][0]))
        self.mot_max = tk.DoubleVar(value=float(bounds["motivity"][1]))
        self.gam_min = tk.DoubleVar(value=float(bounds["gamma"][0]))
        self.gam_max = tk.DoubleVar(value=float(bounds["gamma"][1]))
        self.smo_min = tk.DoubleVar(value=float(bounds["smooth"][0]))
        self.smo_max = tk.DoubleVar(value=float(bounds["smooth"][1]))

        self.population_var = tk.IntVar(value=int(self.cfg["search"]["population"]))
        self.elite_var = tk.IntVar(value=int(self.cfg["search"]["elite"]))
        self.generations_var = tk.IntVar(value=int(self.cfg["search"]["generations"]))
        self.seed_var = tk.IntVar(value=int(self.cfg["search"]["seed"]))
        self.repeats_var = tk.IntVar(value=int(self.cfg["search"].get("repeats", 2)))

        self.status_var = tk.StringVar(value="Idle")
        self.best_var = tk.StringVar(value="")
        self.progress_var = tk.StringVar(value="")

        self._session = None
        self._stop_requested = False

        self._curve_canvas = None
        self._last_best = None

        self._build_ui()
        self.after(100, self._first_run_prompt)

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        frm_paths = tk.LabelFrame(self, text="Raw Accel")
        frm_paths.grid(row=0, column=0, sticky="ew", **pad)

        tk.Label(frm_paths, text="writer.exe").grid(row=0, column=0, sticky="w", **pad)
        tk.Entry(frm_paths, width=60, textvariable=self.writer_var).grid(row=0, column=1, **pad)
        tk.Button(frm_paths, text="Browse", command=self._pick_writer).grid(row=0, column=2, **pad)

        tk.Label(frm_paths, text="settings.json").grid(row=1, column=0, sticky="w", **pad)
        tk.Entry(frm_paths, width=60, textvariable=self.settings_var).grid(row=1, column=1, **pad)
        tk.Button(frm_paths, text="Browse", command=self._pick_settings).grid(row=1, column=2, **pad)

        frm_task = tk.LabelFrame(self, text="Task")
        frm_task.grid(row=1, column=0, sticky="ew", **pad)

        tk.Label(frm_task, text="Trials per block").grid(row=0, column=0, sticky="w", **pad)
        tk.Entry(frm_task, width=10, textvariable=self.trials_var).grid(row=0, column=1, sticky="w", **pad)

        tk.Label(frm_task, text="Miss penalty").grid(row=0, column=2, sticky="w", **pad)
        tk.Entry(frm_task, width=10, textvariable=self.penalty_var).grid(row=0, column=3, sticky="w", **pad)

        tk.Label(frm_task, text="Timeout ms").grid(row=1, column=0, sticky="w", **pad)
        tk.Entry(frm_task, width=10, textvariable=self.timeout_var).grid(row=1, column=1, sticky="w", **pad)

        tk.Checkbutton(frm_task, text="Start gate", variable=self.start_gate_var).grid(row=1, column=2, columnspan=2, sticky="w", **pad)

        tk.Checkbutton(frm_task, text="Micro+Flick", variable=self.dual_enabled_var).grid(row=2, column=0, sticky="w", **pad)
        tk.Label(frm_task, text="w micro").grid(row=2, column=1, sticky="e", **pad)
        tk.Entry(frm_task, width=8, textvariable=self.weight_micro_var).grid(row=2, column=2, sticky="w", **pad)
        tk.Label(frm_task, text="w flick").grid(row=2, column=3, sticky="e", **pad)
        tk.Entry(frm_task, width=8, textvariable=self.weight_flick_var).grid(row=2, column=4, sticky="w", **pad)
        tk.Label(frm_task, text="micro floor").grid(row=2, column=5, sticky="e", **pad)
        tk.Entry(frm_task, width=8, textvariable=self.micro_floor_var).grid(row=2, column=6, sticky="w", **pad)

        frm_sens = tk.LabelFrame(self, text="Sensitivity bounds (no accel phase)")
        frm_sens.grid(row=2, column=0, sticky="ew", **pad)

        tk.Label(frm_sens, text="min").grid(row=0, column=1, **pad)
        tk.Label(frm_sens, text="max").grid(row=0, column=2, **pad)
        self._bound_row(frm_sens, 1, "outputDpi", self.dpi_min, self.dpi_max)

        frm_bounds = tk.LabelFrame(self, text="Synchronous bounds")
        frm_bounds.grid(row=3, column=0, sticky="ew", **pad)

        headers = ["min", "max"]
        for i, h in enumerate(headers):
            tk.Label(frm_bounds, text=h).grid(row=0, column=i + 1, **pad)

        self._bound_row(frm_bounds, 1, "syncSpeed", self.sync_min, self.sync_max)
        self._bound_row(frm_bounds, 2, "motivity", self.mot_min, self.mot_max)
        self._bound_row(frm_bounds, 3, "gamma", self.gam_min, self.gam_max)
        self._bound_row(frm_bounds, 4, "smooth", self.smo_min, self.smo_max)

        frm_search = tk.LabelFrame(self, text="Search")
        frm_search.grid(row=4, column=0, sticky="ew", **pad)

        tk.Label(frm_search, text="population").grid(row=0, column=0, sticky="w", **pad)
        tk.Entry(frm_search, width=8, textvariable=self.population_var).grid(row=0, column=1, sticky="w", **pad)

        tk.Label(frm_search, text="elite").grid(row=0, column=2, sticky="w", **pad)
        tk.Entry(frm_search, width=8, textvariable=self.elite_var).grid(row=0, column=3, sticky="w", **pad)

        tk.Label(frm_search, text="generations").grid(row=0, column=4, sticky="w", **pad)
        tk.Entry(frm_search, width=8, textvariable=self.generations_var).grid(row=0, column=5, sticky="w", **pad)

        tk.Label(frm_search, text="seed").grid(row=0, column=6, sticky="w", **pad)
        tk.Entry(frm_search, width=10, textvariable=self.seed_var).grid(row=0, column=7, sticky="w", **pad)

        tk.Label(frm_search, text="repeats").grid(row=0, column=8, sticky="w", **pad)
        tk.Entry(frm_search, width=6, textvariable=self.repeats_var).grid(row=0, column=9, sticky="w", **pad)

        frm_actions = tk.Frame(self)
        frm_actions.grid(row=5, column=0, sticky="ew", **pad)

        tk.Button(frm_actions, text="Start optimization", command=self._start_optimization).grid(row=0, column=0, **pad)
        tk.Button(frm_actions, text="Quick sens (7)", command=self._start_quick_sens).grid(row=0, column=1, **pad)
        tk.Button(frm_actions, text="A/B duel", command=self._start_duel).grid(row=0, column=2, **pad)
        tk.Button(frm_actions, text="Guided tune", command=self._start_guided).grid(row=0, column=3, **pad)
        tk.Button(frm_actions, text="AI tune", command=self._start_ai_tune).grid(row=0, column=4, **pad)
        tk.Button(frm_actions, text="Apply best", command=self._apply_best).grid(row=0, column=5, **pad)
        tk.Button(frm_actions, text="Save best", command=self._save_best).grid(row=0, column=6, **pad)
        tk.Button(frm_actions, text="Stop", command=self._stop).grid(row=0, column=7, **pad)
        tk.Button(frm_actions, text="Restore base", command=self._restore_base).grid(row=0, column=8, **pad)
        tk.Button(frm_actions, text="Open runs", command=self._open_runs).grid(row=0, column=9, **pad)

        frm_status = tk.LabelFrame(self, text="Status")
        frm_status.grid(row=6, column=0, sticky="ew", **pad)

        tk.Label(frm_status, textvariable=self.status_var, width=92, anchor="w").grid(row=0, column=0, **pad)
        tk.Label(frm_status, textvariable=self.progress_var, width=92, anchor="w").grid(row=1, column=0, **pad)
        tk.Label(frm_status, textvariable=self.best_var, width=92, anchor="w").grid(row=2, column=0, **pad)

        frm_curve = tk.LabelFrame(self, text="Curve preview (synchronous)")
        frm_curve.grid(row=7, column=0, sticky="ew", **pad)
        self._curve_canvas = tk.Canvas(frm_curve, width=700, height=220, bg="#0b0f14", highlightthickness=0)
        self._curve_canvas.grid(row=0, column=0, **pad)

    def _bound_row(self, parent, row, name, vmin, vmax):
        pad = {"padx": 8, "pady": 2}
        tk.Label(parent, text=name).grid(row=row, column=0, sticky="w", **pad)
        tk.Entry(parent, width=10, textvariable=vmin).grid(row=row, column=1, sticky="w", **pad)
        tk.Entry(parent, width=10, textvariable=vmax).grid(row=row, column=2, sticky="w", **pad)

    def _first_run_prompt(self):
        if self.writer_var.get() and self.settings_var.get():
            return
        messagebox.showinfo(
            "Setup",
            "Select Raw Accel writer.exe and your settings.json."
        )

    def _pick_writer(self):
        path = filedialog.askopenfilename(title="Select writer.exe", filetypes=[("writer.exe", "writer.exe"), ("All files", "*")])
        if path:
            self.writer_var.set(path)
            self._persist_ui_to_config()

    def _pick_settings(self):
        path = filedialog.askopenfilename(title="Select settings.json", filetypes=[("settings.json", "settings.json"), ("JSON", "*.json"), ("All files", "*")])
        if path:
            self.settings_var.set(path)
            self._persist_ui_to_config()

    def _persist_ui_to_config(self):
        self.cfg["writer_path"] = self.writer_var.get().strip()
        self.cfg["settings_path"] = self.settings_var.get().strip()
        self.cfg["task"]["trials"] = int(self.trials_var.get())
        self.cfg["task"]["penalty"] = float(self.penalty_var.get())
        self.cfg["task"]["timeout_ms"] = int(self.timeout_var.get())
        self.cfg["task"]["start_gate"] = bool(self.start_gate_var.get())

        self.cfg.setdefault("dual_drills", drills.default_dual_config())
        if not isinstance(self.cfg.get("dual_drills"), dict):
            self.cfg["dual_drills"] = drills.default_dual_config()
        self.cfg["dual_drills"]["enabled"] = bool(self.dual_enabled_var.get())
        self.cfg["dual_drills"].setdefault("weights", {})
        self.cfg["dual_drills"]["weights"] = drills.norm_weights(
            {"micro": float(self.weight_micro_var.get()), "flick": float(self.weight_flick_var.get())}
        )
        self.cfg["dual_drills"]["micro_floor"] = float(self.micro_floor_var.get())

        self.cfg.setdefault("sensitivity", {})
        self.cfg["sensitivity"].setdefault("bounds", {})
        self.cfg["sensitivity"]["bounds"]["outputDpi"] = [float(self.dpi_min.get()), float(self.dpi_max.get())]
        self.cfg["search"]["population"] = int(self.population_var.get())
        self.cfg["search"]["elite"] = int(self.elite_var.get())
        self.cfg["search"]["generations"] = int(self.generations_var.get())
        self.cfg["search"]["seed"] = int(self.seed_var.get())
        self.cfg["search"]["repeats"] = int(self.repeats_var.get())
        self.cfg["search"]["bounds"] = {
            "syncSpeed": [float(self.sync_min.get()), float(self.sync_max.get())],
            "motivity": [float(self.mot_min.get()), float(self.mot_max.get())],
            "gamma": [float(self.gam_min.get()), float(self.gam_max.get())],
            "smooth": [float(self.smo_min.get()), float(self.smo_max.get())],
        }
        _save_config(self.cfg)

    def _validate_ready(self):
        writer_path = self.writer_var.get().strip()
        settings_path = self.settings_var.get().strip()
        if not writer_path or not pathlib.Path(writer_path).exists():
            messagebox.showerror("Missing", "writer.exe path is missing or invalid")
            return False
        if not settings_path or not pathlib.Path(settings_path).exists():
            messagebox.showerror("Missing", "settings.json path is missing or invalid")
            return False
        return True

    def _score_result(self, result, penalty):
        overshoot_penalty = 1.0 / (1.0 + float(result.get("avg_overshoots", 0.0)) * 0.25)
        reaccel_penalty = 1.0 / (1.0 + float(result.get("avg_reaccels", 0.0)) * 0.2)
        miss_penalty = max(0.0, 1.0 - float(result.get("miss_rate", 1.0))) ** float(penalty)

        error_penalty = 1.0 / (1.0 + float(result.get("p90_error_px", result.get("avg_error_px", 0.0))) / 28.0)
        perp_penalty = 1.0 / (1.0 + float(result.get("avg_perp_dev", 0.0)) / 55.0)
        correction_penalty = 1.0 / (1.0 + float(result.get("avg_correction_ms", 0.0)) / 650.0)
        bias_mag = math.hypot(float(result.get("avg_bias_x", 0.0)), float(result.get("avg_bias_y", 0.0)))
        bias_penalty = 1.0 / (1.0 + bias_mag / 20.0)

        return (
            float(result.get("throughput", 0.0))
            * miss_penalty
            * float(result.get("avg_path_eff", 0.0))
            * perp_penalty
            * error_penalty
            * correction_penalty
            * bias_penalty
            * overshoot_penalty
            * reaccel_penalty
        )

    def _run_single_drill(self, cfg, seed, progress_hook=None):
        result = run_task_block(
            self,
            trials=int(cfg["trials"]),
            distances_px=list(cfg["distances_px"]),
            radii_px=list(cfg["radii_px"]),
            seed=int(seed),
            timeout_ms=int(cfg.get("timeout_ms", 0)),
            start_gate=bool(cfg.get("start_gate", False)),
        )
        if result is not None and progress_hook is not None:
            try:
                progress_hook()
            except Exception:
                pass
        return result

    def _eval_drills(self, seed, baseline=None, progress_hook=None):
        penalty = float(self.cfg["task"]["penalty"])

        dual_cfg = self.cfg.get("dual_drills")
        if isinstance(dual_cfg, dict) and bool(dual_cfg.get("enabled")):
            weights = drills.norm_weights(dual_cfg.get("weights", {}))
            micro_cfg = dual_cfg.get("micro") if isinstance(dual_cfg.get("micro"), dict) else drills.default_micro()
            flick_cfg = dual_cfg.get("flick") if isinstance(dual_cfg.get("flick"), dict) else drills.default_flick()

            micro_result = self._run_single_drill(micro_cfg, seed, progress_hook=progress_hook)
            if micro_result is None:
                return None
            micro_score = float(self._score_result(micro_result, penalty))

            flick_result = self._run_single_drill(flick_cfg, seed + 1, progress_hook=progress_hook)
            if flick_result is None:
                return None
            flick_score = float(self._score_result(flick_result, penalty))

            combined = weights["micro"] * micro_score + weights["flick"] * flick_score
            micro_floor = float(dual_cfg.get("micro_floor", 0.95))
            if baseline is not None:
                baseline_micro = float(baseline.get("micro_score", micro_score))
                if micro_score < baseline_micro * micro_floor:
                    combined = float("-inf")

            return {
                "combined_score": float(combined),
                "micro": micro_result,
                "flick": flick_result,
                "micro_score": float(micro_score),
                "flick_score": float(flick_score),
            }

        task_cfg = self.cfg["task"]
        result = self._run_single_drill(task_cfg, seed, progress_hook=progress_hook)
        if result is None:
            return None
        score = float(self._score_result(result, penalty))
        return {"combined_score": float(score), "single": result}

    def _draw_curve(self, cand):
        canvas = self._curve_canvas
        if canvas is None:
            return

        canvas.delete("all")
        if not isinstance(cand, dict) or cand.get("mode") != "synchronous":
            return

        w = int(canvas.cget("width"))
        h = int(canvas.cget("height"))
        pad = 18

        sync_speed = float(cand.get("syncSpeed", 5.0))
        motivity = float(cand.get("motivity", 1.5))
        gamma = float(cand.get("gamma", 1.0))
        smooth = float(cand.get("smooth", 0.5))

        pts = curve_preview.curve_points(sync_speed, motivity, gamma, smooth)
        xs = [math.log10(p[0]) for p in pts]
        ys = [p[1] for p in pts]

        x_min = min(xs)
        x_max = max(xs)
        y_min = min(ys)
        y_max = max(ys)
        y_min = min(y_min, 0.5)
        y_max = max(y_max, 1.5)

        def sx(x):
            return pad + (x - x_min) / (x_max - x_min) * (w - 2 * pad)

        def sy(y):
            return h - pad - (y - y_min) / (y_max - y_min) * (h - 2 * pad)

        canvas.create_rectangle(pad, pad, w - pad, h - pad, outline="#1f2937")

        for tick in (-1, 0, 1, 2):
            x = sx(float(tick))
            canvas.create_line(x, h - pad, x, h - pad + 4, fill="#475569")
            canvas.create_text(x, h - pad + 12, text=f"{10**tick:g}", fill="#94a3b8", font=("Segoe UI", 8))

        for y_tick in (0.5, 1.0, 1.5, 2.0):
            if y_tick < y_min or y_tick > y_max:
                continue
            y = sy(y_tick)
            canvas.create_line(pad - 4, y, pad, y, fill="#475569")
            canvas.create_text(pad - 8, y, text=f"{y_tick:g}", fill="#94a3b8", font=("Segoe UI", 8), anchor="e")

        coords = []
        for x, y in zip(xs, ys):
            coords.extend([sx(x), sy(y)])
        if len(coords) >= 4:
            canvas.create_line(*coords, fill="#2dd4bf", width=2)

        x0 = sx(math.log10(max(1e-9, sync_speed)))
        canvas.create_line(x0, pad, x0, h - pad, fill="#7c3aed")

        canvas.create_text(
            w - pad,
            pad,
            text=f"sync={sync_speed:.2f} mot={motivity:.2f} g={gamma:.2f} s={smooth:.2f}",
            fill="#cbd5e1",
            font=("Segoe UI", 9),
            anchor="ne",
        )

    def _read_current_output_dpi(self, settings_path):
        try:
            obj = json.loads(pathlib.Path(settings_path).read_text(encoding="utf-8"))
        except Exception:
            return None

        profiles = obj.get("profiles")
        if not isinstance(profiles, list) or not profiles:
            return None
        idx = int(self.cfg.get("profile_index", 0))
        if idx < 0 or idx >= len(profiles):
            idx = 0
        prof = profiles[idx]
        if not isinstance(prof, dict):
            return None
        val = prof.get("Output DPI")
        if val is None:
            return None
        try:
            return float(val)
        except Exception:
            return None

    def _start_quick_sens(self):
        if self._session is not None:
            messagebox.showinfo("Running", "A session is already running")
            return
        if not self._validate_ready():
            return

        self._persist_ui_to_config()

        sens_bounds = self.cfg.get("sensitivity", {}).get("bounds", {}).get("outputDpi", [200.0, 800.0])
        dpi_lo, dpi_hi = float(sens_bounds[0]), float(sens_bounds[1])
        if dpi_lo <= 0 or dpi_hi <= 0 or dpi_lo > dpi_hi:
            messagebox.showerror("Invalid", "outputDpi bounds must be positive and min <= max")
            return

        base_dpi = self._read_current_output_dpi(self.settings_var.get().strip())
        if base_dpi is None:
            base_dpi = 3200.0
        base_dpi = float(base_dpi)

        if dpi_hi <= 1000.0 and base_dpi >= 2000.0:
            messagebox.showinfo(
                "Tip",
                "Your Output DPI bounds look very low.\n"
                "For 3200 mouse DPI, a good starting range is 1600–4800.",
            )

        def clamp(v):
            return float(min(dpi_hi, max(dpi_lo, v)))

        base_dpi = clamp(base_dpi)

        initial = [round(dpi_lo, 1), round(base_dpi, 1), round(dpi_hi, 1)]
        initial = [v for i, v in enumerate(initial) if v not in initial[:i]]

        self._stop_requested = False

        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        run_id = time.strftime("%Y%m%d-%H%M%S")
        run_dir = RUNS_DIR / f"quick_sens_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        controller = RawAccelController(
            self.writer_var.get().strip(),
            self.settings_var.get().strip(),
            profile_index=int(self.cfg.get("profile_index", 0)),
        )
        try:
            controller.snapshot_base(run_dir / "base_settings.json")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        log_path = run_dir / "results.csv"
        log_path.write_text(
            "phase,idx,score,tag,throughput,miss_rate,p90_error,pathEff,perpDev,overshoots,reaccels,timeToMoveMs,correctionMs,biasX,biasY,outputDpi\n",
            encoding="utf-8",
        )

        self._session = {
            "type": "quick_sens",
            "controller": controller,
            "run_dir": run_dir,
            "log_path": log_path,
            "pending": list(initial),
            "init_points": list(initial),
            "init_done": False,
            "results": {},
            "lo": float(dpi_lo),
            "hi": float(dpi_hi),
            "iter_points": None,
            "iter_scores": {},
            "best": None,
            "best_score": float("-inf"),
            "eval": 0,
            "max_evals": 7,
        }

        self.status_var.set(f"Quick sens: init [{dpi_lo:.0f}, {dpi_hi:.0f}], base {base_dpi:.0f}")
        self.best_var.set("")
        self.after(100, self._quick_sens_next)

    def _quick_sens_next(self):
        if self._session is None or self._session.get("type") != "quick_sens":
            return
        if self._stop_requested:
            self._finish("Stopped")
            return

        if int(self._session["eval"]) >= int(self._session["max_evals"]):
            best = self._session.get("best")
            if best is not None:
                controller = self._session["controller"]
                final_path = self._session["run_dir"] / "best_settings.json"
                try:
                    controller.write_candidate_settings({"mode": "noaccel", "outputDpi": float(best)}, final_path)
                    controller.apply_settings(final_path)
                except Exception:
                    pass
                self.status_var.set(f"Quick sens done: best Output DPI={float(best):.1f}")
            self._finish("Done")
            return

        pending = self._session["pending"]
        if not pending:
            lo = float(self._session["lo"])
            hi = float(self._session["hi"])
            span = hi - lo
            if span <= 1e-6:
                self._session["eval"] = int(self._session["max_evals"])
                self.after(10, self._quick_sens_next)
                return

            left = round(lo + span / 3.0, 1)
            right = round(hi - span / 3.0, 1)

            if left == right:
                mid = round((lo + hi) / 2.0, 1)
                if mid not in self._session["results"]:
                    pending.append(mid)
                else:
                    self._session["eval"] = int(self._session["max_evals"])
                    self.after(10, self._quick_sens_next)
                    return
            else:
                if left not in self._session["results"]:
                    pending.append(left)
                if right not in self._session["results"]:
                    pending.append(right)

            self._session["iter_points"] = (left, right)
            self._session["iter_scores"] = {}
            self.status_var.set(f"Quick sens: bracket [{lo:.0f}, {hi:.0f}]")

        dpi = float(pending.pop(0))
        idx = int(self._session["eval"]) + 1
        controller = self._session["controller"]

        cand = {"mode": "noaccel", "outputDpi": dpi}
        cand_path = self._session["run_dir"] / f"candidate_{idx:03d}.json"
        try:
            controller.write_candidate_settings(cand, cand_path)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self._finish("Error writing candidate")
            return

        self.status_var.set(f"Quick sens {idx}/7: applying Output DPI={dpi:.1f}")
        ok = controller.apply_settings(cand_path)
        if not ok:
            self._session["cursor"] += 1
            self.after(100, self._quick_sens_next)
            return

        self.after(1200, lambda: self._quick_sens_eval(idx, dpi))

    def _quick_sens_eval(self, idx, dpi):
        if self._session is None or self._session.get("type") != "quick_sens":
            return

        seed = int(self.seed_var.get()) + 9001
        eval_res = self._eval_drills(seed)
        if eval_res is None:
            self._stop_requested = True
            self._finish("Stopped")
            return

        def row(tag, score, r):
            return (
                f"sens,{idx},{float(score):.6f},{tag},{float(r.get('throughput', 0.0)):.6f},{float(r.get('miss_rate', 1.0)):.6f},"
                f"{float(r.get('p90_error_px', r.get('avg_error_px', 0.0))):.6f},{float(r.get('avg_path_eff', 0.0)):.6f},"
                f"{float(r.get('avg_perp_dev', 0.0)):.6f},{float(r.get('avg_overshoots', 0.0)):.6f},{float(r.get('avg_reaccels', 0.0)):.6f},"
                f"{float(r.get('avg_time_to_move_ms', 0.0)):.6f},{float(r.get('avg_correction_ms', 0.0)):.6f},"
                f"{float(r.get('avg_bias_x', 0.0)):.6f},{float(r.get('avg_bias_y', 0.0)):.6f},{dpi:.3f}\n"
            )

        lines = []
        if "single" in eval_res:
            r = eval_res["single"]
            score = eval_res["combined_score"]
            lines.append(row("single", score, r))
        else:
            lines.append(row("micro", eval_res.get("micro_score", 0.0), eval_res["micro"]))
            lines.append(row("flick", eval_res.get("flick_score", 0.0), eval_res["flick"]))
            lines.append(row("combined", eval_res["combined_score"], {"throughput": 0.0, "miss_rate": 0.0}))

        with open(self._session["log_path"], "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln)

        score = float(eval_res["combined_score"])
        self._session["results"][round(float(dpi), 3)] = score

        if not self._session.get("init_done"):
            init_points = self._session.get("init_points")
            if isinstance(init_points, list) and all(p in self._session["results"] for p in init_points):
                lo = float(self._session["lo"])
                hi = float(self._session["hi"])
                mid = float(sorted(init_points)[1]) if len(init_points) >= 3 else (lo + hi) / 2.0
                best = float(self._session["best"]) if self._session.get("best") is not None else mid
                if best <= lo + 1e-6:
                    self._session["hi"] = min(hi, mid)
                elif best >= hi - 1e-6:
                    self._session["lo"] = max(lo, mid)
                self._session["init_done"] = True

        if math.isfinite(score) and score > float(self._session["best_score"]):
            self._session["best_score"] = score
            self._session["best"] = dpi
            self.best_var.set(f"Best sens {score:.3f}: Output DPI={dpi:.1f}")

        iter_points = self._session.get("iter_points")
        if iter_points is not None:
            left, right = iter_points
            if round(float(dpi), 1) == float(left):
                self._session["iter_scores"]["left"] = score
            elif round(float(dpi), 1) == float(right):
                self._session["iter_scores"]["right"] = score

            scores = self._session["iter_scores"]
            if "left" in scores and "right" in scores:
                lo = float(self._session["lo"])
                hi = float(self._session["hi"])
                if float(scores["left"]) < float(scores["right"]):
                    self._session["lo"] = max(lo, float(left))
                else:
                    self._session["hi"] = min(hi, float(right))
                self._session["iter_points"] = None
                self._session["iter_scores"] = {}

        self._session["eval"] += 1
        self.after(150, self._quick_sens_next)

    def _read_current_curve(self, settings_path):
        try:
            obj = json.loads(pathlib.Path(settings_path).read_text(encoding="utf-8"))
        except Exception:
            return None

        profiles = obj.get("profiles")
        if not isinstance(profiles, list) or not profiles:
            return None
        idx = int(self.cfg.get("profile_index", 0))
        if idx < 0 or idx >= len(profiles):
            idx = 0
        prof = profiles[idx]
        if not isinstance(prof, dict):
            return None
        args = prof.get("Whole or horizontal accel parameters")
        if not isinstance(args, dict):
            return None
        if args.get("mode") != "synchronous":
            return None
        out = {}
        for k in ("syncSpeed", "motivity", "gamma", "smooth"):
            if k in args:
                try:
                    out[k] = float(args[k])
                except Exception:
                    pass
        return out if out else None

    def _start_duel(self):
        if self._session is not None:
            messagebox.showinfo("Running", "A session is already running")
            return
        if not self._validate_ready():
            return

        self._persist_ui_to_config()

        bounds = self.cfg["search"]["bounds"]
        fixed_dpi = self._read_current_output_dpi(self.settings_var.get().strip())
        if fixed_dpi is None:
            messagebox.showerror("Missing", "Could not read 'Output DPI' from settings.json. Run Quick sens or set it in settings.json.")
            return

        base_curve = self._read_current_curve(self.settings_var.get().strip())
        if base_curve is None:
            base_curve = {k: (float(v[0]) + float(v[1])) / 2.0 for k, v in bounds.items()}

        seed = int(self.seed_var.get())
        rng = random.Random(seed + 123)

        def sample(k):
            lo, hi = bounds[k]
            return float(rng.uniform(float(lo), float(hi)))

        candidates = []
        candidates.append({"syncSpeed": base_curve.get("syncSpeed", 5.0), "motivity": base_curve.get("motivity", 1.5), "gamma": base_curve.get("gamma", 1.0), "smooth": base_curve.get("smooth", 0.5)})
        for _ in range(7):
            candidates.append({k: sample(k) for k in ("syncSpeed", "motivity", "gamma", "smooth")})

        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        run_id = time.strftime("%Y%m%d-%H%M%S")
        run_dir = RUNS_DIR / f"duel_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        controller = RawAccelController(
            self.writer_var.get().strip(),
            self.settings_var.get().strip(),
            profile_index=int(self.cfg.get("profile_index", 0)),
        )
        try:
            controller.snapshot_base(run_dir / "base_settings.json")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        log_path = run_dir / "results.csv"
        log_path.write_text(
            "phase,idx,score,tag,throughput,miss_rate,p90_error,pathEff,perpDev,overshoots,reaccels,timeToMoveMs,correctionMs,biasX,biasY,outputDpi,syncSpeed,motivity,gamma,smooth,round,match,side\n",
            encoding="utf-8",
        )

        self._stop_requested = False
        self._session = {
            "type": "duel",
            "controller": controller,
            "run_dir": run_dir,
            "log_path": log_path,
            "fixed_dpi": float(fixed_dpi),
            "baseline": self._eval_drills(seed + 40002),
            "candidates": candidates,
            "round": 1,
            "match": 0,
            "winners": [],
            "eval_idx": 0,
            "seed": seed,
        }

        self.status_var.set("A/B duel: starting")
        self.after(100, self._duel_next)

    def _duel_pick(self, a, b, a_score, b_score):
        msg = (
            f"Pick winner:\n\n"
            f"A score={a_score:.4f}  sync={a['syncSpeed']:.2f} mot={a['motivity']:.2f} g={a['gamma']:.2f} s={a['smooth']:.2f}\n"
            f"B score={b_score:.4f}  sync={b['syncSpeed']:.2f} mot={b['motivity']:.2f} g={b['gamma']:.2f} s={b['smooth']:.2f}\n\n"
            "Yes=A  No=B  Cancel=Auto"
        )
        return messagebox.askyesnocancel("A/B Duel", msg)

    def _duel_next(self):
        if self._session is None or self._session.get("type") != "duel":
            return
        if self._stop_requested:
            self._finish("Stopped")
            return

        sess = self._session
        cand_list = sess["candidates"]
        if len(cand_list) <= 1:
            if cand_list:
                winner = cand_list[0]
                best_path = sess["run_dir"] / "best_settings.json"
                try:
                    cand = {"mode": "synchronous", "outputDpi": float(sess["fixed_dpi"]), **winner}
                    sess["controller"].write_candidate_settings(cand, best_path)
                    sess["controller"].apply_settings(best_path)
                except Exception:
                    pass
            self._finish("Done")
            return

        if len(cand_list) % 2 == 1:
            sess["winners"].append(cand_list.pop())

        if not cand_list:
            sess["candidates"] = sess["winners"]
            sess["winners"] = []
            sess["round"] += 1
            sess["match"] = 0
            self.after(100, self._duel_next)
            return

        a = cand_list.pop(0)
        b = cand_list.pop(0)
        sess["match"] += 1
        rnd = int(sess["round"])
        match = int(sess["match"])
        seed = int(sess["seed"]) + rnd * 1000 + match * 10

        a_cand = {"mode": "synchronous", "outputDpi": float(sess["fixed_dpi"]), **a}
        b_cand = {"mode": "synchronous", "outputDpi": float(sess["fixed_dpi"]), **b}

        self._draw_curve(a_cand)
        self.status_var.set(f"A/B duel r{rnd} m{match}: A")
        a_path = sess["run_dir"] / f"r{rnd}_m{match}_A.json"
        sess["controller"].write_candidate_settings(a_cand, a_path)
        if not sess["controller"].apply_settings(a_path):
            a_eval = {"combined_score": float("-inf"), "single": {}}
        else:
            a_eval = self._eval_drills(seed, baseline=sess.get("baseline"))
            if a_eval is None:
                self._stop_requested = True
                self._finish("Stopped")
                return

        self._draw_curve(b_cand)
        self.status_var.set(f"A/B duel r{rnd} m{match}: B")
        b_path = sess["run_dir"] / f"r{rnd}_m{match}_B.json"
        sess["controller"].write_candidate_settings(b_cand, b_path)
        if not sess["controller"].apply_settings(b_path):
            b_eval = {"combined_score": float("-inf"), "single": {}}
        else:
            b_eval = self._eval_drills(seed, baseline=sess.get("baseline"))
            if b_eval is None:
                self._stop_requested = True
                self._finish("Stopped")
                return

        a_score = float(a_eval.get("combined_score", float("-inf")))
        b_score = float(b_eval.get("combined_score", float("-inf")))

        def log_eval(side, score, eval_res, cand):
            sess["eval_idx"] += 1
            idx0 = int(sess["eval_idx"])
            phase = "duel"

            def row(tag, score, r):
                return (
                    f"{phase},{idx0},{float(score):.6f},{tag},{float(r.get('throughput', 0.0)):.6f},{float(r.get('miss_rate', 1.0)):.6f},"
                    f"{float(r.get('p90_error_px', r.get('avg_error_px', 0.0))):.6f},{float(r.get('avg_path_eff', 0.0)):.6f},"
                    f"{float(r.get('avg_perp_dev', 0.0)):.6f},{float(r.get('avg_overshoots', 0.0)):.6f},{float(r.get('avg_reaccels', 0.0)):.6f},"
                    f"{float(r.get('avg_time_to_move_ms', 0.0)):.6f},{float(r.get('avg_correction_ms', 0.0)):.6f},"
                    f"{float(r.get('avg_bias_x', 0.0)):.6f},{float(r.get('avg_bias_y', 0.0)):.6f},{float(sess.get('fixed_dpi', 0.0)):.3f},"
                    f"{float(cand.get('syncSpeed', 0.0)):.6f},{float(cand.get('motivity', 0.0)):.6f},{float(cand.get('gamma', 0.0)):.6f},{float(cand.get('smooth', 0.0)):.6f},"
                    f"{rnd},{match},{side}\n"
                )

            lines = []
            if eval_res is None:
                return
            if "single" in eval_res:
                lines.append(row("single", score, eval_res["single"]))
            else:
                lines.append(row("micro", eval_res.get("micro_score", 0.0), eval_res["micro"]))
                lines.append(row("flick", eval_res.get("flick_score", 0.0), eval_res["flick"]))
                lines.append(row("combined", score, {"throughput": 0.0, "miss_rate": 0.0}))
            with open(sess["log_path"], "a", encoding="utf-8") as f:
                for ln in lines:
                    f.write(ln)

        log_eval("A", a_score, a_eval, a)
        log_eval("B", b_score, b_eval, b)

        choice = self._duel_pick(a, b, a_score, b_score)
        if choice is True:
            winner = a
        elif choice is False:
            winner = b
        else:
            winner = a if a_score >= b_score else b

        sess["winners"].append(winner)
        self.after(100, self._duel_next)

    def _start_optimization(self):
        if self._session is not None:
            messagebox.showinfo("Running", "Optimization already running")
            return
        if not self._validate_ready():
            return

        self._persist_ui_to_config()

        bounds = self.cfg["search"]["bounds"]
        if float(bounds["syncSpeed"][0]) <= 0 or float(bounds["syncSpeed"][1]) <= 0:
            messagebox.showerror("Invalid", "syncSpeed bounds must be positive")
            return
        if float(bounds["gamma"][0]) <= 0 or float(bounds["gamma"][1]) <= 0:
            messagebox.showerror("Invalid", "gamma bounds must be positive")
            return
        if float(bounds["syncSpeed"][0]) > float(bounds["syncSpeed"][1]):
            messagebox.showerror("Invalid", "syncSpeed min must be <= max")
            return
        if float(bounds["gamma"][0]) > float(bounds["gamma"][1]):
            messagebox.showerror("Invalid", "gamma min must be <= max")
            return

        repeats = int(self.cfg["search"].get("repeats", 2))
        if repeats < 1:
            messagebox.showerror("Invalid", "repeats must be >= 1")
            return

        self._stop_requested = False

        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        run_id = time.strftime("%Y%m%d-%H%M%S")
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        controller = RawAccelController(
            self.writer_var.get().strip(),
            self.settings_var.get().strip(),
            profile_index=int(self.cfg.get("profile_index", 0)),
        )
        try:
            controller.snapshot_base(run_dir / "base_settings.json")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        base_seed = int(self.seed_var.get())
        task_seeds = [base_seed + 10000 * i for i in range(repeats)]

        curve_tuner = CemTuner(
            bounds=bounds,
            population=int(self.population_var.get()),
            elite=int(self.elite_var.get()),
            generations=int(self.generations_var.get()),
            seed=base_seed + 23,
        )

        fixed_dpi = self._read_current_output_dpi(self.settings_var.get().strip())
        if fixed_dpi is None:
            messagebox.showerror("Missing", "Could not read 'Output DPI' from settings.json. Run Quick sens or set it in settings.json.")
            return

        log_path = run_dir / "results.csv"
        log_path.write_text(
            "phase,idx,generation,member,score,tag,throughput,miss_rate,p90_error,pathEff,perpDev,overshoots,reaccels,timeToMoveMs,correctionMs,biasX,biasY,outputDpi,syncSpeed,motivity,gamma,smooth\n",
            encoding="utf-8",
        )

        self._session = {
            "controller": controller,
            "phase": "curve",
            "curve_tuner": curve_tuner,
            "repeats": repeats,
            "task_seeds": task_seeds,
            "base_seed": base_seed,
            "baseline_checked_at": None,
            "repeat_idx": 0,
            "repeat_runs": [],
            "candidate": None,
            "best_curve": None,
            "fixed_dpi": float(fixed_dpi),
            "baseline": None,
            "run_dir": run_dir,
            "log_path": log_path,
            "idx": 0,
            "best": None,
            "best_score": -1e9,
            "last_best_idx": 0,
        }

        self.status_var.set(f"Run {run_id}: applying base settings")
        ok = controller.apply_settings(controller.base_settings_path)
        if not ok:
            messagebox.showwarning("Writer", "writer.exe reported an error applying base settings")

        self.status_var.set(f"Run {run_id}: warmup (not logged)")
        warmup = self._eval_drills(base_seed + 40001)
        if warmup is None:
            self._stop_requested = True
            self._finish("Stopped")
            return

        self.status_var.set(f"Run {run_id}: baseline")
        baseline = self._eval_drills(base_seed + 40002)
        if baseline is None:
            self._stop_requested = True
            self._finish("Stopped")
            return
        self._session["baseline"] = baseline

        self.after(100, self._next_eval)

    def _stop(self):
        self._stop_requested = True
        self.status_var.set("Stop requested; finishing current block")

    def _restore_base(self):
        if not self._validate_ready():
            return
        self._persist_ui_to_config()
        controller = RawAccelController(
            self.writer_var.get().strip(),
            self.settings_var.get().strip(),
            profile_index=int(self.cfg.get("profile_index", 0)),
        )
        ok = controller.apply_settings(controller.base_settings_path)
        if not ok:
            messagebox.showwarning("Writer", "writer.exe reported an error")
        else:
            self.status_var.set("Base settings applied")

    def _apply_best(self):
        if self._session is not None:
            messagebox.showinfo("Running", "Session is running")
            return
        if not self._validate_ready():
            return
        if self._last_best is None:
            messagebox.showerror("Missing", "No best candidate yet")
            return

        self._persist_ui_to_config()
        controller = RawAccelController(
            self.writer_var.get().strip(),
            self.settings_var.get().strip(),
            profile_index=int(self.cfg.get("profile_index", 0)),
        )
        cand = dict(self._last_best)
        if "outputDpi" not in cand:
            dpi = self._read_current_output_dpi(self.settings_var.get().strip())
            if dpi is not None:
                cand["outputDpi"] = float(dpi)
        if "mode" not in cand:
            cand["mode"] = "synchronous" if "syncSpeed" in cand else "noaccel"

        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = RUNS_DIR / "best_applied.json"
        try:
            controller.write_candidate_settings(cand, out_path)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        ok = controller.apply_settings(out_path)
        if not ok:
            messagebox.showwarning("Writer", "writer.exe reported an error")
            return
        self.status_var.set("Best applied")
        self._draw_curve(cand)

    def _save_best(self):
        if self._session is not None:
            messagebox.showinfo("Running", "Session is running")
            return
        if not self._validate_ready():
            return
        if self._last_best is None:
            messagebox.showerror("Missing", "No best candidate yet")
            return

        dest = filedialog.asksaveasfilename(
            title="Save best settings.json",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*")],
        )
        if not dest:
            return

        controller = RawAccelController(
            self.writer_var.get().strip(),
            self.settings_var.get().strip(),
            profile_index=int(self.cfg.get("profile_index", 0)),
        )

        cand = dict(self._last_best)
        if "outputDpi" not in cand:
            dpi = self._read_current_output_dpi(self.settings_var.get().strip())
            if dpi is not None:
                cand["outputDpi"] = float(dpi)
        if "mode" not in cand:
            cand["mode"] = "synchronous" if "syncSpeed" in cand else "noaccel"

        try:
            controller.write_candidate_settings(cand, dest)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        messagebox.showinfo("Saved", str(dest))

    def _open_runs(self):
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(RUNS_DIR)])

    def _finish(self, msg):
        sess = self._session
        if isinstance(sess, dict):
            if isinstance(sess.get("best"), dict):
                self._last_best = dict(sess["best"])
            elif sess.get("type") == "quick_sens" and sess.get("best") is not None:
                self._last_best = {"mode": "noaccel", "outputDpi": float(sess["best"])}
            log_path = sess.get("log_path")
            run_dir = sess.get("run_dir")
            if log_path:
                try:
                    title = f"LoL RawAccel Tuner - {sess.get('type', sess.get('phase', 'run'))}"
                    out = report.write_report(log_path, title=title)
                    if run_dir:
                        self.status_var.set(f"{msg} (report: {out.name})")
                    else:
                        self.status_var.set(msg)
                except Exception:
                    self.status_var.set(msg)
            else:
                self.status_var.set(msg)
        else:
            self.status_var.set(msg)
        self.progress_var.set("")
        self._session = None

    def _progress_hook(self):
        sess = self._session
        if not isinstance(sess, dict):
            return
        if "current_run" not in sess or "total_runs" not in sess:
            return
        sess["current_run"] = int(sess.get("current_run", 0)) + 1
        self.progress_var.set(f"{sess['current_run']}/{sess['total_runs']}")

    def _start_guided(self):
        if self._session is not None:
            messagebox.showinfo("Running", "A session is already running")
            return
        if not self._validate_ready():
            return

        self._persist_ui_to_config()

        fixed_dpi = self._read_current_output_dpi(self.settings_var.get().strip())
        if fixed_dpi is None:
            messagebox.showerror("Missing", "Could not read 'Output DPI' from settings.json. Run Quick sens first or set it.")
            return

        dual_cfg = self.cfg.get("dual_drills")
        dual_enabled = isinstance(dual_cfg, dict) and bool(dual_cfg.get("enabled"))
        runs_per_eval = 2 if dual_enabled else 1

        sens_evals = 7
        curve_candidates = 8
        curve_matches = curve_candidates - 1
        curve_evals = curve_matches * 2
        confirm_evals = 2
        total_evals = sens_evals + curve_evals + confirm_evals
        total_runs = total_evals * runs_per_eval

        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        run_id = time.strftime("%Y%m%d-%H%M%S")
        run_dir = RUNS_DIR / f"guided_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        controller = RawAccelController(
            self.writer_var.get().strip(),
            self.settings_var.get().strip(),
            profile_index=int(self.cfg.get("profile_index", 0)),
        )
        controller.snapshot_base(run_dir / "base_settings.json")

        log_path = run_dir / "results.csv"
        log_path.write_text(
            "phase,idx,score,tag,outputDpi,syncSpeed,motivity,gamma,smooth\n",
            encoding="utf-8",
        )

        self._stop_requested = False
        self._session = {
            "type": "guided",
            "controller": controller,
            "run_dir": run_dir,
            "log_path": log_path,
            "fixed_dpi": float(fixed_dpi),
            "sens_best": None,
            "curve_best": None,
            "baseline": None,
            "seed": int(self.seed_var.get()),
            "current_run": 0,
            "total_runs": int(total_runs),
        }
        self.progress_var.set(f"0/{total_runs}")
        self.status_var.set("Guided: sens")
        self.after(50, self._guided_sens)

    def _guided_sens(self):
        if self._session is None or self._session.get("type") != "guided":
            return
        if self._stop_requested:
            self._finish("Stopped")
            return

        sess = self._session
        seed = int(sess["seed"]) + 9100
        best = None
        best_score = float("-inf")

        sens_bounds = self.cfg.get("sensitivity", {}).get("bounds", {}).get("outputDpi", [200.0, 800.0])
        lo, hi = float(sens_bounds[0]), float(sens_bounds[1])
        base = float(sess["fixed_dpi"])
        points = [lo, base, hi]
        points = [float(p) for p in points]

        for i in range(7):
            if self._stop_requested:
                self._finish("Stopped")
                return
            t = i / 6.0
            dpi = lo * (1.0 - t) + hi * t
            if i in (0, 3, 6):
                dpi = points[(0 if i == 0 else 1 if i == 3 else 2)]
            cand = {"mode": "noaccel", "outputDpi": float(dpi)}
            path = sess["run_dir"] / f"sens_{i+1:02d}.json"
            sess["controller"].write_candidate_settings(cand, path)
            if not sess["controller"].apply_settings(path):
                continue

            eval_res = self._eval_drills(seed + i, progress_hook=self._progress_hook)
            if eval_res is None:
                self._finish("Stopped")
                return
            score = float(eval_res["combined_score"])
            with open(sess["log_path"], "a", encoding="utf-8") as f:
                f.write(f"sens,{i+1},{score:.6f},combined,{dpi:.3f},0,0,0,0\n")
            if score > best_score:
                best_score = score
                best = float(dpi)
                self.best_var.set(f"Guided sens best {best_score:.3f}: Output DPI={best:.1f}")

        if best is None:
            self._finish("Done")
            return

        sess["sens_best"] = best
        sess["fixed_dpi"] = float(best)
        self.status_var.set("Guided: curve")
        self.after(50, self._guided_curve)

    def _guided_curve(self):
        if self._session is None or self._session.get("type") != "guided":
            return
        if self._stop_requested:
            self._finish("Stopped")
            return

        sess = self._session
        bounds = self.cfg["search"]["bounds"]
        rng = random.Random(int(sess["seed"]) + 123)

        def sample(k):
            lo, hi = bounds[k]
            return float(rng.uniform(float(lo), float(hi)))

        candidates = []
        center = {k: (float(v[0]) + float(v[1])) / 2.0 for k, v in bounds.items()}
        candidates.append(center)
        for _ in range(7):
            candidates.append({k: sample(k) for k in ("syncSpeed", "motivity", "gamma", "smooth")})

        seed_base = int(sess["seed"]) + 9200
        while len(candidates) > 1:
            if len(candidates) % 2 == 1:
                candidates.append(candidates[-1])
            winners = []
            for m in range(0, len(candidates), 2):
                a = candidates[m]
                b = candidates[m + 1]

                def run_one(tag, params, s):
                    cand = {"mode": "synchronous", "outputDpi": float(sess["fixed_dpi"]), **params}
                    self._draw_curve(cand)
                    path = sess["run_dir"] / f"curve_r{len(winners)+1:02d}_{tag}.json"
                    sess["controller"].write_candidate_settings(cand, path)
                    if not sess["controller"].apply_settings(path):
                        return float("-inf")
                    ev = self._eval_drills(s, baseline=sess.get("baseline"), progress_hook=self._progress_hook)
                    if ev is None:
                        return None
                    score = float(ev["combined_score"])
                    with open(sess["log_path"], "a", encoding="utf-8") as f:
                        f.write(
                            f"curve,{sess.get('curve_idx',0)+1},{score:.6f},combined,{sess['fixed_dpi']:.3f},"
                            f"{params['syncSpeed']:.6f},{params['motivity']:.6f},{params['gamma']:.6f},{params['smooth']:.6f}\n"
                        )
                    sess["curve_idx"] = int(sess.get("curve_idx", 0)) + 1
                    return score

                sa = run_one("A", a, seed_base + m)
                if sa is None:
                    self._finish("Stopped")
                    return
                sb = run_one("B", b, seed_base + m + 1)
                if sb is None:
                    self._finish("Stopped")
                    return
                winners.append(a if sa >= sb else b)

            candidates = winners

        sess["curve_best"] = candidates[0]
        self.best_var.set(
            f"Guided curve best: syncSpeed={candidates[0]['syncSpeed']:.3f} mot={candidates[0]['motivity']:.3f} gamma={candidates[0]['gamma']:.3f} smooth={candidates[0]['smooth']:.3f}"
        )
        self.status_var.set("Guided: confirm")
        self.after(50, self._guided_confirm)

    def _guided_confirm(self):
        if self._session is None or self._session.get("type") != "guided":
            return
        if self._stop_requested:
            self._finish("Stopped")
            return

        sess = self._session
        best = sess.get("curve_best")
        if not isinstance(best, dict):
            self._finish("Done")
            return

        cand = {"mode": "synchronous", "outputDpi": float(sess["fixed_dpi"]), **best}
        path = sess["run_dir"] / "best_settings.json"
        sess["controller"].write_candidate_settings(cand, path)
        sess["controller"].apply_settings(path)

        seed = int(sess["seed"]) + 9300
        a = self._eval_drills(seed, progress_hook=self._progress_hook)
        if a is None:
            self._finish("Stopped")
            return
        b = self._eval_drills(seed + 1, progress_hook=self._progress_hook)
        if b is None:
            self._finish("Stopped")
            return

        with open(sess["log_path"], "a", encoding="utf-8") as f:
            f.write(f"confirm,1,{float(a['combined_score']):.6f},combined,{sess['fixed_dpi']:.3f},{best['syncSpeed']:.6f},{best['motivity']:.6f},{best['gamma']:.6f},{best['smooth']:.6f}\n")
            f.write(f"confirm,2,{float(b['combined_score']):.6f},combined,{sess['fixed_dpi']:.3f},{best['syncSpeed']:.6f},{best['motivity']:.6f},{best['gamma']:.6f},{best['smooth']:.6f}\n")

        self._last_best = dict(cand)
        self._finish("Done")

    def _next_eval(self):
        if self._session is None:
            return
        if self._stop_requested:
            self._finish("Stopped")
            return

        phase = self._session["phase"]
        tuner = self._session["curve_tuner"]
        controller = self._session["controller"]
        run_dir = self._session["run_dir"]
        idx = self._session["idx"]

        baseline = self._session.get("baseline")
        if (
            isinstance(baseline, dict)
            and idx > 0
            and idx % 10 == 0
            and self._session.get("baseline_checked_at") != idx
        ):
            self._session["baseline_checked_at"] = idx
            self.status_var.set("Drift check: baseline")
            base_seed = int(self._session.get("base_seed", 0))
            cur = self._eval_drills(base_seed + 60000 + idx)
            if cur is None:
                self._stop_requested = True
                self._finish("Stopped")
                return
            base0 = float(baseline.get("combined_score", 0.0))
            cur0 = float(cur.get("combined_score", 0.0))
            ratio = (cur0 / base0) if base0 != 0 else 1.0
            if ratio < 0.85:
                cont = messagebox.askyesno("Drift", f"Baseline dropped to {ratio*100:.0f}% of start. Continue?")
                if not cont:
                    self._stop_requested = True
                    self._finish("Stopped")
                    return

        candidate = tuner.next_candidate()
        if candidate is None:
            self._finish("Done")
            return

        self._session["candidate"] = candidate
        self._session["repeat_idx"] = 0
        self._session["repeat_runs"] = []

        fixed_dpi = float(self._session["fixed_dpi"])
        cand = {
            "mode": "synchronous",
            "outputDpi": fixed_dpi,
            "syncSpeed": float(candidate["syncSpeed"]),
            "motivity": float(candidate["motivity"]),
            "gamma": float(candidate["gamma"]),
            "smooth": float(candidate["smooth"]),
        }
        label = (
            f"Curve {idx+1}: DPI={fixed_dpi:.1f} syncSpeed={cand['syncSpeed']:.3f} motivity={cand['motivity']:.3f} "
            f"gamma={cand['gamma']:.3f} smooth={cand['smooth']:.3f}"
        )

        self._draw_curve(cand)

        cand_path = run_dir / f"candidate_{idx:03d}.json"
        try:
            controller.write_candidate_settings(cand, cand_path)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self._finish("Error writing candidate")
            return

        self.status_var.set(label)

        ok = controller.apply_settings(cand_path)
        if not ok:
            tuner.report_result(float("-inf"))
            self._session["idx"] += 1
            self.after(100, self._next_eval)
            return

        self.after(1300, lambda: self._run_block(idx, cand))

    def _run_block(self, idx, cand):
        if self._session is None:
            return

        repeat_idx = int(self._session["repeat_idx"])
        seeds = list(self._session["task_seeds"])
        seed = int(seeds[min(repeat_idx, len(seeds) - 1)])

        eval_res = self._eval_drills(seed, baseline=self._session.get("baseline"))
        if eval_res is None:
            self._stop_requested = True
            self._finish("Stopped")
            return

        score = float(eval_res["combined_score"])
        self._session["repeat_runs"].append((score, eval_res))
        self._session["repeat_idx"] += 1

        if int(self._session["repeat_idx"]) < int(self._session["repeats"]):
            self.after(250, lambda: self._run_block(idx, cand))
            return

        runs_sorted = sorted(self._session["repeat_runs"], key=lambda x: x[0])
        mid_run = runs_sorted[len(runs_sorted) // 2]
        score_med = float(mid_run[0])
        mid_eval = mid_run[1]

        phase = self._session["phase"]
        tuner = self._session["curve_tuner"]

        tuner.report_result(score_med)

        gen = tuner.generation
        member = tuner.member

        def row(tag, score, r):
            return (
                f"{phase},{idx},{gen},{member},{float(score):.6f},{tag},{float(r.get('throughput', 0.0)):.6f},{float(r.get('miss_rate', 1.0)):.6f},"
                f"{float(r.get('p90_error_px', r.get('avg_error_px', 0.0))):.6f},{float(r.get('avg_path_eff', 0.0)):.6f},"
                f"{float(r.get('avg_perp_dev', 0.0)):.6f},{float(r.get('avg_overshoots', 0.0)):.6f},{float(r.get('avg_reaccels', 0.0)):.6f},"
                f"{float(r.get('avg_time_to_move_ms', 0.0)):.6f},{float(r.get('avg_correction_ms', 0.0)):.6f},"
                f"{float(r.get('avg_bias_x', 0.0)):.6f},{float(r.get('avg_bias_y', 0.0)):.6f},{float(cand.get('outputDpi', 0.0)):.3f},"
                f"{float(cand.get('syncSpeed', 0.0)):.6f},{float(cand.get('motivity', 0.0)):.6f},{float(cand.get('gamma', 0.0)):.6f},{float(cand.get('smooth', 0.0)):.6f}\n"
            )

        lines = []
        if "single" in mid_eval:
            lines.append(row("single", score_med, mid_eval["single"]))
        else:
            lines.append(row("micro", mid_eval.get("micro_score", 0.0), mid_eval["micro"]))
            lines.append(row("flick", mid_eval.get("flick_score", 0.0), mid_eval["flick"]))
            lines.append(row("combined", score_med, {"throughput": 0.0, "miss_rate": 0.0}))
        with open(self._session["log_path"], "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln)

        if math.isfinite(score_med) and score_med > self._session["best_score"]:
            self._session["best_score"] = score_med
            self._session["best"] = dict(cand)
            self._session["last_best_idx"] = int(idx)

            self._session["best_curve"] = dict(cand)
            self._draw_curve(cand)
            self.best_var.set(
                (
                    f"Best curve {score_med:.3f}: DPI={cand['outputDpi']:.1f} syncSpeed={cand['syncSpeed']:.3f} "
                    f"mot={cand['motivity']:.3f} gamma={cand['gamma']:.3f} smooth={cand['smooth']:.3f}"
                )
            )

        self._session["idx"] += 1
        next_idx = int(self._session["idx"])
        last_best_idx = int(self._session.get("last_best_idx", 0))
        population = int(self.population_var.get())
        if next_idx - last_best_idx >= max(8, population * 2) and next_idx >= max(12, population * 3):
            self._finish("Done")
            return

        self.after(200, self._next_eval)

        return


    def _limit_step(self, proposed, current, bounds, frac):
        out = {}
        for k, v in proposed.items():
            if k not in bounds:
                continue
            lo, hi = bounds[k]
            span = float(hi) - float(lo)
            max_delta = span * float(frac)
            cur = float(current.get(k, (float(lo) + float(hi)) / 2.0))
            x = float(v)
            if max_delta > 0:
                if x > cur + max_delta:
                    x = cur + max_delta
                if x < cur - max_delta:
                    x = cur - max_delta
            out[k] = x
        return ai_tuner.clamp_candidate(out, bounds)

    def _start_ai_tune(self):
        if self._session is not None:
            messagebox.showinfo("Running", "A session is already running")
            return
        if not self._validate_ready():
            return

        self._persist_ui_to_config()

        fixed_dpi = self._read_current_output_dpi(self.settings_var.get().strip())
        if fixed_dpi is None:
            messagebox.showerror("Missing", "Could not read 'Output DPI' from settings.json. Run Quick sens first or set it.")
            return

        openai_cfg = ai_tuner.default_openai_compat_config()
        azure_cfg = ai_tuner.default_azure_config()
        if openai_cfg["api_base"] and openai_cfg["model"]:
            client = ai_tuner.OpenAICompatibleClient(
                api_base=openai_cfg["api_base"],
                api_key=openai_cfg["api_key"],
                model=openai_cfg["model"],
            )
        elif azure_cfg["endpoint"] and azure_cfg["api_key"] and azure_cfg["deployment"]:
            client = ai_tuner.AzureOpenAIClient(
                endpoint=azure_cfg["endpoint"],
                api_key=azure_cfg["api_key"],
                deployment=azure_cfg["deployment"],
                api_version=azure_cfg["api_version"],
            )
        else:
            messagebox.showerror(
                "Missing",
                "Set OPENAI_API_BASE + OPENAI_MODEL (+ optional OPENAI_API_KEY)\n"
                "or AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY + AZURE_OPENAI_DEPLOYMENT.",
            )
            return

        bounds = self.cfg["search"]["bounds"]
        start_curve = self._read_current_curve(self.settings_var.get().strip())
        if start_curve is None:
            start_curve = {k: (float(v[0]) + float(v[1])) / 2.0 for k, v in bounds.items()}

        max_iters = int(self.cfg.get("ai", {}).get("max_iters", 18))
        conf_th = float(self.cfg.get("ai", {}).get("confidence_threshold", 0.85))
        hist_lim = int(self.cfg.get("ai", {}).get("history_limit", 12))
        temp = float(self.cfg.get("ai", {}).get("temperature", 0.2))

        dual_cfg = self.cfg.get("dual_drills")
        dual_enabled = isinstance(dual_cfg, dict) and bool(dual_cfg.get("enabled"))
        runs_per_eval = 2 if dual_enabled else 1
        total_runs = int(max_iters * runs_per_eval)

        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        run_id = time.strftime("%Y%m%d-%H%M%S")
        run_dir = RUNS_DIR / f"ai_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        controller = RawAccelController(
            self.writer_var.get().strip(),
            self.settings_var.get().strip(),
            profile_index=int(self.cfg.get("profile_index", 0)),
        )
        try:
            controller.snapshot_base(run_dir / "base_settings.json")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        log_path = run_dir / "results.csv"
        log_path.write_text(
            "phase,iter,score,confidence,reason,tag,throughput,miss_rate,p90_error,pathEff,perpDev,overshoots,reaccels,timeToMoveMs,correctionMs,biasX,biasY,outputDpi,syncSpeed,motivity,gamma,smooth\n",
            encoding="utf-8",
        )

        trace_path = run_dir / "ai_trace.jsonl"
        trace_path.write_text("", encoding="utf-8")

        self._stop_requested = False
        self._session = {
            "type": "ai",
            "controller": controller,
            "run_dir": run_dir,
            "log_path": log_path,
            "trace_path": trace_path,
            "client": client,
            "bounds": bounds,
            "fixed_dpi": float(fixed_dpi),
            "candidate": ai_tuner.clamp_candidate(start_curve, bounds),
            "history": [],
            "best": None,
            "best_score": float("-inf"),
            "iter": 0,
            "max_iters": max_iters,
            "confidence_threshold": conf_th,
            "history_limit": hist_lim,
            "temperature": temp,
            "no_improve": 0,
            "step_frac": 0.25,
            "ai_thread": None,
            "ai_result": None,
            "ai_error": None,
            "current_run": 0,
            "total_runs": total_runs,
        }

        self.progress_var.set(f"0/{total_runs}")
        self.status_var.set("AI tune: starting")
        self.best_var.set("")

        self.after(50, self._ai_eval_step)

    def _ai_eval_step(self):
        sess = self._session
        if not isinstance(sess, dict) or sess.get("type") != "ai":
            return
        if self._stop_requested:
            self._finish("Stopped")
            return

        it = int(sess["iter"])
        if it >= int(sess["max_iters"]):
            self._last_best = dict(sess["best"]) if isinstance(sess.get("best"), dict) else None
            self._finish("Done")
            return

        cand = dict(sess["candidate"])
        full = {"mode": "synchronous", "outputDpi": float(sess["fixed_dpi"]), **cand}
        self._draw_curve(full)

        cand_path = pathlib.Path(sess["run_dir"]) / f"candidate_{it:03d}.json"
        sess["controller"].write_candidate_settings(full, cand_path)
        ok = sess["controller"].apply_settings(cand_path)
        if not ok:
            sess["iter"] += 1
            self.after(50, self._ai_eval_step)
            return

        self.status_var.set(f"AI tune {it+1}/{sess['max_iters']}: play")

        eval_res = self._eval_drills(
            int(self.seed_var.get()) + 50000 + it,
            baseline=sess.get("baseline"),
            progress_hook=self._progress_hook,
        )
        if eval_res is None:
            self._stop_requested = True
            self._finish("Stopped")
            return

        score = float(eval_res.get("combined_score", float("-inf")))
        reason = ""
        conf = 0.0

        record = {
            "iter": it,
            "candidate": cand,
            "score": score,
            "eval": eval_res,
        }
        sess["history"].append(record)
        if len(sess["history"]) > int(sess["history_limit"]):
            sess["history"] = sess["history"][len(sess["history"]) - int(sess["history_limit"]) :]

        improved = score > float(sess.get("best_score", float("-inf")))
        if improved:
            sess["best_score"] = score
            sess["best"] = dict(full)
            sess["no_improve"] = 0
            self.best_var.set(
                f"Best {score:.3f}: DPI={full['outputDpi']:.1f} sync={full['syncSpeed']:.3f} mot={full['motivity']:.3f} g={full['gamma']:.3f} s={full['smooth']:.3f}"
            )
        else:
            sess["no_improve"] = int(sess.get("no_improve", 0)) + 1

        def log_one(tag, r, s, conf, reason):
            with open(sess["log_path"], "a", encoding="utf-8") as f:
                f.write(
                    f"ai,{it},{float(s):.6f},{float(conf):.3f},{json.dumps(str(reason)[:200])},{tag},"
                    f"{float(r.get('throughput', 0.0)):.6f},{float(r.get('miss_rate', 1.0)):.6f},{float(r.get('p90_error_px', r.get('avg_error_px', 0.0))):.6f},"
                    f"{float(r.get('avg_path_eff', 0.0)):.6f},{float(r.get('avg_perp_dev', 0.0)):.6f},{float(r.get('avg_overshoots', 0.0)):.6f},{float(r.get('avg_reaccels', 0.0)):.6f},"
                    f"{float(r.get('avg_time_to_move_ms', 0.0)):.6f},{float(r.get('avg_correction_ms', 0.0)):.6f},"
                    f"{float(r.get('avg_bias_x', 0.0)):.6f},{float(r.get('avg_bias_y', 0.0)):.6f},"
                    f"{float(full['outputDpi']):.3f},{float(full['syncSpeed']):.6f},{float(full['motivity']):.6f},{float(full['gamma']):.6f},{float(full['smooth']):.6f}\n"
                )

        if "single" in eval_res:
            log_one("single", eval_res["single"], score, conf, reason)
        else:
            log_one("micro", eval_res["micro"], float(eval_res.get("micro_score", 0.0)), conf, reason)
            log_one("flick", eval_res["flick"], float(eval_res.get("flick_score", 0.0)), conf, reason)
            log_one("combined", {"throughput": 0.0, "miss_rate": 0.0}, score, conf, reason)

        sess["ai_result"] = None
        sess["ai_error"] = None

        def worker():
            try:
                bounds = sess["bounds"]
                state = {
                    "mode": "synchronous",
                    "bounds": bounds,
                    "fixed": {"outputDpi": float(sess["fixed_dpi"])},
                    "history": [
                        {
                            "iter": int(h["iter"]),
                            "candidate": h["candidate"],
                            "score": float(h["score"]),
                            "summary": _ai_eval_summary(h["eval"]),
                        }
                        for h in sess["history"]
                    ],
                    "best": {
                        "score": float(sess.get("best_score", float("-inf"))),
                        "candidate": dict(sess.get("best", {})),
                    },
                    "objective": {
                        "goal": "maximize combined_score",
                        "notes": "Prefer stable improvements. Keep motivity>1, gamma>0, syncSpeed>0, smooth in [0,1].",
                    },
                    "limits": {
                        "iter": it,
                        "max_iters": int(sess["max_iters"]),
                        "no_improve": int(sess.get("no_improve", 0)),
                    },
                }

                msgs = ai_tuner.build_ai_messages(state)
                content = sess["client"].chat(msgs, temperature=float(sess["temperature"]))
                parsed = ai_tuner.parse_ai_response(content)
                cand2 = ai_tuner.clamp_candidate(parsed["candidate"], bounds)
                cand2 = self._limit_step(cand2, cand, bounds, float(sess.get("step_frac", 0.25)))
                parsed["candidate"] = cand2
                sess["ai_result"] = parsed

                with open(sess["trace_path"], "a", encoding="utf-8") as f:
                    f.write(json.dumps({"iter": it, "request": state, "response": parsed}, ensure_ascii=False) + "\n")
            except Exception as e:
                sess["ai_error"] = str(e)

        def _ai_eval_summary(ev):
            if not isinstance(ev, dict):
                return {}
            if "single" in ev:
                return {"score": float(ev.get("combined_score", 0.0)), "single": ev["single"]}
            return {
                "score": float(ev.get("combined_score", 0.0)),
                "micro_score": float(ev.get("micro_score", 0.0)),
                "flick_score": float(ev.get("flick_score", 0.0)),
                "micro": ev.get("micro"),
                "flick": ev.get("flick"),
            }

        thread = threading.Thread(target=worker, daemon=True)
        sess["ai_thread"] = thread
        thread.start()

        self.status_var.set(f"AI tune {it+1}/{sess['max_iters']}: thinking")
        self.after(200, self._ai_poll)

    def _ai_poll(self):
        sess = self._session
        if not isinstance(sess, dict) or sess.get("type") != "ai":
            return
        if self._stop_requested:
            self._finish("Stopped")
            return

        th = sess.get("ai_thread")
        if isinstance(th, threading.Thread) and th.is_alive():
            self.after(200, self._ai_poll)
            return

        err = sess.get("ai_error")
        if err:
            messagebox.showerror("AI error", str(err))
            self._finish("Error")
            return

        res = sess.get("ai_result")
        if not isinstance(res, dict):
            self._finish("Error")
            return

        stop = bool(res.get("stop"))
        conf = float(res.get("confidence", 0.0))
        reason = str(res.get("reason", ""))
        cand2 = res.get("candidate")
        if not isinstance(cand2, dict):
            self._finish("Error")
            return

        with open(sess["log_path"], "a", encoding="utf-8") as f:
            f.write(f"ai,{int(sess['iter'])},0.000000,{conf:.3f},{json.dumps(reason[:200])},ai_note,0,0,0,0,0,0,0,0,0,0,0,{float(sess['fixed_dpi']):.3f},{cand2['syncSpeed']:.6f},{cand2['motivity']:.6f},{cand2['gamma']:.6f},{cand2['smooth']:.6f}\n")

        if stop and conf >= float(sess["confidence_threshold"]) and int(sess["iter"]) >= 3:
            self._last_best = dict(sess["best"]) if isinstance(sess.get("best"), dict) else None
            self._finish("Done")
            return

        if int(sess.get("no_improve", 0)) >= 6 and int(sess["iter"]) >= 6:
            self._last_best = dict(sess["best"]) if isinstance(sess.get("best"), dict) else None
            self._finish("Done")
            return

        sess["candidate"] = dict(cand2)
        sess["iter"] = int(sess["iter"]) + 1
        self.after(100, self._ai_eval_step)



if __name__ == "__main__":
    App().mainloop()
