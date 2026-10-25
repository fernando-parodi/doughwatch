# SPDX-FileCopyrightText: 2026 Fernando Parodi
# SPDX-License-Identifier: GPL-3.0-only

import unittest
import numpy as np
from doughwatch_v021_sidecar import Guard, assess_transition


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.roi=(10,10,110,110)
        self.image=np.zeros((120,120,3),dtype=np.uint8)
        self.image[30:85,30:90,:]=180

    def test_13percent_jump_in_identical_images(self):
        a=assess_transition(self.image,self.image,self.roi,1.59,14.75,1.0)
        self.assertEqual(a['quality'],'MASK_JUMP_WITH_STABLE_IMAGE')

    def test_small_noise_is_accepted(self):
        alt=self.image.copy()
        alt[35:55,35:55]=190
        a=assess_transition(self.image,alt,self.roi,0.0,.4,1)
        self.assertEqual(a['quality'],'OK')

    def test_guard_does_not_accept_later_contaminated_epoch(self):
        g=Guard(self.roi)
        items=[('r','t0',0,49635,0,'OK','a.jpg'),('r','t1',1,50000,0.75,'OK','b.jpg'),
               ('r','t2',2,56638,14.12,'OK','c.jpg'),('r','t3',3,57000,14.86,'OK','d.jpg')]
        for row in items:g.push(row,self.image)
        self.assertEqual(g.rows[2]['sidecar_quality'],'MASK_JUMP_WITH_STABLE_IMAGE')
        self.assertEqual(g.rows[3]['sidecar_state'],'REVIEW_REQUIRED_NO_PEAK_ALERT')
        self.assertIsNone(g.rows[3]['accepted_area_gain_pct'])


if __name__=='__main__':unittest.main(verbosity=2)
