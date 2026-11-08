import queue
import unittest
from unittest.mock import MagicMock, patch
from ustc_bot import app, history


class MemoryTests(unittest.TestCase):
    def setUp(self):
        cleanup = patch.object(app, 'cleanup_round')
        cleanup.start()
        self.addCleanup(cleanup.stop)

    def tearDown(self):
        app.REPORT_DETAILS.clear()

    def test_round_releases_details_after_error(self):
        def failed_round(*args):
            self.assertEqual(app.REPORT_DETAILS, {})
            app.REPORT_DETAILS['new'] = {'report_time': 'example'}
            raise RuntimeError('test failure')
        app.REPORT_DETAILS['old'] = {}
        with patch.object(app, '_batch_enrollment', side_effect=failed_round):
            with self.assertRaises(RuntimeError):
                app.batch_enrollment(MagicMock())
        self.assertEqual(app.REPORT_DETAILS, {})

    def test_round_keeps_details_until_processing_finishes(self):
        def completed_round(*args):
            app.REPORT_DETAILS['new'] = {'report_time': 'example'}
            return {'scan_completed': True}
        with patch.object(app, '_batch_enrollment', side_effect=completed_round):
            self.assertTrue(app.batch_enrollment(MagicMock())['scan_completed'])
        self.assertEqual(app.REPORT_DETAILS, {})

    def test_unattended_popup_queue_is_bounded(self):
        pending = queue.Queue(maxsize=2)
        worker = MagicMock()
        worker.is_alive.return_value = True
        with patch.object(history, 'POPUPS', pending), patch.object(history, '_worker', worker), patch.object(history.sys, 'platform', 'win32'):
            for number in range(100):
                history.show_success_popup({'报告名称': str(number)})
        self.assertEqual(pending.qsize(), 2)

    def test_media_filter_preserves_captcha_images(self):
        route = MagicMock()
        route.request.frame.url = 'https://id.ustc.edu.cn/login'
        route.request.resource_type = 'image'
        app.route_lightweight_resources(route)
        route.abort.assert_not_called()
        route.continue_.assert_called_once()

    def test_media_filter_blocks_only_portal_images(self):
        route = MagicMock()
        route.request.frame.url = 'https://yjs1.ustc.edu.cn/gsapp/report'
        route.request.resource_type = 'image'
        app.route_lightweight_resources(route)
        route.abort.assert_called_once()
