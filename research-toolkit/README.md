# DoughWatch Research Toolkit

Open-source Python tools for experimental optical monitoring of dough fermentation.

Developed by Fernando Parodi.

**License:** GNU GPL v3.0 only (`GPL-3.0-only`).

## Research status

DoughWatch measures projected dough area in camera images and analyzes changes over time.

**Projected image area is not physical dough volume.**

The toolkit is experimental research software. Its measurements, anomaly classifications, and trend states are not yet validated predictors of fermentation readiness.

## Components

### 1. Core — `core/`

Image segmentation and fermentation trend processing.

Includes synthetic tests for:
- Dough expansion and recession
- Growth, plateau, and decline transitions
- Low-activity detection
- Prevention of premature peak alerts

### 2. Optical validation sidecar — `sidecar/`

An independent plausibility guard that compares reported area changes against visible differences between photographs.

Includes:
- Detection of suspicious segmentation jumps
- Persistent quarantine of affected measurement sequences
- CSV validation reports
- Offline replay from CSV and JPEG images

Peak alerts are disabled in the sidecar.

### 3. Stabilized tracker — `stabilized/`

Independent experimental mask tracking with checks for unsupported boundary changes.

Supports archived DoughWatch SQLite measurements and JPEG photographs.

Requires an explicit calibration file matching the selected experiment.

## Installation

Validated on Raspberry Pi with Python 3.13.5:

- Original environment: NumPy 2.2.4, OpenCV 4.10.0
- Fresh virtual environment: NumPy 2.5.4, OpenCV Headless 4.14.0

All 14 functional and integration tests passed in both environments.

Create a Python virtual environment:

    python -m venv .venv

Activate it using the appropriate command for your operating system, then install:

    python -m pip install -r requirements.txt

The dependency ranges have not yet been verified on every supported operating system.

## Run the tests

From each corresponding directory:

    cd core
    python test_core.py

    cd ../sidecar
    python test_sidecar.py
    python test_offline_replay.py

    cd ../stabilized
    python test_stable_tracker.py

The test suites use synthetic data and do not require the original fermentation experiment.

## Offline optical replay

The sidecar supports a CSV with these columns:

    run_id,recorded_utc,elapsed_min,area_px,area_gain_pct,quality,image_file

Each image filename refers to a JPEG in the supplied frames directory.

From the toolkit root:

    python sidecar/offline_replay.py --csv measurements.csv --frames frames --roi 20,10,320,210 --output reports

The ROI coordinates are `x1,y1,x2,y2`, expressed in image pixels.

Choose an ROI appropriate for the actual image dimensions and experiment.

The output contains diagnostic classifications and measurement acceptance states.

## Stabilized tracker

For an archived DoughWatch v0.2 experiment:

    python stabilized/stable_tracker.py --base ARCHIVE_DIRECTORY --output reports --config CALIBRATION.json --run-id EXPERIMENT_ID

The archive must contain:

    data/doughwatch.sqlite
    data/frames_v02/

The selected calibration must match the experiment ID and ROI.

`stabilized/calibration_example.json` is synthetic test geometry, not a real-experiment calibration.

## Verification history

Initial release candidate:
- 14 automated tests passed
- Four core tests
- Three optical sidecar tests
- One end-to-end offline replay test
- Six stabilized tracker tests

During development, the offline sidecar also replayed 289 original measurements from an October 2026 fermentation experiment and reproduced a previously identified suspicious segmentation jump.

These results demonstrate functional behavior and reproducibility of the diagnostic process, not independently established physical measurement accuracy.

## Data integrity

The archived-data readers use read-only SQLite connections.

Analysis reports are written separately from the original experimental database and photographs.

Do not use the research tools to make unattended safety-critical or production decisions.

## License

Copyright (c) 2026 Fernando Parodi.

Licensed under GNU GPL v3.0 only. See `LICENSE`.
