"""重置命令的回复文案。

PURE 模块：只依赖标准库，不导入 gsuid_core。

重置是一个**看不见**的操作：群里不会有任何可见变化，直到有人再抽。
所以回复必须带上被清除的条数 —— 否则发命令的人无法区分「生效了」与「类型名打错了」。
"""
from __future__ import annotations

USAGE = '用法：TodayImage重置<类型名>，例如 TodayImage重置黑丝'
DIRECT_CHAT = '这个命令用于重置群里的每日绑定。私聊本就不限次数，无需重置。'
MISSING_FOLDER_NOTE = '注意：服务器上目前没有这个类型的文件夹。'


def reset_reply(category: str, *, cleared: int, folder_exists: bool = True) -> str:
    if cleared > 0:
        text = f'已重置本群的【{category}】，清除 {cleared} 条绑定，大家可以重新抽了。'
    else:
        # 清 0 条是正常结果而不是错误：当天本就没人抽过。
        # 注意代数仍然 +1，所以这次重置对之后抽的人依然有效（V-RES-2）。
        text = f'本群今天还没有人抽过【{category}】，已重置（清除 0 条）。'
    if not folder_exists:
        text += MISSING_FOLDER_NOTE
    return text
