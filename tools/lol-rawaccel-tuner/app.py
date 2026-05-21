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

        self._session = None
        self._stop_requested = False

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
        tk.Button(frm_actions, text="Stop", command=self._stop).grid(row=0, column=2, **pad)
        tk.Button(frm_actions, text="Restore base", command=self._restore_base).grid(row=0, column=3, **pad)
        tk.Button(frm_actions, text="Open runs", command=self._open_runs).grid(row=0, column=4, **pad)

        frm_status = tk.LabelFrame(self, text="Status")
        frm_status.grid(row=6, column=0, sticky="ew", **pad)

        tk.Label(frm_status, textvariable=self.status_var, width=92, anchor="w").grid(row=0, column=0, **pad)
        tk.Label(frm_status, textvariable=self.best_var, width=92, anchor="w").grid(row=1, column=0, **pad)

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
        overshoot_penalty = 1.0 / (1.0 + result["avg_overshoots"] * 0.25)
        reaccel_penalty = 1.0 / (1.0 + result["avg_reaccels"] * 0.2)
        miss_penalty = max(0.0, 1.0 - result["miss_rate"]) ** penalty
        return (
            result["throughput"]
            * miss_penalty
            * result["avg_path_eff"]
            * overshoot_penalty
            * reaccel_penalty
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
            "phase,idx,score,throughput,miss_rate,pathEff,overshoots,reaccels,avgErrorPx,outputDpi\n",
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

        task_cfg = self.cfg["task"]
        trials = int(task_cfg["trials"])
        penalty = float(task_cfg["penalty"])
        timeout_ms = int(task_cfg.get("timeout_ms", 0))
        start_gate = bool(task_cfg.get("start_gate", False))
        distances_px = list(task_cfg["distances_px"])
        radii_px = list(task_cfg["radii_px"])

        result = run_task_block(
            self,
            trials=trials,
            distances_px=distances_px,
            radii_px=radii_px,
            seed=int(self.seed_var.get()) + 9001,
            timeout_ms=timeout_ms,
            start_gate=start_gate,
        )
        if result is None:
            self._stop_requested = True
            self._finish("Stopped")
            return

        score = float(self._score_result(result, penalty))

        line = (
            f"sens,{idx},{score:.6f},{result['throughput']:.6f},{result['miss_rate']:.6f},"
            f"{result['avg_path_eff']:.6f},{result['avg_overshoots']:.6f},{result['avg_reaccels']:.6f},{result['avg_error_px']:.6f},"
            f"{dpi:.3f}\n"
        )
        with open(self._session["log_path"], "a", encoding="utf-8") as f:
            f.write(line)

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
            "phase,idx,generation,member,score,throughput,miss_rate,pathEff,overshoots,reaccels,avgErrorPx,outputDpi,syncSpeed,motivity,gamma,smooth\n",
            encoding="utf-8",
        )

        self._session = {
            "controller": controller,
            "phase": "curve",
            "curve_tuner": curve_tuner,
            "repeats": repeats,
            "task_seeds": task_seeds,
            "repeat_idx": 0,
            "repeat_scores": [],
            "candidate": None,
            "best_curve": None,
            "fixed_dpi": float(fixed_dpi),
            "run_dir": run_dir,
            "log_path": log_path,
            "idx": 0,
            "best": None,
            "best_score": -1e9,
        }

        self.status_var.set(f"Run {run_id}: applying base settings")
        ok = controller.apply_settings(controller.base_settings_path)
        if not ok:
            messagebox.showwarning("Writer", "writer.exe reported an error applying base settings")

        self.after(100, self._next_eval)

    def _stop(self):
        self._stop_requested = True
        self.status_var.set("Stop requested; finishing current block")

    def _restore_base(self):
        if not self._validate_ready():
            return
        self._persist_ui_to_config()
        controller = RawAccelController(self.writer_var.get().strip(), self.settings_var.get().strip())
        ok = controller.apply_settings(controller.base_settings_path)
        if not ok:
            messagebox.showwarning("Writer", "writer.exe reported an error")
        else:
            self.status_var.set("Base settings applied")

    def _open_runs(self):
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(RUNS_DIR)])

    def _finish(self, msg):
        self.status_var.set(msg)
        self._session = None

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

        candidate = tuner.next_candidate()
        if candidate is None:
            self._finish("Done")
            return

        self._session["candidate"] = candidate
        self._session["repeat_idx"] = 0
        self._session["repeat_scores"] = []

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

        task_cfg = self.cfg["task"]
        trials = int(task_cfg["trials"])
        penalty = float(task_cfg["penalty"])
        timeout_ms = int(task_cfg.get("timeout_ms", 0))
        start_gate = bool(task_cfg.get("start_gate", False))
        distances_px = list(task_cfg["distances_px"])
        radii_px = list(task_cfg["radii_px"])

        repeat_idx = int(self._session["repeat_idx"])
        seeds = list(self._session["task_seeds"])
        seed = int(seeds[min(repeat_idx, len(seeds) - 1)])

        result = run_task_block(
            self,
            trials=trials,
            distances_px=distances_px,
            radii_px=radii_px,
            seed=seed,
            timeout_ms=timeout_ms,
            start_gate=start_gate,
        )
        if result is None:
            self._stop_requested = True
            self._finish("Stopped")
            return

        overshoot_penalty = 1.0 / (1.0 + result["avg_overshoots"] * 0.25)
        reaccel_penalty = 1.0 / (1.0 + result["avg_reaccels"] * 0.2)
        miss_penalty = max(0.0, 1.0 - result["miss_rate"]) ** penalty
        score = (
            result["throughput"]
            * miss_penalty
            * result["avg_path_eff"]
            * overshoot_penalty
            * reaccel_penalty
        )

        self._session["repeat_scores"].append(float(score))
        self._session["repeat_idx"] += 1

        if int(self._session["repeat_idx"]) < int(self._session["repeats"]):
            self.after(250, lambda: self._run_block(idx, cand))
            return

        score_med = float(statistics.median(self._session["repeat_scores"]))

        phase = self._session["phase"]
        tuner = self._session["curve_tuner"]

        tuner.report_result(score_med)

        gen = tuner.generation
        member = tuner.member

        line = (
            f"{phase},{idx},{gen},{member},{score_med:.6f},{result['throughput']:.6f},{result['miss_rate']:.6f},"
            f"{result['avg_path_eff']:.6f},{result['avg_overshoots']:.6f},{result['avg_reaccels']:.6f},{result['avg_error_px']:.6f},"
            f"{float(cand.get('outputDpi', 0.0)):.3f},{float(cand.get('syncSpeed', 0.0)):.6f},{float(cand.get('motivity', 0.0)):.6f},"
            f"{float(cand.get('gamma', 0.0)):.6f},{float(cand.get('smooth', 0.0)):.6f}\n"
        )
        with open(self._session["log_path"], "a", encoding="utf-8") as f:
            f.write(line)

        if math.isfinite(score_med) and score_med > self._session["best_score"]:
            self._session["best_score"] = score_med
            self._session["best"] = dict(cand)

            self._session["best_curve"] = dict(cand)
            self.best_var.set(
                (
                    f"Best curve {score_med:.3f}: DPI={cand['outputDpi']:.1f} syncSpeed={cand['syncSpeed']:.3f} "
                    f"mot={cand['motivity']:.3f} gamma={cand['gamma']:.3f} smooth={cand['smooth']:.3f}"
                )
            )

        self._session["idx"] += 1
        self.after(200, self._next_eval)


        self._session["candidate"] = candidate
        self._session["repeat_idx"] = 0
        self._session["repeat_scores"] = []

        best_sens = self._session.get("best_sens")
        best_curve = self._session.get("best_curve")

        if phase == "sens":
            cand = {"mode": "noaccel", "outputDpi": float(candidate["outputDpi"])}
            label = f"Sens {idx+1}: Output DPI={cand['outputDpi']:.1f} (noaccel)"
        elif phase == "curve":
            cand = {
                "mode": "synchronous",
                "outputDpi": float(best_sens["outputDpi"]),
                "syncSpeed": float(candidate["syncSpeed"]),
                "motivity": float(candidate["motivity"]),
                "gamma": float(candidate["gamma"]),
                "smooth": float(candidate["smooth"]),
            }
            label = (
                f"Curve {idx+1}: syncSpeed={cand['syncSpeed']:.3f} motivity={cand['motivity']:.3f} "
                f"gamma={cand['gamma']:.3f} smooth={cand['smooth']:.3f}"
            )
        else:
            cand = {
                "mode": "synchronous",
                "outputDpi": float(candidate["outputDpi"]),
                "syncSpeed": float(candidate["syncSpeed"]),
                "motivity": float(candidate["motivity"]),
                "gamma": float(candidate["gamma"]),
                "smooth": float(candidate["smooth"]),
            }
            label = (
                f"Fine {idx+1}: DPI={cand['outputDpi']:.1f} syncSpeed={cand['syncSpeed']:.3f} mot={cand['motivity']:.3f} "
                f"g={cand['gamma']:.3f} s={cand['smooth']:.3f}"
            )

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

        task_cfg = self.cfg["task"]
        trials = int(task_cfg["trials"])
        penalty = float(task_cfg["penalty"])
        timeout_ms = int(task_cfg.get("timeout_ms", 0))
        start_gate = bool(task_cfg.get("start_gate", False))
        distances_px = list(task_cfg["distances_px"])
        radii_px = list(task_cfg["radii_px"])

        repeat_idx = int(self._session["repeat_idx"])
        seeds = list(self._session["task_seeds"])
        seed = int(seeds[min(repeat_idx, len(seeds) - 1)])

        result = run_task_block(
            self,
            trials=trials,
            distances_px=distances_px,
            radii_px=radii_px,
            seed=seed,
            timeout_ms=timeout_ms,
            start_gate=start_gate,
        )
        if result is None:
            self._stop_requested = True
            self._finish("Stopped")
            return

        overshoot_penalty = 1.0 / (1.0 + result["avg_overshoots"] * 0.25)
        reaccel_penalty = 1.0 / (1.0 + result["avg_reaccels"] * 0.2)
        miss_penalty = max(0.0, 1.0 - result["miss_rate"]) ** penalty
        score = (
            result["throughput"]
            * miss_penalty
            * result["avg_path_eff"]
            * overshoot_penalty
            * reaccel_penalty
        )

        self._session["repeat_scores"].append(float(score))
        self._session["repeat_idx"] += 1

        if int(self._session["repeat_idx"]) < int(self._session["repeats"]):
            self.after(250, lambda: self._run_block(idx, cand))
            return

        score_med = float(statistics.median(self._session["repeat_scores"]))

        phase = self._session["phase"]
        if phase == "sens":
            tuner = self._session["sens_tuner"]
        elif phase == "curve":
            tuner = self._session["curve_tuner"]
        else:
            tuner = self._session["fine_tuner"]

        tuner.report_result(score_med)

        gen = tuner.generation
        member = tuner.member

        line = (
            f"{phase},{idx},{gen},{member},{score_med:.6f},{result['throughput']:.6f},{result['miss_rate']:.6f},"
            f"{result['avg_path_eff']:.6f},{result['avg_overshoots']:.6f},{result['avg_reaccels']:.6f},{result['avg_error_px']:.6f},"
            f"{float(cand.get('outputDpi', 0.0)):.3f},{float(cand.get('syncSpeed', 0.0)):.6f},{float(cand.get('motivity', 0.0)):.6f},"
            f"{float(cand.get('gamma', 0.0)):.6f},{float(cand.get('smooth', 0.0)):.6f}\n"
        )
        with open(self._session["log_path"], "a", encoding="utf-8") as f:
            f.write(line)

        if math.isfinite(score_med) and score_med > self._session["best_score"]:
            self._session["best_score"] = score_med
            self._session["best"] = dict(cand)

            if phase == "sens":
                self._session["best_sens"] = {"outputDpi": float(cand["outputDpi"])}
                self.best_var.set(f"Best sens {score_med:.3f}: Output DPI={cand['outputDpi']:.1f}")
            else:
                if phase == "curve":
                    self._session["best_curve"] = dict(cand)
                self.best_var.set(
                    (
                        f"Best {phase} {score_med:.3f}: DPI={cand['outputDpi']:.1f} syncSpeed={cand['syncSpeed']:.3f} "
                        f"mot={cand['motivity']:.3f} gamma={cand['gamma']:.3f} smooth={cand['smooth']:.3f}"
                    )
                )

        self._session["idx"] += 1
        self.after(200, self._next_eval)


if __name__ == "__main__":
    App().mainloop()
