"""Hai tiến trình không được đồng thời ghi vào cùng root."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from project3.crawl.gha import crawl_lock


class CrawlLockTest(unittest.TestCase):
    def test_second_process_waits_until_release(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        marker = root / 'acquired.txt'
        code = ("from pathlib import Path\nfrom project3.crawl.gha import crawl_lock\n"
                "print('started', flush=True)\n"
                f"with crawl_lock({str(root)!r}):\n"
                f"    Path({str(marker)!r}).write_text('acquired')\n")
        child = None
        try:
            with crawl_lock(str(root)):
                child = subprocess.Popen([sys.executable, '-u', '-c', code], stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True, encoding='utf-8')
                self.assertEqual(child.stdout.readline().strip(), 'started')
                self.assertIn('Chờ crawler khác', child.stdout.readline())
                self.assertFalse(marker.exists())
                self.assertIsNone(child.poll())
            _, stderr = child.communicate(timeout=15)
            self.assertEqual(child.returncode, 0, stderr)
            self.assertEqual(marker.read_text(), 'acquired')
        finally:
            if child and child.poll() is None:
                child.kill()
                child.communicate()


if __name__ == '__main__':
    unittest.main()
