"""分群类型重置：重置代数、带 epoch 的种子、批量清除。

**为什么这些断言必须先写**：按字面实现（只删每日记录）会是一个空操作 ——
命令有回复、记录确实被清了、人工测试看起来完全正常，但所有人重抽会拿回
一模一样的图，因为种子 {日期}:{用户}:{会话}:{类型} 一字未变（research R1 实测）。
只有「重置后图必须不同」这条断言能抓住它。
"""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from _loader import load_pure_module

DATE = '2026-09-17'


class ResetEpochStorageTests(unittest.TestCase):
    def setUp(self):
        self.ds = load_pure_module('daily_store')
        self.ds.clear_locks()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'daily_records.json'

    def tearDown(self):
        self.temp.cleanup()

    def test_epoch_defaults_to_zero(self):
        # V-EPO-2：没有记录 = 从未重置
        self.assertEqual(self.ds.reset_epoch(self.ds.load_resets(self.path, DATE), 'g1', '黑丝'), 0)

    def test_reset_key_splits_on_the_first_separator_only(self):
        # V-EPO-1：类型名含 | 时仍可还原
        key = self.ds.reset_key('g1', 'a|b')
        self.assertEqual(self.ds.parse_reset_key(key), ('g1', 'a|b'))

    def test_epoch_increments_on_each_reset(self):
        # V-EPO-3：同日可反复重置
        for expected in (1, 2, 3):
            _, epoch = asyncio.run(self.ds.reset_group_category(self.path, DATE, 'g1', '黑丝'))
            self.assertEqual(epoch, expected)

    def test_epoch_is_per_group_and_per_category(self):
        asyncio.run(self.ds.reset_group_category(self.path, DATE, 'g1', '黑丝'))
        resets = self.ds.load_resets(self.path, DATE)
        self.assertEqual(self.ds.reset_epoch(resets, 'g1', '黑丝'), 1)
        self.assertEqual(self.ds.reset_epoch(resets, 'g1', '白丝'), 0)
        self.assertEqual(self.ds.reset_epoch(resets, 'g2', '黑丝'), 0)

    def test_resets_are_dropped_together_with_records_on_a_new_day(self):
        # V-EPO-4 / I-405：两者同生命周期
        asyncio.run(self.ds.reset_group_category(self.path, DATE, 'g1', '黑丝'))
        self.ds.save_records(self.path, '2026-09-18', {})
        payload = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(payload['date'], '2026-09-18')
        self.assertEqual(payload.get('resets', {}), {})

    def test_legacy_file_without_resets_reads_as_empty(self):
        # S-402：老文件无需迁移
        self.path.write_text(json.dumps({
            'version': 1, 'date': DATE,
            'records': {'g1|u1|黑丝': {'image': '/a.png'}},
        }), encoding='utf-8')
        self.assertEqual(self.ds.load_resets(self.path, DATE), {})
        self.assertEqual(self.ds.reset_epoch(self.ds.load_resets(self.path, DATE), 'g1', '黑丝'), 0)

    def test_corrupt_file_reads_resets_as_empty(self):
        # S-405：降级结果是「回到未重置状态」，不放大影响面
        self.path.write_text('{ broken', encoding='utf-8')
        self.assertEqual(self.ds.load_resets(self.path, DATE), {})

    def test_drawing_does_not_wipe_the_epoch(self):
        # 最阴险的一条：抽图走 upsert_record -> save_records。若那条路径不带上
        # resets，第一次抽图就会把代数清零，重置从第二个人开始就失效了。
        asyncio.run(self.ds.reset_group_category(self.path, DATE, 'g1', '黑丝'))
        self.ds.upsert_record(self.path, DATE, self.ds.record_key('g1', 'u1', '黑丝'), '/a.png')
        self.assertEqual(self.ds.reset_epoch(self.ds.load_resets(self.path, DATE), 'g1', '黑丝'), 1)


