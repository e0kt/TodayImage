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

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable

DEFAULT_MAX_ENTRIES = 512


@dataclass(frozen=True)
class SentImageRef:
    image: str
    category: str
    chat_key: str
    user_key: str


class SentIndex:
    """有界 LRU。抽图是高频操作，不设上限的字典会随运行时间单调增长。"""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self.max_entries = max_entries
        self._entries: OrderedDict[str, SentImageRef] = OrderedDict()

    def remember(
        self,
        message_ids: Iterable[Any] | None,
        image: str,
        category: str,
        chat_key: str,
        user_key: str,
    ) -> None:
        """记下一次发送。拿不到消息 ID 时静默跳过 —— 绝不能因此报错或拖慢发送。"""
        if not message_ids or not image:
            return
        ref = SentImageRef(str(image), str(category), str(chat_key), str(user_key))
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

    def clear(self) -> None:
        self._entries.clear()

    @property
    def size(self) -> int:
        return len(self._entries)
