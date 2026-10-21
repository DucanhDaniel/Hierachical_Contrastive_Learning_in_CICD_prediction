"""Retry lỗi tạm thời của GitHub client."""
import contextlib
import io
import unittest
from unittest.mock import Mock, patch

import requests

from project3.crawl.github import GitHub


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


if __name__ == '__main__':
    unittest.main()