class SeedWithEpochTests(unittest.TestCase):
    def setUp(self):
        self.ds = load_pure_module('daily_store')

    def test_epoch_zero_seed_is_byte_identical_to_the_old_format(self):
        # V-SEED-1 / I-401：本功能上线不得改变任何人当天已经拿到的图。
        # 直接断言字面量，而不是与另一个函数比对 —— 两边一起改就发现不了了。
        self.assertEqual(
            self.ds.draw_seed(DATE, 'qq:1', 'g1', '黑丝'),
            '2026-09-17:qq:1:g1:黑丝',
        )
        self.assertEqual(
            self.ds.draw_seed(DATE, 'qq:1', 'g1', '黑丝', epoch=0),
            '2026-09-17:qq:1:g1:黑丝',
        )

    def test_nonzero_epoch_appends_a_suffix(self):
        self.assertEqual(
            self.ds.draw_seed(DATE, 'qq:1', 'g1', '黑丝', epoch=2),
            '2026-09-17:qq:1:g1:黑丝:r2',
        )

    def test_each_epoch_yields_a_distinct_seed(self):
        # V-SEED-4：用计数而非时间戳，故同一秒两次重置也必然不同
        seeds = {self.ds.draw_seed(DATE, 'qq:1', 'g1', '黑丝', epoch=e) for e in range(6)}
        self.assertEqual(len(seeds), 6)

    def test_incrementing_the_epoch_usually_changes_the_chosen_image(self):
        """换种子只能做到「很可能不同」，不能做到「一定不同」。

        两个不同的种子有约 1/N 的概率落回同一张图。FR-402 要的是 MUST，
        所以真正的保证来自重置时写下的排除集，见 ClearRecordsTests 与
        test_reset_flow 里的端到端断言。这里只确认种子确实在起作用。
        """
        images = tuple(f'/img/{i}.png' for i in range(50))
        picks = [
            self.ds.pick_image(images, self.ds.draw_seed(DATE, 'qq:1', 'g1', '黑丝', epoch=e))
            for e in range(8)
        ]
        self.assertGreater(len(set(picks)), 1, '种子必须真的影响选取结果')

    def test_seed_still_varies_per_user_at_the_same_epoch(self):
        # V-SEED-3：新一轮里用户之间仍然独立
        a = self.ds.draw_seed(DATE, 'qq:1', 'g1', '黑丝', epoch=3)
        b = self.ds.draw_seed(DATE, 'qq:2', 'g1', '黑丝', epoch=3)
        self.assertNotEqual(a, b)


class ClearRecordsTests(unittest.TestCase):
    def setUp(self):
        self.ds = load_pure_module('daily_store')
        self.ds.clear_locks()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'daily_records.json'

    def tearDown(self):
        self.temp.cleanup()

    def _seed_records(self):
        for chat, user, cat in (
            ('g1', 'u1', '黑丝'), ('g1', 'u2', '黑丝'),
            ('g1', 'u1', '白丝'), ('g2', 'u1', '黑丝'),
        ):
            self.ds.upsert_record(self.path, DATE, self.ds.record_key(chat, user, cat), f'/{cat}.png')

    def test_clears_only_matching_chat_and_category(self):
        self._seed_records()
        cleared, _ = asyncio.run(self.ds.reset_group_category(self.path, DATE, 'g1', '黑丝'))
        self.assertEqual(cleared, 2)
        remaining = set(self.ds.load_records(self.path, DATE))
        self.assertEqual(remaining, {
            self.ds.record_key('g1', 'u1', '白丝'),
            self.ds.record_key('g2', 'u1', '黑丝'),
        })

    def test_returns_zero_when_nothing_to_clear(self):
        # V-RES-1 / FR-413：0 条是正常结果，不是错误
        cleared, epoch = asyncio.run(self.ds.reset_group_category(self.path, DATE, 'g1', '黑丝'))
        self.assertEqual(cleared, 0)
        self.assertEqual(epoch, 1, '清 0 条时代数仍要 +1（V-RES-2）')

    def test_category_name_is_normalised(self):
        self._seed_records()
        cleared, _ = asyncio.run(self.ds.reset_group_category(self.path, DATE, 'g1', ' 黑丝 '))
        self.assertEqual(cleared, 2)

    def test_clear_and_increment_land_in_one_write(self):
        # I-402：分两次写的话，中间崩溃会留下「记录清了但种子没变」
        self._seed_records()
        asyncio.run(self.ds.reset_group_category(self.path, DATE, 'g1', '黑丝'))
        payload = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertNotIn(self.ds.record_key('g1', 'u1', '黑丝'), payload['records'])
        self.assertEqual(payload['resets'][self.ds.reset_key('g1', '黑丝')], 1)

    def test_atomic_write_leaves_no_temp_file(self):
        asyncio.run(self.ds.reset_group_category(self.path, DATE, 'g1', '黑丝'))
        leftovers = [p.name for p in Path(self.temp.name).iterdir() if p.name != 'daily_records.json']
        self.assertEqual(leftovers, [])


