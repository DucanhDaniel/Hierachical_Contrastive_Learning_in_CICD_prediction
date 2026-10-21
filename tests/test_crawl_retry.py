"""Retry lỗi tạm thời và chọn đúng phần dữ liệu còn thiếu."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import uuid

import requests

from project3.crawl.github import GitHub
from project3.crawl.retry_plan import needs_retry


class RetryTest(unittest.TestCase):
    def test_server_error_then_success(self):
        gh = GitHub(None)
        error = Mock(status_code=502, headers={})
        ok = Mock(status_code=200, headers={})
        ok.json.return_value = {'jobs': []}
        with patch.object(gh, '_request', side_effect=[error, ok]) as request, \
             patch('project3.crawl.github.time.sleep') as sleep, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gh.get('/example'), {'jobs': []})
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(5)

    def test_not_found_is_not_retried(self):
        gh = GitHub(None)
        response = Mock(status_code=404, headers={})
        response.raise_for_status.side_effect = requests.HTTPError('404')
        with patch.object(gh, '_request', return_value=response) as request:
            with self.assertRaises(requests.HTTPError):
                gh.get('/example')
        request.assert_called_once()

    def test_missing_marker_retried_once_and_preserved(self):
        root = Path('data') / f'retry_test_{uuid.uuid4().hex}'
        d = root / 'example__repo'
        (d / 'logs').mkdir(parents=True)
        (d / 'runs.jsonl').write_text(json.dumps({'id': 1, 'conclusion': 'failure'}) + '\n')
        job = {'id': 2, 'name': 'build', 'conclusion': 'failure', 'steps': []}
        (d / 'jobs.jsonl').write_text(json.dumps({'run_id': 1, 'jobs': [job]}) + '\n')
        marker = d / 'logs/2.missing'
        marker.touch()
        self.assertFalse(needs_retry(root, 'example/repo', 2, False, False))
        self.assertTrue(needs_retry(root, 'example/repo', 2, True, False))
        self.assertTrue(marker.exists())
        self.assertTrue(needs_retry(root, 'example/repo', 2, True, True))
        self.assertFalse(marker.exists())
        self.assertEqual(len(list((d / 'logs').glob('2.missing.retry.*'))), 1)
        self.assertTrue(needs_retry(root, 'example/repo', 2, False, False))
        marker.touch()
        self.assertFalse(needs_retry(root, 'example/repo', 2, False, False))
        (d / 'jobs.jsonl').write_text('')
        self.assertTrue(needs_retry(root, 'example/repo', 2, False, False))


if __name__ == '__main__':
    unittest.main()
