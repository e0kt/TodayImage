"""每日抽图记录的存取与「抽签 + 定桩」逻辑。

PURE 模块：只依赖标准库，不导入 gsuid_core。

抽签用种子随机（date:user:chat:category），这是今日萝莉的原方案，
天然给出「同一天同一人同一群固定」以及跨用户/跨群互不相干。

但只靠种子不够：种子选的是**列表下标**，一旦当天有人上传或删图，
列表一变，所有人的当天结果就跟着变了，FR-006 的承诺当场失效。
所以把抽到的具体路径落盘定桩，图库中途变动也不影响已抽的人。

原子写入方案沿用 TodayWaifu 的 twf/storage.py（GPL-3.0）。
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

from .group_permissions import normalize_tag

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

def _load_payload(
    path: Path, date: str
) -> tuple[dict[str, dict[str, Any]], dict[str, int], dict[str, list[str]]]:
    """一次读盘同时取出当天的记录与重置代数。文件坏了一律当空表。

    降级方向：记录为空 = 少定一天的桩；代数为空 = 回到未重置状态。
    两者都不会放大影响面（S-405）。
    """
    if not path.is_file():
        return {}, {}, {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}, {}, {}
    if not isinstance(payload, dict) or payload.get('date') != date:
        return {}, {}, {}

    raw_records = payload.get('records')
    records = (
        {str(k): dict(v) for k, v in raw_records.items() if isinstance(v, dict)}
        if isinstance(raw_records, dict) else {}
    )
    # 老文件没有 resets 字段，读作空表即可，无需迁移（S-402）。
    raw_resets = payload.get('resets')
    resets = (
        {str(k): int(v) for k, v in raw_resets.items() if isinstance(v, int)}
        if isinstance(raw_resets, dict) else {}
    )
    raw_excludes = payload.get('excludes')
    excludes = (
        {str(k): [str(i) for i in v] for k, v in raw_excludes.items() if isinstance(v, list)}
        if isinstance(raw_excludes, dict) else {}
    )
    return records, resets, excludes


def load_records(path: Path, date: str) -> dict[str, dict[str, Any]]:
    """读取当天记录。文件坏了就当空表 —— 大不了少定一天的桩，不能让命令炸掉。"""
    return _load_payload(path, date)[0]


def load_resets(path: Path, date: str) -> dict[str, int]:
    """读取当天的重置代数表。"""
    return _load_payload(path, date)[1]


def load_excludes(path: Path, date: str) -> dict[str, list[str]]:
    """读取当天各 (群,类型) 上一轮已发出、本轮需排除的图片。"""
    return _load_payload(path, date)[2]


def save_records(
    path: Path,
    date: str,
    records: dict[str, dict[str, Any]],
    resets: dict[str, int] | None = None,
    excludes: dict[str, list[str]] | None = None,
) -> None:
    """整份覆盖写。写入时只留当天，过期记录直接丢掉（S-2），不做归档。

    resets 传 None 表示「沿用盘上当天的代数」。这一点不能省：抽图走
    upsert_record -> save_records，若那条路径把 resets 写没了，第一次抽图
    就会把代数清零，重置对后面的人当场失效（S-403 同时要求跨日一并丢弃）。
    """
    if resets is None or excludes is None:
        _, disk_resets, disk_excludes = _load_payload(path, date)
        if resets is None:
            resets = disk_resets
        if excludes is None:
            excludes = disk_excludes
    payload = {
        'version': RECORDS_VERSION,
        'date': date,
        'records': records,
        'resets': resets,
        'excludes': excludes,
    }
    _atomic_write_json(path, payload)


def upsert_record(path: Path, date: str, key: str, image: str) -> dict[str, dict[str, Any]]:
    records, resets, excludes = _load_payload(path, date)
    records[key] = {'image': image, 'created_at': time.time()}
    save_records(path, date, records, resets, excludes)
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


def reset_key(chat_key: str, category: str) -> str:
    """代数与排除集的键。

    类型名在这里统一归一（去括号、strip、casefold），与图库索引、分群授权用同一套规则。
    不归一的话，存储层拿到 '【黑丝】' 会静默匹配不到任何记录 ——
    表现为「清除 0 条」，看起来跟「本来就没人抽过」一模一样，极难排查。
    """
    return f'{chat_key}{_SEPARATOR}{normalize_tag(category)}'


def parse_reset_key(key: str) -> tuple[str, str] | None:
    """只切第一个分隔符，因此类型名里带 | 也能正确还原（V-EPO-1）。"""
    parts = key.split(_SEPARATOR, 1)
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def reset_epoch(resets: dict[str, int], chat_key: str, category: str) -> int:
    value = resets.get(reset_key(chat_key, category))
    return value if isinstance(value, int) and value > 0 else 0


def draw_seed(
    date: str,
    user_key: str,
    chat_key: str,
    category: str,
    epoch: int = 0,
) -> str:
    """抽图种子。

    epoch 为 0 时**必须**与加入重置功能之前逐字节相同 —— 否则这个功能一上线，
    就会把所有群当天已经抽到的图静默换掉一遍，那是一次无声的全局副作用（V-SEED-1）。
    只有真的被重置过的 (日期, 群, 类型) 才会拿到不同的种子。
    """
    seed = f'{date}:{user_key}:{chat_key}:{category}'
    if epoch:
        seed = f'{seed}:r{epoch}'
    return seed


def pick_image(images: tuple[str, ...], seed: str) -> str | None:
    if not images:
        return None
    return random.Random(seed).choice(list(images))


def pick_random(images: tuple[str, ...], rng: Any = None) -> str | None:
    """不定桩地随便抽一张，用于私聊。

    与 pick_image 的区别是**不带种子**：私聊要的是每次都换一张，
    而种子随机的整个意义恰恰是「同一天同一个人拿到同一张」。
    因为不定桩，这条路径也不写 daily_records —— 私聊不该把记录文件撑大。
    """
    if not images:
        return None
    source = rng if rng is not None else random
    return source.choice(list(images))


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


async def reset_group_category(
    path: Path,
    date: str,
    chat_key: str,
    category: str,
) -> tuple[int, int]:
    """清掉某群某类型当天的全部绑定，并把重置代数 +1。

    返回 (清除条数, 新代数)。

    两件事必须在同一次原子写内完成：只清记录而不改代数的话，所有人重抽会用
    同样的种子拿回同样的图 —— 功能等于没做（research R1 实测）。分两次写则中间
    崩溃会留下同样的状态（I-402）。

    持的是抽图那把锁，否则会出现一半人停在上一轮、一半人进入新一轮，
    而两轮之间并不保证互不撞图（FR-408）。
    """
    category = normalize_tag(category)
    async with _lock_for(chat_key, category):
        records, resets, excludes = await asyncio.to_thread(_load_payload, path, date)

        target = category
        survivors: dict[str, dict[str, Any]] = {}
        cleared_images: set[str] = set()
        cleared = 0
        for key, entry in records.items():
            parsed = parse_key(key)
            if parsed is not None:
                row_chat, _row_user, row_category = parsed
                if row_chat == chat_key and normalize_tag(row_category) == target:
                    cleared += 1
                    image = entry.get('image')
                    if isinstance(image, str) and image:
                        cleared_images.add(image)
                    continue
            survivors[key] = entry

        # 即使一条都没清，代数也要 +1：否则「今天还没人抽过 -> 重置无效 ->
        # 稍后抽的人仍落在旧种子」会形成一个很难察觉的空洞（V-RES-2）。
        rkey = reset_key(chat_key, category)
        epoch = reset_epoch(resets, chat_key, category) + 1
        resets = dict(resets)
        resets[rkey] = epoch

        # 只换种子只能做到「很可能不同」：两个不同的种子有 1/N 的概率落回同一张图，
        # 50 张的图库下连抽几轮就会撞上。而 FR-402 要的是 MUST。
        # 所以把这一轮清掉的图记成排除集，下一轮直接不从里面选。
        excludes = dict(excludes)
        excludes[rkey] = sorted(cleared_images)

        await asyncio.to_thread(save_records, path, date, survivors, resets, excludes)
        return cleared, epoch


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
    # 重置代数也在同一把锁内读，否则可能出现一半人用旧代数、一半人用新代数。
    async with _lock_for(chat_key, category):
        records, resets, excludes = await asyncio.to_thread(_load_payload, records_path, date)
        epoch = reset_epoch(resets, chat_key, category)
        excluded = set(excludes.get(reset_key(chat_key, category), ()))
        pinned = get_record_image(records, key)
        if pinned is not None and file_exists(pinned):
            return pinned

        pool = list(images)
        if excluded:
            # 上一轮已经发过的图不再参与，保证重置后确实换一张（FR-402）。
            # 图不够分时退回全量，宁可重复也不能没得发。
            pool = [image for image in pool if image not in excluded] or pool
        if unique_per_chat:
            taken = taken_images(records, chat_key, category, key)
            remaining = [image for image in pool if image not in taken]
            # 图片不够分时退回整个图库：宁可有人撞图，也不能因为「没得挑」而不回复。
            pool = remaining or pool

        seed = draw_seed(date, user_key, chat_key, category, epoch)
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
