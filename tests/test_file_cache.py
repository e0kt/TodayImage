import os
import tempfile
import time
import unittest
from pathlib import Path

from _loader import load_pure_module


class FileCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cache = load_pure_module('file_cache')
        self.cache.clear_file_caches()

    def test_reads_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.bin'
            path.write_bytes(b'hello')
            self.assertEqual(self.cache.read_file_bytes_cached(path), b'hello')

    def test_second_call_does_not_re_read_from_disk(self) -> None:
        # The cache still stat()s to validate mtime -- that is deliberate, since the draw
        # path relies on a vanished image being detected (V-REC-3). What it must avoid is
        # the read itself, which is the expensive part for large images.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.bin'
            path.write_bytes(b'hello')

            reads = []
            original = Path.read_bytes

            def counting_read(self_path):
                reads.append(str(self_path))
                return original(self_path)

            Path.read_bytes = counting_read
            try:
                first = self.cache.read_file_bytes_cached(path)
                second = self.cache.read_file_bytes_cached(path)
            finally:
                Path.read_bytes = original

            self.assertEqual(first, second)
            self.assertEqual(len(reads), 1)

    def test_deleted_file_is_reported_not_served_from_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.bin'
            path.write_bytes(b'hello')
            self.cache.read_file_bytes_cached(path)
            path.unlink()
            with self.assertRaises(OSError):
                self.cache.read_file_bytes_cached(path)

    def test_cache_invalidates_when_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.bin'
            path.write_bytes(b'old')
            self.assertEqual(self.cache.read_file_bytes_cached(path), b'old')

            path.write_bytes(b'new-and-longer')
            # Force a distinct mtime even on coarse-grained clocks.
            future = time.time() + 10
            os.utime(path, (future, future))
            self.assertEqual(self.cache.read_file_bytes_cached(path), b'new-and-longer')

    def test_evicts_by_entry_count(self) -> None:
        self.cache.LOCAL_BYTES_CACHE_MAX_ENTRIES = 3
        with tempfile.TemporaryDirectory() as temp:
            paths = []
            for i in range(5):
                p = Path(temp) / f'{i}.bin'
                p.write_bytes(bytes([i]))
                paths.append(p)
                self.cache.read_file_bytes_cached(p)
            self.assertLessEqual(self.cache.cache_entry_count(), 3)

    def test_evicts_by_total_bytes(self) -> None:
        self.cache.LOCAL_BYTES_CACHE_MAX_BYTES = 100
        with tempfile.TemporaryDirectory() as temp:
            for i in range(5):
                p = Path(temp) / f'{i}.bin'
                p.write_bytes(b'x' * 60)
                self.cache.read_file_bytes_cached(p)
            self.assertLessEqual(self.cache.cache_total_bytes(), 100)
            self.assertGreaterEqual(self.cache.cache_entry_count(), 1)

    def test_clear_resets_both_counters(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'a.bin'
            path.write_bytes(b'hello')
            self.cache.read_file_bytes_cached(path)
            self.assertGreater(self.cache.cache_entry_count(), 0)

            self.cache.clear_file_caches()
            self.assertEqual(self.cache.cache_entry_count(), 0)
            self.assertEqual(self.cache.cache_total_bytes(), 0)

    def test_missing_file_raises_oserror(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(OSError):
                self.cache.read_file_bytes_cached(Path(temp) / 'nope.bin')


if __name__ == '__main__':
    unittest.main()
