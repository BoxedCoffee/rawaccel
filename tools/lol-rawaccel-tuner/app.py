import json
import math
import os
import pathlib
import random
import subprocess
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from optimizer import CemTuner
from rawaccel import RawAccelController, SynchronousParams
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
            "distances_px": [140, 240, 360],
            "radii_px": [10, 14, 20],
        },
        "search": {
            "population": 5,
            "elite": 2,
            "generations": 8,
            "seed": 1337,
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
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LoL RawAccel Tuner (Synchronous)")
        self.resizable(False, False)

        self.cfg = _load_config()

        self.writer_var = tk.StringVar(value=self.cfg.get("writer_path", ""))
        self.settings_var = tk.StringVar(value=self.cfg.get("settings_path", ""))

        self.trials_var = tk.IntVar(value=int(self.cfg["task"]["trials"]))
        self.penalty_var = tk.DoubleVar(value=float(self.cfg["task"]["penalty"]))

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

        frm_bounds = tk.LabelFrame(self, text="Synchronous bounds")
        frm_bounds.grid(row=2, column=0, sticky="ew", **pad)

        headers = ["min", "max"]
        for i, h in enumerate(headers):
            tk.Label(frm_bounds, text=h).grid(row=0, column=i + 1, **pad)

        self._bound_row(frm_bounds, 1, "syncSpeed", self.sync_min, self.sync_max)
        self._bound_row(frm_bounds, 2, "motivity", self.mot_min, self.mot_max)
        self._bound_row(frm_bounds, 3, "gamma", self.gam_min, self.gam_max)
        self._bound_row(frm_bounds, 4, "smooth", self.smo_min, self.smo_max)

        frm_search = tk.LabelFrame(self, text="Search")
        frm_search.grid(row=3, column=0, sticky="ew", **pad)

        tk.Label(frm_search, text="population").grid(row=0, column=0, sticky="w", **pad)
        tk.Entry(frm_search, width=8, textvariable=self.population_var).grid(row=0, column=1, sticky="w", **pad)

        tk.Label(frm_search, text="elite").grid(row=0, column=2, sticky="w", **pad)
        tk.Entry(frm_search, width=8, textvariable=self.elite_var).grid(row=0, column=3, sticky="w", **pad)

        tk.Label(frm_search, text="generations").grid(row=0, column=4, sticky="w", **pad)
        tk.Entry(frm_search, width=8, textvariable=self.generations_var).grid(row=0, column=5, sticky="w", **pad)

        tk.Label(frm_search, text="seed").grid(row=0, column=6, sticky="w", **pad)
        tk.Entry(frm_search, width=10, textvariable=self.seed_var).grid(row=0, column=7, sticky="w", **pad)

        frm_actions = tk.Frame(self)
        frm_actions.grid(row=4, column=0, sticky="ew", **pad)

        tk.Button(frm_actions, text="Start optimization", command=self._start_optimization).grid(row=0, column=0, **pad)
        tk.Button(frm_actions, text="Stop", command=self._stop).grid(row=0, column=1, **pad)
        tk.Button(frm_actions, text="Restore base", command=self._restore_base).grid(row=0, column=2, **pad)
        tk.Button(frm_actions, text="Open runs", command=self._open_runs).grid(row=0, column=3, **pad)

        frm_status = tk.LabelFrame(self, text="Status")
        frm_status.grid(row=5, column=0, sticky="ew", **pad)

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
        self.cfg["search"]["population"] = int(self.population_var.get())
        self.cfg["search"]["elite"] = int(self.elite_var.get())
        self.cfg["search"]["generations"] = int(self.generations_var.get())
        self.cfg["search"]["seed"] = int(self.seed_var.get())
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

    def _start_optimization(self):
        if self._session is not None:
            messagebox.showinfo("Running", "Optimization already running")
            return
        if not self._validate_ready():
            return

        self._persist_ui_to_config()
        self._stop_requested = False

        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        run_id = time.strftime("%Y%m%d-%H%M%S")
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        controller = RawAccelController(self.writer_var.get().strip(), self.settings_var.get().strip())
        try:
            controller.snapshot_base(run_dir / "base_settings.json")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        bounds = self.cfg["search"]["bounds"]
        tuner = CemTuner(
            bounds=bounds,
            population=int(self.population_var.get()),
            elite=int(self.elite_var.get()),
            generations=int(self.generations_var.get()),
            seed=int(self.seed_var.get()),
        )

        log_path = run_dir / "results.csv"
        log_path.write_text("idx,generation,member,score,throughput,miss_rate,syncSpeed,motivity,gamma,smooth\n", encoding="utf-8")

        self._session = {
            "controller": controller,
            "tuner": tuner,
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

        tuner = self._session["tuner"]
        controller = self._session["controller"]
        run_dir = self._session["run_dir"]
        idx = self._session["idx"]

        candidate = tuner.next_candidate()
        if candidate is None:
            self._finish("Done")
            return

        params = SynchronousParams(
            syncSpeed=candidate["syncSpeed"],
            motivity=candidate["motivity"],
            gamma=candidate["gamma"],
            smooth=candidate["smooth"],
        )

        cand_path = run_dir / f"candidate_{idx:03d}.json"
        try:
            controller.write_candidate_settings(params, cand_path)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self._finish("Error writing candidate")
            return

        self.status_var.set(
            f"Eval {idx+1}: applying syncSpeed={params.syncSpeed:.3f} motivity={params.motivity:.3f} gamma={params.gamma:.3f} smooth={params.smooth:.3f}"
        )

        ok = controller.apply_settings(cand_path)
        if not ok:
            tuner.report_result(float("-inf"))
            self._session["idx"] += 1
            self.after(100, self._next_eval)
            return

        self.after(1300, lambda: self._run_block(idx, params))

    def _run_block(self, idx, params):
        if self._session is None:
            return

        task_cfg = self.cfg["task"]
        trials = int(task_cfg["trials"])
        penalty = float(task_cfg["penalty"])
        distances_px = list(task_cfg["distances_px"])
        radii_px = list(task_cfg["radii_px"])

        result = run_task_block(self, trials=trials, distances_px=distances_px, radii_px=radii_px)
        if result is None:
            self._stop_requested = True
            self._finish("Stopped")
            return

        score = result["throughput"] - penalty * result["miss_rate"]

        tuner = self._session["tuner"]
        tuner.report_result(score)

        gen = tuner.generation
        member = tuner.member

        line = (
            f"{idx},{gen},{member},{score:.6f},{result['throughput']:.6f},{result['miss_rate']:.6f},"
            f"{params.syncSpeed:.6f},{params.motivity:.6f},{params.gamma:.6f},{params.smooth:.6f}\n"
        )
        with open(self._session["log_path"], "a", encoding="utf-8") as f:
            f.write(line)

        if math.isfinite(score) and score > self._session["best_score"]:
            self._session["best_score"] = score
            self._session["best"] = params
            self.best_var.set(
                f"Best score {score:.3f}: syncSpeed={params.syncSpeed:.3f} motivity={params.motivity:.3f} gamma={params.gamma:.3f} smooth={params.smooth:.3f}"
            )

        self._session["idx"] += 1
        self.after(200, self._next_eval)


if __name__ == "__main__":
    App().mainloop()
