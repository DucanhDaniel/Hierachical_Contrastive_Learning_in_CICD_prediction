import csv
import json
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

from project3.crawl.build_log_labels import load_commits


class NonBuildCommitTest(unittest.TestCase):
    def test_excluded_failure_does_not_poison_passing_commit(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            root = Path(temp)
            repo = root / 'example__repo'
            repo.mkdir()
            common = dict(event='push', name='CI', head_sha='same', created_at='2026-10-10T00:00:00Z')
            runs = [dict(common, id=1, conclusion='success'), dict(common, id=2, conclusion='failure'),
                    dict(common, id=3, head_sha='excluded-only', conclusion='failure')]
            (repo / 'runs.jsonl').write_text('\n'.join(json.dumps(r) for r in runs), encoding='utf-8')
            with (root / 'gold_labels.csv').open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, ['run_id', 'gold', 'non_build'])
                writer.writeheader()
                writer.writerows([dict(run_id=2, gold='?', non_build='True'),
                                  dict(run_id=3, gold='non_build', non_build='True')])
            commits = defaultdict(lambda: dict(runs=0, fail=0, labels=[], start=None, pr=None))
            load_commits(root, commits)
            self.assertEqual(len(commits), 1)
            commit = commits[('example/repo', 'push', 'same')]
            self.assertEqual(commit['runs'], 1)
            self.assertEqual(commit['fail'], 0)


if __name__ == '__main__':
    unittest.main()
