# Field report 01 — First live poolish fermentation run

**Project:** DoughWatch · Raspberry Pi 5 optical fermentation monitor  
**Trial date:** 24 October 2026 · Dubai, UAE (UTC+04:00)  
**Prototype:** v0.2 (CPU-based OpenCV segmentation)  
**Data cut-off:** 21:52:22 Dubai time / 17:52:22 UTC  
**Status:** **Candidate peak independently reproduced by offline replay and visually corroborated in original photographs; physical volume, readiness, and repeatability not yet validated**

## Executive finding

The first sustained live run produced **150 timestamped readings over 149.8 minutes**. A masked image-area signal rose from its baseline, reached a **maximum smoothed increase of +77.534% at approximately 21:20 Dubai time**, and ended **6.217 percentage points below that peak** at 21:52.

This pattern is **consistent with a transition from expansion to plateau and recession**. Subsequent independent offline replay of **all 150 original photographs** also found a peak around **21:23**, and targeted comparison of unmodified photographs showed a small downward movement in the apparent upper dough boundary by **21:52**. The finding is now a **visually corroborated candidate peak**—not a calibrated measurement of physical volume or a reliable automatic readiness indication. Both trackers share the same photographic input and have known segmentation limitations.

![Prototype smoothed image-area signal across the first run](../assets/field-run-2026-10-24.svg)

*Chart: sampled points from the exported v0.2 smoothed-area series, with the recorded maximum and final measurement explicitly included. Percentage means change in **detected projected image area relative to the initial mask**, not change in real dough volume. The known false early step remains visible.*

## Experimental setup and method

- **Compute:** Raspberry Pi 5; connected IMX708 camera with a fixed view of a transparent glass bowl containing poolish.
- **Observation:** Operator-selected rectangular ROI with an initial hand-traced dough silhouette; the algorithm estimates foreground pixels corresponding to the visible poolish.
- **Sampling:** Approximately one measurement per minute.
- **Storage:** Local images and measurement records; browser dashboard and CSV export.
- **Processing:** OpenCV/GrabCut segmentation on the Pi CPU. The connected **Hailo-8 accelerator was not used** by v0.2.
- **Sample identifier:** `20261024T152234_205348`. **ROI:** 198,750 image pixels. **Initial detected area:** 49,635 pixels (**24.97% ROI occupancy**).

The experiment tracks **projected image coverage** in a fixed camera view. Bowl curvature, perspective, backlighting, reflections, occlusion, and changing segmentation boundaries prevent treating this signal directly as volumetric expansion.

## Measured timeline

All times in Dubai local time (UTC+04:00) unless otherwise stated.

| Event | Local time | Source observation |
| --- | --- | --- |
| Experiment baseline | **19:22:34** | 49,635 detected pixels, 0% change |
| Previously diagnosed segmentation anomaly | **19:36:39** | Detected area jumped from 50,425 to 57,063 pixels in ~1 minute |
| Highest **smoothed** reported area change | **21:20:11** | **+77.534%** relative to baseline |
| Highest **single-frame raw** reported area change | **21:22:13** | **+81.225%** — less reliable than a sustained trend |
| Latest CSV sample | **21:52:22** | Raw +69.890%; smoothed **+71.317%**; occupancy 42.43% |

From the smoothed maximum to the last logged sample, **approximately 32.18 minutes elapsed**, with a **6.217-percentage-point decrease** in the reported smoothed mask-area signal. Over the final 30 readings, the dashboard's own state classification was **`SLOWING_OR_HOLDING` for 25** and **`GROWING` for 5**.

**Interpretation:** the late-stage signal exhibits a sustained decline from a high point, with small rebounds. The **21:20–21:25 candidate peak window** is now supported by independent tracker replay and a small downward shift in the photographed surface boundary. Visual cues such as bubble behavior, aroma, and handling were not instrumentally measured.

## Critical measurement limitation: mask instability

The first run also established a concrete failure mode:

| Consecutive frames | Detected area | Consequence |
| --- | ---: | --- |
| 19:35:39 | 50,425 pixels | Reference |
| 19:36:39 | 57,063 pixels | **+6,638 pixels / +13.16% in one minute** |

Inspection of both saved photographs found no comparable physical change in the poolish silhouette. The most plausible cause was **unstable re-segmentation** rather than actual dough expansion.

Other substantial positive and negative frame-to-frame jumps occurred later. The CSV marks **all 150 samples `quality=OK`**, demonstrating that the existing quality flag does **not** provide adequate protection against this failure mode. Smoothing can reduce noise without eliminating systematic mask errors.

The historical [live dashboard capture](../assets/doughwatch-live-v02.png) and [baseline comparison](../assets/doughwatch-actual-comparison.png) document the prototype's operation, but their reported percentages remain **unvalidated optical measurements**.

## Independent v0.2.1 investigation — complete replay

A separate read-only validator and stabilized tracker were used to investigate mask changes without disturbing the live camera, original v0.2 process, or its records.

Early offline checks identified an abrupt v0.2 segmentation jump and demonstrated that mask updates unsupported by source-image changes could be quarantined. Initial 60-frame tests were provisional and exposed an overly high hold rate. The tracker was subsequently replayed across the **complete 150-frame sequence**, with **zero photographs skipped**.

### Two optical trackers: peak comparison

