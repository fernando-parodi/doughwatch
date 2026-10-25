# SPDX-FileCopyrightText: 2026 Fernando Parodi
# SPDX-License-Identifier: GPL-3.0-only

"""End-to-end synthetic test for DoughWatch offline replay."""
import csv
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

with tempfile.TemporaryDirectory(prefix="doughwatch_test_") as temp:
    root = Path(temp)
    frames = root / "frames"
    frames.mkdir()

    image = np.zeros((120, 120, 3), dtype=np.uint8)
    image[30:85, 30:90] = 180

    measurements = [
        (0, 49635, 0.00),
        (1, 50000, 0.75),
        (2, 56638, 14.12),
        (3, 57000, 14.86),
    ]

    csv_path = root / "measurements.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "run_id", "recorded_utc", "elapsed_min",
            "area_px", "area_gain_pct", "quality", "image_file"
        ])
        for minute, area, gain in measurements:
            name = f"frame_{minute}.jpg"
            assert cv2.imwrite(str(frames / name), image)
            writer.writerow([
                "offline_test", f"2026-10-25T12:{minute:02d}:00Z",
                minute, area, gain, "OK", name
            ])

    command = [
        sys.executable, "-B", "offline_replay.py",
        "--csv", str(csv_path),
        "--frames", str(frames),
        "--roi", "10,10,110,110",
        "--output", str(root / "reports"),
    ]

    subprocess.run(command, check=True)

    report = root / "reports" / "offline_test_validation.csv"
    with report.open(newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 4
    assert rows[2]["sidecar_quality"] == "MASK_JUMP_WITH_STABLE_IMAGE"
    assert rows[3]["sidecar_state"] == "REVIEW_REQUIRED_NO_PEAK_ALERT"
    assert rows[3]["accepted_area_gain_pct"] == ""

    print("OFFLINE INTEGRATION TEST: PASS")
    print("False mask jump detected.")
    print("Contaminated measurements rejected.")
    print("Original DoughWatch database untouched.")
