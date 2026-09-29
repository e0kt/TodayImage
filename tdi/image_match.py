"""把一张图片的字节匹配回本地图库里的文件。

PURE 模块：只依赖标准库。感知哈希需要 Pillow，按可选依赖处理 ——
装不上就只剩字节比对，功能降级但不报错。

**为什么走这条路**：适配器会把被回复的那张图放进 ev.image / ev.image_list。
拿到图本身就不必依赖发送回执（本部署的 OneBot 适配器根本不返回消息 ID），
也不怕核心重启清空内存表。
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Iterable


def _sha256_file(path: str) -> str:
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def find_exact(data: bytes, candidates: Iterable[str]) -> str | None:
    """在候选文件里找字节完全相同的那个。

    先按体积筛：图库有几万张，无差别哈希会让一条低频的管理命令变得很慢，
    而体积相同才有可能内容相同，os.stat 比读文件便宜得多。
    """
    if not data:
        return None
    size = len(data)
    digest = hashlib.sha256(data).hexdigest()
    for path in candidates:
        try:
            if os.path.getsize(path) != size:
                continue
            if _sha256_file(path) == digest:
                return path
        except OSError:
            continue
    return None


def _dhash(image: Any, size: int = 8) -> int | None:
    """差分哈希：缩到 (size+1)×size 灰度，逐行比较相邻像素。"""
    try:
        small = image.convert('L').resize((size + 1, size))
    except Exception:  # noqa: BLE001
        return None
    pixels = list(small.getdata())
    bits = 0
    for row in range(size):
        base = row * (size + 1)
        for col in range(size):
            bits = (bits << 1) | int(pixels[base + col] < pixels[base + col + 1])
    return bits


# 感知哈希要解码图片，实测 200 张要 5 秒多。候选集必须很小，
# 这条硬上限是防止将来有人把它接到整个图库上。
MAX_SIMILAR_CANDIDATES = 32


def find_similar(
    data: bytes,
    candidates: Iterable[str],
    max_distance: int = 8,
) -> str | None:
    """字节比对失败时的退路：感知哈希，抗重新编码与轻微缩放。

    **只应用于很小的候选集** —— 对几万张图逐一解码是不可接受的，
    超过 MAX_SIMILAR_CANDIDATES 会直接放弃而不是慢慢算。
    Pillow 不可用时返回 None，由调用方继续往下退。
    """
    candidates = list(candidates)
    if len(candidates) > MAX_SIMILAR_CANDIDATES:
        return None
    if not data or not candidates:
        return None
    try:
        import io

        from PIL import Image
    except Exception:  # noqa: BLE001
        return None

    try:
        with Image.open(io.BytesIO(data)) as probe:
            target = _dhash(probe)
    except Exception:  # noqa: BLE001
        return None
    if target is None:
        return None

    best, best_distance = None, max_distance + 1
    for path in candidates:
        try:
            with Image.open(path) as image:
                other = _dhash(image)
        except Exception:  # noqa: BLE001
            continue
        if other is None:
            continue
        distance = bin(target ^ other).count('1')
        if distance < best_distance:
            best, best_distance = path, distance
    return best if best_distance <= max_distance else None
