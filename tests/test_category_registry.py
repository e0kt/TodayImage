import json
import tempfile
import unittest
from pathlib import Path

from _loader import load_pure_module


def rows(*names):
    return tuple((n, (f'/img/{n}/a.png',)) for n in names)


class ResolveCategoriesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = load_pure_module('category_registry')

    def test_defaults_when_no_overrides(self) -> None:
        cats, skips = self.reg.resolve_categories(rows('黑丝', '白丝'), {}, '今日')
        self.assertEqual([c.name for c in cats], ['黑丝', '白丝'])
        self.assertEqual([c.commands for c in cats], [('今日黑丝',), ('今日白丝',)])
        self.assertTrue(all(c.enabled for c in cats))
        self.assertTrue(all(c.caption is None for c in cats))
        self.assertEqual(skips, ())

    def test_disabled_category_yields_no_commands(self) -> None:
        # V-CAT-6
        overrides = {'白丝': {'enabled': False}}
        cats, _ = self.reg.resolve_categories(rows('黑丝', '白丝'), overrides, '今日')
        by_name = {c.name: c for c in cats}
        self.assertEqual(by_name['白丝'].commands, ())
        self.assertFalse(by_name['白丝'].enabled)
        self.assertEqual(by_name['黑丝'].commands, ('今日黑丝',))

    def test_aliases_add_commands(self) -> None:
        overrides = {'黑丝': {'aliases': ['丝袜', '黑色丝袜']}}
        cats, _ = self.reg.resolve_categories(rows('黑丝'), overrides, '今日')
        self.assertEqual(cats[0].commands, ('今日黑丝', '今日丝袜', '今日黑色丝袜'))

    def test_caption_override_is_carried(self) -> None:
        overrides = {'黑丝': {'caption': '收好~'}}
        cats, _ = self.reg.resolve_categories(rows('黑丝'), overrides, '今日')
        self.assertEqual(cats[0].caption, '收好~')

    def test_case_or_whitespace_equal_names_conflict(self) -> None:
        # V-CAT-2: stable-sort winner kept, loser reported.
        cats, skips = self.reg.resolve_categories(rows('Alpha', 'alpha'), {}, '今日')
        self.assertEqual([c.name for c in cats], ['Alpha'])
        self.assertEqual(len(skips), 1)
        self.assertIn('alpha', skips[0])

    def test_alias_colliding_with_another_category_is_dropped(self) -> None:
        # V-CAT-4
        overrides = {'黑丝': {'aliases': ['白丝']}}
        cats, skips = self.reg.resolve_categories(rows('黑丝', '白丝'), overrides, '今日')
        by_name = {c.name: c for c in cats}
        self.assertEqual(by_name['黑丝'].commands, ('今日黑丝',))
        self.assertEqual(by_name['白丝'].commands, ('今日白丝',))
        self.assertEqual(len(skips), 1)
        self.assertIn('今日白丝', skips[0])

    def test_empty_category_still_registers(self) -> None:
        # V-CAT-3
        cats, _ = self.reg.resolve_categories((('空的', ()),), {}, '今日')
        self.assertEqual(cats[0].commands, ('今日空的',))
        self.assertEqual(cats[0].images, ())

    def test_blank_and_dot_names_are_skipped(self) -> None:
        # V-CAT-1
        cats, _ = self.reg.resolve_categories(
            (('   ', ('/img/a.png',)), ('.hidden', ('/img/b.png',)), ('黑丝', ('/img/c.png',))),
            {},
            '今日',
        )
        self.assertEqual([c.name for c in cats], ['黑丝'])

    def test_prefix_change_re_resolves_every_command(self) -> None:
        cats, _ = self.reg.resolve_categories(rows('黑丝'), {'黑丝': {'aliases': ['丝袜']}}, '每日')
        self.assertEqual(cats[0].commands, ('每日黑丝', '每日丝袜'))

    def test_empty_prefix_falls_back_to_default(self) -> None:
        # V-CFG-3: a bare category name as a command would collide with ordinary chat.
        cats, _ = self.reg.resolve_categories(rows('黑丝'), {}, '')
        self.assertEqual(cats[0].commands, ('今日黑丝',))
        cats, _ = self.reg.resolve_categories(rows('黑丝'), {}, '   ')
        self.assertEqual(cats[0].commands, ('今日黑丝',))

    def test_duplicate_aliases_within_one_category_are_collapsed(self) -> None:
        overrides = {'黑丝': {'aliases': ['丝袜', '丝袜', '黑丝']}}
        cats, _ = self.reg.resolve_categories(rows('黑丝'), overrides, '今日')
        self.assertEqual(cats[0].commands, ('今日黑丝', '今日丝袜'))


class OverridesFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = load_pure_module('category_registry')

    def test_missing_file_reads_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self.reg.read_overrides(Path(temp) / 'nope.json'), {})

    def test_malformed_file_degrades_to_empty(self) -> None:
        # V-OVR-2
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'categories.json'
            path.write_text('{ not json', encoding='utf-8')
            self.assertEqual(self.reg.read_overrides(path), {})

    def test_round_trip_preserves_unknown_keys(self) -> None:
        # V-OVR-3
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'categories.json'
            payload = {
                'version': 1,
                'categories': {'黑丝': {'enabled': True, 'future_key': 42}},
            }
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')

            overrides = self.reg.read_overrides(path)
            self.assertEqual(overrides['黑丝']['future_key'], 42)

            self.reg.write_overrides(path, overrides)
            again = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(again['categories']['黑丝']['future_key'], 42)

    def test_entries_for_absent_folders_are_retained(self) -> None:
        # V-OVR-1
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'categories.json'
            self.reg.write_overrides(path, {'搬走了': {'enabled': False}})
            self.assertIn('搬走了', self.reg.read_overrides(path))

    def test_write_is_atomic_and_leaves_no_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'categories.json'
            self.reg.write_overrides(path, {'黑丝': {'enabled': True}})
            leftovers = [p.name for p in Path(temp).iterdir() if p.name != 'categories.json']
            self.assertEqual(leftovers, [])


if __name__ == '__main__':
    unittest.main()
