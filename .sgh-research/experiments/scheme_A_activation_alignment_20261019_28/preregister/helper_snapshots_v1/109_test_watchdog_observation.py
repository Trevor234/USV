import unittest
from run_no_output_calibration import watchdog_observation as observe
class WatchdogObservationRisks(unittest.TestCase):
    def test_equality_is_not_expiry_and_external_expiry_needs_regulator(self):
        self.assertEqual(observe(100,1100,"",0,1000,220),("idle",None))
        self.assertEqual(observe(100,1101,"",0,1000,220),("pending",1101))
    def test_delayed_regulator_confirmation_is_in_finite_observation_window(self):
        self.assertEqual(observe(100,1121,"worker_unusable",1120,1000,220,1101),("confirmed",1101))
    def test_stale_or_future_decision_cannot_confirm_watchdog(self):
        for stamp in (1099,1122):self.assertEqual(observe(100,1121,"worker_unusable",stamp,1000,220,1101),("pending",1101))
    def test_confirmation_deadline_is_inclusive_and_overdue_fails(self):
        self.assertEqual(observe(100,1321,"worker_unusable",1321,1000,220,1101),("confirmed",1101))
        self.assertEqual(observe(100,1322,"worker_unusable",1322,1000,220,1101),("timeout",1101))
if __name__=="__main__":unittest.main()
