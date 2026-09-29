"""三级解析：这条「回复 + 删除<标签>」对应哪一张图，或为什么不能确定。

本功能会**永久删除文件**，所以拒绝路径比成功路径更要紧：
除 ok 外的任何结果都不得携带可删除的文件路径。
"""
import unittest

from _loader import load_pure_module


class Ref:
    def __init__(self, image, category, chat_key='g1', user_key='u1'):
        self.image = image
        self.category = category
        self.chat_key = chat_key
        self.user_key = user_key


class FakeIndex:
    """最小化的回执表替身。默认不提供时间兜底，用于测试前两级精确路径。"""

    def __init__(self, mapping=None, recent_ref=None):
        self._m = mapping or {}
        self._recent = recent_ref

    def lookup(self, message_id):
        return self._m.get(str(message_id))

    def recent(self, chat_key, category, now=None, within=0.0):
        return self._recent if within > 0 else None


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.dr = load_pure_module('delete_resolve')
        self.ds = load_pure_module('daily_store')
        self.category_of = {'/img/黑丝/a.png': '黑丝', '/img/黑丝/b.png': '黑丝',
                            '/img/白丝/c.png': '白丝'}

    def records(self, *triples):
        return {self.ds.record_key(c, u, cat): {'image': img}
                for c, u, cat, img in triples}

    def resolve(self, reply_id, tag, index=None, records=None):
        return self.dr.resolve(
            reply_id, tag,
            index if index is not None else FakeIndex(),
            records if records is not None else {},
            self.category_of.get,
            chat_key='g1',
        )

    # ── 第 1 级：回执表命中 ──
    def test_receipt_hit_is_unambiguous(self):
        idx = FakeIndex({'m1': Ref('/img/黑丝/a.png', '黑丝')})
        r = self.resolve('m1', '黑丝', index=idx)
        self.assertEqual(r.outcome, 'ok')
        self.assertEqual(r.image, '/img/黑丝/a.png')

    # ── 第 2 级：当日记录唯一 ──
    def test_falls_back_to_a_unique_record(self):
        recs = self.records(('g1', 'u1', '黑丝', '/img/黑丝/a.png'))
        r = self.resolve('unknown-id', '黑丝', records=recs)
        self.assertEqual(r.outcome, 'ok')
        self.assertEqual(r.image, '/img/黑丝/a.png')

    def test_unique_record_is_scoped_to_this_chat_and_category(self):
        recs = self.records(
            ('g1', 'u1', '黑丝', '/img/黑丝/a.png'),
            ('g2', 'u9', '黑丝', '/img/黑丝/b.png'),
            ('g1', 'u2', '白丝', '/img/白丝/c.png'),
        )
        r = self.resolve('unknown-id', '黑丝', records=recs)
        self.assertEqual(r.outcome, 'ok')
        self.assertEqual(r.image, '/img/黑丝/a.png')

    # ── 第 3 级：拒绝 ──
    def test_no_reply_id_is_not_a_draw(self):
        for reply_id in ('', None):
            with self.subTest(reply_id=reply_id):
                self.assertEqual(self.resolve(reply_id, '黑丝').outcome, 'not_a_draw')

    def test_nothing_to_go_on_is_not_found(self):
        self.assertEqual(self.resolve('m1', '黑丝').outcome, 'not_found')

    def test_multiple_records_are_ambiguous_with_candidates(self):
        recs = self.records(
            ('g1', 'u1', '黑丝', '/img/黑丝/a.png'),
            ('g1', 'u2', '黑丝', '/img/黑丝/b.png'),
        )
        r = self.resolve('unknown-id', '黑丝', records=recs)
        self.assertEqual(r.outcome, 'ambiguous')
        self.assertEqual(len(r.candidates), 2)

    def test_tag_mismatch_reports_the_real_category(self):
        # V-DRS-2：防「看错了图，删错了类型」
        idx = FakeIndex({'m1': Ref('/img/白丝/c.png', '白丝')})
        r = self.resolve('m1', '黑丝', index=idx)
        self.assertEqual(r.outcome, 'tag_mismatch')
        self.assertEqual(r.actual_category, '白丝')

    # ── 安全性质 ──
    def test_no_non_ok_outcome_carries_a_deletable_path(self):
        """V-DRS-1：这是本功能的安全核心。"""
        idx = FakeIndex({'m1': Ref('/img/白丝/c.png', '白丝')})
        recs = self.records(
            ('g1', 'u1', '黑丝', '/img/黑丝/a.png'),
            ('g1', 'u2', '黑丝', '/img/黑丝/b.png'),
        )
        for label, r in (
            ('not_a_draw', self.resolve(None, '黑丝')),
            ('not_found', self.resolve('m9', '黑丝')),
            ('ambiguous', self.resolve('m9', '黑丝', records=recs)),
            ('tag_mismatch', self.resolve('m1', '黑丝', index=idx)),
        ):
            with self.subTest(outcome=label):
                self.assertNotEqual(r.outcome, 'ok')
                self.assertIsNone(r.image, f'{label} 不得携带可删除的路径')

    def test_the_five_outcomes_are_distinct(self):
        idx = FakeIndex({'m1': Ref('/img/黑丝/a.png', '黑丝'),
                         'm2': Ref('/img/白丝/c.png', '白丝')})
        recs = self.records(
            ('g1', 'u1', '黑丝', '/img/黑丝/a.png'),
            ('g1', 'u2', '黑丝', '/img/黑丝/b.png'),
        )
        outcomes = {
            self.resolve('m1', '黑丝', index=idx).outcome,
            self.resolve('m2', '黑丝', index=idx).outcome,
            self.resolve(None, '黑丝').outcome,
            self.resolve('m9', '黑丝').outcome,
            self.resolve('m9', '黑丝', records=recs).outcome,
        }
        self.assertEqual(len(outcomes), 5)

    def test_tag_is_normalised(self):
        idx = FakeIndex({'m1': Ref('/img/黑丝/a.png', '黑丝')})
        for tag in ('黑丝', ' 黑丝 ', '【黑丝】'):
            with self.subTest(tag=tag):
                self.assertEqual(self.resolve('m1', tag, index=idx).outcome, 'ok')

    def test_empty_tag_is_refused(self):
        idx = FakeIndex({'m1': Ref('/img/黑丝/a.png', '黑丝')})
        self.assertNotEqual(self.resolve('m1', '', index=idx).outcome, 'ok')


