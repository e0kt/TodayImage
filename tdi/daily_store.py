"""每日抽图记录的存取与「抽签 + 定桩」逻辑。

PURE 模块：只依赖标准库，不导入 gsuid_core。

抽签用种子随机（date:user:chat:category），这是今日萝莉的原方案，
天然给出「同一天同一人同一群固定」以及跨用户/跨群互不相干。

但只靠种子不够：种子选的是**列表下标**，一旦当天有人上传或删图，
列表一变，所有人的当天结果就跟着变了，FR-006 的承诺当场失效。
所以把抽到的具体路径落盘定桩，图库中途变动也不影响已抽的人。
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
import random
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

# 每日重置的时区偏移（小时）。默认 +8 = 北京时间：
# 若直接用服务器本地时间，机器放在别的时区时重置点就会漂到当地半夜以外的时刻。
# 中国全年不实行夏令时，所以固定偏移就够精确，不必依赖系统的 tzdata。
DEFAULT_RESET_UTC_OFFSET = 8

RECORDS_VERSION = 1
_SEPARATOR = '|'

_locks: dict[tuple[str, str], asyncio.Lock] = {}


# ── 记录键 ────────────────────────────────────────────────────────────────────

def record_key(chat_key: str, user_key: str, category: str) -> str:
    return f'{chat_key}{_SEPARATOR}{user_key}{_SEPARATOR}{category}'


def parse_key(key: str) -> tuple[str, str, str] | None:
    """只按前两个分隔符切分，因此类型名里带 | 也能正确还原。"""
    parts = key.split(_SEPARATOR, 2)
    if len(parts) != 3:
        return None
    return parts[0], parts[1], parts[2]


# ── 读写 ──────────────────────────────────────────────────────────────────────

def load_records(path: Path, date: str) -> dict[str, dict[str, Any]]:
    """读取当天记录。文件坏了就当空表 —— 大不了少定一天的桩，不能让命令炸掉。"""
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get('date') != date:
        return {}
    records = payload.get('records')
    if not isinstance(records, dict):
        return {}
    return {str(k): dict(v) for k, v in records.items() if isinstance(v, dict)}


def save_records(path: Path, date: str, records: dict[str, dict[str, Any]]) -> None:
    """整份覆盖写。写入时只留当天，过期记录直接丢掉（S-2），不做归档。"""
    payload = {'version': RECORDS_VERSION, 'date': date, 'records': records}
    _atomic_write_json(path, payload)


def upsert_record(path: Path, date: str, key: str, image: str) -> dict[str, dict[str, Any]]:
    records = load_records(path, date)
    records[key] = {'image': image, 'created_at': time.time()}
    save_records(path, date, records)
    return records


def get_record_image(records: dict[str, dict[str, Any]], key: str) -> str | None:
    entry = records.get(key)
    if not isinstance(entry, dict):
        return None
    image = entry.get('image')
    return image if isinstance(image, str) and image else None


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f'.{path.name}.',
        suffix='.tmp',
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


# ── 抽签 ──────────────────────────────────────────────────────────────────────

def current_date(utc_offset_hours: float = DEFAULT_RESET_UTC_OFFSET, now: Any = None) -> str:
    """按指定时区偏移取「今天」，默认北京时间。"""
    moment = now or _dt.datetime.now(_dt.timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_dt.timezone.utc)
    shifted = moment.astimezone(_dt.timezone(_dt.timedelta(hours=utc_offset_hours)))
    return shifted.date().isoformat()


def taken_images(
    records: dict[str, dict[str, Any]],
    chat_key: str,
    category: str,
    exclude_key: str,
) -> set[str]:
    """同一个群、同一个类型下，今天已经被别人抽走的图片。"""
    taken: set[str] = set()
    for key, entry in records.items():
        if key == exclude_key:
            continue
        parsed = parse_key(key)
        if parsed is None:
            continue
        row_chat, _row_user, row_category = parsed
        if row_chat != chat_key or row_category != category:
            continue
        image = entry.get('image') if isinstance(entry, dict) else None
        if isinstance(image, str) and image:
            taken.add(image)
    return taken


def draw_seed(date: str, user_key: str, chat_key: str, category: str) -> str:
    return f'{date}:{user_key}:{chat_key}:{category}'


def pick_image(images: tuple[str, ...], seed: str) -> str | None:
    if not images:
        return None
    return random.Random(seed).choice(list(images))


def _lock_for(chat_key: str, category: str) -> asyncio.Lock:
    key = (chat_key, category)
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


def clear_locks() -> None:
    """测试用：锁绑定在事件循环上，跨 asyncio.run 必须清掉。"""
    _locks.clear()


def _default_exists(path: str) -> bool:
    return Path(path).is_file()


async def resolve_daily_image(
    records_path: Path,
    date: str,
    chat_key: str,
    user_key: str,
    category: str,
    images: tuple[str, ...],
    exists: Callable[[str], bool] | None = None,
    unique_per_chat: bool = True,
) -> str | None:
    """取当天该类型该用户的图片，必要时抽签并定桩。

    date 由调用方在一次抽图开始时取一次并原样传进来：
    若在函数内部各处 today() 各取一次，跨零点的请求可能用 A 日的种子写进 B 日的记录（V-REC-6）。
    """
    if not images:
        return None  # 空图库不写记录（V-REC-5）

    file_exists = exists or _default_exists
    key = record_key(chat_key, user_key, category)

    records = await asyncio.to_thread(load_records, records_path, date)
    pinned = get_record_image(records, key)
    if pinned is not None and file_exists(pinned):
        return pinned

    # 抽签必须在锁内完成：去重要看「别人已经抽走了哪些」，
    # 在锁外算会让并发的首抽读到同一份快照，从而抽到同一张图。
    async with _lock_for(chat_key, category):
        records = await asyncio.to_thread(load_records, records_path, date)
        pinned = get_record_image(records, key)
        if pinned is not None and file_exists(pinned):
            return pinned

        pool = list(images)
        if unique_per_chat:
            taken = taken_images(records, chat_key, category, key)
            remaining = [image for image in pool if image not in taken]
            # 图片不够分时退回整个图库：宁可有人撞图，也不能因为「没得挑」而不回复。
            pool = remaining or pool

        seed = draw_seed(date, user_key, chat_key, category)
        chosen = pick_image(tuple(pool), seed)
        if chosen is None:
            return None
        if not file_exists(chosen):
            # 抽中的文件刚好被删了，就在存在的图片里重挑一次。
            alive = [image for image in pool if file_exists(image)]
            chosen = pick_image(tuple(alive), seed)
            if chosen is None:
                return None

        await asyncio.to_thread(upsert_record, records_path, date, key, chosen)
        return chosen