if __name__ == '__main__':
    unittest.main()


class ResetExclusionTests(unittest.TestCase):
    """重置**保证**换一张：靠的是排除集，不是概率。"""

    def setUp(self):
        self.ds = load_pure_module('daily_store')
        self.ds.clear_locks()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'daily_records.json'

    def tearDown(self):
        self.temp.cleanup()

    def draw(self, user, images, category='黑丝', chat='g1'):
        return asyncio.run(self.ds.resolve_daily_image(
            self.path, DATE, chat, user, category, images,
            exists=lambda p: True, unique_per_chat=True))

    def reset(self, category='黑丝', chat='g1'):
        self.ds.clear_locks()
        return asyncio.run(self.ds.reset_group_category(self.path, DATE, chat, category))

    def test_cleared_images_are_recorded_as_excluded(self):
        images = tuple(f'/img/{i}.png' for i in range(20))
        first = self.draw('u1', images)
        self.reset()
        excluded = self.ds.load_excludes(self.path, DATE)[self.ds.reset_key('g1', '黑丝')]
        self.assertIn(first, excluded)

    def test_reset_guarantees_a_different_image_even_on_a_tiny_gallery(self):
        # 两张图的图库最容易撞：纯种子方案在这里有 1/2 概率原地不动。
        images = ('/img/a.png', '/img/b.png')
        first = self.draw('u1', images)
        self.reset()
        self.assertNotEqual(self.draw('u1', images), first)

    def test_repeated_resets_keep_yielding_new_images(self):
        images = tuple(f'/img/{i}.png' for i in range(20))
        seen = [self.draw('u1', images)]
        for _ in range(5):
            self.reset()
            nxt = self.draw('u1', images)
            self.assertNotEqual(nxt, seen[-1], '每一轮都必须与上一轮不同')
            seen.append(nxt)

    def test_falls_back_to_the_full_pool_when_everything_is_excluded(self):
        # 单图图库：排除后无图可选，必须退回全量而不是静默失败。
        images = ('/img/only.png',)
        self.assertEqual(self.draw('u1', images), '/img/only.png')
        self.reset()
        self.assertEqual(self.draw('u1', images), '/img/only.png')

    def test_exclusion_is_scoped_per_group_and_category(self):
        images = tuple(f'/img/{i}.png' for i in range(20))
        a = self.draw('u1', images, category='黑丝', chat='g1')
        b = self.draw('u1', images, category='白丝', chat='g1')
        c = self.draw('u1', images, category='黑丝', chat='g2')
        self.reset(category='黑丝', chat='g1')
        self.assertNotEqual(self.draw('u1', images, category='黑丝', chat='g1'), a)
        self.assertEqual(self.draw('u1', images, category='白丝', chat='g1'), b)
        self.assertEqual(self.draw('u1', images, category='黑丝', chat='g2'), c)


