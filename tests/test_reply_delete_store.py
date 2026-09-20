"""按图片路径清理当日记录：删图之后让持有者能重抽。

图库是全局的 —— 同一张图可能被多个群、多个用户抽到，
所以必须扫描当天**全部**记录，而不只是命令所在的那个会话。
"""
import asyncio
import tempfile
import unittest
from pathlib import Path

from _loader import load_pure_module

DATE = '2026-09-19'


class RecordsHoldingImageTests(unittest.TestCase):
    def setUp(self):
        self.ds = load_pure_module('daily_store')

    def test_finds_holders_across_chats_and_users(self):
        recs = {
            self.ds.record_key('g1', 'u1', '黑丝'): {'image': '/img/a.png'},
            self.ds.record_key('g2', 'u2', '黑丝'): {'image': '/img/a.png'},
            self.ds.record_key('g1', 'u3', '黑丝'): {'image': '/img/b.png'},
        }
        holders = self.ds.records_holding_image(recs, '/img/a.png')
        self.assertEqual(len(holders), 2)

    def test_same_filename_in_a_different_directory_is_not_matched(self):
        # V-DOC-7：按完整路径匹配，不按 8 位短 ID
        recs = {
            self.ds.record_key('g1', 'u1', '黑丝'): {'image': '/img/黑丝/x.png'},
            self.ds.record_key('g1', 'u2', '黑丝'): {'image': '/img/白丝/x.png'},
        }
        self.assertEqual(len(self.ds.records_holding_image(recs, '/img/黑丝/x.png')), 1)

    def test_no_holder_returns_empty(self):
        self.assertEqual(self.ds.records_holding_image({}, '/img/a.png'), ())


class ClearRecordsForImageTests(unittest.TestCase):
    def setUp(self):
        self.ds = load_pure_module('daily_store')
        self.ds.clear_locks()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'daily_records.json'

    def tearDown(self):
        self.temp.cleanup()

    def seed(self, *triples):
        for chat, user, cat, img in triples:
            self.ds.upsert_record(self.path, DATE, self.ds.record_key(chat, user, cat), img)

    def test_clears_every_holder_across_chats(self):
        self.seed(('g1', 'u1', '黑丝', '/img/a.png'),
                  ('g2', 'u2', '黑丝', '/img/a.png'),
                  ('g1', 'u3', '黑丝', '/img/b.png'))
        cleared, chats = asyncio.run(
            self.ds.clear_records_for_image(self.path, DATE, '/img/a.png'))
        self.assertEqual(cleared, 2)
        self.assertEqual(chats, 2)
        remaining = self.ds.load_records(self.path, DATE)
        self.assertEqual(list(remaining), [self.ds.record_key('g1', 'u3', '黑丝')])

    def test_bumps_epoch_and_excludes_for_each_affected_pair(self):
        # V-DOC-5：复用 004 的机制，保证重抽必定换图
        self.seed(('g1', 'u1', '黑丝', '/img/a.png'), ('g2', 'u2', '黑丝', '/img/a.png'))
        asyncio.run(self.ds.clear_records_for_image(self.path, DATE, '/img/a.png'))
        resets = self.ds.load_resets(self.path, DATE)
        excludes = self.ds.load_excludes(self.path, DATE)
        for chat in ('g1', 'g2'):
            with self.subTest(chat=chat):
                self.assertEqual(self.ds.reset_epoch(resets, chat, '黑丝'), 1)
                self.assertIn('/img/a.png', excludes[self.ds.reset_key(chat, '黑丝')])

    def test_no_holder_is_not_an_error(self):
        cleared, chats = asyncio.run(
            self.ds.clear_records_for_image(self.path, DATE, '/img/nobody.png'))
        self.assertEqual((cleared, chats), (0, 0))

    def test_other_categories_are_untouched(self):
        self.seed(('g1', 'u1', '黑丝', '/img/a.png'), ('g1', 'u1', '白丝', '/img/w.png'))
        asyncio.run(self.ds.clear_records_for_image(self.path, DATE, '/img/a.png'))
        remaining = self.ds.load_records(self.path, DATE)
        self.assertIn(self.ds.record_key('g1', 'u1', '白丝'), remaining)


if __name__ == '__main__':
    unittest.main()


class DeleteThenRedrawTests(unittest.TestCase):
    """删图之后，持有者必须拿到**另一张**，而不是静默。"""

    def setUp(self):
        self.ds = load_pure_module('daily_store')
        self.ds.clear_locks()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'daily_records.json'
        self.images = tuple(f'/img/{i}.png' for i in range(30))

    def tearDown(self):
        self.temp.cleanup()

    def draw(self, chat, user, alive=None):
        pool = alive if alive is not None else self.images
        return asyncio.run(self.ds.resolve_daily_image(
            self.path, DATE, chat, user, '黑丝', pool,
            exists=lambda p: p in pool, unique_per_chat=True))

    def test_holders_in_two_chats_both_redraw_to_something_new(self):
        # FR-508 / SC-504：图库全局，别的群抽到同一张也要能重抽
        a = self.draw('g1', 'u1')
        self.ds.clear_locks()
        # 构造 g2 的用户也持有同一张
        self.ds.upsert_record(self.path, DATE, self.ds.record_key('g2', 'u2', '黑丝'), a)

        self.ds.clear_locks()
        cleared, chats = asyncio.run(self.ds.clear_records_for_image(self.path, DATE, a))
        self.assertEqual((cleared, chats), (2, 2))

        alive = tuple(p for p in self.images if p != a)
        self.ds.clear_locks()
        self.assertNotEqual(self.draw('g1', 'u1', alive), a)
        self.ds.clear_locks()
        self.assertNotEqual(self.draw('g2', 'u2', alive), a)

    def test_deleted_image_is_never_drawn_again(self):
        # FR-509 / I-502：进了排除集，即便还在候选列表里也不会被选中
        a = self.draw('g1', 'u1')
        self.ds.clear_locks()
        asyncio.run(self.ds.clear_records_for_image(self.path, DATE, a))
        for user in (f'u{i}' for i in range(10)):
            self.ds.clear_locks()
            # 故意仍把被删图放进候选池，验证排除集确实生效
            self.assertNotEqual(self.draw('g1', user), a)

    def test_new_round_still_avoids_collisions(self):
        users = [f'u{i}' for i in range(5)]
        first = [self.draw('g1', u) for u in users]
        target = first[0]
        self.ds.clear_locks()
        asyncio.run(self.ds.clear_records_for_image(self.path, DATE, target))
        alive = tuple(p for p in self.images if p != target)
        self.ds.clear_locks()
        second = [self.draw('g1', u, alive) for u in users]
        self.assertNotIn(target, second)
        self.assertEqual(len(set(second)), len(users))

    def test_empty_gallery_after_deletion_is_silent_not_an_error(self):
        self.draw('g1', 'u1', ('/img/only.png',))
        self.ds.clear_locks()
        asyncio.run(self.ds.clear_records_for_image(self.path, DATE, '/img/only.png'))
        self.ds.clear_locks()
        self.assertIsNone(asyncio.run(self.ds.resolve_daily_image(
            self.path, DATE, 'g1', 'u1', '黑丝', (), exists=lambda p: False)))
