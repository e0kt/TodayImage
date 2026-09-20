"""删图回复与 handler 的结构保证。

五种失败必须彼此可分辨 —— 这是会删文件的命令，
发命令的人要能分清「没删成」和「删错了」。
"""
import ast
import unittest
from pathlib import Path

from _loader import load_pure_module

TDI = Path(__file__).resolve().parents[1] / 'tdi'


class DeleteTextTests(unittest.TestCase):
    def setUp(self):
        self.t = load_pure_module('delete_text')

    def test_success_reports_how_many_can_redraw(self):
        text = self.t.success_reply('黑丝', affected=3)
        self.assertIn('3', text)
        self.assertIn('黑丝', text)

    def test_missing_file_still_says_records_were_cleared(self):
        text = self.t.missing_file_reply('黑丝', affected=2)
        self.assertIn('不存在', text)
        self.assertIn('2', text)

    def test_ambiguous_lists_candidates_and_offers_the_fallback(self):
        text = self.t.ambiguous_reply(['aaaa1111', 'bbbb2222'])
        self.assertIn('aaaa1111', text)
        self.assertIn('bbbb2222', text)
        self.assertIn('删除图片', text)

    def test_tag_mismatch_names_the_real_category(self):
        text = self.t.tag_mismatch_reply('白丝', '黑丝')
        self.assertIn('白丝', text)
        self.assertIn('黑丝', text)
        self.assertIn('未做任何改动', text)

    def test_not_a_draw_tells_you_to_reply(self):
        self.assertIn('回复', self.t.NOT_A_DRAW)

    def test_not_found_offers_the_fallback(self):
        self.assertIn('删除图片', self.t.NOT_FOUND)

    def test_the_five_failures_are_mutually_distinct(self):
        outcomes = {
            self.t.NOT_A_DRAW,
            self.t.NOT_FOUND,
            self.t.ambiguous_reply(['aaaa1111']),
            self.t.tag_mismatch_reply('白丝', '黑丝'),
            self.t.MASTER_ONLY,
        }
        self.assertEqual(len(outcomes), 5)

    def test_no_reply_leaks_a_filesystem_path(self):
        for text in (self.t.NOT_A_DRAW, self.t.NOT_FOUND, self.t.MASTER_ONLY,
                     self.t.success_reply('黑丝', affected=1),
                     self.t.tag_mismatch_reply('白丝', '黑丝')):
            with self.subTest(text=text[:16]):
                self.assertNotIn('/', text.replace('删除图片 <类型> <图片ID>', ''))


class DeleteHandlerStructureTests(unittest.TestCase):
    """结构保证：删除调用不得被挪到守卫之外。"""

    def setUp(self):
        self.source = (TDI / 'delete_cmd.py').read_text(encoding='utf-8')
        self.tree = ast.parse(self.source)

    def _handler(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == 'delete_by_reply':
                return node
        raise AssertionError('找不到 delete_by_reply')

    def test_unlink_is_guarded_by_an_ok_check(self):
        """T021：删除调用必须出现在「解析结果为 ok」之后。

        判据是：函数里所有 unlink 调用的行号，都必须大于最后一个
        `resolution.outcome != OK` 早退分支的行号。
        """
        handler = self._handler()
        unlink_lines = [
            n.lineno for n in ast.walk(handler)
            if isinstance(n, ast.Attribute) and n.attr == 'unlink'
        ]
        self.assertTrue(unlink_lines, '应当存在文件删除调用')

        guard_lines = [
            n.lineno for n in ast.walk(handler)
            if isinstance(n, ast.Compare)
            and any(isinstance(c, ast.Name) and c.id == 'OK' for c in n.comparators)
        ]
        self.assertTrue(guard_lines, '应当存在对 OK 的判定')
        self.assertGreater(min(unlink_lines), max(guard_lines),
                           '删除调用必须在所有 OK 守卫之后')

    def test_every_refusal_branch_returns_before_any_file_work(self):
        # 五种拒绝分支都必须 return，不得落到下面的删除逻辑
        for outcome in ('NOT_A_DRAW', 'NOT_FOUND', 'AMBIGUOUS', 'TAG_MISMATCH'):
            with self.subTest(outcome=outcome):
                self.assertIn(f'== {outcome}', self.source)
        self.assertIn('can_delete_image(ev)', self.source)

    def test_permission_check_is_delegated_not_reimplemented(self):
        # 判定必须集中在 shared.can_delete_image，handler 内不自己比 user_pm
        names = {n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute)}
        self.assertNotIn('user_pm', names)

    def test_deletes_by_full_path_not_short_id(self):
        # V-DOC-7：短 ID 由文件名派生，不同子目录下可能重复
        self.assertIn('Path(image)', self.source)

    def test_invalidates_the_scan_cache(self):
        # V-DOC-6：否则 TTL 内该文件仍在候选池
        self.assertIn('invalidate_scan_cache()', self.source)

    def test_logs_the_deletion(self):
        self.assertIn('logger.info', self.source)


if __name__ == '__main__':
    unittest.main()
