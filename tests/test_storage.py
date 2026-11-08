import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from ustc_bot.storage import trim_history, cleanup_round, storage_settings


class StorageTests(unittest.TestCase):
    def test_history_prunes_by_age_and_count(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.jsonl'
            now = datetime.now(timezone.utc)
            records = [{'报告名称': 'old', '选课时间': (now - timedelta(days=400)).isoformat()}]
            records.extend({'报告名称': str(n), '选课时间': now.isoformat()} for n in range(4))
            path.write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')
            trim_history(path, 2, 180)
            kept = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
            self.assertEqual([row['报告名称'] for row in kept], ['2', '3'])

    def test_cleanup_preserves_credentials_session_and_failed_diagnostic(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('credentials.json', 'config.json', 'grid_structure.json', 'enrollment_results.json'):
                (root / name).write_text('{}', encoding='utf-8')
            cleanup_round(root, {}, completed=False)
            self.assertTrue((root / 'grid_structure.json').exists())
            cleanup_round(root, {}, completed=True)
            self.assertFalse((root / 'grid_structure.json').exists())
            self.assertTrue((root / 'credentials.json').exists())
            self.assertTrue((root / 'enrollment_results.json').exists())

    def test_browser_clear_only_targets_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            context = MagicMock()
            context.pages = [MagicMock()]
            cleanup_round(folder, {}, context)
            context.new_cdp_session.return_value.send.assert_called_once_with('Network.clearBrowserCache')
            context.new_cdp_session.return_value.detach.assert_called_once()

    def test_invalid_limits_rejected(self):
        with self.assertRaises(ValueError):
            storage_settings({'storage': {'history_max_records': 0}})
