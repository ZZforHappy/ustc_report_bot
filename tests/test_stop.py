import unittest
from unittest.mock import patch
from ustc_bot import app as main


class StopTests(unittest.TestCase):
    def tearDown(self):
        main.STOP_EVENT.clear()

    def test_enter_requests_stop(self):
        with patch('builtins.input', return_value=''):
            main.listen_for_enter()
        with self.assertRaises(main.StopRequested):
            main.check_stop()

    def test_closed_stdin_does_not_stop_automatically(self):
        main.STOP_EVENT.clear()
        with patch('builtins.input', side_effect=EOFError):
            main.listen_for_enter()
        self.assertFalse(main.STOP_EVENT.is_set())

    def test_stop_prevents_new_submission(self):
        from unittest.mock import MagicMock
        frame, button = MagicMock(), MagicMock()
        main.STOP_EVENT.set()
        with self.assertRaises(main.StopRequested):
            main.submit_batch_report(frame, button)
        button.click.assert_not_called()
