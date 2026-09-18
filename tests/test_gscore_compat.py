"""Contract tests against the GsCore surface TodayImage depends on.

Two independent guarantees live here:

1. **Module purity** — the PURE modules must never pull in gsuid_core. This runs
   everywhere, including a dev checkout with no core installed, and is what keeps the
   rest of the suite runnable without a bot.
2. **Framework shape** — tdi/registry_binding.py reaches into `sv.TL` to unregister a
   trigger, because the core exposes no public API for that. These assertions are the
   tripwire: if a GsCore upgrade reshapes TL, this fails loudly instead of the reload
   command silently going dead in production. Skipped when gsuid_core is unavailable.
"""
from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

from _loader import PURE_MODULES, TDI_DIR, load_pure_module

GSCORE_AVAILABLE = importlib.util.find_spec('gsuid_core') is not None

# Modules that may import gsuid_core, with a note on why.
GSCORE_FACING = {
    'shared': 'SV/config/segment surface',
    'daily': 'command handler',
    'manage': 'command handlers',
    'help': 'command handler + register_help',
    'message_delivery': 'guarded import, degrades without the core',
    'registry_binding': 'lazy import inside _registry() only',
}


class ModulePurityTests(unittest.TestCase):
    def test_pure_modules_have_no_gsuid_core_import_in_source(self) -> None:
        pattern = re.compile(r'^\s*(?:from|import)\s+gsuid_core', re.MULTILINE)
        for name in PURE_MODULES:
            path = TDI_DIR / f'{name}.py'
            with self.subTest(module=name):
                self.assertFalse(
                    pattern.search(path.read_text(encoding='utf-8')),
                    f'tdi/{name}.py is marked PURE but imports gsuid_core',
                )

    def test_loading_pure_modules_does_not_pull_in_gsuid_core(self) -> None:
        for name in PURE_MODULES:
            sys.modules.pop('gsuid_core', None)
            load_pure_module(name)
            with self.subTest(module=name):
                self.assertNotIn(
                    'gsuid_core',
                    sys.modules,
                    f'loading tdi/{name}.py imported gsuid_core',
                )

    def test_nothing_mutates_the_framework_trigger_table(self) -> None:
        # Feature 002 deleted registry_binding, so the plugin has no internal reach left.
        offenders = [
            path.name for path in sorted(TDI_DIR.glob('*.py'))
            if re.search(r"\bdel\s+\w+\.TL\b", path.read_text(encoding='utf-8'))
        ]
        self.assertEqual(offenders, [], 'no module may mutate sv.TL directly any more')


def _load_plugin():
    """Import the installed plugin, or return None.

    Assertions run against the plugin's *real* SVs rather than a freshly constructed
    probe, because SV.__init__ derives the plugin name from the caller's file path
    (sv.py:180-190) and raises ValueError for any file outside a plugins/ tree -- a
    test module can never satisfy that. The real SVs are also the objects the reload
    path actually mutates, so this is the more meaningful target.
    """
    if not GSCORE_AVAILABLE:
        return None
    try:
        import plugins.TodayImage  # noqa: F401
        from gsuid_core.sv import SL
    except Exception:
        return None
    return {name: sv for name, sv in SL.lst.items() if '今日图片' in name}


PLUGIN_SVS = _load_plugin()


