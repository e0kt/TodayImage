import unittest

from _loader import load_pure_module


class DefaultsTests(unittest.TestCase):
    def setUp(self):
        self.bl = load_pure_module('blocklist')

    def test_todaywaifu_commands_are_blocked_by_default(self):
        for command in ('今日老婆', '今日老公', '今日萝莉', '今日战双老婆', '今日异环老婆',
                        '今日群友离婚', '今日老婆帮助', '今日萝莉列表', '今日萝莉上传'):
            with self.subTest(command=command):
                self.assertTrue(self.bl.is_blocked(command, []))

    def test_a_command_extending_a_base_name_is_blocked(self):
        # V-BLK-1: 今日老婆 covers 今日老婆离婚 and any future suffix.
        self.assertTrue(self.bl.is_blocked('今日老婆离婚', []))
        self.assertTrue(self.bl.is_blocked('今日老婆某个新后缀', []))

    def test_our_own_categories_are_not_blocked(self):
        for command in ('今日黑丝', '今日白丝', '今日制服'):
            with self.subTest(command=command):
                self.assertFalse(self.bl.is_blocked(command, []))

    def test_matching_is_stripped_and_casefolded(self):
        self.assertTrue(self.bl.is_blocked('  今日老婆  ', []))

    def test_operator_entries_extend_the_defaults(self):
        self.assertTrue(self.bl.is_blocked('今日天气', ['今日天气']))
        self.assertTrue(self.bl.is_blocked('今日天气预报', ['今日天气']))
        self.assertFalse(self.bl.is_blocked('今日天气', []))

    def test_operator_entries_cannot_remove_a_default(self):
        # V-BLK-5: no console edit may make us start answering another plugin's command.
        self.assertTrue(self.bl.is_blocked('今日老婆', ['今日天气']))

    def test_empty_config_still_blocks_the_defaults(self):
        # CF-5: an empty list means "defaults only", never "block nothing".
        for extra in ([], (), '', None):
            with self.subTest(extra=extra):
                self.assertTrue(self.bl.is_blocked('今日老婆', extra))

    def test_blank_entries_are_ignored(self):
        self.assertFalse(self.bl.is_blocked('今日黑丝', ['', '   ']))

    def test_a_blank_entry_does_not_block_everything(self):
        # An empty base name would prefix-match every command if not filtered.
        self.assertFalse(self.bl.is_blocked('今日任意', ['']))

    def test_defaults_are_immutable(self):
        before = tuple(self.bl.DEFAULT_BLOCKLIST)
        try:
            self.bl.DEFAULT_BLOCKLIST.append('今日黑丝')  # type: ignore[attr-defined]
        except AttributeError:
            pass
        self.assertEqual(tuple(self.bl.DEFAULT_BLOCKLIST), before)

    def test_empty_command_is_not_blocked(self):
        self.assertFalse(self.bl.is_blocked('', []))


if __name__ == '__main__':
    unittest.main()


class PrecedenceTests(unittest.TestCase):
    """A blocked name must lose to nothing -- not even a real folder of that name."""

    def setUp(self):
        self.bl = load_pure_module('blocklist')
        self.d = load_pure_module('dispatch')

    def test_blocklist_beats_an_existing_folder(self):
        # V-BLK-3 / US3 AS3. Someone creating data/TodayImage/老婆 must not make us
        # start answering TodayWaifu's command.
        index = {'老婆': '老婆', '萝莉': '萝莉'}
        images = {'老婆': ('/img/w.png',), '萝莉': ('/img/l.png',)}
        for command, suffix in (('今日老婆', '老婆'), ('今日萝莉', '萝莉')):
            with self.subTest(command=command):
                self.assertIsNone(
                    self.d.decide(command, suffix, index, images.get, [], is_direct=True)
                )

    def test_an_unblocked_folder_of_a_similar_name_still_works(self):
        # 今日老婆饼 starts with 今日老婆, so it IS blocked by prefix matching -- but a
        # genuinely unrelated name must not be caught.
        index = {'黑丝': '黑丝'}
        images = {'黑丝': ('/img/a.png',)}
        self.assertEqual(
            self.d.decide('今日黑丝', '黑丝', index, images.get, [], is_direct=True), '黑丝'
        )

    def test_operator_addition_takes_effect_without_restart_semantics(self):
        # The list is read per call, so a changed config value changes the outcome
        # immediately -- no module reload involved.
        index = {'天气': '天气'}
        images = {'天气': ('/img/t.png',)}
        self.assertEqual(
            self.d.decide('今日天气', '天气', index, images.get, [], is_direct=True), '天气'
        )
        self.assertIsNone(
            self.d.decide('今日天气', '天气', index, images.get, ['今日天气'], is_direct=True)
        )
