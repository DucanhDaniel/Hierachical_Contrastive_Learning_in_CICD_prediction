import unittest
from unittest.mock import Mock, patch

from project3.pipeline.crawl_100 import DEADLINE, MIDPOINT, stop_child, save, save_snapshot, load_results, wait_child


class Crawl100Test(unittest.TestCase):
    def test_locked_state_replace_retries_then_recovers(self):
        path = Mock(suffix='.json')
        partial = path.with_suffix.return_value
        partial.replace.side_effect = [PermissionError(5, 'locked'), PermissionError(5, 'locked'), None]
        with patch('project3.pipeline.crawl_100.time.sleep'):
            save(path, {'status': 'running'})
        self.assertEqual(partial.replace.call_count, 3)
        partial.write_text.assert_called_once()

    def test_persistently_locked_state_does_not_stop_child(self):
        path = Mock(suffix='.json')
        path.with_suffix.return_value.replace.side_effect = PermissionError(5, 'locked')
        proc = Mock(returncode=0)
        proc.poll.side_effect = [None, None, 0]
        with patch('project3.pipeline.crawl_100.time.sleep'), patch('builtins.print'), patch('project3.pipeline.crawl_100.stop_child') as stop:
            result = wait_child(proc, lambda: save_snapshot(path, {'status': 'running'}))
        self.assertEqual(result, 0)
        stop.assert_not_called()
        self.assertEqual(path.with_suffix.return_value.replace.call_count, 10)

    def test_results_resume_newer_valid_partial(self):
        path = Mock(suffix='.json')
        part = path.with_suffix.return_value
        path.stat.return_value.st_mtime_ns = 1
        part.stat.return_value.st_mtime_ns = 2
        path.read_text.return_value = '{}'
        part.read_text.return_value = '{"pull_request|repo": {"status": "completed"}}'
        self.assertEqual(load_results(path)['pull_request|repo']['status'], 'completed')

    def test_invalid_partial_uses_committed_results(self):
        path = Mock(suffix='.json')
        part = path.with_suffix.return_value
        path.stat.return_value.st_mtime_ns = 1
        part.stat.return_value.st_mtime_ns = 2
        path.read_text.return_value = '{}'
        part.read_text.return_value = '{cut'
        with patch('builtins.print'):
            self.assertEqual(load_results(path), {})

    def test_vietnam_cutoffs(self):
        self.assertEqual(DEADLINE.isoformat(), "2026-10-14T22:00:00+07:00")
        self.assertEqual(MIDPOINT.isoformat(), "2026-10-12T22:00:00+07:00")
        self.assertLess(MIDPOINT, DEADLINE)

    def test_windows_stops_launcher_and_descendants(self):
        proc = Mock(pid=123)
        proc.poll.return_value = None
        with patch("project3.pipeline.crawl_100.os.name", "nt"), patch("project3.pipeline.crawl_100.subprocess.run") as run:
            stop_child(proc)
        self.assertEqual(run.call_args.args[0], ["taskkill", "/PID", "123", "/T", "/F"])
        proc.wait.assert_called_once_with(timeout=30)

    def test_finished_process_is_not_killed(self):
        proc = Mock()
        proc.poll.return_value = 0
        with patch("project3.pipeline.crawl_100.subprocess.run") as run:
            stop_child(proc)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