if __name__ == '__main__':
    unittest.main()


class RecencyFallbackTests(unittest.TestCase):
    """第 3 级：按发送时间兜底。

    第 1 级（回执）在不支持回执的适配器上永远落空，第 2 级（当日唯一）
    在多人抽过同一类型时落空 —— 这正是线上遇到的情形。
    第 3 级用"最近发出的那张"兜底，代价是回复旧图会删错，故有时间窗。
    """

    def setUp(self):
        self.dr = load_pure_module('delete_resolve')
        self.ds = load_pure_module('daily_store')
        self.si = load_pure_module('sent_index')
        self.category_of = {f'/img/靴子/{c}.png': '靴子' for c in 'abc'}
        self.category_of['/img/白丝/w.png'] = '白丝'

    def records(self, *triples):
        return {self.ds.record_key(c, u, cat): {'image': img} for c, u, cat, img in triples}

    def resolve(self, reply_id, tag, index, records, now=1000.0, within=600):
        return self.dr.resolve(
            reply_id, tag, index, records, self.category_of.get,
            chat_key='g1', now=now, recent_window=within,
        )

    def test_recency_resolves_what_used_to_be_ambiguous(self):
        # 线上实际场景：群里 3 个人抽过靴子，回执又没命中
        idx = self.si.SentIndex()
        idx.remember(None, '/img/靴子/c.png', '靴子', 'g1', 'u3', now=990.0)
        recs = self.records(
            ('g1', 'u1', '靴子', '/img/靴子/a.png'),
            ('g1', 'u2', '靴子', '/img/靴子/b.png'),
            ('g1', 'u3', '靴子', '/img/靴子/c.png'),
        )
        r = self.resolve('unknown', '靴子', idx, recs)
        self.assertEqual(r.outcome, 'ok')
        self.assertEqual(r.image, '/img/靴子/c.png')
        self.assertTrue(r.by_recency, '必须标记为兜底路径，供回复提示')

    def test_exact_paths_are_preferred_over_recency(self):
        # 回执命中时不得退到兜底 —— 兜底会删错
        class Ref:
            image, category, chat_key, user_key = '/img/靴子/a.png', '靴子', 'g1', 'u1'
        class Idx:
            def lookup(self, mid): return Ref()
            def recent(self, *a, **k): raise AssertionError('回执命中时不该查兜底')
        r = self.resolve('m1', '靴子', Idx(), {})
        self.assertEqual(r.image, '/img/靴子/a.png')
        self.assertFalse(r.by_recency)

    def test_unique_record_is_preferred_over_recency(self):
        idx = self.si.SentIndex()
        idx.remember(None, '/img/靴子/c.png', '靴子', 'g1', 'u3', now=990.0)
        recs = self.records(('g1', 'u1', '靴子', '/img/靴子/a.png'))
        r = self.resolve('unknown', '靴子', idx, recs)
        self.assertEqual(r.image, '/img/靴子/a.png', '唯一记录是精确的，优先于兜底')
        self.assertFalse(r.by_recency)

    def test_outside_the_window_falls_back_to_refusing(self):
        idx = self.si.SentIndex()
        idx.remember(None, '/img/靴子/c.png', '靴子', 'g1', 'u3', now=100.0)
        recs = self.records(
            ('g1', 'u1', '靴子', '/img/靴子/a.png'),
            ('g1', 'u2', '靴子', '/img/靴子/b.png'),
        )
        r = self.resolve('unknown', '靴子', idx, recs, now=100.0 + 601)
        self.assertEqual(r.outcome, 'ambiguous')
        self.assertIsNone(r.image)

    def test_recency_still_honours_the_tag_check(self):
        # 兜底也不能绕过「标签必须与实际类型一致」
        idx = self.si.SentIndex()
        idx.remember(None, '/img/白丝/w.png', '白丝', 'g1', 'u1', now=990.0)
        r = self.resolve('unknown', '白丝', idx, {}, now=1000.0)
        self.assertEqual(r.outcome, 'ok')
        r2 = self.dr.resolve(
            'unknown', '靴子', idx, {}, self.category_of.get,
            chat_key='g1', now=1000.0, recent_window=600,
        )
        self.assertNotEqual(r2.outcome, 'ok')

    def test_disabling_the_window_disables_the_fallback(self):
        idx = self.si.SentIndex()
        idx.remember(None, '/img/靴子/c.png', '靴子', 'g1', 'u3', now=990.0)
        recs = self.records(
            ('g1', 'u1', '靴子', '/img/靴子/a.png'),
            ('g1', 'u2', '靴子', '/img/靴子/b.png'),
        )
        r = self.resolve('unknown', '靴子', idx, recs, within=0)
        self.assertEqual(r.outcome, 'ambiguous')


