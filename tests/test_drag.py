"""Desktop drag region and controls regression tests."""
import unittest
from core import brand_drag_hit

class TestDragTarget(unittest.TestCase):
    def test_left_mouse_down_on_zeitop_brand_may_start_native_move(self):
        for xy in [(49,19),(70,24),(100,31)]:
            with self.subTest(xy=xy):
                self.assertTrue(brand_drag_hit(*xy, button=1))
    def test_only_brand_and_only_left_button(self):
        for x,y,button in [(70,24,2),(70,24,3),(7,8,1),(200,30,1),
                           (380,24,1),(70,65,1),(-1,20,1)]:
            with self.subTest(x=x,y=y,button=button):
                self.assertFalse(brand_drag_hit(x,y,button=button))
