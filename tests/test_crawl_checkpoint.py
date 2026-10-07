"""Checkpoint không được bỏ record hoàn tất hoặc tự sửa dữ liệu hỏng ở giữa."""
import unittest

from project3.crawl.checkpoint import valid_prefix


class CheckpointTest(unittest.TestCase):
    def test_complete_records(self):
        for raw in (b'', b'{"id":1}\n', b'{"id":1}\r\n{"id":2}', '{"name":"lỗi"}\n'.encode()):
            self.assertEqual(valid_prefix(raw), len(raw))

    def test_interrupted_final_record(self):
        good = b'{"id":1}\n'
        self.assertEqual(valid_prefix(good + b'{"id":'), len(good))
        self.assertEqual(valid_prefix(good + b'{"name":"\xe1'), len(good))

    def test_invalid_middle_is_not_repaired(self):
        with self.assertRaises(ValueError):
            valid_prefix(b'{"id":}\n{"id":2}\n')


if __name__ == '__main__':
    unittest.main()
