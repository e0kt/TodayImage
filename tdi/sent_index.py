"""已发图片回执表：消息 ID -> 图片文件。

PURE 模块：只依赖标准库，不导入 gsuid_core。

**为什么需要它**：实测（生产日志）回复事件里适配器只给 reply_id 和被回复消息的
**文本**，image / image_list / image_id 全空 —— 拿不到被回复的那张图本身。
所以「这是哪一张」只能靠发送时记下的映射反查。

仅内存、有界、不落盘：用途是「刚发出的图被回复」，窗口以分钟计；
跨天跨重启的需求不存在，落盘只会多一个要按日清理的文件。
丢失是安全的 —— 退回按当日记录唯一性解析，再不行就拒绝，绝不会因此误删。
"""
from __future__ import annotations

import time as _time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable

from .group_permissions import normalize_tag

DEFAULT_MAX_ENTRIES = 512
# 「最近发出的那张」按 (会话, 类型) 各留一条即可 —— 兜底只关心最新的
DEFAULT_MAX_RECENT = 256


@dataclass(frozen=True)
class SentImageRef:
    image: str
    category: str
    chat_key: str
    user_key: str


class SentIndex:
    """有界 LRU。抽图是高频操作，不设上限的字典会随运行时间单调增长。"""

    def __init__(
        self,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        max_recent: int | None = None,
    ) -> None:
        self.max_entries = max_entries
        # 只给一个上限时两者一致，避免"限了消息表却没限时间线"这种意外
        self.max_recent = max_entries if max_recent is None else max_recent
        self._entries: OrderedDict[str, SentImageRef] = OrderedDict()
        # (会话, 归一化类型) -> (发送时刻, 引用)
        self._recent: OrderedDict[tuple[str, str], tuple[float, SentImageRef]] = OrderedDict()

    def remember(
        self,
        message_ids: Iterable[Any] | None,
        image: str,
        category: str,
        chat_key: str,
        user_key: str,
        now: float | None = None,
    ) -> None:
        """记下一次发送。

        **时间线无论如何都要记**：不支持回执的适配器上 message_ids 恒为空，
        若那时连时间线也不记，按时间兜底的那一级同样没有数据可用 ——
        功能就只剩「当日记录恰好唯一」那一种情况能用。
        """
        if not image:
            return
        ref = SentImageRef(str(image), str(category), str(chat_key), str(user_key))

        recent_key = (str(chat_key), normalize_tag(category))
        self._recent[recent_key] = (
            _time.time() if now is None else float(now),
            ref,
        )
        self._recent.move_to_end(recent_key)
        while len(self._recent) > self.max_recent:
            self._recent.popitem(last=False)

        if not message_ids:
            return
        for raw in message_ids:
            key = str(raw or '').strip()
            if not key:
                continue
            # 一次发送可能被平台拆成多条消息，每条都可能被回复，故逐个登记。
            self._entries[key] = ref
            self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def lookup(self, message_id: Any) -> SentImageRef | None:
        key = str(message_id or '').strip()
        if not key:
            return None
        ref = self._entries.get(key)
        if ref is not None:
            self._entries.move_to_end(key)
        return ref

    def recent(
        self,
        chat_key: str,
        category: str,
        now: float | None = None,
        within: float = 0.0,
    ) -> SentImageRef | None:
        """该会话该类型最近发出的那张，仅在时间窗内有效。

        时间窗是这条路径唯一的安全边界：回复一张很久以前的图时必须落空，
        而不是把最新那张删掉。within<=0 表示禁用兜底。
        """
        if within <= 0:
            return None
        entry = self._recent.get((str(chat_key), normalize_tag(category)))
        if entry is None:
            return None
        sent_at, ref = entry
        moment = _time.time() if now is None else float(now)
        if moment - sent_at > within:
            return None
        return ref

    def clear(self) -> None:
        self._entries.clear()
        self._recent.clear()

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def recent_size(self) -> int:
        return len(self._recent)
