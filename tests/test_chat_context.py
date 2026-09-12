"""How a chat is classified — the single riskiest thing for a new adapter.

GsCore's own code (models.py:282, bot.py:735/1029/1095) decides "is this a private
chat?" with `user_type != "direct"`, never with `group_id`. `user_type` has FOUR
values: group, direct, channel, sub_channel. Discord/KOOK/QQ-guild adapters use
channel and sub_channel.

TodayImage originally tested `group_id is None`. On an adapter that sends
user_type='channel' without populating group_id, that reads as a private chat — which
would bypass feature 003's per-group authorisation entirely and serve a public server
channel ungated. These tests pin the classification to the core's own rule.
"""
import unittest

from _loader import load_pure_module


class FakeEvent:
    def __init__(self, user_type='group', group_id=None):
        self.user_type = user_type
        self.group_id = group_id


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.cc = load_pure_module('chat_context')

    def test_direct_is_direct(self):
        self.assertTrue(self.cc.is_direct_chat(FakeEvent('direct', None)))
        self.assertTrue(self.cc.is_direct_chat(FakeEvent('direct', '123')))

    def test_group_with_an_id_is_not_direct(self):
        self.assertFalse(self.cc.is_direct_chat(FakeEvent('group', '123')))

    def test_discord_style_channel_is_never_direct(self):
        # The bug this module exists to prevent: a guild channel must be gated even if
        # the adapter leaves group_id unset.
        for user_type in ('channel', 'sub_channel'):
            for group_id in ('123', None, ''):
                with self.subTest(user_type=user_type, group_id=group_id):
                    self.assertFalse(self.cc.is_direct_chat(FakeEvent(user_type, group_id)))

    def test_legacy_adapter_group_default_without_an_id_is_direct(self):
        # user_type defaults to 'group'; an adapter that forgets to set 'direct' for a
        # DM leaves group_id None. Treating that as a group would black out DMs.
        self.assertTrue(self.cc.is_direct_chat(FakeEvent('group', None)))
        self.assertTrue(self.cc.is_direct_chat(FakeEvent('group', '')))

    def test_missing_user_type_falls_back_to_group_id(self):
        class Bare:
            group_id = None
        self.assertTrue(self.cc.is_direct_chat(Bare()))

        class BareGroup:
            group_id = '123'
        self.assertFalse(self.cc.is_direct_chat(BareGroup()))

    def test_unknown_user_type_with_an_id_fails_closed(self):
        # An adapter inventing a new value must not accidentally open the gate.
        self.assertFalse(self.cc.is_direct_chat(FakeEvent('guild_forum', '123')))
        self.assertFalse(self.cc.is_direct_chat(FakeEvent('guild_forum', None)))


class ChatKeyTests(unittest.TestCase):
    def setUp(self):
        self.cc = load_pure_module('chat_context')

    def test_group_key_is_the_group_id(self):
        self.assertEqual(self.cc.chat_group_key(FakeEvent('group', '123')), '123')

    def test_channel_key_is_the_group_id(self):
        self.assertEqual(self.cc.chat_group_key(FakeEvent('channel', 'c456')), 'c456')

    def test_direct_chat_has_no_group_key(self):
        self.assertEqual(self.cc.chat_group_key(FakeEvent('direct', None)), '')

    def test_channel_without_an_id_yields_an_empty_key_not_a_bypass(self):
        # Empty key = its own permission bucket that nobody has authorised = denied.
        # Wrong-ish, but it fails closed, which is the required direction.
        self.assertEqual(self.cc.chat_group_key(FakeEvent('channel', None)), '')
        self.assertFalse(self.cc.is_direct_chat(FakeEvent('channel', None)))


if __name__ == '__main__':
    unittest.main()


class CallSiteTests(unittest.TestCase):
    """No module may classify a chat by group_id any more — only chat_context may."""

    def test_no_module_outside_chat_context_uses_group_id_for_classification(self):
        import re
        from pathlib import Path
        tdi = Path(__file__).resolve().parents[1] / 'tdi'
        offenders = []
        for path in sorted(tdi.glob('*.py')):
            if path.stem in ('chat_context', 'group_permissions'):
                continue  # chat_context owns the rule; group_permissions just normalises a key
            source = path.read_text(encoding='utf-8')
            if re.search(r'group_id\s+is\s+(not\s+)?None', source):
                offenders.append(path.name)
        self.assertEqual(
            offenders, [],
            'classify chats with chat_context.is_direct_chat, not group_id',
        )
