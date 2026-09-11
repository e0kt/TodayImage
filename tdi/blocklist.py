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


def effective_blocklist(extra: Any = None) -> tuple[str, ...]:
    """默认名单 + 运营方补充。补充只能增不能减（V-BLK-5）：
    任何控制台改动都不该让本插件开始回复别的插件的命令。
    """
    bases = [name.casefold() for name in DEFAULT_BLOCKLIST]
    for name in normalize_entries(extra):
        if name not in bases:
            bases.append(name)
    return tuple(bases)


def is_blocked(command: str, extra: Any = None) -> bool:
    text = str(command or '').strip().casefold()
    if not text:
        return False
    return any(text == base or text.startswith(base) for base in effective_blocklist(extra))
