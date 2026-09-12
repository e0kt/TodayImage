import asyncio
import tempfile
import unittest
from pathlib import Path

from _loader import load_pure_module

DATE = '2026-09-08'


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.store = load_pure_module('daily_store')

    def test_seed_is_stable_for_the_same_inputs(self):
        a = self.store.draw_seed(DATE, 'qq:1', 'g1', '黑丝')
        b = self.store.draw_seed(DATE, 'qq:1', 'g1', '黑丝')
        self.assertEqual(a, b)

    def test_seed_differs_across_user_chat_category_and_date(self):
        base = self.store.draw_seed(DATE, 'qq:1', 'g1', '黑丝')
        self.assertNotEqual(base, self.store.draw_seed(DATE, 'qq:2', 'g1', '黑丝'))
        self.assertNotEqual(base, self.store.draw_seed(DATE, 'qq:1', 'g2', '黑丝'))
        self.assertNotEqual(base, self.store.draw_seed(DATE, 'qq:1', 'g1', '白丝'))
        self.assertNotEqual(base, self.store.draw_seed('2026-09-09', 'qq:1', 'g1', '黑丝'))

    def test_pick_is_deterministic_for_a_seed(self):
        images = tuple(f'/img/{i}.png' for i in range(20))
        seed = self.store.draw_seed(DATE, 'qq:1', 'g1', '黑丝')
        self.assertEqual(self.store.pick_image(images, seed), self.store.pick_image(images, seed))

    def test_pick_returns_none_for_an_empty_gallery(self):
        self.assertIsNone(self.store.pick_image((), 'anything'))


class ResolveDailyImageTests(unittest.TestCase):
    def setUp(self):
        self.store = load_pure_module('daily_store')
        self.store.clear_locks()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'daily_records.json'

    def tearDown(self):
        self.temp.cleanup()

    def resolve(self, images, exists=None, category='黑丝', user='qq:1', chat='g1'):
        return asyncio.run(
            self.store.resolve_daily_image(
                self.path, DATE, chat, user, category, images,
                exists=exists if exists is not None else (lambda p: True),
            )
        )

    def test_first_draw_persists_a_record(self):
        images = tuple(f'/img/{i}.png' for i in range(5))
        chosen = self.resolve(images)
        self.assertIn(chosen, images)
        records = self.store.load_records(self.path, DATE)
        self.assertEqual(records[self.store.record_key('g1', 'qq:1', '黑丝')]['image'], chosen)

    def test_repeat_draw_returns_the_pinned_image(self):
        images = tuple(f'/img/{i}.png' for i in range(5))
        first = self.resolve(images)
        second = self.resolve(images)
        self.assertEqual(first, second)

    def test_pin_survives_a_gallery_change(self):
        # This is why a seeded pick alone is not enough: a mid-day upload shifts every
        # index, so without the persisted pin everyone's draw would silently reshuffle.
        first = self.resolve(tuple(f'/img/{i}.png' for i in range(5)))
        grown = tuple(f'/img/{i}.png' for i in range(50))
        self.assertEqual(self.resolve(grown), first)

    def test_missing_pinned_file_triggers_a_redraw_and_repin(self):
        images = tuple(f'/img/{i}.png' for i in range(5))
        first = self.resolve(images)

        remaining = tuple(p for p in images if p != first)
        second = self.resolve(remaining, exists=lambda p: p in remaining)

        self.assertNotEqual(second, first)
        self.assertIn(second, remaining)
        records = self.store.load_records(self.path, DATE)
        self.assertEqual(records[self.store.record_key('g1', 'qq:1', '黑丝')]['image'], second)

    def test_empty_gallery_writes_no_record(self):
        self.assertIsNone(self.resolve(()))
        self.assertEqual(self.store.load_records(self.path, DATE), {})

    def test_different_users_chats_and_categories_are_independent(self):
        images = tuple(f'/img/{i}.png' for i in range(30))
        self.resolve(images, user='qq:1', chat='g1')
        self.resolve(images, user='qq:2', chat='g1')
        self.resolve(images, user='qq:1', chat='g2')
        self.resolve(images, user='qq:1', chat='g1', category='白丝')

        records = self.store.load_records(self.path, DATE)
        self.assertEqual(len(records), 4)

    def test_concurrent_first_draws_persist_exactly_one_record(self):
        images = tuple(f'/img/{i}.png' for i in range(30))

        async def race():
            return await asyncio.gather(*[
                self.store.resolve_daily_image(
                    self.path, DATE, 'g1', 'qq:1', '黑丝', images, exists=lambda p: True
                )
                for _ in range(12)
            ])

        results = asyncio.run(race())
        self.assertEqual(len(set(results)), 1, 'all concurrent callers must see one image')

        records = self.store.load_records(self.path, DATE)
        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[self.store.record_key('g1', 'qq:1', '黑丝')]['image'], results[0]
        )

    def test_deleted_then_drawn_regression(self):
        # Mirrors quickstart Scenario 4 step 3: the pinned file is deleted by the delete
        # command, and the next draw must recover rather than error (V-REC-3).
        images = ('/img/a.png', '/img/b.png')
        first = self.resolve(images)
        survivors = tuple(p for p in images if p != first)
        again = self.resolve(survivors, exists=lambda p: p in survivors)
        self.assertEqual(again, survivors[0])


