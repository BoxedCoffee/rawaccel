import json
import math
import os
import pathlib
import random
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import statistics

import ai_tuner
from optimizer import CemTuner
from rawaccel import RawAccelController
from task import run_task_block
import drills
import curve_preview
import report

APP_DIR = pathlib.Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
RUNS_DIR = APP_DIR / "runs"
AI_STATE_FILE = "ai_state.json"


def _load_dotenv(path):
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except Exception:
        return

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if key not in os.environ:
            os.environ[key] = value


_load_dotenv(APP_DIR / ".env")


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
        "axis": {
            "bounds": {
                "yToXRatio": [0.85, 1.25],
            }
        },
        "ai": {
            "enabled": True,
            "preset": "Custom",
            "presets": {
                "Custom": {},
                "Wide tune": {
                    "max_iters": 40,
                    "confidence_threshold": 0.92,
                    "history_limit": 16,
                    "temperature": 0.25,
                    "baseline_recheck_every": 10,
                    "baseline_drop_ratio": 0.85,
                    "confirm_repeats": 3,
                    "confirm_win_rate": 0.67,
                    "min_step_frac": 0.10,
                    "max_step_frac": 0.45,
                    "start_step_frac": 0.30,
                    "eval_repeats": 2,
                    "eval_repeats_min": 1,
                    "repeat_gate_ratio": 0.05,
                    "axis_iters": 8,
                    "max_no_improve": 16,
                    "final_confirm_repeats": 6,
                    "plateau_stop": True,
                    "selection_metric": "median",
                    "stability_k": 0.5,
                },
                "Fine tune": {
                    "max_iters": 22,
                    "confidence_threshold": 0.88,
                    "history_limit": 14,
                    "temperature": 0.15,
                    "baseline_recheck_every": 8,
                    "baseline_drop_ratio": 0.85,
                    "confirm_repeats": 2,
                    "confirm_win_rate": 0.60,
                    "min_step_frac": 0.05,
                    "max_step_frac": 0.25,
                    "start_step_frac": 0.14,
                    "eval_repeats": 2,
                    "eval_repeats_min": 1,
                    "repeat_gate_ratio": 0.05,
                    "axis_iters": 6,
                    "max_no_improve": 12,
                    "final_confirm_repeats": 4,
                    "plateau_stop": True,
                    "selection_metric": "median",
                    "stability_k": 0.5,
                },
                "Balanced": {
                    "max_iters": 60,
                    "confidence_threshold": 0.94,
                    "history_limit": 30,
                    "temperature": 0.2,
                    "baseline_recheck_every": 12,
                    "baseline_drop_ratio": 0.83,
                    "confirm_repeats": 4,
                    "confirm_win_rate": 0.67,
                    "min_step_frac": 0.07,
                    "max_step_frac": 0.45,
                    "start_step_frac": 0.26,
                    "eval_repeats": 3,
                    "eval_repeats_min": 1,
                    "repeat_gate_ratio": 0.04,
                    "axis_iters": 10,
                    "max_no_improve": 24,
                    "final_confirm_repeats": 8,
                    "plateau_stop": True,
                    "selection_metric": "stable",
                    "stability_k": 0.5,
                },
                "Marathon": {
                    "max_iters": 120,
                    "confidence_threshold": 0.97,
                    "history_limit": 50,
                    "temperature": 0.2,
                    "baseline_recheck_every": 12,
                    "baseline_drop_ratio": 0.82,
                    "confirm_repeats": 4,
                    "confirm_win_rate": 0.70,
                    "min_step_frac": 0.06,
                    "max_step_frac": 0.50,
                    "start_step_frac": 0.28,
                    "eval_repeats": 3,
                    "eval_repeats_min": 1,
                    "repeat_gate_ratio": 0.04,
                    "axis_iters": 14,
                    "max_no_improve": 40,
                    "final_confirm_repeats": 10,
                    "plateau_stop": False,
                    "selection_metric": "stable",
                    "stability_k": 0.5,
                },
            },
            "max_iters": 18,
            "confidence_threshold": 0.85,
            "history_limit": 12,
            "temperature": 0.2,
            "baseline_recheck_every": 8,
            "baseline_drop_ratio": 0.85,
            "confirm_repeats": 2,
            "confirm_win_rate": 0.6,
            "min_step_frac": 0.08,
            "max_step_frac": 0.35,
            "start_step_frac": 0.25,
            "eval_repeats": 1,
            "eval_repeats_min": 1,
            "repeat_gate_ratio": 0.05,
            "axis_iters": 0,
            "max_no_improve": 6,
            "final_confirm_repeats": 0,
            "plateau_stop": True,
            "selection_metric": "median",
            "stability_k": 0.5,
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

        ai_cfg = self.cfg.get("ai")
        if not isinstance(ai_cfg, dict):
            ai_cfg = {}
        self.ai_preset_var = tk.StringVar(value=str(ai_cfg.get("preset", "Custom")))

        self.status_var = tk.StringVar(value="Idle")
        self.best_var = tk.StringVar(value="")
        self.progress_var = tk.StringVar(value="")
        self.ai_var = tk.StringVar(value="")

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

        tk.Label(frm_actions, text="AI preset").grid(row=1, column=0, sticky="w", **pad)
        tk.OptionMenu(frm_actions, self.ai_preset_var, "Custom", "Wide tune", "Fine tune", "Balanced", "Marathon").grid(row=1, column=1, sticky="w", **pad)
        tk.Button(frm_actions, text="Resume AI", command=self._resume_ai_tune).grid(row=1, column=2, sticky="w", **pad)

        frm_status = tk.LabelFrame(self, text="Status")
        frm_status.grid(row=6, column=0, sticky="ew", **pad)

        tk.Label(frm_status, textvariable=self.status_var, width=92, anchor="w").grid(row=0, column=0, **pad)
        tk.Label(frm_status, textvariable=self.progress_var, width=92, anchor="w").grid(row=1, column=0, **pad)
        tk.Label(frm_status, textvariable=self.best_var, width=92, anchor="w").grid(row=2, column=0, **pad)
        tk.Label(frm_status, textvariable=self.ai_var, width=92, anchor="w").grid(row=3, column=0, **pad)

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

        self.cfg.setdefault("ai", {})
        if isinstance(self.cfg.get("ai"), dict):
            self.cfg["ai"]["preset"] = str(self.ai_preset_var.get())
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
            dir_bins=int(cfg.get("dir_bins", 16)),
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

    def _read_current_y_to_x_ratio(self, settings_path):
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
        v = prof.get("Y/X output DPI ratio (vertical sens multiplier)")
        if v is None:
            return None
        try:
            return float(v)
        except Exception:
            return None

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

        settings_path = pathlib.Path(self.settings_var.get().strip())
        backup = None
        try:
            ts = time.strftime("%Y%m%d-%H%M%S")
            backup = RUNS_DIR / f"settings_backup_{ts}.json"
            backup.write_bytes(settings_path.read_bytes())
        except Exception:
            backup = None

        try:
            controller.write_candidate_settings(cand, settings_path)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        ok2 = controller.apply_settings(settings_path)
        if not ok2:
            messagebox.showwarning("Writer", "writer.exe reported an error")
            return

        dpi_cur = self._read_current_output_dpi(str(settings_path))
        curve_cur = self._read_current_curve(str(settings_path))
        yxr_cur = self._read_current_y_to_x_ratio(str(settings_path))
        ok_verify = True
        if "outputDpi" in cand and dpi_cur is not None:
            ok_verify = ok_verify and abs(float(dpi_cur) - float(cand["outputDpi"])) < 1e-6
        if "yToXRatio" in cand and yxr_cur is not None:
            ok_verify = ok_verify and abs(float(yxr_cur) - float(cand["yToXRatio"])) < 1e-6
        if any(k in cand for k in ("syncSpeed", "motivity", "gamma", "smooth")) and curve_cur is not None:
            for k in ("syncSpeed", "motivity", "gamma", "smooth"):
                if k in cand and k in curve_cur:
                    ok_verify = ok_verify and abs(float(curve_cur[k]) - float(cand[k])) < 1e-6

        if backup is not None:
            self.status_var.set(f"Best applied (saved; backup: {backup.name})")
        else:
            self.status_var.set("Best applied (saved)")
        if not ok_verify:
            messagebox.showwarning("Verify", "Applied, but settings.json did not match expected values")
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
            if sess.get("type") == "ai":
                self._save_ai_state(sess=sess, finished=msg)
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
        self.ai_var.set("")
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

    def _build_ai_client(self):
        openai_cfg = ai_tuner.default_openai_compat_config()
        azure_cfg = ai_tuner.default_azure_config()
        if openai_cfg["api_base"] and openai_cfg["model"]:
            return ai_tuner.OpenAICompatibleClient(
                api_base=openai_cfg["api_base"],
                api_key=openai_cfg["api_key"],
                model=openai_cfg["model"],
            )
        if azure_cfg["endpoint"] and azure_cfg["api_key"] and azure_cfg["deployment"]:
            return ai_tuner.AzureOpenAIClient(
                endpoint=azure_cfg["endpoint"],
                api_key=azure_cfg["api_key"],
                deployment=azure_cfg["deployment"],
                api_version=azure_cfg["api_version"],
            )
        return None

    def _save_ai_state(self, sess=None, finished=None):
        if sess is None:
            sess = self._session
        if not isinstance(sess, dict) or sess.get("type") != "ai":
            return
        run_dir = sess.get("run_dir")
        if run_dir is None:
            return
        path = pathlib.Path(run_dir) / AI_STATE_FILE

        def get_path(p):
            if p is None:
                return ""
            return str(p)

        def num(x):
            try:
                v = float(x)
            except Exception:
                return None
            return v if math.isfinite(v) else None

        state = {
            "version": 1,
            "type": "ai",
            "saved_at": float(time.time()),
            "finished": str(finished) if finished is not None else None,
            "run_dir": str(run_dir),
            "log_path": get_path(sess.get("log_path")),
            "trace_path": get_path(sess.get("trace_path")),
            "writer_path": str(self.writer_var.get().strip()),
            "settings_path": str(self.settings_var.get().strip()),
            "profile_index": int(self.cfg.get("profile_index", 0)),
            "fixed_dpi": float(sess.get("fixed_dpi", 0.0)),
            "seed_base": int(sess.get("seed_base", 0)),
            "bounds": sess.get("bounds"),
            "candidate": sess.get("candidate"),
            "history": sess.get("history"),
            "best": sess.get("best"),
            "best_score": num(sess.get("best_score")),
            "best_sig": sess.get("best_sig"),
            "second": sess.get("second"),
            "second_score": num(sess.get("second_score")),
            "second_sig": sess.get("second_sig"),
            "iter": int(sess.get("iter", 0)),
            "max_iters": int(sess.get("max_iters", 0)),
            "confidence_threshold": float(sess.get("confidence_threshold", 0.0)),
            "history_limit": int(sess.get("history_limit", 0)),
            "temperature": float(sess.get("temperature", 0.0)),
            "no_improve": int(sess.get("no_improve", 0)),
            "selection_metric": str(sess.get("selection_metric", "median")),
            "stability_k": float(sess.get("stability_k", 0.5)),
            "step_frac": float(sess.get("step_frac", 0.0)),
            "min_step_frac": float(sess.get("min_step_frac", 0.0)),
            "max_step_frac": float(sess.get("max_step_frac", 0.0)),
            "noise_est": float(sess.get("noise_est", 0.0)),
            "runs_per_eval": int(sess.get("runs_per_eval", 1)),
            "eval_repeats": int(sess.get("eval_repeats", 1)),
            "axis_iters": int(sess.get("axis_iters", 0)),
            "max_no_improve": int(sess.get("max_no_improve", 6)),
            "final_confirm_repeats": int(sess.get("final_confirm_repeats", 0)),
            "plateau_stop": bool(sess.get("plateau_stop", True)),
            "dual_enabled": bool(sess.get("dual_enabled", False)),
            "baseline_candidate": sess.get("baseline_candidate"),
            "baseline_score": num(sess.get("baseline_score")),
            "baseline_checked_at": sess.get("baseline_checked_at"),
            "baseline_recheck_every": int(sess.get("baseline_recheck_every", 0)),
            "baseline_drop_ratio": float(sess.get("baseline_drop_ratio", 0.0)),
            "confirm_repeats": int(sess.get("confirm_repeats", 0)),
            "confirm_win_rate": float(sess.get("confirm_win_rate", 0.0)),
            "confirm": sess.get("confirm"),
            "current_run": int(sess.get("current_run", 0)),
            "total_runs": int(sess.get("total_runs", 0)),
        }

        try:
            path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_ai_state(self, run_dir):
        path = pathlib.Path(run_dir) / AI_STATE_FILE
        if not path.exists():
            return None
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(obj, dict) or obj.get("type") != "ai":
            return None
        return obj

    def _resume_ai_tune(self):
        if self._session is not None:
            messagebox.showinfo("Running", "A session is already running")
            return
        if not self._validate_ready():
            return

        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        run_dir = filedialog.askdirectory(title="Select AI run folder", initialdir=str(RUNS_DIR))
        if not run_dir:
            return

        state = self._load_ai_state(run_dir)
        if not isinstance(state, dict):
            messagebox.showerror("Missing", f"No {AI_STATE_FILE} found in that folder")
            return

        prev_writer = str(state.get("writer_path", ""))
        prev_settings = str(state.get("settings_path", ""))
        cur_writer = self.writer_var.get().strip()
        cur_settings = self.settings_var.get().strip()
        if prev_writer and cur_writer and pathlib.Path(prev_writer) != pathlib.Path(cur_writer):
            messagebox.showwarning("Mismatch", "writer.exe differs from when this run started")
        if prev_settings and cur_settings and pathlib.Path(prev_settings) != pathlib.Path(cur_settings):
            messagebox.showwarning("Mismatch", "settings.json differs from when this run started")

        client = self._build_ai_client()
        if client is None:
            messagebox.showerror(
                "Missing",
                "Set OPENAI_API_BASE + OPENAI_MODEL (+ optional OPENAI_API_KEY)\n"
                "or AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY + AZURE_OPENAI_DEPLOYMENT.",
            )
            return

        run_dir_p = pathlib.Path(run_dir)
        base_path = run_dir_p / "base_settings.json"
        if not base_path.exists():
            messagebox.showwarning("Missing", "base_settings.json missing; snapshotting current settings")
            try:
                base_path.write_bytes(pathlib.Path(self.settings_var.get().strip()).read_bytes())
            except Exception as e:
                messagebox.showerror("Error", str(e))
                return

        controller = RawAccelController(
            self.writer_var.get().strip(),
            str(base_path),
            profile_index=int(state.get("profile_index", int(self.cfg.get("profile_index", 0)))),
        )
        try:
            controller.snapshot_base(base_path)
        except Exception:
            pass

        bounds = state.get("bounds")
        if not isinstance(bounds, dict):
            bounds = self.cfg.get("search", {}).get("bounds", {})

        fixed_dpi = state.get("fixed_dpi")
        if fixed_dpi is None:
            fixed_dpi = self._read_current_output_dpi(self.settings_var.get().strip())
        if fixed_dpi is None:
            messagebox.showerror("Missing", "Could not read Output DPI")
            return

        dual_cfg = self.cfg.get("dual_drills")
        dual_enabled_now = isinstance(dual_cfg, dict) and bool(dual_cfg.get("enabled"))
        dual_enabled_saved = bool(state.get("dual_enabled", dual_enabled_now))
        if dual_enabled_now != dual_enabled_saved:
            messagebox.showwarning("Mismatch", "Dual-drill setting differs from when this run started")

        sess = {
            "type": "ai",
            "controller": controller,
            "run_dir": run_dir_p,
            "log_path": run_dir_p / "results.csv",
            "trace_path": run_dir_p / "ai_trace.jsonl",
            "client": client,
            "bounds": bounds,
            "fixed_dpi": float(fixed_dpi),
            "seed_base": int(state.get("seed_base", int(self.seed_var.get()))),
            "candidate": state.get("candidate") if isinstance(state.get("candidate"), dict) else None,
            "history": state.get("history") if isinstance(state.get("history"), list) else [],
            "best": state.get("best") if isinstance(state.get("best"), dict) else None,
            "best_score": float(state["best_score"]) if state.get("best_score") is not None else float("-inf"),
            "best_sig": state.get("best_sig"),
            "second": state.get("second") if isinstance(state.get("second"), dict) else None,
            "second_score": float(state["second_score"]) if state.get("second_score") is not None else float("-inf"),
            "second_sig": state.get("second_sig"),
            "iter": int(state.get("iter", 0)),
            "max_iters": int(state.get("max_iters", 18)),
            "confidence_threshold": float(state.get("confidence_threshold", 0.85)),
            "history_limit": int(state.get("history_limit", 12)),
            "temperature": float(state.get("temperature", 0.2)),
            "no_improve": int(state.get("no_improve", 0)),
            "step_frac": float(state.get("step_frac", 0.25)),
            "min_step_frac": float(state.get("min_step_frac", 0.08)),
            "max_step_frac": float(state.get("max_step_frac", 0.35)),
            "noise_est": float(state.get("noise_est", 0.0)),
            "runs_per_eval": int(state.get("runs_per_eval", 1)),
            "eval_repeats": int(state.get("eval_repeats", 1)),
            "eval_repeats_min": int(state.get("eval_repeats_min", 1)),
            "repeat_gate_ratio": float(state.get("repeat_gate_ratio", 0.05)),
            "axis_iters": int(state.get("axis_iters", 0)),
            "max_no_improve": int(state.get("max_no_improve", 6)),
            "final_confirm_repeats": int(state.get("final_confirm_repeats", 0)),
            "plateau_stop": bool(state.get("plateau_stop", True)),
            "selection_metric": str(state.get("selection_metric", "median") or "median"),
            "stability_k": float(state.get("stability_k", 0.5)),
            "dual_enabled": bool(dual_enabled_saved),
            "baseline_candidate": state.get("baseline_candidate"),
            "baseline_score": state.get("baseline_score"),
            "baseline_checked_at": state.get("baseline_checked_at"),
            "baseline_recheck_every": int(state.get("baseline_recheck_every", 8)),
            "baseline_drop_ratio": float(state.get("baseline_drop_ratio", 0.85)),
            "confirm_repeats": int(state.get("confirm_repeats", 2)),
            "confirm_win_rate": float(state.get("confirm_win_rate", 0.6)),
            "confirm": state.get("confirm"),
            "ai_thread": None,
            "ai_result": None,
            "ai_error": None,
            "current_run": int(state.get("current_run", 0)),
            "total_runs": int(state.get("total_runs", 0)),
        }

        if not isinstance(sess.get("candidate"), dict):
            messagebox.showerror("Missing", "Saved state is missing candidate")
            return

        self._stop_requested = False
        self._session = sess
        self.progress_var.set(f"{int(sess.get('current_run', 0))}/{int(sess.get('total_runs', 0))}")

        it = int(sess.get("iter", 0))
        max_iters = int(sess.get("max_iters", 0))
        axis_total = int(sess.get("axis_iters", 0))
        if axis_total > 0 and it < axis_total:
            stage_label = f"Axis {it+1}/{axis_total}"
        else:
            curve_total = max(1, max_iters - axis_total) if axis_total > 0 else max(1, max_iters)
            curve_idx = it - axis_total + 1 if axis_total > 0 else it + 1
            stage_label = f"Curve {max(1, curve_idx)}/{curve_total}"

        self.status_var.set(f"AI resumed: {stage_label} (iter {it+1}/{max_iters})")
        self.ai_var.set("AI: resumed")

        cur_best = sess.get("best")
        if isinstance(cur_best, dict):
            self.best_var.set(
                f"Best {float(sess.get('best_score', 0.0)):.3f}: DPI={cur_best.get('outputDpi', 0.0):.1f} sync={cur_best.get('syncSpeed', 0.0):.3f} mot={cur_best.get('motivity', 0.0):.3f} g={cur_best.get('gamma', 0.0):.3f} s={cur_best.get('smooth', 0.0):.3f} yx={float(cur_best.get('yToXRatio', 1.0)):.3f}"
            )
        else:
            self.best_var.set("")

        cand = {"mode": "synchronous", "outputDpi": float(sess["fixed_dpi"]), **dict(sess["candidate"])}
        self._draw_curve(cand)

        if isinstance(sess.get("confirm"), dict):
            self.after(50, self._ai_confirm_step)
        else:
            self.after(50, self._ai_eval_step)

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

        client = self._build_ai_client()
        if client is None:
            messagebox.showerror(
                "Missing",
                "Set OPENAI_API_BASE + OPENAI_MODEL (+ optional OPENAI_API_KEY)\n"
                "or AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY + AZURE_OPENAI_DEPLOYMENT.",
            )
            return

        bounds = dict(self.cfg["search"]["bounds"])
        axis_bounds = self.cfg.get("axis", {}).get("bounds", {})
        if isinstance(axis_bounds, dict) and "yToXRatio" in axis_bounds:
            bounds["yToXRatio"] = list(axis_bounds["yToXRatio"])
        start_curve = self._read_current_curve(self.settings_var.get().strip())
        if start_curve is None:
            start_curve = {k: (float(v[0]) + float(v[1])) / 2.0 for k, v in bounds.items()}

        yxr = self._read_current_y_to_x_ratio(self.settings_var.get().strip())
        if yxr is None:
            yxr = 1.0
        start_curve["yToXRatio"] = float(yxr)

        ai_cfg0 = self.cfg.get("ai")
        if not isinstance(ai_cfg0, dict):
            ai_cfg0 = {}
        preset = str(self.ai_preset_var.get() or ai_cfg0.get("preset") or "Custom")
        presets = ai_cfg0.get("presets") if isinstance(ai_cfg0.get("presets"), dict) else {}
        overrides = presets.get(preset) if isinstance(presets.get(preset), dict) else {}
        ai_cfg = dict(ai_cfg0)
        ai_cfg.update(dict(overrides))

        max_iters = int(ai_cfg.get("max_iters", 18))
        conf_th = float(ai_cfg.get("confidence_threshold", 0.85))
        hist_lim = int(ai_cfg.get("history_limit", 12))
        temp = float(ai_cfg.get("temperature", 0.2))
        baseline_every = int(ai_cfg.get("baseline_recheck_every", 8))
        baseline_drop_ratio = float(ai_cfg.get("baseline_drop_ratio", 0.85))
        confirm_repeats = int(ai_cfg.get("confirm_repeats", 2))
        confirm_win_rate = float(ai_cfg.get("confirm_win_rate", 0.6))
        min_step_frac = float(ai_cfg.get("min_step_frac", 0.08))
        max_step_frac = float(ai_cfg.get("max_step_frac", 0.35))
        start_step_frac = float(ai_cfg.get("start_step_frac", 0.25))
        eval_repeats = int(ai_cfg.get("eval_repeats", 1))
        axis_iters = int(ai_cfg.get("axis_iters", 0))
        max_no_improve = int(ai_cfg.get("max_no_improve", 6))
        final_confirm_repeats = int(ai_cfg.get("final_confirm_repeats", 0))
        plateau_stop = bool(ai_cfg.get("plateau_stop", True))
        selection_metric = str(ai_cfg.get("selection_metric", "median") or "median").strip().lower()
        if selection_metric not in ("median", "stable"):
            selection_metric = "median"
        stability_k = float(ai_cfg.get("stability_k", 0.5))

        dual_cfg = self.cfg.get("dual_drills")
        dual_enabled = isinstance(dual_cfg, dict) and bool(dual_cfg.get("enabled"))
        runs_per_eval = 2 if dual_enabled else 1
        total_runs = int(max_iters * runs_per_eval * max(1, eval_repeats))

        seed_base = int(self.seed_var.get())

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
            "phase,iter,score,confidence,reason,tag,throughput,miss_rate,p90_error,pathEff,perpDev,overshoots,reaccels,timeToMoveMs,correctionMs,biasX,biasY,h_miss_rate,v_miss_rate,h_p90_error,v_p90_error,outputDpi,syncSpeed,motivity,gamma,smooth,yToXRatio,weakness_path\n",
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
            "seed_base": int(seed_base),
            "candidate": ai_tuner.clamp_candidate(start_curve, bounds),
            "history": [],
            "best": None,
            "best_score": float("-inf"),
            "best_sig": None,
            "second": None,
            "second_score": float("-inf"),
            "second_sig": None,
            "iter": 0,
            "max_iters": max_iters,
            "confidence_threshold": conf_th,
            "history_limit": hist_lim,
            "temperature": temp,
            "no_improve": 0,
            "step_frac": float(start_step_frac),
            "min_step_frac": float(min_step_frac),
            "max_step_frac": float(max_step_frac),
            "noise_est": 0.0,
            "runs_per_eval": int(runs_per_eval),
            "eval_repeats": int(max(1, eval_repeats)),
            "axis_iters": int(max(0, axis_iters)),
            "max_no_improve": int(max(0, max_no_improve)),
            "final_confirm_repeats": int(max(0, final_confirm_repeats)),
            "plateau_stop": bool(plateau_stop),
            "selection_metric": str(selection_metric),
            "stability_k": float(stability_k),
            "dual_enabled": bool(dual_enabled),
            "baseline_candidate": None,
            "baseline_score": None,
            "baseline_checked_at": None,
            "baseline_recheck_every": int(baseline_every),
            "baseline_drop_ratio": float(baseline_drop_ratio),
            "confirm_repeats": int(confirm_repeats),
            "confirm_win_rate": float(confirm_win_rate),
            "confirm": None,
            "ai_thread": None,
            "ai_result": None,
            "ai_error": None,
            "current_run": 0,
            "total_runs": total_runs,
        }

        self.progress_var.set(f"0/{total_runs}")
        self.status_var.set(f"AI tune: starting ({preset})")
        self.best_var.set("")
        self.ai_var.set("")

        self._save_ai_state()

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
            if self._ai_start_final_confirm("max_iters"):
                return
            self._last_best = dict(sess["best"]) if isinstance(sess.get("best"), dict) else None
            self._finish("Done")
            return

        baseline_every = int(sess.get("baseline_recheck_every", 0))
        baseline_cand = sess.get("baseline_candidate")
        baseline_score0 = sess.get("baseline_score")
        if (
            baseline_every > 0
            and it > 0
            and baseline_cand is not None
            and baseline_score0 is not None
            and it % baseline_every == 0
            and sess.get("baseline_checked_at") != it
        ):
            sess["baseline_checked_at"] = it
            self._ai_bump_total_runs(int(sess.get("runs_per_eval", 1)))

            full0 = {"mode": "synchronous", "outputDpi": float(sess["fixed_dpi"]), **dict(baseline_cand)}
            self._draw_curve(full0)
            path0 = pathlib.Path(sess["run_dir"]) / f"baseline_{it:03d}.json"
            sess["controller"].write_candidate_settings(full0, path0)
            sess["controller"].apply_settings(path0)

            seed0 = int(sess.get("seed_base", 0)) + 61000 + it
            ev0 = self._eval_drills(seed0, progress_hook=self._progress_hook)
            if ev0 is None:
                self._stop_requested = True
                self._finish("Stopped")
                return
            score0 = float(ev0.get("combined_score", float("-inf")))
            ratio = (score0 / float(baseline_score0)) if float(baseline_score0) != 0 else 1.0
            with open(sess["log_path"], "a", encoding="utf-8") as f:
                    f.write(
                        f"baseline,{it},{float(score0):.6f},0.000,{json.dumps(f'ratio={ratio:.3f}')},combined,"
                        f"0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,{float(sess['fixed_dpi']):.3f},"
                        f"{float(full0['syncSpeed']):.6f},{float(full0['motivity']):.6f},{float(full0['gamma']):.6f},{float(full0['smooth']):.6f},{float(full0.get('yToXRatio', 1.0)):.6f},\n"
                    )

            if ratio < float(sess.get("baseline_drop_ratio", 0.85)):
                cont = messagebox.askyesno(
                    "Drift",
                    f"Baseline dropped to {ratio*100:.0f}% of start. Continue?",
                )
                if not cont:
                    self._stop_requested = True
                    self._finish("Stopped")
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

        step_frac = float(sess.get("step_frac", 0.25))

        max_iters = int(sess.get("max_iters", 0))
        axis_total = int(sess.get("axis_iters", 0))
        if axis_total > 0 and it < axis_total:
            stage_label = f"Axis {it+1}/{axis_total}"
        else:
            curve_total = max(1, max_iters - axis_total) if axis_total > 0 else max(1, max_iters)
            curve_idx = it - axis_total + 1 if axis_total > 0 else it + 1
            stage_label = f"Curve {max(1, curve_idx)}/{curve_total}"

        params_line = (
            f"sync={full['syncSpeed']:.3f} mot={full['motivity']:.3f} g={full['gamma']:.3f} "
            f"s={full['smooth']:.3f} yx={float(full.get('yToXRatio', 1.0)):.3f} step={step_frac:.2f}"
        )
        self.status_var.set(f"AI {stage_label} (iter {it+1}/{max_iters}): {params_line}")

        seed_base = int(sess.get("seed_base", 0))
        eval_repeats_max = max(1, int(sess.get("eval_repeats", 1)))
        eval_repeats_min = max(1, int(sess.get("eval_repeats_min", 1)))
        eval_repeats_min = min(eval_repeats_min, eval_repeats_max)
        rep_seed0 = seed_base + 50000 + it * 1000

        repeat_gate_ratio = float(sess.get("repeat_gate_ratio", 0.05))

        repeat_runs = []

        def run_one(rep):
            self.status_var.set(f"AI {stage_label} (iter {it+1}/{max_iters}) rep {rep+1}/{eval_repeats_max}: {params_line}")
            ev = self._eval_drills(
                rep_seed0 + rep * 10,
                baseline=sess.get("baseline"),
                progress_hook=self._progress_hook,
            )
            if ev is None:
                return None
            return (float(ev.get("combined_score", float("-inf"))), ev)

        for rep in range(eval_repeats_min):
            out = run_one(rep)
            if out is None:
                self._stop_requested = True
                self._finish("Stopped")
                return
            repeat_runs.append(out)

        def current_median_score():
            xs = sorted(float(s) for s, _ in repeat_runs)
            return float(xs[len(xs) // 2]) if xs else float("-inf")

        def should_refine():
            best = float(sess.get("best_score", float("-inf")))
            if not math.isfinite(best):
                return True
            noise = float(sess.get("noise_est", 0.0))
            margin = max(abs(best) * float(repeat_gate_ratio), noise)
            return current_median_score() >= (best - margin)

        rep = eval_repeats_min
        while rep < eval_repeats_max and should_refine():
            out = run_one(rep)
            if out is None:
                self._stop_requested = True
                self._finish("Stopped")
                return
            repeat_runs.append(out)
            rep += 1

        repeat_runs.sort(key=lambda x: x[0])
        score = float(repeat_runs[len(repeat_runs) // 2][0])
        eval_res = repeat_runs[len(repeat_runs) // 2][1]
        repeat_scores = [float(s) for s, _ in repeat_runs]
        try:
            score_mean = float(statistics.mean(repeat_scores))
        except Exception:
            score_mean = float(score)
        try:
            score_std = float(statistics.pstdev(repeat_scores)) if len(repeat_scores) >= 2 else 0.0
        except Exception:
            score_std = 0.0
        reason = ""
        conf = 0.0

        if sess.get("baseline_candidate") is None:
            sess["baseline_candidate"] = dict(cand)
            sess["baseline_score"] = float(score)

        record = {
            "iter": it,
            "candidate": cand,
            "score": score,
            "score_mean": score_mean,
            "score_std": score_std,
            "repeat_scores": repeat_scores,
            "eval": eval_res,
        }
        sess["history"].append(record)
        if len(sess["history"]) > int(sess["history_limit"]):
            sess["history"] = sess["history"][len(sess["history"]) - int(sess["history_limit"]) :]

        selection_metric = str(sess.get("selection_metric", "median") or "median")
        stability_k = float(sess.get("stability_k", 0.5))
        metric_score = float(score)
        if selection_metric == "stable":
            metric_score = float(score_mean) - float(stability_k) * float(score_std)

        improved = metric_score > float(sess.get("best_score", float("-inf")))
        if improved:
            prev_best = sess.get("best")
            prev_best_sig = sess.get("best_sig")
            prev_best_score = float(sess.get("best_score", float("-inf")))
            sess["best_score"] = float(metric_score)
            sess["best"] = dict(full)
            sess["best_sig"] = (
                round(float(full.get("syncSpeed", 0.0)), 6),
                round(float(full.get("motivity", 0.0)), 6),
                round(float(full.get("gamma", 0.0)), 6),
                round(float(full.get("smooth", 0.0)), 6),
                round(float(full.get("yToXRatio", 1.0)), 6),
            )
            if isinstance(prev_best, dict) and prev_best_sig is not None and math.isfinite(prev_best_score):
                sess["second"] = dict(prev_best)
                sess["second_score"] = float(prev_best_score)
                sess["second_sig"] = prev_best_sig
            sess["no_improve"] = 0
            self.best_var.set(
                f"Best {float(metric_score):.3f} (raw {score:.3f}): DPI={full['outputDpi']:.1f} sync={full['syncSpeed']:.3f} mot={full['motivity']:.3f} g={full['gamma']:.3f} s={full['smooth']:.3f} yx={float(full.get('yToXRatio', 1.0)):.3f}"
            )
        else:
            sess["no_improve"] = int(sess.get("no_improve", 0)) + 1
            sig = (
                round(float(full.get("syncSpeed", 0.0)), 6),
                round(float(full.get("motivity", 0.0)), 6),
                round(float(full.get("gamma", 0.0)), 6),
                round(float(full.get("smooth", 0.0)), 6),
                round(float(full.get("yToXRatio", 1.0)), 6),
            )
            if sig != sess.get("best_sig") and metric_score > float(sess.get("second_score", float("-inf"))):
                sess["second"] = dict(full)
                sess["second_score"] = float(metric_score)
                sess["second_sig"] = sig

        scores = [float(h.get("score", 0.0)) for h in sess.get("history", []) if math.isfinite(float(h.get("score", 0.0)))]
        if len(scores) >= 3:
            window = scores[-min(6, len(scores)) :]
            try:
                noise_hist = float(statistics.pstdev(window))
            except Exception:
                noise_hist = 0.0
        else:
            noise_hist = 0.0

        noise_iter = float(record.get("score_std", 0.0)) if isinstance(record, dict) else 0.0
        sess["noise_est"] = float(max(noise_hist, noise_iter))

        step_frac = float(sess.get("step_frac", 0.25))
        min_step = float(sess.get("min_step_frac", 0.08))
        max_step = float(sess.get("max_step_frac", 0.35))
        if improved:
            step_frac = max(min_step, step_frac * 0.9)
        else:
            if int(sess.get("no_improve", 0)) >= 2:
                step_frac = min(max_step, step_frac * 1.15)
        noise = float(sess.get("noise_est", 0.0))
        if math.isfinite(noise) and noise > 0.0 and math.isfinite(score) and abs(score) > 1e-9:
            if (noise / abs(score)) > 0.15:
                step_frac = max(min_step, step_frac * 0.9)
        sess["step_frac"] = float(min(max_step, max(min_step, step_frac)))

        def log_one(tag, r, s, conf, reason):
            weakness_path = ""
            if isinstance(r, dict) and (isinstance(r.get("dir_bins"), dict) or isinstance(r.get("dir_summary"), dict)):
                weakness_path = f"weakness_{it:03d}_{tag}.json"
                try:
                    (pathlib.Path(sess["run_dir"]) / weakness_path).write_text(
                        json.dumps(
                            {
                                "tag": str(tag),
                                "iter": int(it),
                                "dir_bins": r.get("dir_bins"),
                                "dir_summary": r.get("dir_summary"),
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                except Exception:
                    weakness_path = ""
            with open(sess["log_path"], "a", encoding="utf-8") as f:
                f.write(
                    f"ai,{it},{float(s):.6f},{float(conf):.3f},{json.dumps(str(reason)[:200])},{tag},"
                    f"{float(r.get('throughput', 0.0)):.6f},{float(r.get('miss_rate', 1.0)):.6f},{float(r.get('p90_error_px', r.get('avg_error_px', 0.0))):.6f},"
                    f"{float(r.get('avg_path_eff', 0.0)):.6f},{float(r.get('avg_perp_dev', 0.0)):.6f},{float(r.get('avg_overshoots', 0.0)):.6f},{float(r.get('avg_reaccels', 0.0)):.6f},"
                    f"{float(r.get('avg_time_to_move_ms', 0.0)):.6f},{float(r.get('avg_correction_ms', 0.0)):.6f},"
                    f"{float(r.get('avg_bias_x', 0.0)):.6f},{float(r.get('avg_bias_y', 0.0)):.6f},"
                    f"{float(r.get('h_miss_rate', 1.0)):.6f},{float(r.get('v_miss_rate', 1.0)):.6f},"
                    f"{float(r.get('h_p90_error_px', 0.0)):.6f},{float(r.get('v_p90_error_px', 0.0)):.6f},"
                    f"{float(full['outputDpi']):.3f},{float(full['syncSpeed']):.6f},{float(full['motivity']):.6f},{float(full['gamma']):.6f},{float(full['smooth']):.6f},{float(full.get('yToXRatio', 1.0)):.6f},{weakness_path}\n"
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
                axis_iters = int(sess.get("axis_iters", 0))
                stage = "axis" if axis_iters > 0 and it < axis_iters else "curve"
                notes = "Prefer stable improvements. Keep motivity>1, gamma>0, syncSpeed>0, smooth in [0,1]."
                if stage == "axis":
                    notes = notes + " Axis stage: ONLY change yToXRatio; keep syncSpeed/motivity/gamma/smooth the same."

                hist = sess.get("history")
                if not isinstance(hist, list):
                    hist = []

                def _sig(c):
                    if not isinstance(c, dict):
                        return None
                    return (
                        round(float(c.get("syncSpeed", 0.0)), 6),
                        round(float(c.get("motivity", 0.0)), 6),
                        round(float(c.get("gamma", 0.0)), 6),
                        round(float(c.get("smooth", 0.0)), 6),
                        round(float(c.get("yToXRatio", 1.0)), 6),
                    )

                def _top_k(rows, k):
                    rows = [r for r in rows if isinstance(r, dict) and math.isfinite(float(r.get("score", float("nan"))))]
                    rows.sort(key=lambda r: float(r.get("score", float("-inf"))), reverse=True)
                    out = []
                    seen = set()
                    for r in rows:
                        sig = _sig(r.get("candidate"))
                        if sig is None or sig in seen:
                            continue
                        seen.add(sig)
                        out.append(
                            {
                                "iter": int(r.get("iter", 0)),
                                "score": float(r.get("score", 0.0)),
                                "score_mean": float(r.get("score_mean", r.get("score", 0.0))),
                                "score_std": float(r.get("score_std", 0.0)),
                                "candidate": r.get("candidate"),
                                "summary": _ai_eval_summary(r.get("eval")),
                            }
                        )
                        if len(out) >= k:
                            break
                    return out

                def _recent(rows, k):
                    rows2 = [r for r in rows if isinstance(r, dict)]
                    rows2.sort(key=lambda r: int(r.get("iter", 0)))
                    rows2 = rows2[-k:]
                    out = []
                    for r in rows2:
                        out.append(
                            {
                                "iter": int(r.get("iter", 0)),
                                "score": float(r.get("score", 0.0)),
                                "score_mean": float(r.get("score_mean", r.get("score", 0.0))),
                                "score_std": float(r.get("score_std", 0.0)),
                                "candidate": r.get("candidate"),
                                "summary": _ai_eval_summary(r.get("eval")),
                            }
                        )
                    return out

                recent = _recent(hist, 8)
                top = _top_k(hist, 5)
                noise_est = float(sess.get("noise_est", 0.0))
                step_frac = float(sess.get("step_frac", 0.25))
                no_improve = int(sess.get("no_improve", 0))
                best_score = float(sess.get("best_score", float("-inf")))

                trend = {
                    "stage": stage,
                    "iter": int(it),
                    "no_improve": no_improve,
                    "step_frac": step_frac,
                    "noise_est": noise_est,
                    "eval_repeats": int(sess.get("eval_repeats", 1)),
                    "best_score": best_score,
                    "best_candidate": dict(sess.get("best", {})) if isinstance(sess.get("best"), dict) else None,
                    "second_score": float(sess.get("second_score", float("-inf"))),
                    "second_candidate": dict(sess.get("second", {})) if isinstance(sess.get("second"), dict) else None,
                    "top": top,
                    "recent": recent,
                }
                state = {
                    "mode": "synchronous",
                    "bounds": bounds,
                    "fixed": {"outputDpi": float(sess["fixed_dpi"])},
                    "history": _recent(hist, int(sess.get("history_limit", 12))),
                    "trend": trend,
                    "best": {
                        "score": float(sess.get("best_score", float("-inf"))),
                        "candidate": dict(sess.get("best", {})),
                    },
                    "objective": {
                        "goal": "maximize combined_score",
                        "notes": notes,
                    },
                    "limits": {
                        "iter": it,
                        "max_iters": int(sess["max_iters"]),
                        "no_improve": int(sess.get("no_improve", 0)),
                        "step_frac": float(sess.get("step_frac", 0.25)),
                        "noise_est": float(sess.get("noise_est", 0.0)),
                        "eval_repeats": int(sess.get("eval_repeats", 1)),
                        "stage": stage,
                        "selection_metric": str(sess.get("selection_metric", "median")),
                        "stability_k": float(sess.get("stability_k", 0.5)),
                    },
                }

                msgs = ai_tuner.build_ai_messages(state)
                content = sess["client"].chat(msgs, temperature=float(sess["temperature"]))
                parsed = ai_tuner.parse_ai_response(content)
                cand2 = ai_tuner.clamp_candidate(parsed["candidate"], bounds)
                if "yToXRatio" in bounds and "yToXRatio" not in cand2 and isinstance(cand, dict) and "yToXRatio" in cand:
                    cand2["yToXRatio"] = float(cand.get("yToXRatio", 1.0))

                if stage == "axis" and isinstance(cand, dict):
                    for k in ("syncSpeed", "motivity", "gamma", "smooth"):
                        if k in cand:
                            cand2[k] = float(cand[k])
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

            def pack(r):
                if not isinstance(r, dict):
                    return {}
                out = {}
                for k in (
                    "throughput",
                    "miss_rate",
                    "p90_error_px",
                    "avg_path_eff",
                    "avg_perp_dev",
                    "avg_overshoots",
                    "avg_reaccels",
                    "avg_time_to_move_ms",
                    "avg_correction_ms",
                    "avg_bias_x",
                    "avg_bias_y",
                    "h_miss_rate",
                    "v_miss_rate",
                    "h_p90_error_px",
                    "v_p90_error_px",
                ):
                    if k in r and r.get(k) is not None:
                        out[k] = r.get(k)
                if isinstance(r.get("dir_summary"), dict):
                    out["dir_summary"] = r.get("dir_summary")
                return out

            if "single" in ev:
                return {"score": float(ev.get("combined_score", 0.0)), "single": pack(ev["single"])}
            return {
                "score": float(ev.get("combined_score", 0.0)),
                "micro_score": float(ev.get("micro_score", 0.0)),
                "flick_score": float(ev.get("flick_score", 0.0)),
                "micro": pack(ev.get("micro")),
                "flick": pack(ev.get("flick")),
            }

        thread = threading.Thread(target=worker, daemon=True)
        sess["ai_thread"] = thread
        thread.start()

        self.status_var.set(f"AI {stage_label} (iter {it+1}/{max_iters}): thinking")
        self.ai_var.set("AI: waiting for suggestion")
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

        cur = None
        hist = sess.get("history")
        if isinstance(hist, list) and hist:
            last = hist[-1]
            if isinstance(last, dict) and isinstance(last.get("candidate"), dict):
                cur = last["candidate"]
        if not isinstance(cur, dict):
            cur = sess.get("candidate") if isinstance(sess.get("candidate"), dict) else None

        def d(name):
            if not isinstance(cur, dict):
                return 0.0
            return float(cand2.get(name, 0.0)) - float(cur.get(name, 0.0))

        step_frac = float(sess.get("step_frac", 0.25))
        ai_line = (
            f"AI: conf={conf:.2f} stop={str(stop).lower()} step={step_frac:.2f} "
            f"Δsync={d('syncSpeed'):+.3f} Δmot={d('motivity'):+.3f} Δg={d('gamma'):+.3f} Δs={d('smooth'):+.3f} Δyx={d('yToXRatio'):+.3f} "
            f"{reason[:90]}"
        )
        self.ai_var.set(ai_line)

        with open(sess["log_path"], "a", encoding="utf-8") as f:
            f.write(f"ai,{int(sess['iter'])},0.000000,{conf:.3f},{json.dumps(reason[:200])},ai_note,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,{float(sess['fixed_dpi']):.3f},{cand2['syncSpeed']:.6f},{cand2['motivity']:.6f},{cand2['gamma']:.6f},{cand2['smooth']:.6f},{float(cand2.get('yToXRatio', 1.0)):.6f},\n")

        if stop and conf >= float(sess["confidence_threshold"]) and int(sess["iter"]) >= 3:
            best = sess.get("best")
            challenger = sess.get("second")
            best_sig = sess.get("best_sig")
            chal_sig = sess.get("second_sig")
            if challenger is None and isinstance(sess.get("baseline_candidate"), dict):
                challenger = {"mode": "synchronous", "outputDpi": float(sess["fixed_dpi"]), **dict(sess["baseline_candidate"])}
                chal_sig = (
                    round(float(challenger.get("syncSpeed", 0.0)), 6),
                    round(float(challenger.get("motivity", 0.0)), 6),
                    round(float(challenger.get("gamma", 0.0)), 6),
                    round(float(challenger.get("smooth", 0.0)), 6),
                    round(float(challenger.get("yToXRatio", 1.0)), 6),
                )

            if not isinstance(best, dict) or not isinstance(challenger, dict) or best_sig is None or chal_sig is None or best_sig == chal_sig:
                self._last_best = dict(best) if isinstance(best, dict) else None
                self._finish("Done")
                return

            confirm_repeats = int(sess.get("confirm_repeats", 2))
            runs_per_eval = int(sess.get("runs_per_eval", 1))
            eval_repeats = int(sess.get("eval_repeats", 1))
            self._ai_bump_total_runs(confirm_repeats * 2 * runs_per_eval * max(1, eval_repeats))
            sess["confirm"] = {
                "best": dict(best),
                "challenger": dict(challenger),
                "repeats": confirm_repeats,
                "round": 0,
                "pairs": [],
                "seed_base": int(sess.get("seed_base", 0)) + 71000 + int(sess["iter"]) * 10,
                "pending_next": dict(cand2),
            }
            self._save_ai_state()
            self.status_var.set("AI tune: confirm")
            self.after(50, self._ai_confirm_step)
            return

        max_no_improve = int(sess.get("max_no_improve", 6))
        if max_no_improve > 0 and int(sess.get("no_improve", 0)) >= max_no_improve and int(sess["iter"]) >= max(6, max_no_improve // 2):
            if self._ai_start_final_confirm("no_improve"):
                return
            self._last_best = dict(sess["best"]) if isinstance(sess.get("best"), dict) else None
            self._finish("Done")
            return

        noise = float(sess.get("noise_est", 0.0))
        recent = [float(h.get("score", 0.0)) for h in sess.get("history", []) if math.isfinite(float(h.get("score", 0.0)))]
        recent = recent[-5:]
        if len(recent) >= 5:
            spread = max(recent) - min(recent)
            floor = max(0.75 * noise, 0.01 * abs(float(sess.get("best_score", 0.0))))
            if (
                bool(sess.get("plateau_stop", True))
                and spread <= floor
                and int(sess.get("no_improve", 0)) >= 4
                and float(sess.get("step_frac", 0.25)) <= float(sess.get("min_step_frac", 0.08)) * 1.25
            ):
                self._last_best = dict(sess["best"]) if isinstance(sess.get("best"), dict) else None
                self._finish("Done")
                return

        sess["candidate"] = dict(cand2)
        sess["iter"] = int(sess["iter"]) + 1
        self._save_ai_state()
        self.after(100, self._ai_eval_step)

    def _ai_start_final_confirm(self, reason):
        sess = self._session
        if not isinstance(sess, dict) or sess.get("type") != "ai":
            return False

        repeats = int(sess.get("final_confirm_repeats", 0))
        if repeats <= 0:
            return False

        best = sess.get("best")
        challenger = sess.get("second")
        best_sig = sess.get("best_sig")
        chal_sig = sess.get("second_sig")
        if challenger is None and isinstance(sess.get("baseline_candidate"), dict):
            challenger = {"mode": "synchronous", "outputDpi": float(sess["fixed_dpi"]), **dict(sess["baseline_candidate"])}
            chal_sig = (
                round(float(challenger.get("syncSpeed", 0.0)), 6),
                round(float(challenger.get("motivity", 0.0)), 6),
                round(float(challenger.get("gamma", 0.0)), 6),
                round(float(challenger.get("smooth", 0.0)), 6),
                round(float(challenger.get("yToXRatio", 1.0)), 6),
            )

        if not isinstance(best, dict) or not isinstance(challenger, dict) or best_sig is None or chal_sig is None or best_sig == chal_sig:
            return False

        runs_per_eval = int(sess.get("runs_per_eval", 1))
        eval_repeats = int(sess.get("eval_repeats", 1))
        eval_repeats = max(1, eval_repeats)
        self._ai_bump_total_runs(repeats * 2 * runs_per_eval * eval_repeats)

        sess["confirm"] = {
            "best": dict(best),
            "challenger": dict(challenger),
            "repeats": int(repeats),
            "round": 0,
            "pairs": [],
            "seed_base": int(sess.get("seed_base", 0)) + 91000 + int(sess.get("iter", 0)) * 10,
            "pending_next": None,
            "final": True,
            "reason": str(reason),
        }
        self._save_ai_state()
        self.status_var.set("AI tune: final confirm")
        self.after(50, self._ai_confirm_step)
        return True

    def _ai_bump_total_runs(self, extra):
        sess = self._session
        if not isinstance(sess, dict) or sess.get("type") != "ai":
            return
        extra = int(extra)
        if extra <= 0:
            return
        sess["total_runs"] = int(sess.get("total_runs", 0)) + extra
        self.progress_var.set(f"{int(sess.get('current_run', 0))}/{int(sess.get('total_runs', 0))}")

    def _ai_confirm_step(self):
        sess = self._session
        if not isinstance(sess, dict) or sess.get("type") != "ai":
            return
        if self._stop_requested:
            self._finish("Stopped")
            return
        conf = sess.get("confirm")
        if not isinstance(conf, dict):
            return

        r = int(conf.get("round", 0))
        repeats = int(conf.get("repeats", 0))
        if r >= repeats:
            pairs = conf.get("pairs")
            if not isinstance(pairs, list) or not pairs:
                self._finish("Done")
                return

            wins = sum(1 for p in pairs if float(p.get("best", float("-inf"))) >= float(p.get("challenger", float("inf"))))
            win_rate = wins / float(len(pairs))
            best_mean = sum(float(p.get("best", 0.0)) for p in pairs) / float(len(pairs))
            chal_mean = sum(float(p.get("challenger", 0.0)) for p in pairs) / float(len(pairs))
            diffs = [float(p.get("best", 0.0)) - float(p.get("challenger", 0.0)) for p in pairs]
            try:
                diff_noise = float(statistics.pstdev(diffs)) if len(diffs) >= 2 else 0.0
            except Exception:
                diff_noise = 0.0
            margin = max(0.5 * diff_noise, 0.01 * abs(chal_mean))

            if bool(conf.get("final")):
                best_cand = conf.get("best")
                chal_cand = conf.get("challenger")
                winner = best_cand
                winner_score = best_mean
                if chal_mean > best_mean:
                    winner = chal_cand
                    winner_score = chal_mean
                if isinstance(winner, dict):
                    sess["best"] = dict(winner)
                    sess["best_score"] = float(winner_score)
                    sess["best_sig"] = (
                        round(float(winner.get("syncSpeed", 0.0)), 6),
                        round(float(winner.get("motivity", 0.0)), 6),
                        round(float(winner.get("gamma", 0.0)), 6),
                        round(float(winner.get("smooth", 0.0)), 6),
                        round(float(winner.get("yToXRatio", 1.0)), 6),
                    )
                    self._last_best = dict(winner)
                self._finish("Done")
                return

            if win_rate >= float(sess.get("confirm_win_rate", 0.6)) and (best_mean - chal_mean) >= margin:
                best = conf.get("best")
                self._last_best = dict(best) if isinstance(best, dict) else None
                self._finish("Done")
                return

            sess["confirm"] = None
            pending = conf.get("pending_next")
            if isinstance(pending, dict):
                sess["candidate"] = dict(pending)
            sess["iter"] = int(sess.get("iter", 0)) + 1
            self._save_ai_state()
            self.after(50, self._ai_eval_step)
            return

        seed = int(conf.get("seed_base", 0)) + r * 100
        best = conf.get("best")
        challenger = conf.get("challenger")
        if not isinstance(best, dict) or not isinstance(challenger, dict):
            self._finish("Done")
            return

        order = ["best", "challenger"]
        if r % 2 == 1:
            order = ["challenger", "best"]

        round_scores = {"best": float("-inf"), "challenger": float("-inf")}
        label = "Final confirm" if bool(conf.get("final")) else "Confirm"
        for side in order:
            if self._stop_requested:
                self._finish("Stopped")
                return

            cand_full = best if side == "best" else challenger
            self._draw_curve(cand_full)
            path = pathlib.Path(sess["run_dir"]) / f"confirm_{r+1:02d}_{side}.json"
            sess["controller"].write_candidate_settings(cand_full, path)
            sess["controller"].apply_settings(path)
            self.status_var.set(f"AI {label} {r+1}/{repeats} ({side})")

            eval_repeats = int(sess.get("eval_repeats", 1))
            eval_repeats = max(1, eval_repeats)
            scores = []
            for rep in range(eval_repeats):
                self.status_var.set(f"AI {label} {r+1}/{repeats} ({side}) rep {rep+1}/{eval_repeats}")
                ev = self._eval_drills(seed + rep * 10, progress_hook=self._progress_hook)
                if ev is None:
                    self._stop_requested = True
                    self._finish("Stopped")
                    return
                scores.append(float(ev.get("combined_score", float("-inf"))))
            scores.sort()
            sc = float(scores[len(scores) // 2])
            round_scores[side] = sc

            with open(sess["log_path"], "a", encoding="utf-8") as f:
                f.write(
                    f"confirm,{int(sess.get('iter',0))},{sc:.6f},0.000,{json.dumps('confirm')},{side},"
                    f"0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,{float(sess['fixed_dpi']):.3f},"
                    f"{float(cand_full.get('syncSpeed', 0.0)):.6f},{float(cand_full.get('motivity', 0.0)):.6f},{float(cand_full.get('gamma', 0.0)):.6f},{float(cand_full.get('smooth', 0.0)):.6f},{float(cand_full.get('yToXRatio', 1.0)):.6f},\n"
                )

        pairs = conf.get("pairs")
        if not isinstance(pairs, list):
            pairs = []
            conf["pairs"] = pairs
        pairs.append({"seed": seed, "best": round_scores["best"], "challenger": round_scores["challenger"]})
        conf["round"] = r + 1
        self._save_ai_state()
        self.after(50, self._ai_confirm_step)



if __name__ == "__main__":
    App().mainloop()
