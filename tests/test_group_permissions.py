import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from _loader import load_pure_module


class NormalisationTests(unittest.TestCase):
    def setUp(self):
        self.gp = load_pure_module('group_permissions')

    def test_tag_identity_is_stripped_and_casefolded(self):
        for probe in ('黑丝', ' 黑丝 ', '\t黑丝\n'):
            with self.subTest(probe=probe):
                self.assertEqual(self.gp.normalize_tag(probe), '黑丝')
        self.assertEqual(self.gp.normalize_tag(' Alpha '), 'alpha')

    def test_surrounding_brackets_are_stripped(self):
        # The request literally wrote 【tag名字】; an admin copying that form must not
        # end up authorising a tag called 【黑丝】 (V-GRP-2).
        for probe in ('【黑丝】', '[黑丝]', '「黑丝」', '（黑丝）', '(黑丝)', ' 【 黑丝 】 '):
            with self.subTest(probe=probe):
                self.assertEqual(self.gp.normalize_tag(probe), '黑丝')

    def test_empty_tag_normalises_to_empty(self):
        for probe in ('', '   ', '【】', None):
            with self.subTest(probe=probe):
                self.assertEqual(self.gp.normalize_tag(probe), '')

    def test_group_key_is_a_trimmed_string(self):
        # Adapters differ on int vs str; a group splitting into two records looks to the
        # admin like "my authorisation didn't take effect" (V-GRP-3).
        self.assertEqual(self.gp.normalize_group_key(123), '123')
        self.assertEqual(self.gp.normalize_group_key('123'), '123')
        self.assertEqual(self.gp.normalize_group_key(' 123 '), '123')


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.gp = load_pure_module('group_permissions')
        self.gp.clear_locks()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'group_permissions.json'

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_file_authorises_nothing(self):
        self.assertEqual(self.gp.tags_for_group(self.path, 'g1'), frozenset())
        self.assertFalse(self.gp.is_tag_allowed(self.path, 'g1', '黑丝'))

    def test_malformed_file_fails_closed(self):
        # FR-218 / V-PST-1: this INVERTS feature 001's posture. A corrupt store there
        # cost one day's pin; here it must remove access, never grant it.
        self.path.write_text('{ broken', encoding='utf-8')
        self.assertEqual(self.gp.tags_for_group(self.path, 'g1'), frozenset())
        self.assertFalse(self.gp.is_tag_allowed(self.path, 'g1', '黑丝'))

    def test_authorise_then_allowed(self):
        asyncio.run(self.gp.authorise_tag(self.path, 'g1', '黑丝', 'admin1'))
        self.assertTrue(self.gp.is_tag_allowed(self.path, 'g1', '黑丝'))
        self.assertTrue(self.gp.is_tag_allowed(self.path, 'g1', ' 【黑丝】 '))

    def test_authorisation_does_not_leak_between_groups(self):
        asyncio.run(self.gp.authorise_tag(self.path, 'g1', '黑丝', 'admin1'))
        self.assertFalse(self.gp.is_tag_allowed(self.path, 'g2', '黑丝'))

    def test_authorisation_is_per_tag(self):
        asyncio.run(self.gp.authorise_tag(self.path, 'g1', '黑丝', 'admin1'))
        self.assertFalse(self.gp.is_tag_allowed(self.path, 'g1', '白丝'))

    def test_authorise_is_idempotent(self):
        first = asyncio.run(self.gp.authorise_tag(self.path, 'g1', '黑丝', 'admin1'))
        second = asyncio.run(self.gp.authorise_tag(self.path, 'g1', '黑丝', 'admin1'))
        self.assertTrue(first)
        self.assertFalse(second, 'second authorisation should report "already allowed"')
        self.assertEqual(self.gp.tags_for_group(self.path, 'g1'), frozenset({'黑丝'}))

    def test_revoke_removes_only_the_named_tag(self):
        asyncio.run(self.gp.authorise_tag(self.path, 'g1', '黑丝', 'a'))
        asyncio.run(self.gp.authorise_tag(self.path, 'g1', '白丝', 'a'))
        self.assertTrue(asyncio.run(self.gp.revoke_tag(self.path, 'g1', '黑丝', 'a')))
        self.assertEqual(self.gp.tags_for_group(self.path, 'g1'), frozenset({'白丝'}))

    def test_revoking_an_unauthorised_tag_is_reported_not_raised(self):
        self.assertFalse(asyncio.run(self.gp.revoke_tag(self.path, 'g1', '黑丝', 'a')))

    def test_revoking_the_last_tag_leaves_an_empty_entry(self):
        asyncio.run(self.gp.authorise_tag(self.path, 'g1', '黑丝', 'a'))
        asyncio.run(self.gp.revoke_tag(self.path, 'g1', '黑丝', 'a'))
        payload = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertIn('g1', payload['groups'])
        self.assertEqual(payload['groups']['g1']['tags'], [])

    def test_persists_across_reload(self):
        asyncio.run(self.gp.authorise_tag(self.path, 'g1', '黑丝', 'admin1'))
        reloaded = load_pure_module('group_permissions')
        self.assertTrue(reloaded.is_tag_allowed(self.path, 'g1', '黑丝'))

    def test_records_who_changed_it_and_when(self):
        asyncio.run(self.gp.authorise_tag(self.path, 'g1', '黑丝', 'admin1'))
        entry = json.loads(self.path.read_text(encoding='utf-8'))['groups']['g1']
        self.assertEqual(entry['updated_by'], 'admin1')
        self.assertGreater(entry['updated_at'], 0)

    def test_tags_are_stored_sorted_and_deduplicated(self):
        for tag in ('白丝', '黑丝', '白丝'):
            asyncio.run(self.gp.authorise_tag(self.path, 'g1', tag, 'a'))
        stored = json.loads(self.path.read_text(encoding='utf-8'))['groups']['g1']['tags']
        self.assertEqual(stored, sorted(set(stored)))

    def test_atomic_write_leaves_no_temp_file(self):
        asyncio.run(self.gp.authorise_tag(self.path, 'g1', '黑丝', 'a'))
        leftovers = [p.name for p in Path(self.temp.name).iterdir() if p.name != 'group_permissions.json']
        self.assertEqual(leftovers, [])

    def test_unknown_keys_in_an_entry_are_preserved(self):
        self.path.write_text(json.dumps({
            'version': 1,
            'groups': {'g1': {'tags': ['黑丝'], 'future_key': 42}},
        }, ensure_ascii=False), encoding='utf-8')
        asyncio.run(self.gp.authorise_tag(self.path, 'g1', '白丝', 'a'))
        entry = json.loads(self.path.read_text(encoding='utf-8'))['groups']['g1']
        self.assertEqual(entry['future_key'], 42)

    def test_entries_for_other_groups_are_retained(self):
        asyncio.run(self.gp.authorise_tag(self.path, 'g1', '黑丝', 'a'))
        asyncio.run(self.gp.authorise_tag(self.path, 'g2', '白丝', 'a'))
        self.assertEqual(self.gp.tags_for_group(self.path, 'g1'), frozenset({'黑丝'}))
        self.assertEqual(self.gp.tags_for_group(self.path, 'g2'), frozenset({'白丝'}))

    def test_concurrent_authorisations_in_one_group_do_not_lose_an_update(self):
        async def race():
            await asyncio.gather(*[
                self.gp.authorise_tag(self.path, 'g1', f'tag{i}', 'a') for i in range(12)
            ])
        asyncio.run(race())
        self.assertEqual(len(self.gp.tags_for_group(self.path, 'g1')), 12)


