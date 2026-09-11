import unittest

from _loader import load_pure_module


class BuildCategoryIndexTests(unittest.TestCase):
    def setUp(self):
        self.gallery = load_pure_module('gallery')

    def rows(self, *names):
        return tuple((n, (f'/img/{n}/a.png',)) for n in names)

    def test_keys_are_stripped_and_casefolded(self):
        index = self.gallery.build_category_index(self.rows('黑丝', 'Alpha'))
        self.assertEqual(index['黑丝'], '黑丝')
        self.assertEqual(index['alpha'], 'Alpha')

    def test_lookup_ignores_case_and_surrounding_space(self):
        index = self.gallery.build_category_index(self.rows('Alpha'))
        for probe in ('Alpha', 'alpha', 'ALPHA', '  alpha  ', '\talpha\n'):
            with self.subTest(probe=probe):
                self.assertEqual(self.gallery.lookup_category(index, probe), 'Alpha')

    def test_traversal_and_separators_simply_miss(self):
        # The suffix is only ever a dict key -- never joined onto a path -- so these
        # cannot resolve by construction (V-IDX-2, FR-104).
        index = self.gallery.build_category_index(self.rows('黑丝'))
        for probe in ('../黑丝', '../../etc/passwd', '/etc/passwd', r'..\黑丝',
                      '黑丝/../黑丝', './黑丝', '黑丝/a.png'):
            with self.subTest(probe=probe):
                self.assertIsNone(self.gallery.lookup_category(index, probe))

    def test_empty_and_whitespace_probes_miss(self):
        index = self.gallery.build_category_index(self.rows('黑丝'))
        self.assertIsNone(self.gallery.lookup_category(index, ''))
        self.assertIsNone(self.gallery.lookup_category(index, '   '))

    def test_unknown_name_misses(self):
        index = self.gallery.build_category_index(self.rows('黑丝'))
        self.assertIsNone(self.gallery.lookup_category(index, '不存在'))

    def test_case_collision_keeps_the_stable_sort_winner(self):
        # V-IDX-5: first in stable order holds the key; the loser is unreachable.
        index = self.gallery.build_category_index(self.rows('Alpha', 'alpha'))
        self.assertEqual(index['alpha'], 'Alpha')
        self.assertEqual(len(index), 1)

    def test_empty_folder_still_indexed(self):
        # V-CAT-3 carried forward: the command resolves; emptiness is handled downstream.
        index = self.gallery.build_category_index((('空的', ()),))
        self.assertEqual(self.gallery.lookup_category(index, '空的'), '空的')

    def test_blank_names_are_not_indexed(self):
        index = self.gallery.build_category_index(((' ', ('/a.png',)), ('黑丝', ('/b.png',))))
        self.assertEqual(list(index.values()), ['黑丝'])

    def test_index_of_nothing_is_empty(self):
        self.assertEqual(self.gallery.build_category_index(()), {})


if __name__ == '__main__':
    unittest.main()
