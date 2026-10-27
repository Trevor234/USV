import unittest
from unittest.mock import Mock,patch
from p1_live_loss_cleanup import ObservingSupervisor

class CleanupObservation(unittest.TestCase):
    def setUp(self):
        self.s=object.__new__(ObservingSupervisor)
        self.s.observer_errors=[];self.s.observer_pump=Mock();self.s.event=Mock()
        self.s.members=Mock();self.item=Mock()
    def test_empty_does_not_pump(self):
        self.s.members.return_value=[]
        self.assertTrue(self.s.wait_empty(self.item,1))
        self.s.observer_pump.assert_not_called()
    def test_live_group_drains_until_reaped(self):
        self.s.members.side_effect=[[{'pid':7}],[]]
        self.assertTrue(self.s.wait_empty(self.item,1))
        self.s.observer_pump.assert_called_once()
        self.assertEqual(self.item.process.poll.call_count,2)
    def test_zero_bound_retains_live_group(self):
        self.s.members.return_value=[{'pid':7}]
        self.assertFalse(self.s.wait_empty(self.item,0))
        self.s.observer_pump.assert_not_called()
    def test_error_recorded_cleanup_continues(self):
        self.s.members.side_effect=[[{'pid':7}],[]]
        self.s.observer_pump.side_effect=RuntimeError('lost observer')
        with patch('p1_live_loss_cleanup.time.sleep'):
            self.assertTrue(self.s.wait_empty(self.item,1))
        self.assertEqual(len(self.s.observer_errors),1)
        self.s.event.assert_called_once()
        self.assertEqual(self.item.process.poll.call_count,2)
    def test_nonfinite_bound_rejected(self):
        with self.assertRaises(ValueError):self.s.wait_empty(self.item,float('inf'))

if __name__=='__main__':unittest.main()
