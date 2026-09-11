"""按 mtime 缓存本地文件字节。

PURE 模块：只依赖标准库，不导入 gsuid_core。

发图时把文件字节交给 MessageSegment.image 而不是 Path，是为了让这层缓存真正生效 ——
传 Path 会让核心在每次发送时自己去读盘，缓存就白做了。
缓存键包含 mtime 与大小，图片被替换后会自动重新读取，不需要手动清缓存。
条目数与总字节数双重设限：只限条目数的话，几张大图就能把核心进程的内存吃掉。

本模块改编自 TodayWaifu 的 twf/file_cache.py（GPL-3.0）。
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

LOCAL_BYTES_CACHE_MAX_ENTRIES = 128
LOCAL_BYTES_CACHE_MAX_BYTES = 128 * 1024 * 1024

_CACHE: OrderedDict[str, tuple[int, int, bytes]] = OrderedDict()
_TOTAL_BYTES = 0


def read_file_bytes_cached(path: Path) -> bytes:
    """读取文件字节，按 (路径, mtime_ns, 大小) 命中缓存。

    文件不存在时按 stat 的原样抛 OSError，交给调用方决定怎么回复。
    """
    global _TOTAL_BYTES

    stat = path.stat()
    key = str(path)

    cached = _CACHE.get(key)
    if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        _CACHE.move_to_end(key)
        return cached[2]

    data = path.read_bytes()

    previous = _CACHE.pop(key, None)
    if previous is not None:
        _TOTAL_BYTES -= len(previous[2])

    _CACHE[key] = (stat.st_mtime_ns, stat.st_size, data)
    _CACHE.move_to_end(key)
    _TOTAL_BYTES += len(data)

    _evict()
    return data


def _evict() -> None:
    """按条目数和总字节数淘汰最久未使用的条目，但至少保留一条。"""
    global _TOTAL_BYTES
    while len(_CACHE) > 1 and (
        len(_CACHE) > LOCAL_BYTES_CACHE_MAX_ENTRIES
        or _TOTAL_BYTES > LOCAL_BYTES_CACHE_MAX_BYTES
    ):
        _, removed = _CACHE.popitem(last=False)
        _TOTAL_BYTES -= len(removed[2])


def clear_file_caches() -> None:
    """清空缓存（测试与调试用）。"""
    global _TOTAL_BYTES
    _CACHE.clear()
    _TOTAL_BYTES = 0


def cache_entry_count() -> int:
    return len(_CACHE)


def cache_total_bytes() -> int:
    return _TOTAL_BYTES
