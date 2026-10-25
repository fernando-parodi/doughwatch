# SPDX-FileCopyrightText: 2026 Fernando Parodi
# SPDX-License-Identifier: GPL-3.0-only

"""Image segmentation and trend processing for DoughWatch v0.2.

Projected dough area is an *image-space proxy*, not physical dough volume.
No Hailo model is trained yet: this baseline uses OpenCV GrabCut and user seeds.
"""
from __future__ import annotations
import datetime as dt
import statistics

import cv2
import numpy as np


def roi_and_poly_mask(roi, points):
    x1, y1, x2, y2 = roi
    h, w = y2-y1, x2-x1
    pts = np.array([[(int(x)-x1), (int(y)-y1)] for x, y in points], dtype=np.int32)
    mask = np.zeros((h, w), np.uint8)
    cv2.fillPoly(mask, [pts], 255)
    return mask


def _largest_seeded_component(binary, seed):
    n, lab, stats, _ = cv2.connectedComponentsWithStats(binary.astype(np.uint8), 8)
    if n < 2:
        return np.zeros_like(binary)
    overlaps = [int(np.count_nonzero((lab == i) & (seed > 0))) for i in range(1, n)]
    idx = 1 + int(np.argmax(overlaps))
    if overlaps[idx-1] == 0:
        return np.zeros_like(binary)
    return np.uint8(lab == idx) * 255


class DoughMaskTracker:
    """Constrain one foreground segment to a fixed hand-seeded dough region."""
    def __init__(self, roi, poly_points, frame):
        self.roi = tuple(map(int, roi))
        self.seed_polygon = roi_and_poly_mask(roi, poly_points)
        h, w = self.seed_polygon.shape
        self.roi_pixels = h*w
        if cv2.countNonZero(self.seed_polygon) < max(200, int(self.roi_pixels * .01)):
            raise ValueError('Dough outline is too small; trace the full visible dough patch.')
        # Use a small *permanent* seed in the deep lower central body of the
        # dough. This does not freeze its surface/outline during a decline.
        seed = cv2.erode(self.seed_polygon, np.ones((19, 19), np.uint8), iterations=1)
        yy, xx = np.nonzero(seed)
        if len(yy) < 20:
            raise ValueError('Outline too narrow to establish an interior seed.')
        keep = yy >= np.quantile(yy, .65)
        seed2 = np.zeros_like(seed)
        seed2[yy[keep], xx[keep]] = 255
        self.anchor = cv2.erode(seed2, np.ones((7, 7), np.uint8), iterations=1)
        if cv2.countNonZero(self.anchor) < 10:
            self.anchor = seed2
        self.prev = self.seed_polygon.copy()
        self.bg = np.zeros((1, 65), np.float64)
        self.fg = np.zeros((1, 65), np.float64)
        self.initial_mask = self._refine(frame, initializing=True)
        if self.initial_mask is None:
            raise ValueError('Could not identify dough mask. Try a tighter dough outline.')
        self.prev = self.initial_mask.copy()
        if cv2.countNonZero(self.initial_mask) > 1.75 * cv2.countNonZero(self.seed_polygon):
            raise ValueError('Automatic mask spread far beyond your outline; please outline the dough more closely.')
        self.baseline_area = cv2.countNonZero(self.prev)
        self.last_area = self.baseline_area
        if self.baseline_area / self.roi_pixels >= .87:
            raise ValueError('Dough fills nearly all ROI; enlarge ROI to allow growth.')

    def _refine(self, frame, initializing=False):
        x1,y1,x2,y2 = self.roi
        crop = frame[y1:y2, x1:x2].copy()
        if crop.size == 0:
            return None
        h,w = self.prev.shape
        # An adjustable growth corridor allows modest expansion/shrinkage.
        # Pixels far outside corridor cannot be newly classified as dough.
        reach = max(50, min(130, int(min(h,w)*.36)))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*reach+1, 2*reach+1))
        template = self.seed_polygon if initializing else self.initial_mask
        corridor = cv2.dilate(template, kernel)
        trim = np.zeros((h,w), np.uint8)
        trim[:3,:] = 255; trim[-3:,:] = 255; trim[:,:3] = 255; trim[:,-3:] = 255
        mask = np.full((h,w), cv2.GC_PR_BGD, np.uint8)
        mask[template > 0] = cv2.GC_PR_FGD
        mask[corridor == 0] = cv2.GC_BGD
        mask[trim > 0] = cv2.GC_BGD
        mask[self.anchor > 0] = cv2.GC_FGD
        # GrabCut re-estimates appearance for every frame, while spatial prior
        # and a permanent *small* seed stop jumps to bright bowl reflections.
        try:
            bg = self.bg.copy(); fg = self.fg.copy()
            cv2.grabCut(crop, mask, None, bg, fg, 4 if initializing else 2,
                        cv2.GC_INIT_WITH_MASK)
            binary = np.uint8(np.isin(mask, (cv2.GC_FGD, cv2.GC_PR_FGD))) * 255
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE,
                                       cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5)))
            binary = _largest_seeded_component(binary, self.anchor)
            if cv2.countNonZero(binary) < max(50, int(self.roi_pixels*.005)):
                return None
            return binary
        except cv2.error:
            return None

    def read(self, frame):
        mask = self._refine(frame)
        if mask is None:
            return None, 'SEGMENTATION_LOST'
        area = cv2.countNonZero(mask)
        occupancy = area/self.roi_pixels
        if occupancy > .90:
            return None, 'ROI_FULL'
        # A minute of fermentation should not cause dramatic mask jumps.
        # Rejection preserves the prior mask and prevents false peaks.
        if not .70 <= area/max(1,self.last_area) <= 1.30:
            return None, 'SUDDEN_MASK_CHANGE'
        x1,y1,x2,y2 = self.roi
        crop = frame[y1:y2,x1:x2]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        if np.mean(gray[mask > 0] >= 250) > .30:
            return None, 'OVEREXPOSED'
        self.prev = mask
        self.last_area = area
        return {'area_px':area, 'occupancy_pct':round(100*occupancy,2),
                'area_gain_pct':round(100*(area/self.baseline_area-1),3)}, 'OK'


