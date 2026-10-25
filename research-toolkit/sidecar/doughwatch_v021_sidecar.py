#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Fernando Parodi
# SPDX-License-Identifier: GPL-3.0-only

"""DoughWatch v0.2.1: read-only optical plausibility guard (sidecar).

Reads saved, UNANNOTATED v0.2 JPEGs and the v0.2 SQLite database in read-only
mode. Writes only to a new independent output directory, never starts a camera,
never edits v0.2 calibration or images, and never makes authoritative peak claims.

This patch detects and quarantines suspicious mask changes. It does NOT yet
implement independent segmentation; temporal re-segmentation is future work.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
import time
from urllib.request import urlopen

import cv2
import numpy as np

LOG = logging.getLogger('doughwatch-sidecar')
FIELDNAMES = [
    'run_id','recorded_utc','elapsed_min','source_quality','source_area_px',
    'source_area_gain_pct','image_file','mean_pixel_change',
    'changed_pixels_gt10_pct','area_step_pp','sidecar_quality',
    'accepted_area_gain_pct','sidecar_state'
]


def assess_transition(previous_bgr, current_bgr, roi, prior_gain, current_gain, delta_min,
                      source_quality='OK', mean_limit=1.75, changed_limit_pct=0.5):
    """Check a source area jump against change actually visible in raw photographs."""
    x1,y1,x2,y2 = map(int,roi)
    if previous_bgr.shape != current_bgr.shape:
        return {'quality':'IMAGE_DIMENSIONS_CHANGED','mean_diff':None,'pct_changed':None,'step_pp':None}
    h,w=previous_bgr.shape[:2]
    if not (0<=x1<x2<=w and 0<=y1<y2<=h):
        return {'quality':'INVALID_ROI','mean_diff':None,'pct_changed':None,'step_pp':None}
    a=cv2.cvtColor(previous_bgr[y1:y2,x1:x2],cv2.COLOR_BGR2GRAY)
    b=cv2.cvtColor(current_bgr[y1:y2,x1:x2],cv2.COLOR_BGR2GRAY)
    a=cv2.GaussianBlur(a,(5,5),0)
    b=cv2.GaussianBlur(b,(5,5),0)
    d=cv2.absdiff(a,b)
    mad=float(np.mean(d))
    changed=float(100.0*np.count_nonzero(d>10)/d.size)
    step=float(current_gain-prior_gain) if prior_gain is not None and current_gain is not None else None
    if source_quality != 'OK':
        quality='SOURCE_UNRELIABLE'
    elif step is None:
        quality='SOURCE_MISSING_AREA'
    elif (0 < delta_min <= 2.2 and abs(step) >= 3.0
          and mad < mean_limit and changed < changed_limit_pct):
        quality='MASK_JUMP_WITH_STABLE_IMAGE'
    elif 0 < delta_min <= 2.2 and abs(step) >= 8.0:
        quality='REVIEW_LARGE_STEP'
    else:
        quality='OK'
    return {'quality':quality,'mean_diff':round(mad,3),'pct_changed':round(changed,4),
            'step_pp':round(step,3) if step is not None else None}


def get_roi_and_run(status_url):
    with urlopen(status_url,timeout=4) as resp:
        j=json.load(resp)
    roi=j.get('roi');run=j.get('run_id')
    if not roi or not run or len(roi)!=4:
        raise RuntimeError('v0.2 has no active ROI/run. Keep its original experiment running.')
    return tuple(int(v) for v in roi),str(run)


def read_source_rows(db_path,run_id):
    uri=f'file:{db_path.resolve()}?mode=ro'
    with sqlite3.connect(uri,uri=True,timeout=5) as db:
        db.execute('PRAGMA query_only=ON')
        return db.execute('''SELECT run_id, recorded_utc, elapsed_min, area_px,
                              area_gain_pct, quality, image_file
                              FROM area_readings WHERE run_id=?
                              ORDER BY elapsed_min, recorded_utc''',(run_id,)).fetchall()


def read_image(frames_dir,filename):
    if not filename or Path(filename).name!=filename:
        return None
    p=frames_dir/filename
    if not p.is_file():return None
    return cv2.imread(str(p),cv2.IMREAD_COLOR)


class Guard:
    def __init__(self,roi):
        self.roi=roi
        self.last_image=None
        self.last_raw_gain=None
        self.last_minute=None
        self.affected=False
        self.baseline_gain=None
        self.history=[]
        self.rows=[]
        self.count=0

    def push(self,source, image):
        run_id,timestamp,minute,area,gain,source_quality,file=source
        minute=float(minute)
        diag={'quality':'OK','mean_diff':None,'pct_changed':None,'step_pp':None}
        if image is None:
            diag['quality']='IMAGE_NOT_READABLE'
        elif self.last_image is None:
            if source_quality!='OK' or area is None or gain is None:
                diag['quality']='SOURCE_UNRELIABLE'
        else:
            diag=assess_transition(self.last_image,image,self.roi,self.last_raw_gain,
                                   gain,minute-self.last_minute,source_quality)
        q=diag['quality']
        # Any plausible-looking post-jump area belongs to the same unverified
        # epoch. Do NOT resume trusting the new baseline just because it persists.
        if q in ('MASK_JUMP_WITH_STABLE_IMAGE','REVIEW_LARGE_STEP','IMAGE_DIMENSIONS_CHANGED'):
            self.affected=True
        if self.affected:
            label='REVIEW_REQUIRED_NO_PEAK_ALERT'
            accepted=None
        elif q=='OK' and gain is not None:
            label='OBSERVATION_ACCEPTED'
            accepted=float(gain)
            self.history.append((minute,accepted))
        else:
            label='IMAGE_OR_SOURCE_UNRELIABLE'
            accepted=None
        self.rows.append({
            'run_id':run_id,'recorded_utc':timestamp,'elapsed_min':round(minute,3),
            'source_quality':source_quality,'source_area_px':area,
            'source_area_gain_pct':gain,'image_file':file,
            'mean_pixel_change':diag['mean_diff'],
            'changed_pixels_gt10_pct':diag['pct_changed'],
            'area_step_pp':diag['step_pp'],'sidecar_quality':q,
            'accepted_area_gain_pct':accepted,'sidecar_state':label})
        self.count+=1
        if image is not None:
            self.last_image=image
            self.last_minute=minute
            self.last_raw_gain=float(gain) if gain is not None else None
        return q,label


def write_csv_atomic(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.csv.tmp')
    with tmp.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDNAMES)
        writer.writeheader();writer.writerows(rows)
    os.replace(tmp,path)


def analyze_once(base, out_dir, status_url):
    roi,run=get_roi_and_run(status_url)
    db=base/'data'/'doughwatch.sqlite'
    frames=base/'data'/'frames_v02'
    if not frames.is_dir() or not db.is_file():
        raise RuntimeError(f'Cannot find read-only v0.2 data under {base}')
    rows=read_source_rows(db,run)
    if not rows:
        raise RuntimeError(f'No samples yet for run {run}')
    guard=Guard(roi)
    for item in rows:
        img=read_image(frames,item[6])
        guard.push(item,img)
    output=out_dir/f'{run}_validation.csv'
    write_csv_atomic(output,guard.rows)
    issues=[r for r in guard.rows if r['sidecar_quality']!='OK']
    print('DoughWatch v0.2.1 read-only validation')
    print(f'Active run: {run} | ROI: {roi}')
    print(f'Reviewed: {guard.count} measurements; questionable samples: {len(issues)}')
    for r in issues[:5]:
        print(f"  {r['recorded_utc']} | {r['sidecar_quality']} | area step {r['area_step_pp']} pp | image mean change {r['mean_pixel_change']}")
    print(f'Peak alerts: DISABLED in sidecar; source experiment untouched')
    print(f'Separate report: {output}')
    return guard


def main():
    p=argparse.ArgumentParser(description='DoughWatch read-only validation sidecar')
    p.add_argument('--base',type=Path,default=Path.home()/'doughwatch_v02',help='Live v0.2 application directory')
    p.add_argument('--output',type=Path,default=Path.home()/'doughwatch_v021_sidecar'/'reports',help='Independent sidecar output directory')
    p.add_argument('--status-url',default='http://127.0.0.1:8091/api/status')
    p.add_argument('--watch',action='store_true',help='Repeat validation every 60 seconds')
    args=p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    while True:
        try:analyze_once(args.base,args.output,args.status_url)
        except Exception as ex:
            print('Sidecar error (v0.2 unaffected):',ex,file=sys.stderr)
            if not args.watch:return 1
        if not args.watch:return 0
        time.sleep(60)


if __name__=='__main__':
    raise SystemExit(main())
