# DoughWatch visual assets

This folder contains selected, public-facing images from the October 2026 DoughWatch v0.2 experiment.

- `doughwatch-showcase.png` — Designed project-presentation graphic. This is a **composite visual** derived from prototype screenshots, not an unmodified instrument capture.
- `doughwatch-live-v02.png` — Original dashboard screenshot showing the live ROI, dough mask, 31.5% *reported* projected-area increase, and growth curve.
- `doughwatch-actual-comparison.png` — Comparison made from two real dashboard captures, one at baseline and one during later monitoring.

**Evidence note:** The first experimental run revealed a segmentation-instability artifact, including a 13.16% apparent area increase in one minute without a corresponding visible change in the camera images. The displayed growth percentages are **prototype software outputs**, not independently validated increases in physical dough volume. The green mask shows estimated segmented image area.

The Raspberry Pi 5 / IMX708 prototype currently uses CPU-based OpenCV image processing. Hailo-8 acceleration is future research, not an implemented feature of v0.2.
