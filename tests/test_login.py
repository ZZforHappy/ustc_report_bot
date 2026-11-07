import unittest
from unittest.mock import MagicMock, patch

from ustc_bot import app as main


class LoginTests(unittest.TestCase):
    def setUp(self):
        credentials = patch.object(main, 'load_credentials', return_value={'student_id': 'TEST', 'password': 'test-only'})
        self.credentials = credentials.start()
        self.addCleanup(credentials.stop)

    @patch.object(main.time, 'sleep')
    @patch.object(main, 'portal_ready', side_effect=[False, True])
    def test_manual_login_is_detected_without_terminal_input(self, ready, sleep):
        page = MagicMock()
        page.is_closed.return_value = False
        with patch.object(main, 'CFG', {'login': {}}):
            self.assertIs(main.wait_for_manual_login(MagicMock(pages=[page])), page)

    @patch.object(main.time, 'sleep')
    @patch.object(main, 'portal_ready', side_effect=[False, True])
    def test_click_timeout_still_checks_successful_navigation(self, ready, sleep):
        page, username, password, button = self.auth_page()
        button.first.click.side_effect = main.PWTimeout('navigation timeout')
        with patch.object(main, 'login_fields', return_value=(page, username, password)), patch.object(main, 'CFG', {'login': {}}):
            self.assertIs(main.ensure_login(MagicMock(pages=[page])), page)
        button.first.click.assert_called_once()

    def test_credentials_only_allowed_on_exact_https_origins(self):
        for url in ('https://id.ustc.edu.cn/login', 'https://passport.ustc.edu.cn/login'):
            self.assertTrue(main.trusted_auth_url(url))
        for url in ('http://id.ustc.edu.cn/login', 'https://id.ustc.edu.cn.evil.test/',
                    'https://evil.test/', 'https://id.ustc.edu.cn:444/login'):
            self.assertFalse(main.trusted_auth_url(url))

    @patch.object(main, 'portal_ready', return_value=True)
    def test_existing_session_does_not_require_or_fill_credentials(self, ready):
        page = MagicMock()
        page.is_closed.return_value = False
        context = MagicMock(pages=[page])
        with patch.object(main, 'CFG', {}):
            self.assertIs(main.ensure_login(context), page)
        page.get_by_placeholder.assert_not_called()
        page.get_by_role.assert_not_called()
        self.credentials.assert_not_called()

    def auth_page(self):
        page = MagicMock()
        page.url = 'https://id.ustc.edu.cn/login'
        page.is_closed.return_value = False
        username, password, button = MagicMock(), MagicMock(), MagicMock()
        page.get_by_placeholder.side_effect = [username, password]
        page.get_by_role.return_value = button
        button.all.return_value = [button.first]
        return page, username, password, button

    @patch.object(main.time, 'sleep')
    @patch.object(main, 'portal_ready', side_effect=[False, True])
    def test_fill_submit_then_verify_portal(self, ready, sleep):
        page, username, password, button = self.auth_page()
        context = MagicMock(pages=[page])
        with patch.object(main, 'login_fields', return_value=(page, username, password)), patch.object(main, 'CFG', {'login': {}}):
            self.assertIs(main.ensure_login(context), page)
        username.fill.assert_called_once_with('TEST', timeout=5000)
        password.fill.assert_called_once_with('test-only', timeout=5000)
        button.first.click.assert_called_once()

    @patch.object(main.time, 'sleep')
    @patch.object(main, 'has_manual_verification', return_value=False)
    @patch.object(main.time, 'monotonic', side_effect=[0, 1, 2, 3, 200])
    @patch.object(main, 'portal_ready', return_value=False)
    def test_no_repeated_password_submission_on_timeout(self, ready, clock, manual, sleep):
        page, username, password, button = self.auth_page()
        with patch.object(main, 'login_fields', return_value=(page, username, password)), patch.object(main, 'CFG', {'login': {}}):
            with self.assertRaisesRegex(RuntimeError, '超时'):
                main.ensure_login(MagicMock(pages=[page]))
        password.fill.assert_called_once()
        button.first.click.assert_called_once()

    def test_portal_menu_in_child_frame_is_recognized(self):
        page, frame = MagicMock(), MagicMock()
        page.url = 'https://yjs1.ustc.edu.cn/gsapp/sys/yjsemaphome/portal/index.do'
        frame.url = 'https://yjs1.ustc.edu.cn/gsapp/menu'
        page.frames = [frame]
        menu = MagicMock()
        menu.is_visible.return_value = True
        frame.get_by_text.return_value.all.return_value = [menu]
        self.assertTrue(main.portal_ready(page))

    def test_verification_detection_does_not_fill_or_click(self):
        page, frame = MagicMock(), MagicMock()
        page.url = frame.url = 'https://id.ustc.edu.cn/login'
        page.frames = [frame]
        captcha = MagicMock()
        captcha.is_visible.return_value = True
        frame.get_by_placeholder.return_value.all.return_value = [captcha]
        self.assertTrue(main.has_manual_verification(page))
        captcha.fill.assert_not_called()
        captcha.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
