"""DOM integration checks; requires `python -m playwright install chromium`."""
import unittest
from unittest.mock import patch
from playwright.sync_api import sync_playwright
import main


class GridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch(headless=True)
        except Exception:
            cls.pw.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def test_div_grid_filters_full_reports(self):
        page = self.browser.new_page()
        try:
            page.set_content('''<div role="grid">
                <div role="columnheader">操作</div><div role="columnheader">报告题目（中文）</div>
                <div role="columnheader">地点</div><div role="columnheader">容量/已选</div>
                <div role="row"><div role="gridcell"><a>选课</a></div>
                <div role="gridcell">报告A</div><div role="gridcell">高新校区</div><div role="gridcell">20 / 19</div></div>
                <div role="row"><div role="gridcell"><a>选课</a></div>
                <div role="gridcell">报告B</div><div role="gridcell">高新校区</div><div role="gridcell">20 / 20</div></div></div>''')
            with patch.object(main, 'CFG', {'keyword': '高新'}):
                rows = main.parse_rows(page)
            self.assertEqual([row[0] for row in rows], ['报告A'])
        finally:
            page.close()

    def test_table_sizing_row_before_header(self):
        page = self.browser.new_page()
        try:
            page.set_content('''<table><tr><td></td></tr><tr><th>操作</th><th>报告题目（中文）</th>
                <th>地点</th><th>容量/已选</th></tr><tr><td><a>选课</a></td>
                <td>报告C</td><td>高新校区</td><td>10 / 1</td></tr></table>''')
            with patch.object(main, 'CFG', {'keyword': '高新'}):
                self.assertEqual(main.parse_rows(page)[0][0], '报告C')
        finally:
            page.close()
