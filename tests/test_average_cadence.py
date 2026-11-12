import unittest
from core import AverageDisplayCadence

class TestAverageDisplayCadence(unittest.TestCase):
    def test_average_is_frozen_between_one_second_ticks(self):
        gate=AverageDisplayCadence()
        self.assertEqual(gate.display(7, 33.33, now=100.0),33.33)
        self.assertEqual(gate.display(7, 37.5, now=100.5),33.33)
        self.assertEqual(gate.display(7, 40.0, now=100.999),33.33)
        self.assertEqual(gate.display(7, 40.0, now=101.0),40.0)
        self.assertEqual(gate.display(7, 42.0, now=101.01),40.0)
        self.assertEqual(gate.display(7, 35.0, now=102.01),35.0)

    def test_process_switch_and_disconnection_reset_immediately(self):
        gate=AverageDisplayCadence()
        self.assertEqual(gate.display(10,33.0,now=1.0),33.0)
        self.assertEqual(gate.display(20,34.0,now=1.2),34.0)
        self.assertIsNone(gate.display(None,None,now=1.4))
        self.assertEqual(gate.display(10,31.0,now=1.5),31.0)
