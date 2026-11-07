import unittest
from unittest.mock import MagicMock, patch
import main


class SchedulerTests(unittest.TestCase):
    @patch.object(main, 'notify')
    @patch.object(main, 'batch_enrollment')
    def test_unconfirmed_result_stops_without_retry(self, batch, notify):
        batch.return_value = {'scan_completed': True, 'unconfirmed_count': 1}
        with patch.object(main, 'CFG', {'interval_seconds': 600}):
            main.scheduled_monitor(MagicMock())
        batch.assert_called_once()
        self.assertFalse(batch.call_args.kwargs['interactive'])

    @patch.object(main, 'notify')
    @patch.object(main.time, 'monotonic', side_effect=[0, 600])
    @patch.object(main, 'batch_enrollment', side_effect=[
        {'scan_completed': True, 'unconfirmed_count': 0},
        {'scan_completed': False, 'unconfirmed_count': 0}])
    def test_next_round_runs_after_interval(self, batch, clock, notify):
        with patch.object(main, 'CFG', {'interval_seconds': 600}):
            main.scheduled_monitor(MagicMock())
        self.assertEqual(batch.call_count, 2)

    def test_invalid_interval(self):
        with patch.object(main, 'CFG', {'interval_seconds': 0}):
            with self.assertRaises(ValueError):
                main.scheduled_monitor(MagicMock())