if __name__ == '__main__':
    unittest.main()


class ResetTimezoneTests(unittest.TestCase):
    """The day boundary must be Beijing midnight regardless of where the bot runs."""

    def setUp(self):
        self.store = load_pure_module('daily_store')

    def test_uses_the_configured_utc_offset_not_server_local_time(self):
        import datetime as dt
        # 2026-09-09 17:00 UTC == 2026-09-10 01:00 Beijing -> already the next day there.
        moment = dt.datetime(2026, 9, 9, 17, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(self.store.current_date(8, now=moment), '2026-09-10')
        self.assertEqual(self.store.current_date(0, now=moment), '2026-09-09')

    def test_boundary_is_exactly_midnight_beijing(self):
        import datetime as dt
        just_before = dt.datetime(2026, 9, 9, 15, 59, 59, tzinfo=dt.timezone.utc)  # 23:59:59 Beijing
        just_after = dt.datetime(2026, 9, 9, 16, 0, 0, tzinfo=dt.timezone.utc)     # 00:00:00 Beijing
        self.assertEqual(self.store.current_date(8, now=just_before), '2026-09-09')
        self.assertEqual(self.store.current_date(8, now=just_after), '2026-09-10')

    def test_default_offset_is_beijing(self):
        import datetime as dt
        moment = dt.datetime(2026, 9, 9, 17, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(self.store.current_date(now=moment), '2026-09-10')

    def test_negative_and_odd_offsets_work(self):
        import datetime as dt
        moment = dt.datetime(2026, 9, 9, 3, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(self.store.current_date(-8, now=moment), '2026-09-08')

    def test_returns_a_date_string_with_no_arguments(self):
        self.assertRegex(self.store.current_date(), r'^\d{4}-\d{2}-\d{2}$')


class UniquePerDayTests(unittest.TestCase):
    """No two people in the same chat should get the same picture on the same day."""

    def setUp(self):
        self.store = load_pure_module('daily_store')
        self.store.clear_locks()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'daily_records.json'

    def tearDown(self):
        self.temp.cleanup()

    def draw(self, images, user, chat='g1', category='黑丝', unique=True):
        return asyncio.run(
            self.store.resolve_daily_image(
                self.path, DATE, chat, user, category, images,
                exists=lambda p: True, unique_per_chat=unique,
            )
        )

    def test_users_in_one_chat_never_share_an_image(self):
        images = tuple(f'/img/{i}.png' for i in range(40))
        picks = [self.draw(images, f'qq:{i}') for i in range(40)]
        self.assertEqual(len(set(picks)), 40)

    def test_repeat_draw_still_returns_the_same_pinned_image(self):
        images = tuple(f'/img/{i}.png' for i in range(10))
        first = self.draw(images, 'qq:1')
        self.assertEqual(self.draw(images, 'qq:1'), first)

    def test_falls_back_to_reuse_when_the_gallery_is_exhausted(self):
        # 3 images, 5 users: someone must repeat -- refusing to answer would be worse.
        images = ('/img/a.png', '/img/b.png', '/img/c.png')
        picks = [self.draw(images, f'qq:{i}') for i in range(5)]
        self.assertEqual(len(picks), 5)
        self.assertTrue(all(p in images for p in picks))
        self.assertEqual(len(set(picks[:3])), 3)

    def test_dedup_is_scoped_per_chat(self):
        images = ('/img/a.png',)
        a = self.draw(images, 'qq:1', chat='g1')
        b = self.draw(images, 'qq:2', chat='g2')
        self.assertEqual(a, b)  # different chats are independent

    def test_dedup_is_scoped_per_category(self):
        images = ('/img/a.png',)
        a = self.draw(images, 'qq:1', category='黑丝')
        b = self.draw(images, 'qq:2', category='白丝')
        self.assertEqual(a, b)

    def test_can_be_turned_off(self):
        images = ('/img/a.png', '/img/b.png')
        picks = {self.draw(images, f'qq:{i}', unique=False) for i in range(8)}
        self.assertLessEqual(len(picks), 2)

    def test_concurrent_draws_by_different_users_still_do_not_collide(self):
        images = tuple(f'/img/{i}.png' for i in range(20))

        async def race():
            return await asyncio.gather(*[
                self.store.resolve_daily_image(
                    self.path, DATE, 'g1', f'qq:{i}', '黑丝', images,
                    exists=lambda p: True, unique_per_chat=True,
                )
                for i in range(20)
            ])

        picks = asyncio.run(race())
        self.assertEqual(len(set(picks)), 20, 'concurrent draws must not hand out duplicates')

    def test_taken_images_ignores_other_chats_and_categories(self):
        records = {
            self.store.record_key('g1', 'qq:1', '黑丝'): {'image': '/a.png'},
            self.store.record_key('g1', 'qq:2', '白丝'): {'image': '/b.png'},
            self.store.record_key('g2', 'qq:3', '黑丝'): {'image': '/c.png'},
        }
        taken = self.store.taken_images(records, 'g1', '黑丝', exclude_key='')
        self.assertEqual(taken, {'/a.png'})


class UnpinnedDirectDrawTests(unittest.TestCase):
    """Direct chats draw fresh every time, with no daily pin and no stored record."""

    def setUp(self):
        self.store = load_pure_module('daily_store')
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'daily_records.json'

    def tearDown(self):
        self.temp.cleanup()

    def test_pick_random_returns_an_image_from_the_gallery(self):
        images = tuple(f'/img/{i}.png' for i in range(10))
        self.assertIn(self.store.pick_random(images), images)

    def test_pick_random_varies_across_calls(self):
        # The whole point: unlike pick_image(), repeated calls must not be pinned.
        images = tuple(f'/img/{i}.png' for i in range(200))
        seen = {self.store.pick_random(images) for _ in range(40)}
        self.assertGreater(len(seen), 1, 'direct-chat draws must not be deterministic')

    def test_pick_random_on_an_empty_gallery_returns_none(self):
        self.assertIsNone(self.store.pick_random(()))

    def test_pick_random_on_a_single_image_gallery(self):
        self.assertEqual(self.store.pick_random(('/img/only.png',)), '/img/only.png')

    def test_pick_random_accepts_an_injected_rng_for_determinism_in_tests(self):
        import random
        images = tuple(f'/img/{i}.png' for i in range(10))
        a = self.store.pick_random(images, rng=random.Random(1))
        b = self.store.pick_random(images, rng=random.Random(1))
        self.assertEqual(a, b)

    def test_unpinned_draws_write_no_record(self):
        # A direct chat must not grow daily_records.json -- nothing is pinned there.
        images = tuple(f'/img/{i}.png' for i in range(10))
        for _ in range(5):
            self.store.pick_random(images)
        self.assertEqual(self.store.load_records(self.path, DATE), {})
        self.assertFalse(self.path.exists())

    def test_group_pinning_is_untouched_by_the_unpinned_path(self):
        # Regression guard: adding the direct-chat path must not weaken group draws.
        self.store.clear_locks()
        images = tuple(f'/img/{i}.png' for i in range(20))
        first = asyncio.run(self.store.resolve_daily_image(
            self.path, DATE, 'g1', 'qq:1', '黑丝', images, exists=lambda p: True))
        second = asyncio.run(self.store.resolve_daily_image(
            self.path, DATE, 'g1', 'qq:1', '黑丝', images, exists=lambda p: True))
        self.assertEqual(first, second)
