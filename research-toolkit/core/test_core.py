# SPDX-FileCopyrightText: 2026 Fernando Parodi
# SPDX-License-Identifier: GPL-3.0-only

"""Run: /usr/bin/python3 test_core.py (with OpenCV/Numpy installed)."""
from doughwatch_core import DoughMaskTracker, analyze_trend, DEFAULT_SETTINGS
import cv2
import numpy as np


def synthetic_frame(radius):
    image=np.full((720,1280,3),(65,73,81),dtype=np.uint8)
    cv2.ellipse(image,(500,430),(250,radius),0,0,360,(205,218,225),-1)
    cv2.line(image,(450,80),(520,340),(240,245,255),8)
    return image


def test_area():
    pts=[(250,430),(270,370),(310,330),(450,300),(610,330),
         (740,370),(750,440),(650,515),(370,515)]
    tracker=DoughMaskTracker((200,100,900,600),pts,synthetic_frame(110))
    areas=[]
    for radius in [110,112,118,125,140,135,125]:
        value,q=tracker.read(synthetic_frame(radius))
        assert q=='OK',(radius,q)
        areas.append(value['area_px'])
    assert areas[0]<areas[1]<areas[2]<areas[3]<areas[4]
    assert areas[4]>areas[5]>areas[6]
    print('Area tracking: OK, growth and decline recognized')


def test_trend():
    rows=[]
    states={}
    for minute in range(111):
        if minute<25: gain=0.0
        elif minute<55:gain=(minute-25)*.6
        elif minute<74:gain=18.
        else:gain=18.-(minute-74)*.15
        rows.append({'minute':minute,'gain':gain})
        if minute in (20,50,70,80,100):
            states[minute]=analyze_trend(rows,DEFAULT_SETTINGS)['state']
    print('Trend transitions:',states)
    assert states[20]=='INITIAL_LAG'
    assert states[50]=='GROWING'
    assert states[70]=='PLATEAU_AFTER_RISE'
    assert states[100]=='PEAK_PASSED_REVIEW_NOW'


def test_low_activity():
    vals=[{'minute':i,'gain':i*.005} for i in range(101)]
    assert analyze_trend(vals,DEFAULT_SETTINGS)['state']=='LOW_ACTIVITY_CHECK'
    print('Low activity after grace: OK')


def test_no_early_false_peak():
    vals=[]
    for i in range(76):
        gain=(i*.4 if i<=60 else 24-(i-60)*.3)
        vals.append({'minute':i,'gain':gain})
    assert analyze_trend(vals,DEFAULT_SETTINGS)['state']!='PEAK_PASSED_REVIEW_NOW'
    print('No peak alert without prior dwell: OK')


if __name__=='__main__':
    test_area();test_trend();test_low_activity();test_no_early_false_peak()
