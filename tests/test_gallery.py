import tempfile
import unittest
from pathlib import Path

from _loader import load_pure_module

EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}


class ScanCategoryDirectoriesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gallery = load_pure_module('gallery')

    def test_scans_recursively_and_ignores_non_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'images'
            (root / '黑丝' / '画师A').mkdir(parents=True)
            (root / '黑丝' / 'a.PNG').write_bytes(b'a')          # V-IMG-1 case-folded
            (root / '黑丝' / '画师A' / 'b.jpg').write_bytes(b'b')  # V-IMG-3 recursive
            (root / '黑丝' / 'note.txt').write_text('x', encoding='utf-8')
            (root / '黑丝' / 'Thumbs.db').write_bytes(b'x')

            rows = self.gallery.scan_category_directories(root, EXTS)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], '黑丝')
            self.assertEqual(len(rows[0][1]), 2)
            self.assertTrue(all(Path(p).is_absolute() for p in rows[0][1]))

    def test_skips_dot_prefixed_dirs_and_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'images'
            (root / '.cache').mkdir(parents=True)
            (root / '.cache' / 'x.png').write_bytes(b'x')
            (root / '白丝').mkdir()
            (root / '白丝' / '.hidden.png').write_bytes(b'x')
            (root / '白丝' / 'ok.png').write_bytes(b'x')

            rows = self.gallery.scan_category_directories(root, EXTS)

            self.assertEqual([r[0] for r in rows], ['白丝'])
            self.assertEqual(len(rows[0][1]), 1)
            self.assertTrue(rows[0][1][0].endswith('ok.png'))

    def test_empty_category_is_still_returned(self) -> None:
        # V-CAT-3: an emptied folder keeps its command; the draw reports "no images".
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'images'
            (root / '空的').mkdir(parents=True)

            rows = self.gallery.scan_category_directories(root, EXTS)

            self.assertEqual(rows, (('空的', ()),))

    def test_creates_missing_root_and_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'missing'
            self.assertEqual(self.gallery.scan_category_directories(root, EXTS), ())
            self.assertTrue(root.is_dir())

    def test_ordering_is_stable_and_case_folded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'images'
            for name in ('beta', 'Alpha', 'gamma'):
                (root / name).mkdir(parents=True)
                (root / name / 'x.png').write_bytes(b'x')

            names = [r[0] for r in self.gallery.scan_category_directories(root, EXTS)]
            self.assertEqual(names, ['Alpha', 'beta', 'gamma'])

    def test_deduplicates_on_resolved_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'images'
            cat = root / '黑丝'
            cat.mkdir(parents=True)
            real = cat / 'real.png'
            real.write_bytes(b'x')
            try:
                (cat / 'link.png').symlink_to(real)
            except (OSError, NotImplementedError):
                self.skipTest('symlinks unavailable')

            rows = self.gallery.scan_category_directories(root, EXTS)
            self.assertEqual(len(rows[0][1]), 1)

    def test_ignores_stray_files_in_the_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'images'
            root.mkdir(parents=True)
            (root / 'loose.png').write_bytes(b'x')
            self.assertEqual(self.gallery.scan_category_directories(root, EXTS), ())


class FindCategoryDirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gallery = load_pure_module('gallery')

    def test_finds_existing_directory_ignoring_case_and_space(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'images'
            target = root / '黑丝'
            target.mkdir(parents=True)
            self.assertEqual(self.gallery.find_category_directory(root, ' 黑丝 '), target)

    def test_refuses_traversal_and_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'images'
            (root / '黑丝').mkdir(parents=True)
            self.assertIsNone(self.gallery.find_category_directory(root, '../黑丝'))
            self.assertIsNone(self.gallery.find_category_directory(root, '不存在'))
            self.assertIsNone(self.gallery.find_category_directory(root, ''))
            self.assertFalse((root / '不存在').exists())


class ShortIdTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gallery = load_pure_module('gallery')

    def test_short_id_is_eight_lowercase_hex_of_the_file_name(self) -> None:
        a = self.gallery.image_short_id('/tmp/one/x.png')
        b = self.gallery.image_short_id('/other/two/x.png')
        self.assertEqual(a, b)                       # V-IMG-5: name only, not path
        self.assertRegex(a, r'^[0-9a-f]{8}$')
        self.assertNotEqual(a, self.gallery.image_short_id('/tmp/one/y.png'))

    def test_resolve_returns_every_match(self) -> None:
        # V-IMG-5: identical names in sibling folders share an ID -> report ambiguity.
        paths = ('/a/x.png', '/b/x.png', '/c/y.png')
        target = self.gallery.image_short_id('/a/x.png')
        self.assertEqual(
            self.gallery.resolve_short_id(paths, target),
            ('/a/x.png', '/b/x.png'),
        )

    def test_resolve_is_case_insensitive_and_empty_when_unmatched(self) -> None:
        paths = ('/a/x.png',)
        target = self.gallery.image_short_id('/a/x.png')
        self.assertEqual(self.gallery.resolve_short_id(paths, target.upper()), ('/a/x.png',))
        self.assertEqual(self.gallery.resolve_short_id(paths, 'deadbeef'), ())


if __name__ == '__main__':
    unittest.main()


class ReservedDirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gallery = load_pure_module('gallery')

    def test_reserved_directory_names_are_not_categories(self):
        # The image root is data/TodayImage itself, so plugin-owned folders must never
        # turn into phantom image types.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'TodayImage'
            for name in ('黑丝', 'cache', 'Tmp'):
                (root / name).mkdir(parents=True)
                (root / name / 'a.png').write_bytes(b'x')

            rows = self.gallery.scan_category_directories(
                root, EXTS, self.gallery.RESERVED_DIRECTORY_NAMES
            )
            self.assertEqual([r[0] for r in rows], ['黑丝'])

    def test_config_files_beside_the_categories_are_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'TodayImage'
            (root / '黑丝').mkdir(parents=True)
            (root / '黑丝' / 'a.png').write_bytes(b'x')
            for name in ('config.json', 'categories.json', 'daily_records.json'):
                (root / name).write_text('{}', encoding='utf-8')

            rows = self.gallery.scan_category_directories(root, EXTS)
            self.assertEqual([r[0] for r in rows], ['黑丝'])
