"""回复删图的回复文案。

PURE 模块：只依赖标准库，不导入 gsuid_core。

五种失败必须彼此不同且可操作 —— 这是一个会删文件的命令，
发命令的人必须能分清「没删成」和「删错了」。
"""
from __future__ import annotations

from typing import Iterable

FALLBACK = '请改用「删除图片 <类型> <图片ID>」，图片ID 可通过「查看图片 <类型>」获取。'
NOT_A_DRAW = '请对机器人发出的那张图**回复**本命令，例如回复图片并发送「删除黑丝」。'
NOT_FOUND = f'认不出这是哪一张。{FALLBACK}'
MASTER_ONLY = '当前配置下只有机器人主人可以删除图库文件。'
# 走兜底时必须说明 —— 万一删错了，要让人当场就能看出来
BY_RECENCY_NOTE = '（按「本群该类型最近发出的那张」判定，若删错了请用「上传图片」补回）'


def success_reply(category: str, *, affected: int, by_recency: bool = False) -> str:
    if affected > 0:
        text = f'已删除【{category}】的这张图，{affected} 人可以重新抽了。'
    else:
        text = f'已删除【{category}】的这张图。'
    if by_recency:
        text += BY_RECENCY_NOTE
    return text


def missing_file_reply(category: str, *, affected: int) -> str:
    return (
        f'【{category}】的该图片文件已不存在，'
        f'已清理 {affected} 条记录，相关的人可以重新抽了。'
    )


def ambiguous_reply(short_ids: Iterable[str]) -> str:
    ids = '、'.join(sorted(short_ids))
    return f'无法确定是哪一张，候选：{ids}。{FALLBACK}'


def tag_mismatch_reply(actual: str, wanted: str) -> str:
    return f'这张图属于【{actual}】，不是【{wanted}】。为避免误删，未做任何改动。'
