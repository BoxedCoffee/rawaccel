# LoL RawAccel Tuner (Synchronous)

Human-in-the-loop tuner that applies Raw Accel `synchronous` settings, runs a repeatable click-target task, scores performance, and iteratively searches for better parameters.

## Requirements
- Windows 10/11
- Python 3.11+ (includes `tkinter`)
- Raw Accel installed
- `writer.exe` available (from the Raw Accel release zip)

## Setup
1. Open Raw Accel once and make sure it works.
2. Locate:
   - `writer.exe`
   - your `settings.json`

## Run
From this folder:
```bash
python app.py
```

On first run it will ask for `writer.exe` and `settings.json` and create `config.json`.

## How scoring works
- Runs a Fitts-style target clicking block.
- Score = `mean_throughput_bits_per_s - penalty * miss_rate`.

## AI presets
The AI tuner has a few built-in presets in `config.json` under `ai.presets`.

- `Balanced`: shorter-but-thorough run with stability-aware selection (`stable`).
- `Marathon`: long run with more iterations and a longer final confirm.

## Repeats (why a single “iteration” runs multiple blocks)
To reduce noise, the tuner can repeat evaluations:

- `search.repeats`: for the non-AI search mode, runs the same candidate multiple times.
- `ai.eval_repeats`: for AI tuning, runs multiple drill blocks per iteration and aggregates via median (and uses a stability metric when `selection_metric=stable`).

If `dual_drills.enabled=true`, each evaluation is two blocks (micro + flick), so repeats multiply runtime.

## Apply Best
`Apply best` now:

- Backs up your current `settings.json` to `runs/settings_backup_<timestamp>.json`.
- Overwrites `settings.json` with the selected candidate.
- Applies via `writer.exe`, then re-reads `settings.json` to verify key fields match.

## Confirm best vs #2
After an AI run, use `Confirm best vs #2` to run an extra A/B validation block and get a winner summary.

## Directional diagnostics and focus drills
- The task uses 360° direction bins (default 16) and reports per-bin miss/p90 plus bias along/perpendicular to the intended movement.
- By default, blocks use `angle_sampling=stratified` (each bin gets similar samples) to reduce noise.
- Use `Use worst bins` + `Run focus drill` to re-test only your weakest directions.

## Notes
- The app writes candidate settings to `./runs/<timestamp>/candidate.json` and calls `writer.exe` to apply.
- Use the app’s Restore button to re-apply your original settings.
- AI run reports include a 360° directional weakness table (micro/flick).