class ResetEndToEndTests(unittest.TestCase):
    """US1 验收核心：空操作实现只会在这一组上失败。"""

    def setUp(self):
        self.ds = load_pure_module('daily_store')
        self.ds.clear_locks()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'daily_records.json'
        self.images = tuple(f'/img/{i}.png' for i in range(40))

    def tearDown(self):
        self.temp.cleanup()

    def draw(self, user, category='黑丝', chat='g1'):
        return asyncio.run(self.ds.resolve_daily_image(
            self.path, DATE, chat, user, category, self.images,
            exists=lambda p: True, unique_per_chat=True))

    def reset(self, category='黑丝', chat='g1'):
        self.ds.clear_locks()
        return asyncio.run(self.ds.reset_group_category(self.path, DATE, chat, category))

    def test_everyone_gets_a_new_image_after_a_reset(self):
        # FR-402 / SC-401 —— 本功能的验收核心
        a1, b1 = self.draw('u1'), self.draw('u2')
        cleared, epoch = self.reset()
        self.assertEqual((cleared, epoch), (2, 1))
        a2, b2 = self.draw('u1'), self.draw('u2')
        self.assertNotEqual(a2, a1)
        self.assertNotEqual(b2, b1)
        self.assertNotEqual(a2, b2, '新一轮内也不能撞图')

    def test_reset_opens_one_round_not_unlimited(self):
        # FR-404 / SC-402：重置放开的是一次重抽，不是取消当日固定
        self.draw('u1')
        self.reset()
        picks = {self.draw('u1') for _ in range(5)}
        self.assertEqual(len(picks), 1, '重置后仍应当日固定')

    def test_five_consecutive_resets_each_yield_a_new_image(self):
        # FR-405 / SC-403
        previous = self.draw('u1')
        for round_no in range(5):
            self.reset()
            current = self.draw('u1')
            self.assertNotEqual(current, previous, f'第 {round_no + 1} 轮没有换图')
            previous = current

    def test_other_category_group_and_direct_are_untouched(self):
        # FR-403 / SC-404 / I-403
        black = self.draw('u1', category='黑丝')
        white = self.draw('u1', category='白丝')
        other = self.draw('u1', chat='g2')
        self.reset(category='黑丝', chat='g1')
        self.assertNotEqual(self.draw('u1', category='黑丝'), black)
        self.assertEqual(self.draw('u1', category='白丝'), white)
        self.assertEqual(self.draw('u1', chat='g2'), other)
        # 私聊走 pick_random，不读记录也不读 epoch
        self.assertIsNotNone(self.ds.pick_random(self.images))

    def test_new_round_still_avoids_collisions_among_many_users(self):
        # FR-407 / SC-406
        users = [f'u{i}' for i in range(10)]
        [self.draw(u) for u in users]
        self.reset()
        second = [self.draw(u) for u in users]
        self.assertEqual(len(set(second)), len(users))

    def test_epoch_survives_subsequent_draws(self):
        # 回归：抽图写盘不得把代数冲掉
        self.reset()
        self.draw('u1')
        self.draw('u2')
        resets = self.ds.load_resets(self.path, DATE)
        self.assertEqual(self.ds.reset_epoch(resets, 'g1', '黑丝'), 1)


class NormalisationRobustnessTests(unittest.TestCase):
    """存储层拿到未归一的类型名也必须正确。

    不这样做的话，'【黑丝】' 会静默匹配不到任何记录 —— 表现为「清除 0 条」，
    与「本来就没人抽过」完全无法区分。实机演练时就是这么翻车的。
    """

    def setUp(self):
        self.ds = load_pure_module('daily_store')
        self.ds.clear_locks()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'daily_records.json'
        self.images = tuple(f'/img/{i}.png' for i in range(20))

    def tearDown(self):
        self.temp.cleanup()

    def draw(self, user, category):
        return asyncio.run(self.ds.resolve_daily_image(
            self.path, DATE, 'g1', user, category, self.images,
            exists=lambda p: True, unique_per_chat=True))

    def test_bracketed_category_clears_the_same_records(self):
        self.draw('u1', '黑丝')
        self.ds.clear_locks()
        cleared, _ = asyncio.run(self.ds.reset_group_category(self.path, DATE, 'g1', '【黑丝】'))
        self.assertEqual(cleared, 1)

    def test_bracketed_reset_actually_changes_the_next_draw(self):
        first = self.draw('u1', '黑丝')
        self.ds.clear_locks()
        asyncio.run(self.ds.reset_group_category(self.path, DATE, 'g1', ' 【黑丝】 '))
        self.ds.clear_locks()
        self.assertNotEqual(self.draw('u1', '黑丝'), first)

    def test_epoch_key_is_case_insensitive(self):
        asyncio.run(self.ds.reset_group_category(self.path, DATE, 'g1', 'Alpha'))
        resets = self.ds.load_resets(self.path, DATE)
        for probe in ('Alpha', 'alpha', ' ALPHA '):
            with self.subTest(probe=probe):
                self.assertEqual(self.ds.reset_epoch(resets, 'g1', probe), 1)
