"""删图权限：只能收紧，永不放宽。"""
import unittest


class FakeEvent:
    def __init__(self, user_pm):
        self.user_pm = user_pm


class PermissionRuleTests(unittest.TestCase):
    """对权限规则本身的断言，不依赖 gsuid_core。

    规则：SV 的 pm=3 是硬上界；配置为 True 时再收紧到 pm<=1。
    """

    @staticmethod
    def allowed(user_pm, master_only):
        # 与 shared.can_delete_image 同构的纯规则
        if user_pm > 3:
            return False          # SV 硬上界，配置管不着
        if not master_only:
            return True
        return user_pm <= 1

    def test_default_allows_group_admins(self):
        # 错标本身就是全局的，能发现的人修掉它对所有群都是净收益
        for pm in (0, 1, 2, 3):
            with self.subTest(pm=pm):
                self.assertTrue(self.allowed(pm, master_only=False))

    def test_ordinary_members_are_never_allowed(self):
        for master_only in (False, True):
            with self.subTest(master_only=master_only):
                self.assertFalse(self.allowed(6, master_only))

    def test_tightening_excludes_admins_but_keeps_master(self):
        self.assertFalse(self.allowed(3, master_only=True))
        self.assertFalse(self.allowed(2, master_only=True))
        self.assertTrue(self.allowed(1, master_only=True))
        self.assertTrue(self.allowed(0, master_only=True))

    def test_config_can_only_tighten_never_widen(self):
        # 对每个 pm，收紧后的结果不可能比默认更宽松
        for pm in range(0, 8):
            with self.subTest(pm=pm):
                self.assertLessEqual(
                    int(self.allowed(pm, True)), int(self.allowed(pm, False))
                )


if __name__ == '__main__':
    unittest.main()
