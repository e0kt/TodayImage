"""分群授权命令的回复文案。

PURE 模块：只依赖标准库，不导入 gsuid_core。

拆出来是为了能脱离核心直接测 —— 这些文案里有两条容易写错的规则：
私聊要给出解释而不是静默（FR-214），以及只能说「本群」的授权情况、
不能顺带把服务器上有哪些类型列出来（FR-215、V-DIS-6）。
"""
from __future__ import annotations

from typing import Iterable

DIRECT_CHAT_SETTING = '这个命令只能在群里使用，用来设置该群可以发送的图片类型。私聊不受限制。'
DIRECT_CHAT_LIST = '私聊不受类型限制，无需设置。'

USAGE_ALLOW = '用法：TodayImage允许<类型名>，例如 TodayImage允许黑丝'
USAGE_DENY = '用法：TodayImage禁止<类型名>，例如 TodayImage禁止黑丝'

MISSING_FOLDER_NOTE = '注意：服务器上目前没有这个类型的文件夹，建好后即可使用。'


def allow_reply(tag: str, *, newly_added: bool, folder_exists: bool) -> str:
    if not newly_added:
        return f'本群已经允许【{tag}】了。'
    text = f'已允许本群使用【{tag}】。'
    if not folder_exists:
        # 只针对管理员刚输入的那一个类型给提示，不是把目录列出来（V-DIS-7）。
        text += MISSING_FOLDER_NOTE
    return text


def deny_reply(tag: str, *, removed: bool) -> str:
    if not removed:
        return f'本群本来就没有允许【{tag}】。'
    return f'已禁止本群使用【{tag}】。'


def list_reply(tags: Iterable[str], missing: Iterable[str] = ()) -> str:
    """只列出**本群**的授权情况，绝不列出服务器上有哪些类型。"""
    tags = sorted(tags)
    if not tags:
        return '本群还没有允许任何类型。使用「TodayImage允许<类型名>」开启。'
    lines = [f'本群已允许：{"、".join(tags)}']
    missing = sorted(missing)
    if missing:
        lines.append(f'其中以下类型在服务器上没有对应文件夹：{"、".join(missing)}')
    return '\n'.join(lines)
