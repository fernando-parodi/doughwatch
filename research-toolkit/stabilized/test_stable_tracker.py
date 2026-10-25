# SPDX-FileCopyrightText: 2026 Fernando Parodi
# SPDX-License-Identifier: GPL-3.0-only

import json
import unittest
from pathlib import Path

import cv2
import numpy as np
from stable_tracker import StableTracker,polygon_mask,config_from_path

class MaskTests(unittest.TestCase):
    def setUp(self):
        self.roi=(20,10,320,210)
        self.poly=[(85,114),(96,90),(145,72),(190,73),(230,92),(235,117),(213,146),(149,156),(99,141)]

    def test_roi_polygon_shape(self):
        mask=polygon_mask(self.roi,self.poly)
        self.assertEqual(mask.shape,(100,150))
        self.assertGreater(cv2.countNonZero(mask),400)

    def test_identical_raw_photo_cannot_grow(self):
        frame=self.synthetic(0)
        t=StableTracker(self.roi,self.poly,frame)
        baseline=t.area
        for _ in range(3):
            rec=t.read(frame)
            self.assertEqual(t.area,baseline)
            self.assertAlmostEqual(rec['estimated_growth_pct'],0.)

    def test_real_mask_growth_with_image_evidence_is_accepted(self):
        t=StableTracker(self.roi,self.poly,self.synthetic(0))
        start=t.area
        record=t.read(self.synthetic(5))
        self.assertEqual(record['status'],'ACCEPTED')
        self.assertGreater(t.area,start)
        self.assertGreater(record['edge_support_pct'],10.)

    def test_real_movement_not_indistinguishable_from_static_photo(self):
        a=self.synthetic(0)
        b=self.synthetic(5)
        roi=(20,10,320,210)
        x1,y1,x2,y2=roi
        diff=cv2.absdiff(cv2.cvtColor(a[y1:y2,x1:x2],cv2.COLOR_BGR2GRAY),
                        cv2.cvtColor(b[y1:y2,x1:x2],cv2.COLOR_BGR2GRAY))
        self.assertGreater(np.count_nonzero(diff>10),300)
        self.assertGreater(float(np.mean(diff)),1.)

    @staticmethod
    def synthetic(grow):
        f=np.zeros((235,345,3),np.uint8);f[:]=(65,65,65)
        cv2.ellipse(f,(160,115),(75+grow,40+grow),0,0,360,(195,205,220),-1)
        return f

    def test_guard_rejects_fake_mask_expansion_in_unchanged_image(self):
        frame=self.synthetic(0)
        t=StableTracker(self.roi,self.poly,frame)
        baseline=t.area
        original=t._refine
        def fabricated_candidate(current,previous,initializing=False):
            bigger=cv2.dilate(previous,np.ones((17,17),np.uint8))
            return bigger
        t._refine=fabricated_candidate
        row=t.read(frame)
        self.assertEqual(row['status'],'HELD_UNSUPPORTED_BOUNDARY_CHANGE')
        self.assertEqual(t.area,baseline)
        t._refine=original

    def test_config_for_public_example(self):
        p=Path(__file__).with_name('calibration_example.json')
        conf=config_from_path(p)
        self.assertEqual(conf['run_id'],'synthetic_example')
        self.assertEqual(conf['roi'],[20,10,320,210])

if __name__=='__main__': unittest.main(verbosity=2)
