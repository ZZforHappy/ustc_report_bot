import logging
import unittest
from ustc_bot.logging_setup import ConsoleFilter, ConsoleFormatter


class ConsoleTests(unittest.TestCase):
    def record(self, level=logging.INFO, important=False):
        record = logging.LogRecord('ustc', level, '', 0, 'example', (), None)
        record.console = important
        return record

    def test_summary_hides_progress_but_preserves_important_events(self):
        filter_ = ConsoleFilter('summary')
        self.assertFalse(filter_.filter(self.record()))
        self.assertTrue(filter_.filter(self.record(important=True)))
        self.assertTrue(filter_.filter(self.record(logging.ERROR)))

    def test_verbose_preserves_progress(self):
        self.assertTrue(ConsoleFilter('verbose').filter(self.record()))

    def test_console_omits_traceback_without_mutating_file_record(self):
        try:
            raise ValueError('test error')
        except ValueError:
            import sys
            record = self.record(logging.ERROR)
            record.exc_info = sys.exc_info()
        text = ConsoleFormatter('%(message)s').format(record)
        self.assertNotIn('Traceback', text)
        self.assertIsNotNone(record.exc_info)
