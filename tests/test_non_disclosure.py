"""The silence contract: every public negative must be indistinguishable.

Feature 001 replied "不存在图片类型【X】" for an unknown name and printed the image root
in the help and the empty-category hint. Together those let anyone enumerate the host's
folders by difference in replies. These tests assert the difference is gone.
"""
import re
import unittest
from pathlib import Path

from _loader import load_pure_module

TDI = Path(__file__).resolve().parents[1] / 'tdi'


class UniformNegativeTests(unittest.TestCase):
    def setUp(self):
        self.d = load_pure_module('dispatch')
        self.index = {'黑丝': '黑丝', '空的': '空的'}
        self.images = {'黑丝': ('/img/a.png',), '空的': ()}

    def decide(self, command, suffix):
        # Ungated path: this class asserts the uniformity of negatives, which must hold
        # independently of feature 003's gate (GroupGateTests covers the gated case).
        return self.d.decide(command, suffix, self.index, self.images.get, [], is_direct=True)

    def test_unknown_blocked_empty_and_malformed_are_identical(self):
        outcomes = [
            self.decide('今日不存在', '不存在'),   # unknown
            self.decide('今日老婆', '老婆'),       # blocked
            self.decide('今日空的', '空的'),       # exists but empty
            self.decide('今日', ''),               # bare prefix
            self.decide('今日../etc', '../etc'),   # malformed
        ]
        self.assertEqual(set(outcomes), {None})
        self.assertEqual(len(set(map(repr, outcomes))), 1)

    def test_an_existing_empty_folder_is_not_distinguishable_from_a_missing_one(self):
        # FR-113 -- otherwise "no images" becomes the oracle instead.
        self.assertEqual(self.decide('今日空的', '空的'), self.decide('今日没有这个', '没有这个'))


class HandlerSourceTests(unittest.TestCase):
    """Structural guards: a reply re-added to a miss path would silently reopen the oracle."""

    def test_daily_handler_never_sends_text(self):
        source = (TDI / 'daily.py').read_text(encoding='utf-8')
        self.assertNotIn('send_text', source,
                         'the draw handler must answer with an image or not at all')

    def test_daily_handler_has_no_user_facing_category_message(self):
        source = (TDI / 'daily.py').read_text(encoding='utf-8')
        for phrase in ('还没有图片', '不存在图片类型', '暂无图片'):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, source)

    def test_dispatch_exposes_reasons_only_for_logging(self):
        source = (TDI / 'dispatch.py').read_text(encoding='utf-8')
        self.assertIn('miss_reason', source)
        # The reason strings are ASCII log tokens, never Chinese user-facing copy.
        reasons = re.findall(r"return '(\w+)'", source)
        self.assertTrue({'blocked', 'unknown', 'empty'} <= set(reasons))

    def test_public_handler_cannot_reference_the_image_root(self):
        # A path in a public reply is the other half of the oracle (V-DIS-2).
        source = (TDI / 'daily.py').read_text(encoding='utf-8')
        for token in ('image_root', 'data_root'):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_path_disclosure_lives_only_in_master_gated_handlers(self):
        # manage.py may print the root: its listing SV is pm=1 (FR-112). Assert the
        # commands that do so are registered on the master-only service.
        source = (TDI / 'manage.py').read_text(encoding='utf-8')
        for line in source.splitlines():
            if 'image_root()' in line and 'f\'' in line:
                self.assertIn('新增类型', line + source, 'unexpected path disclosure site')

    def test_group_listing_branch_never_reaches_the_image_root(self):
        """「查看图片」在群里必须先收敛再回复：群分支内不得出现 image_root。

        这是 V-DIS-2 在管理命令上的落点。pm=1 限制了谁能调用，但回复是发回原会话的,
        群里每个人都会读到 —— FR-110 管的是「对非主人可见的回复」，不是「发给谁」。
        用 AST 而非字符串匹配，改写措辞不会让这条守卫失效。
        """
        import ast

        tree = ast.parse((TDI / 'manage.py').read_text(encoding='utf-8'))
        handler = next(
            (n for n in ast.walk(tree)
             if isinstance(n, ast.AsyncFunctionDef) and n.name == 'list_images'),
            None,
        )
        self.assertIsNotNone(handler, 'list_images handler not found')

        branches = [
            n for n in ast.walk(handler)
            if isinstance(n, ast.If)
            and isinstance(n.test, ast.UnaryOp) and isinstance(n.test.op, ast.Not)
            and isinstance(n.test.operand, ast.Name) and n.test.operand.id == 'is_direct'
        ]
        self.assertTrue(branches, 'no `if not is_direct:` guard in list_images')

        for branch in branches:
            names = {n.id for n in ast.walk(branch) if isinstance(n, ast.Name)}
            self.assertNotIn('image_root', names,
                             'the group branch must not disclose the image root')
            self.assertIn('allowed', names,
                          'the group branch must scope the listing to authorised tags')

    def test_group_listing_is_scoped_by_authorisation(self):
        """群聊分支必须按本群授权过滤，而不是把整个图库列出来。"""
        source = (TDI / 'manage.py').read_text(encoding='utf-8')
        self.assertIn('_visible_in_group', source)
        self.assertIn('allowed_tags_for', source,
                      'group listing must read the per-group authorisation table')

    def test_silent_paths_are_logged(self):
        source = (TDI / 'daily.py').read_text(encoding='utf-8')
        self.assertIn('logger.debug', source,
                      'chat observability is traded away; log observability is not')


if __name__ == '__main__':
    unittest.main()