def analyze_trend(readings, settings):
    """readings: chronological list of {'minute':float,'gain':float} for valid samples.
    Returns a conservative diagnostic state; thresholds are tunable, *not* a
    validated poolish readiness model.
    """
    if not readings:
        return {'state':'AWAITING_BASELINE','smoothed_gain_pct':None,'growth_pph':None}
    ts = [float(r['minute']) for r in readings]
    vals = [float(r['gain']) for r in readings]
    # Each smoothed point is a trailing median, suppressing isolated bad masks.
    smooth = [statistics.median(vals[max(0,i-4):i+1]) for i in range(len(vals))]
    now = ts[-1]
    elapsed = now-ts[0]
    window = [(t,v) for t,v in zip(ts,smooth) if t >= now - settings['trend_window_min']]
    slope = None
    if len(window) >= 3 and window[-1][0]-window[0][0] >= 5:
        t0,v0 = window[0]; t1,v1 = window[-1]
        slope = 60*(v1-v0)/(t1-t0)
    historical_max = max(smooth)
    peak_i = next(i for i,v in enumerate(smooth) if v >= historical_max-.001)
    peak_at = ts[peak_i]
    has_risen = historical_max >= settings['min_peak_growth_pct']
    decline = historical_max-smooth[-1]
    # Readiness requires a short near-maximum dwell, not merely one peak-shaped
    # camera artifact followed by a lower area reading.
    near_peak_times = [t for t,v in zip(ts,smooth)
                       if v >= historical_max-settings['plateau_range_pct']]
    near_peak_dwell = (near_peak_times[-1]-near_peak_times[0]) if near_peak_times else 0
    plateau_span = [(t,v) for t,v in zip(ts,smooth) if t >= now-settings['plateau_window_min']]
    is_flat = (len(plateau_span)>=5 and
               plateau_span[-1][0]-plateau_span[0][0] >= settings['plateau_window_min']*.8 and
               max(v for _,v in plateau_span)-min(v for _,v in plateau_span)
               <= settings['plateau_range_pct'])
    if has_risen and decline>=settings['decline_pct'] and \
       near_peak_dwell>=settings['min_near_peak_min'] and \
       now-peak_at>=settings['decline_hold_min'] and slope is not None and slope < -0.75:
        label='PEAK_PASSED_REVIEW_NOW'
    elif has_risen and is_flat:
        label='PLATEAU_AFTER_RISE'
    elif elapsed >= settings['inactivity_min'] and historical_max < settings['low_activity_growth_pct']:
        label='LOW_ACTIVITY_CHECK'
    elif elapsed < settings['lag_grace_min']:
        label='INITIAL_LAG'
    elif slope is not None and slope > settings['rise_rate_pph']:
        label='GROWING'
    elif has_risen:
        label='SLOWING_OR_HOLDING'
    else:
        label='MONITORING'
    return {'state':label,'smoothed_gain_pct':round(smooth[-1],3),
            'growth_pph':None if slope is None else round(slope,3),
            'peak_gain_pct':round(historical_max,3),'elapsed_min':round(elapsed,1)}


DEFAULT_SETTINGS = dict(
    min_peak_growth_pct=5.0,
    min_near_peak_min=10,
    decline_pct=1.5,
    decline_hold_min=12,
    plateau_window_min=15,
    plateau_range_pct=1.2,
    inactivity_min=90,
    low_activity_growth_pct=2.0,
    lag_grace_min=30,
    trend_window_min=15,
    rise_rate_pph=1.0,
)
