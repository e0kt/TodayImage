import unittest

from _loader import load_pure_module

ROOT = '<gsuid_core>/data/TodayImage'


class Cat:
    def __init__(self, name, images=(), enabled=True, aliases=()):
        self.name = name
        self.images = tuple(images)
        self.enabled = enabled
        self.aliases = tuple(aliases)


CATS = [Cat('黑丝', ['/a.png', '/b.png']), Cat('白丝', ['/c.png']), Cat('测试', [], enabled=False)]


class PublicHelpTests(unittest.TestCase):
    """Public help explains HOW, never WHAT exists (FR-111, V-DIS-3)."""

    def setUp(self):
        self.mod = load_pure_module('help_text')
        self.text = self.mod.build_help_text('今日', is_master=False, categories=CATS, image_root=ROOT)

    def test_never_names_a_folder(self):
        for name in ('黑丝', '白丝', '测试'):
            with self.subTest(name=name):
                self.assertNotIn(name, self.text)

    def test_never_contains_a_filesystem_path(self):
        self.assertNotIn(ROOT, self.text)
        self.assertNotIn('/Users', self.text)
        self.assertNotIn('data/TodayImage', self.text)

    def test_never_lists_management_commands(self):
        for command in ('上传图片', '查看图片', '删除图片', '重载图片类型'):
            with self.subTest(command=command):
                self.assertNotIn(command, self.text)

    def test_never_reveals_image_counts(self):
        self.assertNotIn('2 张', self.text)
        self.assertNotIn('1 张', self.text)

    def test_still_explains_the_mechanism(self):
        self.assertIn('今日', self.text)
        self.assertTrue(len(self.text.strip()) > 20, 'public help must still say something useful')

    def test_is_identical_whether_or_not_categories_exist(self):
        # Otherwise the help itself reveals whether the host has any folders at all.
        empty = self.mod.build_help_text('今日', is_master=False, categories=[], image_root=ROOT)
        self.assertEqual(empty, self.text)

    def test_reflects_a_custom_prefix(self):
        text = self.mod.build_help_text('每日', is_master=False, categories=CATS, image_root=ROOT)
        self.assertIn('每日', text)


class MasterHelpTests(unittest.TestCase):
    """Disclosure is restricted by permission, not removed outright (FR-112, V-DIS-4)."""

    def setUp(self):
        self.mod = load_pure_module('help_text')
        self.text = self.mod.build_help_text('今日', is_master=True, categories=CATS, image_root=ROOT)

    def test_lists_enabled_folders_with_counts(self):
        self.assertIn('黑丝', self.text)
        self.assertIn('白丝', self.text)
        self.assertIn('2', self.text)

    def test_shows_the_image_root(self):
        self.assertIn(ROOT, self.text)

    def test_lists_management_commands(self):
        for command in ('上传图片', '查看图片', '删除图片', '重载图片类型'):
            with self.subTest(command=command):
                self.assertIn(command, self.text)

    def test_marks_a_disabled_category(self):
        self.assertIn('测试', self.text)

    def test_contains_everything_the_public_text_does(self):
        public = self.mod.build_help_text('今日', is_master=False, categories=CATS, image_root=ROOT)
        for line in public.splitlines():
            if line.strip():
                self.assertIn(line.strip(), self.text)

    def test_empty_gallery_tells_the_master_where_to_put_folders(self):
        text = self.mod.build_help_text('今日', is_master=True, categories=[], image_root=ROOT)
        self.assertIn(ROOT, text)


if __name__ == '__main__':
    unittest.main()