class DefaultTagsTests(unittest.TestCase):
    def setUp(self):
        self.gp = load_pure_module('group_permissions')
        self.gp.clear_locks()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'group_permissions.json'

    def tearDown(self):
        self.temp.cleanup()

    def test_defaults_apply_to_a_group_with_no_record(self):
        self.assertTrue(self.gp.is_tag_allowed(self.path, 'g1', '黑丝', defaults=['黑丝']))

    def test_defaults_do_not_apply_once_a_group_has_a_record(self):
        # CF-301: widening the default must never re-grant a deliberately revoked tag.
        asyncio.run(self.gp.authorise_tag(self.path, 'g1', '白丝', 'a'))
        asyncio.run(self.gp.revoke_tag(self.path, 'g1', '白丝', 'a'))
        self.assertFalse(self.gp.is_tag_allowed(self.path, 'g1', '黑丝', defaults=['黑丝']))

    def test_defaults_are_normalised_like_any_tag(self):
        self.assertTrue(self.gp.is_tag_allowed(self.path, 'g1', '黑丝', defaults=['【黑丝】']))

    def test_empty_defaults_authorise_nothing(self):
        self.assertFalse(self.gp.is_tag_allowed(self.path, 'g1', '黑丝', defaults=[]))


if __name__ == '__main__':
    unittest.main()
