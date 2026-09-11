import unittest

from _loader import load_pure_module


class SpyIndex(dict):
    """A dict that records lookups, so we can prove the blocklist runs first."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queried = []

    def get(self, key, default=None):
        self.queried.append(key)
        return super().get(key, default)


class DecideTests(unittest.TestCase):
    def setUp(self):
        self.d = load_pure_module('dispatch')
        self.index = {'黑丝': '黑丝', '空的': '空的'}
        self.images = {'黑丝': ('/img/a.png',), '空的': ()}

    def decide(self, command, suffix, extra=None, index=None):
        # This class covers resolution and the blocklist, not feature 003's per-group
        # gate, so it exercises the ungated path (a direct chat). GroupGateTests below
        # covers the gate itself.
        return self.d.decide(
            command, suffix,
            index if index is not None else self.index,
            self.images.get,
            extra or [],
            is_direct=True,
        )

    def test_resolves_a_known_non_empty_category(self):
        self.assertEqual(self.decide('今日黑丝', '黑丝'), '黑丝')

    def test_unknown_suffix_returns_none(self):
        self.assertIsNone(self.decide('今日不存在', '不存在'))

    def test_empty_suffix_returns_none(self):
        self.assertIsNone(self.decide('今日', ''))

    def test_empty_category_returns_none(self):
        # V-DIS-1 / FR-113: an empty folder must look exactly like a missing one.
        self.assertIsNone(self.decide('今日空的', '空的'))

    def test_blocked_command_returns_none(self):
        self.assertIsNone(self.decide('今日老婆', '老婆'))

    def test_blocklist_is_checked_before_the_index(self):
        # FR-118 / V-BLK-2: a blocked name must never reach the filesystem layer.
        spy = SpyIndex({'老婆': '老婆'})
        self.assertIsNone(self.decide('今日老婆', '老婆', index=spy))
        self.assertEqual(spy.queried, [], 'index was queried for a blocked command')

    def test_blocklist_beats_a_real_folder_of_the_same_name(self):
        # V-BLK-3 / US3 AS3 -- the rule most likely to regress silently.
        index = {'老婆': '老婆'}
        images = {'老婆': ('/img/w.png',)}
        self.assertIsNone(
            self.d.decide('今日老婆', '老婆', index, images.get, [], is_direct=True)
        )

    def test_operator_blocklist_entry_is_honoured(self):
        self.assertIsNone(self.decide('今日黑丝', '黑丝', extra=['今日黑丝']))

    def test_traversal_suffixes_return_none(self):
        for suffix in ('../黑丝', '/etc/passwd', '黑丝/a.png', '..'):
            with self.subTest(suffix=suffix):
                self.assertIsNone(self.decide(f'今日{suffix}', suffix))

    def test_every_negative_returns_the_same_value(self):
        # The uniformity IS the requirement -- any distinguishable outcome is an oracle.
        outcomes = {
            self.decide('今日不存在', '不存在'),
            self.decide('今日空的', '空的'),
            self.decide('今日老婆', '老婆'),
            self.decide('今日', ''),
            self.decide('今日../x', '../x'),
        }
        self.assertEqual(outcomes, {None})

    def test_case_and_space_insensitive_resolution(self):
        index = {'alpha': 'Alpha'}
        images = {'Alpha': ('/img/a.png',)}
        self.assertEqual(
            self.d.decide('今日 ALPHA ', ' ALPHA ', index, images.get, [], is_direct=True),
            'Alpha',
        )


if __name__ == '__main__':
    unittest.main()


class ExplodingSet(frozenset):
    """Raises if membership is tested — proves the direct path never consults group state."""

    def __contains__(self, item):
        raise AssertionError('group permissions must not be consulted in a direct chat')


class SpyIndexGate(dict):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.queried = []

    def get(self, key, default=None):
        self.queried.append(key)
        return super().get(key, default)


class GroupGateTests(unittest.TestCase):
    """Feature 003: a tag is drawable in a group only if that group authorised it."""

    def setUp(self):
        self.d = load_pure_module('dispatch')
        self.index = {'黑丝': '黑丝', '白丝': '白丝', '空的': '空的'}
        self.images = {'黑丝': ('/img/a.png',), '白丝': ('/img/b.png',), '空的': ()}

    def decide(self, command, suffix, *, allowed=frozenset(), is_direct=False, extra=None, index=None):
        return self.d.decide(
            command, suffix,
            index if index is not None else self.index,
            self.images.get,
            extra or [],
            is_direct=is_direct,
            allowed_tags=allowed,
        )

    def test_group_with_no_authorisation_draws_nothing(self):
        # FR-203: deny by default.
        self.assertIsNone(self.decide('今日黑丝', '黑丝'))

    def test_authorised_tag_resolves(self):
        self.assertEqual(self.decide('今日黑丝', '黑丝', allowed={'黑丝'}), '黑丝')

    def test_authorisation_is_per_tag(self):
        self.assertIsNone(self.decide('今日白丝', '白丝', allowed={'黑丝'}))

    def test_authorisation_does_not_leak_between_groups(self):
        # Group B simply passes a different allowed set (FR-202).
        self.assertEqual(self.decide('今日黑丝', '黑丝', allowed={'黑丝'}), '黑丝')
        self.assertIsNone(self.decide('今日黑丝', '黑丝', allowed=frozenset()))

    def test_gate_is_checked_before_the_index(self):
        # V-GATE-3: an unauthorised group must not be able to infer folder existence.
        spy = SpyIndexGate(self.index)
        self.assertIsNone(self.decide('今日黑丝', '黑丝', index=spy))
        self.assertEqual(spy.queried, [], 'index queried for an unauthorised tag')

    def test_blocklist_still_wins_over_an_authorised_tag(self):
        # FR-206 / V-GATE-1: a group must not authorise its way to 今日老婆.
        index = {'老婆': '老婆'}
        images = {'老婆': ('/img/w.png',)}
        self.assertIsNone(
            self.d.decide('今日老婆', '老婆', index, images.get, [],
                          is_direct=False, allowed_tags={'老婆'})
        )

    def test_gate_matching_is_normalised(self):
        self.assertEqual(self.decide('今日 黑丝 ', ' 黑丝 ', allowed={'黑丝'}), '黑丝')

    def test_authorised_but_empty_folder_is_still_silent(self):
        self.assertIsNone(self.decide('今日空的', '空的', allowed={'空的'}))

    def test_every_negative_including_unauthorised_is_identical(self):
        # V-GATE-4 / SC-206: a fourth reason to be silent must not add a fourth observable.
        outcomes = {
            self.decide('今日黑丝', '黑丝'),                      # unauthorised
            self.decide('今日不存在', '不存在', allowed={'不存在'}),  # unknown
            self.decide('今日老婆', '老婆', allowed={'老婆'}),       # blocked
            self.decide('今日空的', '空的', allowed={'空的'}),       # empty
            self.decide('今日', ''),                              # bare prefix
        }
        self.assertEqual(outcomes, {None})


class DirectChatBypassTests(unittest.TestCase):
    """Feature 003 must not change direct chats at all (FR-204, I-302)."""

    def setUp(self):
        self.d = load_pure_module('dispatch')
        self.index = {'黑丝': '黑丝'}
        self.images = {'黑丝': ('/img/a.png',)}

    def test_direct_chat_resolves_without_any_authorisation(self):
        self.assertEqual(
            self.d.decide('今日黑丝', '黑丝', self.index, self.images.get, [],
                          is_direct=True, allowed_tags=frozenset()),
            '黑丝',
        )

    def test_direct_chat_never_consults_group_state(self):
        # V-GATE-2: the bypass precedes the gate rather than being folded into it.
        self.assertEqual(
            self.d.decide('今日黑丝', '黑丝', self.index, self.images.get, [],
                          is_direct=True, allowed_tags=ExplodingSet()),
            '黑丝',
        )

    def test_blocklist_still_applies_in_a_direct_chat(self):
        index = {'老婆': '老婆'}
        images = {'老婆': ('/img/w.png',)}
        self.assertIsNone(
            self.d.decide('今日老婆', '老婆', index, images.get, [],
                          is_direct=True, allowed_tags=ExplodingSet())
        )

    def test_unknown_tag_in_a_direct_chat_is_still_silent(self):
        self.assertIsNone(
            self.d.decide('今日不存在', '不存在', self.index, self.images.get, [],
                          is_direct=True, allowed_tags=ExplodingSet())
        )
