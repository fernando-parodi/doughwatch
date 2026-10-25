#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Fernando Parodi
# SPDX-License-Identifier: GPL-3.0-only

"""Independent read-only mask tracker for DoughWatch prototype v0.2.1.

Consumes original JPEGs saved by v0.2. Never opens the camera, changes the
source database, changes the source images, or sends fermentation peak alerts.

WARNING: Projected foreground image pixels != physical dough volume.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from urllib.request import urlopen

import cv2
import numpy as np

CSV_FIELDS = ['run_id','recorded_utc','elapsed_min','source_area_px','source_growth_pct',
              'estimated_area_px','estimated_growth_pct','projected_step_pct',
              'change_mean_gray','changed_pct_gt10','mask_xor_pct','edge_support_pct',
              'status','image_file']


def polygon_mask(roi, polygon, scale=0.5):
    x1,y1,x2,y2 = (int(v) for v in roi)
    width=max(1,round((x2-x1)*scale)); height=max(1,round((y2-y1)*scale))
    points=np.asarray([[(p[0]-x1)*scale,(p[1]-y1)*scale] for p in polygon],np.float32)
    p=np.rint(points).astype(np.int32).reshape((-1,1,2))
    mask=np.zeros((height,width),np.uint8)
    cv2.fillPoly(mask,[p],255)
    return mask


def component_with_anchor(binary, anchor):
    n,labels,stats,_=cv2.connectedComponentsWithStats(np.uint8(binary>0),8)
    if n<=1:return np.zeros_like(binary)
    hits=[int(np.count_nonzero((labels==i)&(anchor>0))) for i in range(1,n)]
    if max(hits)==0:return np.zeros_like(binary)
    return np.uint8(labels==(int(np.argmax(hits))+1))*255


class StableTracker:
    """Temporal mask continuity plus photographic boundary-evidence gate.

    The fixed anchor is deliberately small so the outline can move down when
    dough collapses. Only ACCEPTED masks become priors for later frames.
    """
    def __init__(self,roi,polygon,first_bgr,scale=0.5):
        self.roi=tuple(map(int,roi));self.scale=float(scale)
        if not (0.2<=self.scale<=1.0):raise ValueError('Scale outside 0.2–1.0')
        self.initial_poly=polygon_mask(roi,polygon,self.scale)
        self.working_h,self.working_w=self.initial_poly.shape
        self.total_pixels=self.initial_poly.size
        self.bg=np.zeros((1,65),np.float64)
        self.fg=np.zeros((1,65),np.float64)
        if cv2.countNonZero(self.initial_poly)<max(100,int(self.total_pixels*0.02)):
            raise ValueError('Initial dough polygon too small for ROI')
        k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(13,13))
        interior=cv2.erode(self.initial_poly,k)
        yy,xx=np.where(interior>0)
        if len(yy)<50:raise ValueError('Initial polygon has no reliable interior')
        lower=yy>=np.quantile(yy,.73)
        self.anchor=np.zeros_like(self.initial_poly)
        self.anchor[yy[lower],xx[lower]]=255
        self.anchor=cv2.erode(self.anchor,np.ones((5,5),np.uint8))
        if cv2.countNonZero(self.anchor)<20:raise ValueError('Permanent anchor too small')
        first=self._crop(first_bgr)
        self.last_image=first
        mask=self._refine(first,self.initial_poly,initializing=True)
        if mask is None:raise ValueError('Baseline dough segmentation failed')
        initial_px=cv2.countNonZero(self.initial_poly)
        seg_px=cv2.countNonZero(mask)
        if not .70 <= seg_px/initial_px <= 1.35:
            raise ValueError(f'Baseline segmentation drifted away from calibration ({seg_px}/{initial_px} pixels)')
        self.prev=mask.copy()
        self.baseline=seg_px
        self.area=seg_px
        self.last_status='BASELINE_APPROXIMATE_SEED'

    def _crop(self,frame):
        x1,y1,x2,y2=self.roi
        if frame is None or frame.ndim!=3 or frame.shape[2]!=3:
            raise ValueError('Frame must be BGR image')
        h,w=frame.shape[:2]
        if not (0<=x1<x2<=w and 0<=y1<y2<=h):
            raise ValueError('ROI is outside photo frame')
        patch=frame[y1:y2,x1:x2]
        return cv2.resize(patch,(self.working_w,self.working_h),interpolation=cv2.INTER_AREA)

    def _refine(self,patch,previous,initializing=False):
        h,w=previous.shape
        # Narrower corridor than v0.2, but can move every accepted frame.
        radius=20 if initializing else 12
        K=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(radius*2+1,)*2)
        corridor=cv2.dilate(previous,K)
        m=np.full((h,w),cv2.GC_BGD,np.uint8)
        m[corridor>0]=cv2.GC_PR_BGD
        m[previous>0]=cv2.GC_PR_FGD
        k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7))
        core=cv2.erode(previous,k)
        m[core>0]=cv2.GC_FGD
        # Permanent seed prevents a new isolated reflection becoming the dough.
        m[self.anchor>0]=cv2.GC_FGD
        m[:2,:]=cv2.GC_BGD;m[-2:,:]=cv2.GC_BGD
        m[:,:2]=cv2.GC_BGD;m[:,-2:]=cv2.GC_BGD
        bg=self.bg.copy();fg=self.fg.copy()
        try:
            cv2.grabCut(patch,m,None,bg,fg,3 if initializing else 1,cv2.GC_INIT_WITH_MASK)
        except cv2.error:
            return None
        binary=np.uint8((m==cv2.GC_FGD)|(m==cv2.GC_PR_FGD))*255
        binary=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
        binary=component_with_anchor(binary,self.anchor)
        if cv2.countNonZero(binary)<max(70,int(self.total_pixels*.005)):
            return None
        self._candidate_models=(bg,fg)
        return binary

    def read(self,current_bgr,elapsed_min=None):
        current=self._crop(current_bgr)
        pgray=cv2.GaussianBlur(cv2.cvtColor(self.last_image,cv2.COLOR_BGR2GRAY),(5,5),0)
        gray=cv2.GaussianBlur(cv2.cvtColor(current,cv2.COLOR_BGR2GRAY),(5,5),0)
        diff=cv2.absdiff(gray,pgray)
        mad=float(np.mean(diff))
        changed=float(100*np.count_nonzero(diff>10)/diff.size)
        candidate=self._refine(current,self.prev)
        if candidate is None:
            return self._row('SEGMENTATION_FAILED',mad,changed,0.,0.,0.)
        cand_area=cv2.countNonZero(candidate)
        step_pct=100*(cand_area/max(1,self.area)-1.)
        XOR=np.uint8((candidate>0)!=(self.prev>0))*255
        changed_area=cv2.countNonZero(XOR)
        xor_pct=float(100*changed_area/self.total_pixels)
        # If the candidate added/removes pixels, their appearance should have
        # changed too. The blurred diff suppresses noise/compression artifacts.
        support=float(100*np.count_nonzero((diff>7)&(XOR>0))/max(1,changed_area))
        outside=int(np.count_nonzero(candidate[:2,:]))+int(np.count_nonzero(candidate[-2:,:]))
        overfill=(cand_area/self.total_pixels)>.87
        severe=(abs(step_pct)>15 and mad<2.5) or (abs(step_pct)>5 and mad<1.5 and changed<1.)
        unsupported=((abs(step_pct)>2.5 and changed_area>250 and support<8.0 and mad<3.0)
                     or (changed_area>=max(45,int(self.total_pixels*.001)) and support<5.0 and mad<1.2))
        # Photographic evidence can allow a real larger step. Conversely,
        # a dramatic change in lighting invalidates the assumption of continuity.
        if mad>25. or changed>55.:
            status='SCENE_CHANGE_REVIEW'
        elif overfill or outside:
            status='ROI_BOUNDARY_REVIEW'
        elif severe or unsupported:
            status='HELD_UNSUPPORTED_BOUNDARY_CHANGE'
        else:
            status='ACCEPTED'
        if status=='ACCEPTED':
            self.prev=candidate
            self.area=cand_area
            self.last_image=current
            if hasattr(self,'_candidate_models'):
                self.bg,self.fg=self._candidate_models
        self.last_status=status
        return self._row(status,mad,changed,step_pct,xor_pct,support)

    def _row(self,status,mad,changed,step,xor,support):
        return {'estimated_area_px':int(round(self.area/(self.scale*self.scale))),
                'estimated_growth_pct':round(100*(self.area/self.baseline-1.),3),
                'projected_step_pct':round(step,3),
                'change_mean_gray':round(mad,3),
                'changed_pct_gt10':round(changed,4),
                'mask_xor_pct':round(xor,4),
                'edge_support_pct':round(support,2),
                'status':status}

    def overlay(self,frame):
        out=frame.copy();x1,y1,x2,y2=self.roi
        resized=cv2.resize(self.prev,(x2-x1,y2-y1),interpolation=cv2.INTER_NEAREST)
        patch=out[y1:y2,x1:x2]
        tint=patch.copy();tint[resized>0]=(45,195,115)
        patch[resized>0]=cv2.addWeighted(patch,.65,tint,.35,0)[resized>0]
        contours,_=cv2.findContours(resized,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(patch,contours,-1,(65,245,145),2)
        cv2.rectangle(out,(x1,y1),(x2,y2),(0,230,250),2)
        return out


def load_rows(base,run):
    path=base/'data'/'doughwatch.sqlite'
    # SQLite URI in read-only mode, never opening WAL checkpoint or changing data.
    uri=f'file:{path.resolve()}?mode=ro'
    with sqlite3.connect(uri,uri=True,timeout=4) as db:
        db.execute('PRAGMA query_only=ON')
        return db.execute('''SELECT recorded_utc,elapsed_min,area_px,area_gain_pct,quality,image_file
                             FROM area_readings WHERE run_id=? ORDER BY elapsed_min,recorded_utc''',(run,)).fetchall()


def config_from_path(path):
    config=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(config.get('roi'),list) or len(config['roi'])!=4:
        raise ValueError('Calibration must contain 4-element ROI')
    if not isinstance(config.get('points'),list) or len(config['points'])<6:
        raise ValueError('Calibration must contain at least 6 polygon points')
    return config


def resolve_run_from_status(url):
    with urlopen(url,timeout=4) as response:status=json.load(response)
    if not status.get('run_id') or not status.get('roi'):
        raise RuntimeError('No active run in source v0.2 status')
    return status['run_id'],[int(v) for v in status['roi']]


def write_csv_atomic(dst,rows):
    dst.parent.mkdir(parents=True,exist_ok=True)
    tmp=dst.with_suffix('.csv.tmp')
    with tmp.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=CSV_FIELDS);w.writeheader();w.writerows(rows)
    os.replace(tmp,dst)


def process_archive(base,out,config,run_id,max_frames=0,thumbnail=True):
    images=base/'data'/'frames_v02'
    rows=load_rows(base,run_id)
    if max_frames: rows=rows[:max_frames]
    if not rows:raise RuntimeError('No rows found for run')
    tracker=None;output=[];skipped=0
    for i,(date,minute,area,gain,quality,filename) in enumerate(rows):
        if not filename or Path(filename).name!=filename:skipped+=1;continue
        jpg=images/filename
        frame=cv2.imread(str(jpg),cv2.IMREAD_COLOR)
        if frame is None:skipped+=1;continue
        if tracker is None:
            tracker=StableTracker(config['roi'],config['points'],frame)
            result=tracker._row('BASELINE_PROVISIONAL',0.,0.,0.,0.,0.)
            if area is not None:
                drift=abs((tracker.baseline/(tracker.scale*tracker.scale))/float(area)-1)
                if drift>0.20:
                    raise ValueError(f'Initial reconstructed mask differs from v0.2 area by {drift:.1%}. Review calibration.')
        else:
            result=tracker.read(frame,float(minute))
        rec=dict(run_id=run_id,recorded_utc=date,elapsed_min=round(float(minute),3),
                 source_area_px=area,source_growth_pct=gain,image_file=filename,**result)
        output.append(rec)
        if thumbnail and (i==0 or i==len(rows)-1):
            cv2.imwrite(str(out / f'{run_id}_view_{"first" if i==0 else "last"}.jpg'),tracker.overlay(frame),
                        [cv2.IMWRITE_JPEG_QUALITY,86])
    if not output:raise RuntimeError('No readable JPEG frames in selected run')
    csvpath=out/f'{run_id}_stable_comparison.csv'
    write_csv_atomic(csvpath,output)
    return output,csvpath,skipped


def main(argv=None):
    parser=argparse.ArgumentParser(description='DoughWatch read-only independent stabilized mask study')
    parser.add_argument('--base',type=Path,required=True,help='Directory containing archived DoughWatch data')
    parser.add_argument('--output',type=Path,required=True,help='Separate directory for research reports')
    parser.add_argument(
        '--config',
        type=Path,
        required=True,
        help='Calibration JSON matching the selected experiment and ROI'
    )
    parser.add_argument('--run-id',default=None)
    parser.add_argument('--status-url',default='http://127.0.0.1:8091/api/status')
    parser.add_argument('--max-frames',type=int,default=0)
    args=parser.parse_args(argv)
    config=config_from_path(args.config)
    if args.run_id:
        run=args.run_id; roi=config['roi']
    else:
        run,roi=resolve_run_from_status(args.status_url)
    if config.get('run_id')!=run:
        raise RuntimeError(f'Calibration is only for run {config.get("run_id")}, current run is {run}. No changes made.')
    if tuple(roi)!=tuple(config['roi']):
        raise RuntimeError('Current ROI differs from archived calibration; aborting')
    args.output.mkdir(parents=True,exist_ok=True)
    result,path,skipped=process_archive(args.base,args.output,config,run,args.max_frames)
    print(f'DoughWatch v0.2.1 independent tracker — read-only | run {run}')
    print(f'Processed {len(result)} original frames, skipped {skipped}; latest: {result[-1]["status"]}')
    print(f'Last independent projected area change: {result[-1]["estimated_growth_pct"]}% (PROVISIONAL)')
    print(f'Quarantined mask updates: {sum(r["status"]=="HELD_UNSUPPORTED_BOUNDARY_CHANGE" for r in result)}')
    print(f'Comparison: {path}')
    print('No peak alerts; v0.2 and its database unchanged.')
    return 0


if __name__=='__main__':raise SystemExit(main())