| Measurement | Original v0.2 (smoothed signal) | v0.2.1 stabilized replay (provisional) |
| --- | ---: | ---: |
| Time of maximum signal, Dubai | **21:20:11** | **21:23:13** |
| Time of maximum signal, UTC | 17:20:11 | 17:23:13 |
| Maximum reported projected-area change | **+77.534%** | **+92.105%** |
| Final reported projected-area change, 21:52:22 | **+71.317%** | **+86.070%** |
| Net reduction from each algorithm's maximum | **6.217 percentage points** | **6.035 percentage points** |
| Peak time offset | — | **3 minutes 2 seconds later** |

The stabilized replay quarantined **71 of 150 proposed mask updates (47.3%)**, ending with status `HELD_UNSUPPORTED_BOUNDARY_CHANGE`. It reported a larger *absolute* segmented-area change than v0.2, reflecting substantive disagreement about the shape of the foreground mask and the use of provisional baseline calibration. Neither percentage series should be presented as ground-truth dough-volume growth.

**Key finding:** despite considerable disagreement over absolute mask size, both optical analysis pipelines produce a late-stage turning point within about three minutes and finish approximately six percentage points below their respective reported peaks.

**Independence qualification:** v0.2.1 is a different algorithm run offline, but it processes the **same camera photographs** as v0.2. Agreement is valuable corroboration of the *optical signal's turning point*, not independent physical-sensor validation.

## Visual cross-check — original unmodified photographs

The operator retrieved three raw IMX708 JPEGs saved during the original run. The following observations are from the source photographs, **without segmentation overlays**.

| Original photograph, Dubai time | Purpose | Observation |
| --- | --- | --- |
| **21:20:11** (17:20:11 UTC) | v0.2 smoothed-signal peak | Dough surface near its highest photographed position in this selection |
| **21:23:13** (17:23:13 UTC) | v0.2.1 stabilized-signal peak | Similar surface level, marginally higher at several image positions |
| **21:52:22** (17:52:22 UTC) | End of the 150-frame sequence | The upper dough boundary appears slightly lower than at 21:23 |

### Exploratory image-space edge measurement

To make the photographic comparison more reproducible, a simple **intensity-gradient cross-check** was applied to the original 1280 × 720 images:

1. Six horizontal strips across the visible upper surface were examined, spanning image x-coordinates **290–890**, each approximately **100 pixels wide**.
2. Within each strip, mean grayscale intensity was evaluated across image rows **122–199**; a lightly smoothed vertical profile was differentiated to estimate the apparent bright-surface transition.
3. Comparing **21:23:13 → 21:52:22**, the detected transition shifted **4–6 image pixels downward in all six strips** (median **4.5 pixels**).
4. A separate static tabletop image region showed little visual change, consistent with a stationary viewpoint.

These figures describe an **apparent edge displacement in pixels**. Reflections, illumination, curved glass, spatial averaging, and the choice of gradient feature may shift the detected boundary. The estimate has **not** been converted into millimeters, physical dough height, or volume, and three inspected photographs cannot pinpoint the exact instant of true maximum volume.

**Visual cross-check conclusion:** the late photograph shows a subtle but repeatable downward movement of the image-space upper surface boundary, which supports a physical recession interpretation. Combined with the two independently computed time series, the first DoughWatch run merits the label **“candidate peak independently reproduced and visually corroborated.”**

The three complete raw JPEGs and software implementation remain outside this curated public repository. Reported values are sufficient to document the observation but not to certify instrument accuracy.

## Engineering conclusions

1. **End-to-end acquisition demonstrated:** camera, fixed observation zone, local storage, browser visualization, and continuous sampling ran for roughly 2.5 hours in the exported dataset.
2. **A candidate peak was independently reproduced and visually corroborated:** both algorithms locate maxima within 3 minutes 2 seconds; the late original photograph has a 4–6-pixel downward edge displacement relative to the stabilized peak image (exploratory image-space estimate).
3. **Readiness is not yet automated:** visual confirmation and a validated measurement signal are required before identifying an actionable fermentation peak.
4. **Quality control must be redesigned:** the existing mask can change without comparable changes in source photography, and `quality=OK` can hide this failure.
5. **Independent offline replay completed:** all 150 frames processed without skips; however, 71 updates were quarantined and absolute mask-area estimates differ substantially, so calibration and segmentation reliability remain open problems.

## Next validation gate

**Before claiming reliable peak detection:**

- **Completed:** replay the full first run (150/150 photos), identify the peak independently, and visually cross-check three original photographs.
- **Next:** validate the surface-boundary shift on more frames using a fixed, registered optical method; quantify uncertainty in pixels and its susceptibility to reflections.
- Quantify remaining false jumps, hold/release rates, and sensitivity to illumination, bowl geometry, and calibration.
- Improve mask continuity and confidence handling without freezing genuine gradual expansion.
- Repeat with new poolish batches and, where feasible, add a physical reference measurement to estimate real volume.
- Only then enable a conservative **`PEAK_PASSED — REVIEW NOW`** alert with sustained-evidence requirements and clear uncertainty.

## Evidence and provenance

**Sources:** the original v0.2 CSV (**150 rows**, **2026-10-24 15:22:34 to 17:52:22 UTC**); independent v0.2.1 comparison CSV from a 150-frame offline replay of the same run; Raspberry Pi console summaries; and three unmodified camera JPEGs dated **17:20:11**, **17:23:13**, and **17:52:22 UTC**. Summary metrics were calculated from recorded data rather than estimated from the dashboard. The exploratory image-space displacement was estimated from grayscale vertical-gradient locations in the photos. This public report contains a curated numerical summary; the complete source photos, raw datasets, and device application remain unpublished.

This is a **development field report**, not an accuracy certification, commercial performance claim, or food-safety determination.

---

**DoughWatch** · [Repository overview](../README.md) · [Fernando Parodi](https://github.com/fernando-parodi)
