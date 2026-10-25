#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Fernando Parodi
# SPDX-License-Identifier: GPL-3.0-only

"""Offline CSV/JPEG replay for the DoughWatch v0.2.1 research sidecar."""

import argparse
import csv
import re
from pathlib import Path

from doughwatch_v021_sidecar import Guard, read_image, write_csv_atomic


COLUMNS = (
    "run_id", "recorded_utc", "elapsed_min", "area_px",
    "area_gain_pct", "quality", "image_file",
)


def parse_roi(value):
    try:
        roi = tuple(int(v.strip()) for v in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("ROI must contain four integers") from exc

    if len(roi) != 4 or roi[2] <= roi[0] or roi[3] <= roi[1]:
        raise argparse.ArgumentTypeError("Expected ROI: x1,y1,x2,y2")
    return roi


def number(value, field, line, required=False):
    if value is None or not value.strip():
        if required:
            raise ValueError(f"CSV line {line}: missing {field}")
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"CSV line {line}: invalid {field}") from exc


def load_csv(path, selected_run):
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing = set(COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing CSV columns: {sorted(missing)}")

        rows = []
        for line, item in enumerate(reader, start=2):
            run = item["run_id"].strip()
            if selected_run and run != selected_run:
                continue
            rows.append((
                run,
                item["recorded_utc"],
                number(item["elapsed_min"], "elapsed_min", line, True),
                number(item["area_px"], "area_px", line),
                number(item["area_gain_pct"], "area_gain_pct", line),
                item["quality"],
                item["image_file"],
            ))

    if not rows:
        raise ValueError("No measurements found for the selected run")

    runs = {row[0] for row in rows}
    if len(runs) != 1:
        raise ValueError("CSV contains multiple runs; specify --run-id")

    run = runs.pop()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run) or run in (".", ".."):
        raise ValueError("Invalid run_id for report filename")

    rows.sort(key=lambda row: (row[2], row[1]))
    return run, rows


def main():
    parser = argparse.ArgumentParser(
        description="Offline DoughWatch optical validation"
    )
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--roi", type=parse_roi, required=True)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directory for generated validation reports",
    )
    args = parser.parse_args()

    if not args.frames.is_dir():
        parser.error("Photograph directory does not exist")

    run, source_rows = load_csv(args.csv, args.run_id)
    guard = Guard(args.roi)

    for source in source_rows:
        image = read_image(args.frames, source[6])
        guard.push(source, image)

    args.output.mkdir(parents=True, exist_ok=True)
    report = args.output / f"{run}_validation.csv"
    write_csv_atomic(report, guard.rows)

    issues = sum(row["sidecar_quality"] != "OK" for row in guard.rows)

    print("DoughWatch v0.2.1 — OFFLINE REPLAY")
    print(f"Run: {run}")
    print(f"Measurements: {len(source_rows)}")
    print(f"Flagged measurements: {issues}")
    print("Peak alerts: DISABLED")
    print(f"Report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
