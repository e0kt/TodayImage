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
    """最小化的回执表快照。"""

    def __init__(self, mapping=None):
        self._m = mapping or {}

    def lookup(self, message_id):
        return self._m.get(str(message_id))


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
