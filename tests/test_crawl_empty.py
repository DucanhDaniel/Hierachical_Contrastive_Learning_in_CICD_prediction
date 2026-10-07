"""Repo không có run fail vẫn crawl được và giữ checkpoint rỗng hợp lệ."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import uuid

from project3.crawl.gha import crawl_repo


class EmptyCrawlTest(unittest.TestCase):
    def test_no_failure_and_no_workflows(self):
        for workflows in ([], [{'id': 1, 'name': 'CI', 'path': '.github/workflows/ci.yml'}]):
            root = Path('data') / f'empty_crawl_test_{uuid.uuid4().hex}'
            gh = Mock(remaining=5000)
            run = {'id': 1, 'head_branch': 'main', 'conclusion': 'success'}
            with patch('project3.crawl.gha.ci_workflows', return_value=workflows), \
                 patch('project3.crawl.gha.list_runs', return_value=[run]), contextlib.redirect_stdout(io.StringIO()):
                crawl_repo(gh, 'example/repo', 1, 10, True, 100, event='push', root=str(root))
            repo = root / 'example__repo'
            self.assertTrue((repo / 'runs.jsonl').exists())
            self.assertEqual((repo / 'jobs.jsonl').read_text(), '')
            self.assertTrue((repo / 'logs').is_dir())
            gh.get.assert_not_called()
            gh.get_log_tail.assert_not_called()
            for line in (repo / 'runs.jsonl').read_text().splitlines():
                self.assertEqual(json.loads(line)['conclusion'], 'success')


if __name__ == '__main__':
    unittest.main()
