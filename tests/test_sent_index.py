"""已发图片回执表：从回复反查「这是哪一张」的唯一依据。

实测（生产日志）：回复事件只给 reply_id 和被回复消息的**文本**，
image / image_list / image_id 全空 —— 拿不到被回复的那张图本身。
所以必须在发送时记下「消息 ID -> 文件路径」。
"""
import unittest

from _loader import load_pure_module


class SentIndexTests(unittest.TestCase):
    def setUp(self):
        self.si = load_pure_module('sent_index')
        self.idx = self.si.SentIndex(max_entries=4)

    def test_remembers_and_looks_up(self):
        self.idx.remember(['m1'], '/img/a.png', '黑丝', 'g1', 'u1')
        ref = self.idx.lookup('m1')
        self.assertIsNotNone(ref)
        self.assertEqual(ref.image, '/img/a.png')
        self.assertEqual(ref.category, '黑丝')
        self.assertEqual(ref.chat_key, 'g1')
        self.assertEqual(ref.user_key, 'u1')

    def test_multiple_ids_all_point_at_one_file(self):
        # V-SIR-5：平台可能把一次发送拆成多条消息，每条都可能被回复
        self.idx.remember(['m1', 'm2', 'm3'], '/img/a.png', '黑丝', 'g1', 'u1')
        for mid in ('m1', 'm2', 'm3'):
            with self.subTest(mid=mid):
                self.assertEqual(self.idx.lookup(mid).image, '/img/a.png')

    def test_unknown_id_returns_none_without_raising(self):
        # V-SIR-4：查不到是安全的，退回按当日记录唯一性解析
        self.assertIsNone(self.idx.lookup('nope'))

    def test_evicts_oldest_beyond_the_cap(self):
        # V-SIR-2：抽图高频，不设上限会单调增长
        for i in range(6):
            self.idx.remember([f'm{i}'], f'/img/{i}.png', '黑丝', 'g1', 'u1')
        self.assertLessEqual(self.idx.size, 4)
        self.assertIsNone(self.idx.lookup('m0'))
        self.assertIsNotNone(self.idx.lookup('m5'))

    def test_lookup_refreshes_recency(self):
        for i in range(4):
            self.idx.remember([f'm{i}'], f'/img/{i}.png', '黑丝', 'g1', 'u1')
        self.idx.lookup('m0')
        self.idx.remember(['m9'], '/img/9.png', '黑丝', 'g1', 'u1')
        self.assertIsNotNone(self.idx.lookup('m0'), '刚用过的不该被淘汰')

    def test_empty_or_missing_ids_are_not_stored(self):
        # V-SIR-1：拿不到回执时静默跳过，不得报错
        for ids in ([], None, [''], [None]):
            with self.subTest(ids=ids):
                self.idx.remember(ids, '/img/a.png', '黑丝', 'g1', 'u1')
        self.assertEqual(self.idx.size, 0)

    def test_ids_are_normalised_to_strings(self):
        self.idx.remember([12345], '/img/a.png', '黑丝', 'g1', 'u1')
        self.assertIsNotNone(self.idx.lookup('12345'))
        self.assertIsNotNone(self.idx.lookup(12345))

    def test_empty_image_is_not_stored(self):
        self.idx.remember(['m1'], '', '黑丝', 'g1', 'u1')
        self.assertIsNone(self.idx.lookup('m1'))


if __name__ == '__main__':
    unittest.main()


class RecentDrawTests(unittest.TestCase):
    """按发送时间兜底：适配器不返回消息 ID 时，靠「最近发出的那张」定位。

    这是刻意接受的一个取舍 —— 回复一张旧图时会删错。
    所以必须有时间窗，且调用方要在回复里说明用的是这条路径。
    """

    def setUp(self):
        self.si = load_pure_module('sent_index')
        self.idx = self.si.SentIndex(max_entries=8)

    def test_recency_is_recorded_even_without_message_ids(self):
        # 最关键的一条：适配器不给 ID 时，第 1 级注定失效，
        # 若那时连时间线也不记，第 3 级同样没数据可用。
        self.idx.remember(None, '/img/a.png', '靴子', 'g1', 'u1', now=100.0)
        self.assertIsNone(self.idx.lookup('whatever'))
        ref = self.idx.recent('g1', '靴子', now=101.0, within=60)
        self.assertIsNotNone(ref)
        self.assertEqual(ref.image, '/img/a.png')

    def test_recent_returns_the_latest_draw(self):
        self.idx.remember(None, '/img/a.png', '靴子', 'g1', 'u1', now=100.0)
        self.idx.remember(None, '/img/b.png', '靴子', 'g1', 'u2', now=200.0)
        self.assertEqual(self.idx.recent('g1', '靴子', now=201.0, within=600).image, '/img/b.png')

    def test_recent_is_scoped_per_chat_and_category(self):
        self.idx.remember(None, '/img/a.png', '靴子', 'g1', 'u1', now=100.0)
        self.idx.remember(None, '/img/w.png', '白丝', 'g1', 'u1', now=110.0)
        self.idx.remember(None, '/img/o.png', '靴子', 'g2', 'u1', now=120.0)
        self.assertEqual(self.idx.recent('g1', '靴子', now=130.0, within=600).image, '/img/a.png')
        self.assertEqual(self.idx.recent('g1', '白丝', now=130.0, within=600).image, '/img/w.png')
        self.assertEqual(self.idx.recent('g2', '靴子', now=130.0, within=600).image, '/img/o.png')

    def test_outside_the_window_returns_none(self):
        # 时间窗是这条路径唯一的安全边界：回复很久以前的图必须落空而不是删错
        self.idx.remember(None, '/img/a.png', '靴子', 'g1', 'u1', now=100.0)
        self.assertIsNone(self.idx.recent('g1', '靴子', now=100.0 + 601, within=600))

    def test_unknown_chat_or_category_returns_none(self):
        self.assertIsNone(self.idx.recent('nope', '靴子', now=1.0, within=600))

    def test_category_is_normalised(self):
        self.idx.remember(None, '/img/a.png', '靴子', 'g1', 'u1', now=100.0)
        for probe in ('靴子', ' 靴子 ', '【靴子】'):
            with self.subTest(probe=probe):
                self.assertIsNotNone(self.idx.recent('g1', probe, now=101.0, within=600))

    def test_message_id_path_still_works_alongside_recency(self):
        self.idx.remember(['m1'], '/img/a.png', '靴子', 'g1', 'u1', now=100.0)
        self.assertEqual(self.idx.lookup('m1').image, '/img/a.png')
        self.assertEqual(self.idx.recent('g1', '靴子', now=101.0, within=600).image, '/img/a.png')

    def test_recency_entries_are_bounded(self):
        for i in range(30):
            self.idx.remember(None, f'/img/{i}.png', '靴子', f'g{i}', 'u1', now=float(i))
        self.assertLessEqual(self.idx.recent_size, 8)
