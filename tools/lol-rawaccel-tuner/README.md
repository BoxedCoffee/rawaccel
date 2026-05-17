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

## Notes
- The app writes candidate settings to `./runs/<timestamp>/candidate.json` and calls `writer.exe` to apply.
- Use the app’s Restore button to re-apply your original settings.
