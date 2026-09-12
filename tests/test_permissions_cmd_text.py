"""Reply builders for the group-authorisation commands.

Two rules here are easy to get wrong and invisible in production:
  - a direct chat must be *explained*, not silently ignored (FR-214)
  - the list may describe THIS group only, never the server's folders (FR-215)
"""
import re
import unittest
from pathlib import Path

from _loader import load_pure_module

TDI = Path(__file__).resolve().parents[1] / 'tdi'


class AllowReplyTests(unittest.TestCase):
    def setUp(self):
        self.t = load_pure_module('permissions_text')

    def test_new_authorisation_confirms(self):
        text = self.t.allow_reply('黑丝', newly_added=True, folder_exists=True)
        self.assertIn('黑丝', text)
        self.assertNotIn(self.t.MISSING_FOLDER_NOTE, text)

    def test_already_authorised_is_reported_not_repeated(self):
        text = self.t.allow_reply('黑丝', newly_added=False, folder_exists=True)
        self.assertIn('已经允许', text)

    def test_missing_folder_is_warned(self):
        # FR-213 / V-GRP-7: permission and existence are independent.
        text = self.t.allow_reply('黑丝', newly_added=True, folder_exists=False)
        self.assertIn(self.t.MISSING_FOLDER_NOTE, text)

    def test_already_authorised_does_not_warn(self):
        text = self.t.allow_reply('黑丝', newly_added=False, folder_exists=False)
        self.assertNotIn(self.t.MISSING_FOLDER_NOTE, text)


class DenyReplyTests(unittest.TestCase):
    def setUp(self):
        self.t = load_pure_module('permissions_text')

    def test_revocation_confirms(self):
        self.assertIn('已禁止', self.t.deny_reply('黑丝', removed=True))

    def test_revoking_an_unauthorised_tag_is_reported(self):
        self.assertIn('本来就没有', self.t.deny_reply('黑丝', removed=False))


class ListReplyTests(unittest.TestCase):
    def setUp(self):
        self.t = load_pure_module('permissions_text')

    def test_lists_this_group_tags(self):
        text = self.t.list_reply(['黑丝', '白丝'])
        self.assertIn('黑丝', text)
        self.assertIn('白丝', text)

    def test_empty_group_explains_how_to_authorise(self):
        text = self.t.list_reply([])
        self.assertIn('TodayImage允许', text)

    def test_flags_authorised_tags_with_no_folder(self):
        text = self.t.list_reply(['黑丝', '幽灵'], missing=['幽灵'])
        self.assertIn('幽灵', text)
        self.assertIn('没有对应文件夹', text)

    def test_output_is_sorted_for_stability(self):
        self.assertEqual(self.t.list_reply(['b', 'a']), self.t.list_reply(['a', 'b']))

    def test_never_mentions_the_image_root(self):
        text = self.t.list_reply(['黑丝'])
        for token in ('/Users', 'data/TodayImage', 'images'):
            with self.subTest(token=token):
                self.assertNotIn(token, text)


class DirectChatTests(unittest.TestCase):
    def setUp(self):
        self.t = load_pure_module('permissions_text')

    def test_setting_commands_explain_themselves_in_a_direct_chat(self):
        # FR-214 / US3 AS3: explained, not silently ignored.
        self.assertIn('群', self.t.DIRECT_CHAT_SETTING)
        self.assertIn('私聊', self.t.DIRECT_CHAT_SETTING)

    def test_list_command_explains_direct_chats_are_unrestricted(self):
        self.assertIn('不受', self.t.DIRECT_CHAT_LIST)


class HandlerSourceTests(unittest.TestCase):
    def test_handlers_do_not_re_check_permission(self):
        # research R1: the SV's pm=3 is the single source of truth. A second check in
        # the handler is how the two drift apart. Scanned via AST so the module's own
        # docstring explaining *why* there is no check does not trip the assertion.
        import ast
        tree = ast.parse((TDI / 'permissions_cmd.py').read_text(encoding='utf-8'))
        names = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        for token in ('user_pm', 'is_master', 'can_upload'):
            with self.subTest(token=token):
                self.assertNotIn(token, names)

    def test_handlers_never_enumerate_the_server_folders(self):
        import ast
        tree = ast.parse((TDI / 'permissions_cmd.py').read_text(encoding='utf-8'))
        names = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        for token in ('load_categories', 'image_root'):
            with self.subTest(token=token):
                self.assertNotIn(token, names)

    def test_every_handler_guards_against_a_direct_chat(self):
        source = (TDI / 'permissions_cmd.py').read_text(encoding='utf-8')
        handlers = re.findall(r'async def (\w+)\(bot: Bot, ev: Event\):(.*?)(?=\n@|\Z)', source, re.S)
        self.assertEqual(len(handlers), 3)
        for name, body in handlers:
            with self.subTest(handler=name):
                self.assertIn('is_direct_chat(ev)', body)

    def test_no_handler_classifies_a_chat_by_group_id(self):
        # Adapter safety: user_type has four values (group/direct/channel/sub_channel).
        # Discord uses channel and sub_channel, so `group_id is None` would read a guild
        # channel as a private chat and bypass the per-group gate. Classification must
        # go through chat_context, which is what the core itself does.
        source = (TDI / 'permissions_cmd.py').read_text(encoding='utf-8')
        self.assertNotIn('ev.group_id', source)


if __name__ == '__main__':
    unittest.main()
