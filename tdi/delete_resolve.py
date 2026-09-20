"""解析一条「回复 + 删除<标签>」指向哪一张图，或为什么不能确定。

PURE 模块：只依赖标准库，不导入 gsuid_core。不触碰文件系统，因此拒绝分支可穷举测试。

**三级退让**（顺序即优先级）：
  1. reply_id 命中回执表        -> 唯一确定
  2. 未命中，但该会话该类型当天恰好一条记录 -> 采用
  3. 零条或多条                 -> 拒绝

**任何非 ok 的结果都不得携带可删除的路径。** 这是一个不可逆且全局的操作，
误删一个文件影响所有群和今后所有抽取，而"功能暂时不可用"只是不便。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .daily_store import parse_key
from .group_permissions import normalize_tag

OK = 'ok'
NOT_FOUND = 'not_found'
AMBIGUOUS = 'ambiguous'
TAG_MISMATCH = 'tag_mismatch'
NOT_A_DRAW = 'not_a_draw'


@dataclass(frozen=True)
class DeleteResolution:
    outcome: str
    image: str | None = None
    candidates: tuple[str, ...] = field(default=())
    actual_category: str | None = None


def resolve(
    reply_id: Any,
    tag: Any,
    sent_index: Any,
    today_records: dict[str, dict[str, Any]],
    category_of: Callable[[str], Any],
    chat_key: str,
) -> DeleteResolution:
    """Args:
        reply_id: 被回复消息的 ID；为空说明根本不是回复。
        tag: 命令里写的类型名。
        sent_index: 回执表，需提供 lookup(message_id)。
        today_records: 当天全部记录。
        category_of: 文件路径 -> 实际所属类型；用于校验标签。
        chat_key: 命令所在会话，第 2 级解析的范围。
    """
    wanted = normalize_tag(tag)
    if not wanted:
        return DeleteResolution(NOT_A_DRAW)

    key = str(reply_id or '').strip()
    if not key:
        # 不是回复 —— 本命令必须对着那张图用。
        return DeleteResolution(NOT_A_DRAW)

    # 第 1 级：回执表
    ref = sent_index.lookup(key)
    if ref is not None:
        return _verify(ref.image, wanted, category_of)

    # 第 2 级：当日记录唯一性。小群里常常只有一个人抽过该类型，此时唯一性是真实的。
    holders = _records_in(today_records, chat_key, wanted)
    if len(holders) == 1:
        return _verify(holders[0], wanted, category_of)
    if len(holders) > 1:
        return DeleteResolution(AMBIGUOUS, candidates=tuple(holders))

    return DeleteResolution(NOT_FOUND)


def _records_in(
    records: dict[str, dict[str, Any]], chat_key: str, category: str
) -> list[str]:
    images: list[str] = []
    for record_key, entry in records.items():
        parsed = parse_key(record_key)
        if parsed is None:
            continue
        row_chat, _row_user, row_category = parsed
        if row_chat != chat_key or normalize_tag(row_category) != category:
            continue
        image = entry.get('image') if isinstance(entry, dict) else None
        if isinstance(image, str) and image and image not in images:
            images.append(image)
    return images


def _verify(image: str, wanted: str, category_of: Callable[[str], Any]) -> DeleteResolution:
    """标签必须与文件实际所属类型一致。防的是「看错了图，删错了类型」。"""
    actual = normalize_tag(category_of(image) or '')
    if actual and actual != wanted:
        return DeleteResolution(TAG_MISMATCH, actual_category=actual)
    return DeleteResolution(OK, image=image)
