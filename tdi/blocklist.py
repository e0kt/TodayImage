"""不回复的命令名单。

PURE 模块：只依赖标准库，不导入 gsuid_core。

优先级排序本身已经能让 TodayWaifu 先响应它自己的命令（研究 R2），
但那只在 TodayWaifu 处于加载状态时成立。本名单覆盖它管不到的三种情况：
TodayWaifu 被停用、有人真的建了个叫「老婆」的文件夹、以及优先级被改动。

名单在查文件系统之前判断 —— 被屏蔽的名字恰好也是最可能被刷屏的那些。
"""
from __future__ import annotations

from typing import Any, Iterable

# 取自本机上 TodayWaifu 实际注册的 16 个「今日*」触发器，归并为 12 个基名。
# 按前缀匹配，所以「今日老婆」同时覆盖「今日老婆离婚」以及将来新增的后缀。
DEFAULT_BLOCKLIST: tuple[str, ...] = (
    '今日老婆',
    '今日老公',
    '今日萝莉',
    '今日战双老婆',
    '今日异环老婆',
    '今日群友离婚',
    '今日老婆帮助',
    '今日老婆离婚',
    '今日老公离婚',
    '今日萝莉离婚',
    '今日萝莉列表',
    '今日萝莉上传',
)


def normalize_entries(values: Any) -> tuple[str, ...]:
    """把配置里的名单归一化。空串必须丢掉：空基名会前缀匹配到所有命令。"""
    if isinstance(values, str):
        items: Iterable[Any] = values.replace(',', ' ').split()
    elif isinstance(values, (list, tuple, set, frozenset)):
        items = values
    else:
        return ()
    result: list[str] = []
    for value in items:
        text = str(value).strip().casefold()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def effective_blocklist(extra: Any = None, allow: Any = None) -> tuple[str, ...]:
    """默认名单 + 运营方补充 - 运营方放行。

    补充（extra）只能增不能减：随手改个配置就让插件开始抢别的插件的命令，
    风险太大（V-BLK-5）。

    放行（allow）是那条规则的显式出口。当运营方把某个类型**迁移**到本插件、
    并关掉上游对应功能时（例如把「今日萝莉」从 TodayWaifu 搬过来），
    没有出口的话那个类型就永远发不出来。放行要求逐条写明，
    且按**完整基名精确匹配** —— 放行「今日萝莉」不会顺带放行
    「今日萝莉列表」这些仍归上游所有的子命令。
    """
    allowed = set(normalize_entries(allow))
    bases = [name.casefold() for name in DEFAULT_BLOCKLIST]
    for name in normalize_entries(extra):
        if name not in bases:
            bases.append(name)
    return tuple(base for base in bases if base not in allowed)


def is_blocked(command: str, extra: Any = None, allow: Any = None) -> bool:
    text = str(command or '').strip().casefold()
    if not text:
        return False
    return any(text == base or text.startswith(base) for base in effective_blocklist(extra, allow))