class RepliedImageTests(unittest.TestCase):
    """第 0 级：直接拿被回复的那张图去图库里比对。

    这是识别的正路 —— 不依赖发送回执（本部署适配器不返回消息 ID），
    也不怕核心重启清空内存表。
    """

    def setUp(self):
        self.dr = load_pure_module('delete_resolve')
        self.ds = load_pure_module('daily_store')
        self.category_of = {'/img/靴子/a.png': '靴子', '/img/靴子/b.png': '靴子',
                            '/img/白丝/w.png': '白丝'}

    def records(self, *triples):
        return {self.ds.record_key(c, u, cat): {'image': img} for c, u, cat, img in triples}

    def resolve(self, **kw):
        base = dict(
            reply_id='m1', tag='靴子', sent_index=_NoIndex(),
            today_records={}, category_of=self.category_of.get, chat_key='g1',
        )
        base.update(kw)
        return self.dr.resolve(**base)

    def test_matched_image_wins_over_everything_else(self):
        # 多条记录本来会是 ambiguous，但拿到了图就不必猜
        recs = self.records(
            ('g1', 'u1', '靴子', '/img/靴子/a.png'),
            ('g1', 'u2', '靴子', '/img/靴子/b.png'),
        )
        r = self.resolve(today_records=recs, matched_image='/img/靴子/b.png')
        self.assertEqual(r.outcome, 'ok')
        self.assertEqual(r.image, '/img/靴子/b.png')
        self.assertFalse(r.by_recency, '这是精确匹配，不是兜底')

    def test_matched_image_still_honours_the_tag_check(self):
        r = self.resolve(tag='靴子', matched_image='/img/白丝/w.png')
        self.assertEqual(r.outcome, 'tag_mismatch')
        self.assertIsNone(r.image)

    def test_falls_through_when_nothing_matched(self):
        recs = self.records(('g1', 'u1', '靴子', '/img/靴子/a.png'))
        r = self.resolve(today_records=recs, matched_image=None)
        self.assertEqual(r.outcome, 'ok')
        self.assertEqual(r.image, '/img/靴子/a.png', '应退回当日唯一记录')

    def test_works_even_with_an_empty_reply_id(self):
        # 拿到图之后，消息 ID 已经不重要了
        r = self.resolve(reply_id=None, matched_image='/img/靴子/a.png')
        self.assertEqual(r.outcome, 'ok')


class _NoIndex:
    def lookup(self, mid): return None
    def recent(self, *a, **k): return None
