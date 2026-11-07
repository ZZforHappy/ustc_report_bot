import json
import tempfile
import unittest
from pathlib import Path
from ustc_bot.history import append_success


class HistoryTests(unittest.TestCase):
    def test_history_appends_without_overwriting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '选课日志.jsonl'
            append_success(path, '报告甲', '高新校区', '2026-11-08 15:00', '2026-11-07T20:00:00+08:00')
            append_success(path, '报告乙', '西区', '未提供', '2026-11-07T20:01:00+08:00')
            records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]['报告名称'], '报告甲')
            self.assertEqual(records[0]['报告时间'], '2026-11-08 15:00')
            self.assertEqual(records[0]['地点'], '高新校区')
            self.assertEqual(records[0]['选课时间'], '2026-11-07T20:00:00+08:00')
            self.assertTrue(records[0]['核验时间'].endswith('+08:00'))
