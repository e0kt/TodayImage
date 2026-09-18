"""重置命令的回复与权限来源。"""
import ast
import unittest
from pathlib import Path

from _loader import load_pure_module

TDI = Path(__file__).resolve().parents[1] / 'tdi'


def _names(module_name: str) -> set[str]:
    tree = ast.parse((TDI / module_name).read_text(encoding='utf-8'))
    return (
        {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    )


class ResetReplyTests(unittest.TestCase):
    def setUp(self):
        self.t = load_pure_module('reset_text')

    def test_success_reply_reports_the_cleared_count(self):
        # FR-412：重置是看不见的操作，条数是最小且最有信息量的反馈
        text = self.t.reset_reply('黑丝', cleared=3)
        self.assertIn('3', text)
        self.assertIn('黑丝', text)

    def test_zero_cleared_is_explained_not_reported_as_an_error(self):
        # FR-413 / V-RES-1
        text = self.t.reset_reply('黑丝', cleared=0)
        self.assertIn('0', text)
        self.assertNotIn('失败', text)
        self.assertNotIn('错误', text)

    def test_missing_folder_adds_a_note_without_blocking(self):
        # FR-417 / V-RES-3
        text = self.t.reset_reply('幽灵', cleared=0, folder_exists=False)
        self.assertIn(self.t.MISSING_FOLDER_NOTE, text)

    def test_existing_folder_adds_no_note(self):
        self.assertNotIn(
            self.t.MISSING_FOLDER_NOTE, self.t.reset_reply('黑丝', cleared=1, folder_exists=True)
        )

    def test_direct_chat_is_explained(self):
        # FR-415：私聊给解释而不是静默
        self.assertIn('私聊', self.t.DIRECT_CHAT)
        self.assertIn('群', self.t.DIRECT_CHAT)

    def test_usage_names_the_command(self):
        # FR-416
        self.assertIn('TodayImage重置', self.t.USAGE)

    def test_the_four_outcomes_are_mutually_distinct(self):
        # SC-407：四种情形必须彼此不同，否则发命令的人分不清发生了什么
        outcomes = {
            self.t.reset_reply('黑丝', cleared=3),
            self.t.reset_reply('黑丝', cleared=0),
            self.t.reset_reply('幽灵', cleared=0, folder_exists=False),
            self.t.DIRECT_CHAT,
            self.t.USAGE,
        }
        self.assertEqual(len(outcomes), 5)


class ResetHandlerSourceTests(unittest.TestCase):
    def test_handler_does_not_re_check_permission(self):
        # research R2：SV 的 pm=1 是唯一事实来源。用 AST 扫描，避免被解释性的
        # 文档字符串误伤（003 那次就踩过）。
        names = _names('reset_cmd.py')
        for token in ('user_pm', 'is_master', 'can_upload'):
            with self.subTest(token=token):
                self.assertNotIn(token, names)

    def test_handler_classifies_chats_via_chat_context(self):
        # 频道型平台上用 group_id 判私聊会出错
        source = (TDI / 'reset_cmd.py').read_text(encoding='utf-8')
        self.assertIn('is_direct_chat(ev)', source)
        self.assertNotIn('ev.group_id', source)

    def test_handler_guards_direct_chat_empty_arg_and_missing_folder(self):
        source = (TDI / 'reset_cmd.py').read_text(encoding='utf-8')
        for token in ('DIRECT_CHAT', 'USAGE', 'folder_exists'):
            with self.subTest(token=token):
                self.assertIn(token, source)

    def test_handler_logs_the_operation(self):
        # 唯一会改变全群当日结果的人工操作，必须留痕
        self.assertIn('logger.info', (TDI / 'reset_cmd.py').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
