import json
import tempfile
import unittest
from pathlib import Path
from ustc_bot.config import load_credentials, load_settings


class PrivateConfigTests(unittest.TestCase):
    def test_public_config_rejects_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps({'filters': {}, 'login': {'password': 'test-secret'}}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'credentials.json'):
                load_settings(path)

    def test_public_config_defaults_and_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps({'filters': {}}), encoding='utf-8')
            self.assertEqual(load_settings(path)['interval_seconds'], 600)
            path.write_text(json.dumps({'filters': {}, 'interval_seconds': 0}), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_settings(path)
    def test_reads_separate_credentials_and_preserves_password_spaces(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'credentials.json'
            path.write_text(json.dumps({'student_id': ' TEST ', 'password': ' secret '}), encoding='utf-8-sig')
            self.assertEqual(load_credentials(path), {'student_id': 'TEST', 'password': ' secret '})

    def test_malformed_file_does_not_echo_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'credentials.json'
            path.write_text('{"password": "test-secret"', encoding='utf-8')
            with self.assertRaises(ValueError) as caught:
                load_credentials(path)
            self.assertNotIn('test-secret', str(caught.exception))

    def test_missing_file_explains_which_file_to_create(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'credentials.json'):
                load_credentials(Path(folder) / 'credentials.json')