@unittest.skipUnless(PLUGIN_SVS, 'plugin is not installed under gsuid_core/plugins')
class GsCoreContractTests(unittest.TestCase):
    DAILY_SV = '今日图片-每日抽取'

    def test_all_services_are_registered(self) -> None:
        self.assertEqual(
            sorted(PLUGIN_SVS),
            sorted([
                '今日图片-帮助',
                '今日图片-图库管理',
                '今日图片-图片上传',
                '今日图片-群授权',   # feature 003
                '今日图片-重置',     # feature 004
                self.DAILY_SV,
            ]),
        )

    def test_group_permission_sv_is_admin_gated(self) -> None:
        """pm=3 IS the admin gate (research R1).

        If a GsCore upgrade changed the ladder in sv.py, an ordinary member could
        silently gain the ability to widen their group's content scope -- the
        highest-consequence regression in this feature, so it is pinned, not assumed.
        Ladder: 0=master, 1=superuser, 2=群主, 3=群管理员, 6=普通用户.
        """
        sv = PLUGIN_SVS.get('今日图片-群授权')
        self.assertIsNotNone(sv, 'the group-authorisation SV must be registered')
        self.assertEqual(sv.pm, 3)

        # The commands must live on that SV and nowhere more permissive.
        owned = set()
        for table in sv.TL.values():
            owned.update(table)
        self.assertTrue(any(k.startswith('TodayImage允许') for k in owned))
        self.assertTrue(any(k.startswith('TodayImage禁止') for k in owned))

        for name, other in PLUGIN_SVS.items():
            if name == '今日图片-群授权':
                for table in other.TL.values():
                    continue
                continue
            for table in other.TL.values():
                for keyword in table:
                    with self.subTest(sv=name, keyword=keyword):
                        self.assertFalse(
                            str(keyword).startswith('TodayImage允许')
                            or str(keyword).startswith('TodayImage禁止'),
                            f'{keyword} is registered on {name} (pm={other.pm}), not the pm=3 SV',
                        )

    def test_reset_sv_is_restricted_to_master_and_superuser(self) -> None:
        """pm=1 就是权限本身（research R2）。

        核心判据是 user_pm > sv.pm 即拒绝，阶梯为
        0=master, 1=superuser, 2=群主, 3=群管理员, 6=普通用户。
        若上游改了阶梯，群管理员会悄悄获得「改变全群当日结果」的能力 ——
        这是本功能后果最严重的回归，故钉死而非假设（FR-409、FR-410）。
        """
        sv = PLUGIN_SVS.get('今日图片-重置')
        self.assertIsNotNone(sv, '重置 SV 必须已注册')
        self.assertEqual(sv.pm, 1)

        owned = set()
        for table in sv.TL.values():
            owned.update(table)
        self.assertTrue(any(k.startswith('TodayImage重置') for k in owned))

        # 该命令不得出现在任何权限更宽松的 SV 上
        for name, other in PLUGIN_SVS.items():
            if name == '今日图片-重置':
                continue
            for table in other.TL.values():
                for keyword in table:
                    with self.subTest(sv=name, keyword=keyword):
                        self.assertFalse(
                            str(keyword).startswith('TodayImage重置'),
                            f'{keyword} 注册在 {name}(pm={other.pm})，而非 pm=1 的 SV',
                        )

    def test_reset_is_stricter_than_group_authorisation(self) -> None:
        """有意的权限差异：授权 pm<=3（群管理员可用），重置 pm<=1（仅主人）。"""
        self.assertLess(PLUGIN_SVS['今日图片-重置'].pm, PLUGIN_SVS['今日图片-群授权'].pm)

    def test_priorities_stay_above_the_incumbent_plugins(self) -> None:
        # TodayWaifu occupies 0-10; ours must lose any keyword collision (research R3).
        for name, sv in PLUGIN_SVS.items():
            with self.subTest(sv=name):
                self.assertGreaterEqual(sv.priority, 20)

    def test_trigger_table_has_the_shape_the_draw_path_assumes(self) -> None:
        """Feature 002 resolves types at request time, so the draw SV owns exactly one
        non-blocking prefix trigger and no per-keyword fullmatch table."""
        from gsuid_core.trigger import Trigger

        sv = PLUGIN_SVS[self.DAILY_SV]
        self.assertIsInstance(sv.TL, dict)
        self.assertIn('prefix', sv.TL)
        self.assertIsInstance(sv.TL['prefix'], dict)
        self.assertEqual(len(sv.TL['prefix']), 1)
        for keyword, trigger in sv.TL['prefix'].items():
            self.assertIsInstance(keyword, str)
            self.assertIsInstance(trigger, Trigger)
            self.assertFalse(trigger.block)

    def test_the_dynamic_trigger_is_a_non_blocking_prefix(self) -> None:
        """block=True would terminate the dispatch loop ahead of any plugin at a higher
        priority number and silently kill their 今日X command (FR-106, SC-105)."""
        sv = PLUGIN_SVS[self.DAILY_SV]
        prefix_triggers = sv.TL.get('prefix', {})
        self.assertTrue(prefix_triggers, 'the draw SV must own a prefix trigger')
        for keyword, trigger in prefix_triggers.items():
            with self.subTest(keyword=keyword):
                self.assertFalse(trigger.block, 'the dynamic trigger must not block')

    def test_no_per_folder_commands_are_registered(self) -> None:
        # Feature 002 resolves at request time; a fullmatch table here would mean
        # registry_binding came back and every folder answers twice (I-201).
        sv = PLUGIN_SVS[self.DAILY_SV]
        self.assertEqual(sv.TL.get('fullmatch', {}), {})

    def test_sl_lst_maps_names_to_services(self) -> None:
        from gsuid_core.sv import SL

        self.assertIsInstance(SL.lst, dict)
        for name in PLUGIN_SVS:
            self.assertIn(name, SL.lst)
            self.assertTrue(hasattr(SL.lst[name], 'TL'))

    def test_trigger_match_rules_are_what_the_design_assumes(self) -> None:
        from gsuid_core.trigger import Trigger

        full = Trigger('fullmatch', '今日黑丝', lambda *_: None)
        self.assertTrue(full._check_fullmatch('今日黑丝', '今日黑丝'))
        self.assertFalse(full._check_fullmatch('今日黑丝', '今日黑丝吗'))

        # A command trigger is startswith -- the reason a '今日' catch-all was rejected.
        command = Trigger('command', '今日', lambda *_: None)
        self.assertTrue(command._check_command('今日', '今日黑丝'))

    def test_message_segment_accepts_bytes(self) -> None:
        from gsuid_core.segment import MessageSegment

        segment = MessageSegment.image(b'\x89PNG\r\n\x1a\n')
        self.assertEqual(segment.type, 'image')

    def test_does_not_collide_with_todaywaifu(self) -> None:
        """Coexistence check, run only when both plugins are installed."""
        from gsuid_core.sv import SL

        ours = set()
        for sv in PLUGIN_SVS.values():
            for ttype, table in sv.TL.items():
                if ttype == 'prefix':
                    continue  # the dynamic trigger is meant to be broad; see the next test
                ours.update(table)

        theirs = set()
        for name, sv in SL.lst.items():
            if name in PLUGIN_SVS:
                continue
            for table in getattr(sv, 'TL', {}).values():
                if isinstance(table, dict):
                    theirs.update(table)

        self.assertEqual(ours & theirs, set(), 'TodayImage must not shadow another plugin')

    def test_every_foreign_today_command_is_blocklisted(self) -> None:
        """The dynamic 今日 prefix sees other plugins' 今日 commands too.

        Priority ordering already stops us answering them *while they are loaded*, but
        the blocklist is what covers TodayWaifu being disabled, or someone creating a
        folder with the same name (V-BLK-3). Asserting live coverage means a future
        TodayWaifu command we forget to block fails here instead of in chat.
        """
        import importlib.util as _ilu
        import sys as _sys
        from gsuid_core.sv import SL

        spec = _ilu.spec_from_file_location(
            'todayimage_blocklist_probe', TDI_DIR / 'blocklist.py'
        )
        assert spec and spec.loader
        blocklist = _ilu.module_from_spec(spec)
        _sys.modules[spec.name] = blocklist
        spec.loader.exec_module(blocklist)

        prefix = '今日'
        foreign = set()
        for name, sv in SL.lst.items():
            if name in PLUGIN_SVS:
                continue
            for table in getattr(sv, 'TL', {}).values():
                if isinstance(table, dict):
                    foreign.update(k for k in table if str(k).startswith(prefix))

        missed = sorted(k for k in foreign if not blocklist.is_blocked(k, []))
        self.assertEqual(
            missed, [],
            f'these foreign 今日 commands are not blocklisted: {missed}',
        )


if __name__ == '__main__':
    unittest.main()
