import unittest
from unittest.mock import MagicMock, patch
from ustc_bot import app as main


class SingleEnrollmentTests(unittest.TestCase):
    def test_student_scope_rejection_is_closed(self):
        frame, dialog, confirm = MagicMock(), MagicMock(), MagicMock()
        frame.page = None
        frame.locator.return_value.all.return_value = [dialog]
        dialog.is_visible.return_value = True
        dialog.inner_text.return_value = '提示\n您不在可选学生范围内，如需旁听，可联系发布院系教学秘书。\n确定'
        dialog.get_by_role.return_value.all.return_value = [confirm]
        confirm.is_visible.return_value = True
        self.assertEqual(main.handle_enrollment_dialogs(frame), 'rejected')
        confirm.click.assert_called_once_with(timeout=5000)
        confirm.wait_for.assert_called_once_with(state='hidden', timeout=5000)

    def test_zero_sized_modal_container_is_still_handled(self):
        frame, dialog, confirm = MagicMock(), MagicMock(), MagicMock()
        frame.page = None
        frame.locator.return_value.all.return_value = [dialog]
        dialog.is_visible.return_value = False
        dialog.locator.return_value.all.return_value = [confirm]
        dialog.get_by_role.return_value.all.return_value = [confirm]
        confirm.is_visible.return_value = True
        dialog.inner_text.return_value = '提示 您不在可选学生范围内 确定'
        self.assertEqual(main.handle_enrollment_dialogs(frame), 'rejected')
        confirm.click.assert_called_once()

    @patch.object(main, 'handle_enrollment_dialogs', return_value='none')
    @patch.object(main, 'find_table')
    @patch.object(main, 'next_page', return_value=True)
    def test_final_verification_never_exceeds_page_limit(self, next_page, grid, dialogs):
        grid.return_value.get_by_text.return_value.count.return_value = 0
        with patch.object(main, 'FILTERS', {'最多遍历页数': 2}):
            self.assertEqual(main.verify_batch(MagicMock(), [('不存在的报告', '地点')]), [])
        self.assertEqual(grid.call_count, 2)
        self.assertEqual(next_page.call_count, 2)  # reset to page 1, then page 2

    @patch('builtins.input', return_value='')
    @patch.object(main, 'notify')
    @patch.object(main, 'verify_batch', return_value=[])
    @patch.object(main, 'submit_batch_report', return_value='pending')
    @patch.object(main, 'parse_rows')
    @patch.object(main, 'next_page', return_value=False)
    @patch.object(main, 'open_report_page')
    def test_batch_submits_current_page_before_verifying_once(self, open_page, next_page, rows, submit, verify, notify, user_input):
        a, b = MagicMock(), MagicMock()
        a.get_attribute.return_value = 'a'
        b.get_attribute.return_value = 'b'
        rows.side_effect = [[('A', '地点', a), ('B', '地点', b)], [('B', '地点', b)], []]
        with patch.object(main.Path, 'write_text'):
            main.batch_enrollment(MagicMock())
        self.assertEqual(submit.call_count, 2)
        verify.assert_called_once_with(open_page.return_value, [('A', '地点'), ('B', '地点')])

    def test_clicks_pinned_copy_for_same_report(self):
        grid, original, pinned = MagicMock(), MagicMock(), MagicMock()
        original.get_attribute.return_value = 'report-123'
        grid.locator.return_value.all.return_value = [pinned]
        pinned.is_visible.return_value = True
        self.assertIs(main.enrollment_button(grid, original), pinned)
        grid.locator.assert_called_once_with('table[id^="pinnedtable"] a[data-bgbm="report-123"]')

    def test_uses_original_without_pinned_copy(self):
        grid, original = MagicMock(), MagicMock()
        original.get_attribute.return_value = 'report-123'
        grid.locator.return_value.all.return_value = []
        self.assertIs(main.enrollment_button(grid, original), original)

    @patch.object(main, 'pagination_state', side_effect=[(1, 20, 2313), (21, 40, 2313)])
    @patch.object(main, 'find_table')
    @patch.object(main, 'visible_first')
    def test_jump_from_page_one_to_two(self, visible, table, state):
        page, jump = MagicMock(), MagicMock()
        jump.input_value.return_value = '1'
        visible.return_value = jump
        table.return_value.inner_text.side_effect = ['page one rows', 'page two rows']
        self.assertTrue(main.next_page(page))
        jump.fill.assert_called_once_with('2')
        jump.press.assert_called_once_with('Enter')

    @patch.object(main, 'pagination_state', return_value=(1, 20, 2313))
    @patch.object(main, 'find_table')
    @patch.object(main, 'visible_first')
    def test_jump_without_data_update_is_an_error(self, visible, table, state):
        jump = MagicMock()
        jump.input_value.return_value = '1'
        visible.return_value = jump
        table.return_value.inner_text.return_value = 'unchanged rows'
        with self.assertRaisesRegex(RuntimeError, '没有更新'):
            main.next_page(MagicMock())

    @patch('builtins.input', return_value='')
    @patch.object(main, 'notify')
    @patch.object(main, 'monitor', return_value=True)
    @patch.object(main, 'open_report_page')
    def test_success_runs_only_one_scan(self, open_page, monitor, notify, user_input):
        main.test_enrollment(MagicMock())
        monitor.assert_called_once_with(open_page.return_value)

    @patch('builtins.input', return_value='')
    @patch.object(main, 'notify')
    @patch.object(main, 'monitor', side_effect=RuntimeError('Unconfirmed result'))
    @patch.object(main, 'open_report_page')
    def test_uncertain_result_is_never_retried(self, open_page, monitor, notify, user_input):
        main.test_enrollment(MagicMock())
        monitor.assert_called_once()
