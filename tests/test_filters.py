import json
import tempfile
import unittest
from pathlib import Path
from report_filters import load_filters, matches_report


class FilterTests(unittest.TestCase):
    def test_excluded_departments(self):
        rules = self.rules(排除院系关键词=['生命科学', '微电子'])
        self.assertFalse(matches_report({'院系': '生命科学学院', '报告题目': '报告'}, rules))
        self.assertFalse(matches_report({'院系': '微电子学院', '报告题目': '报告'}, rules))
        self.assertTrue(matches_report({'院系': '计算机学院', '报告题目': '报告'}, rules))
        with self.assertRaises(ValueError):
            matches_report({'报告题目': '报告'}, rules)

    def test_excluded_department_takes_priority_over_inclusion(self):
        rules = self.rules(院系='学院', 排除院系关键词=['生命科学'])
        self.assertFalse(matches_report({'院系': '生命科学学院', '报告题目': '报告'}, rules))
        self.assertTrue(matches_report({'报告题目': '报告'}, self.rules(排除院系关键词=[])))
        with self.assertRaises(ValueError):
            self.rules(排除院系关键词='生命科学')

    def test_page_limit(self):
        self.assertEqual(self.rules()['最多遍历页数'], 3)
        self.assertEqual(self.rules(最多遍历页数=5)['最多遍历页数'], 5)
        for invalid in (0, -1, True, '3', 1.5):
            with self.assertRaises(ValueError):
                self.rules(最多遍历页数=invalid)

    def rules(self, **values):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'rules.json'
            path.write_text(json.dumps(values), encoding='utf-8')
            return load_filters(path)

    def test_location_and_any(self):
        report = {'地点': '高新校区图书馆', '报告题目': '学术报告'}
        self.assertTrue(matches_report(report, self.rules(地点='高新')))
        self.assertFalse(matches_report(report, self.rules(地点='西区')))
        self.assertTrue(matches_report(report, self.rules(地点='任意')))

    def test_or_within_field_and_across_fields(self):
        rules = self.rules(地点=['高新', '西区'], 报告题目='AI')
        self.assertTrue(matches_report({'地点': '西区', '报告题目': 'ai 进展'}, rules))
        self.assertFalse(matches_report({'地点': '西区', '报告题目': '材料进展'}, rules))

    def test_exclusions_and_missing_restricted_column(self):
        self.assertFalse(matches_report({'报告题目': '报告作业提交'}, self.rules()))
        with self.assertRaises(ValueError):
            matches_report({'报告题目': '报告'}, self.rules(院系='计算机'))

    def test_typo_and_mixed_any_fail(self):
        with self.assertRaises(ValueError):
            self.rules(地店='高新')
        with self.assertRaises(ValueError):
            self.rules(地点=['任意', '高新'])
