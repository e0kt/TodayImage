import json
import tempfile
import unittest
from pathlib import Path

from _loader import load_pure_module


class RecordKeyTests(unittest.TestCase):
    def setUp(self):
        self.store = load_pure_module('daily_store')

    def test_builds_and_parses_a_key(self):
        key = self.store.record_key('123456', 'qq:10001', '黑丝')
        self.assertEqual(key, '123456|qq:10001|黑丝')
        self.assertEqual(self.store.parse_key(key), ('123456', 'qq:10001', '黑丝'))

    def test_category_name_containing_the_separator_still_parses(self):
        # Split on the FIRST TWO separators only, so a piped category name survives.
        key = self.store.record_key('123456', 'qq:10001', 'a|b|c')
        self.assertEqual(self.store.parse_key(key), ('123456', 'qq:10001', 'a|b|c'))

    def test_malformed_key_returns_none(self):
        self.assertIsNone(self.store.parse_key('nope'))
        self.assertIsNone(self.store.parse_key('only|two'))


class LoadSaveTests(unittest.TestCase):
    def setUp(self):
        self.store = load_pure_module('daily_store')

    def test_missing_file_loads_as_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self.store.load_records(Path(temp) / 'nope.json', '2026-09-08'), {})

    def test_malformed_file_degrades_to_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'daily_records.json'
            path.write_text('{ broken', encoding='utf-8')
            self.assertEqual(self.store.load_records(path, '2026-09-08'), {})

    def test_records_from_another_date_are_ignored_on_read(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'daily_records.json'
            path.write_text(json.dumps({
                'version': 1,
                'date': '2026-09-07',
                'records': {'g|u|黑丝': {'image': '/a.png', 'created_at': 1.0}},
            }), encoding='utf-8')
            self.assertEqual(self.store.load_records(path, '2026-09-08'), {})

    def test_round_trip_for_the_current_date(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'daily_records.json'
            self.store.save_records(path, '2026-09-08', {'g|u|黑丝': {'image': '/a.png', 'created_at': 1.0}})
            loaded = self.store.load_records(path, '2026-09-08')
            self.assertEqual(loaded['g|u|黑丝']['image'], '/a.png')

    def test_save_prunes_records_from_other_dates(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'daily_records.json'
            self.store.save_records(path, '2026-09-07', {'g|u|黑丝': {'image': '/old.png', 'created_at': 1.0}})
            self.store.save_records(path, '2026-09-08', {'g|u|白丝': {'image': '/new.png', 'created_at': 2.0}})

            payload = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(payload['date'], '2026-09-08')
            self.assertEqual(list(payload['records']), ['g|u|白丝'])

    def test_write_is_atomic_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'daily_records.json'
            self.store.save_records(path, '2026-09-08', {'g|u|黑丝': {'image': '/a.png', 'created_at': 1.0}})
            leftovers = [p.name for p in Path(temp).iterdir() if p.name != 'daily_records.json']
            self.assertEqual(leftovers, [])

    def test_upsert_reads_prunes_and_writes_in_one_step(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'daily_records.json'
            self.store.upsert_record(path, '2026-09-08', 'g|u|黑丝', '/a.png')
            self.assertEqual(
                self.store.load_records(path, '2026-09-08')['g|u|黑丝']['image'], '/a.png'
            )

    def test_get_record_image_returns_none_for_absent_or_bad_entries(self):
        records = {'g|u|黑丝': {'image': '/a.png'}, 'g|u|坏的': {'nope': 1}}
        self.assertEqual(self.store.get_record_image(records, 'g|u|黑丝'), '/a.png')
        self.assertIsNone(self.store.get_record_image(records, 'g|u|坏的'))
        self.assertIsNone(self.store.get_record_image(records, 'g|u|不存在'))


if __name__ == '__main__':
    unittest.main()
