"""分群标签授权的存取。

PURE 模块：只依赖标准库，不导入 gsuid_core。

与本插件其它存储最大的不同是**失败方向相反**：
daily_records / categories 读不出来只是少定一天的桩、退回默认设置；
这里是权限控制，文件缺失或损坏必须让所有群「什么都不允许」，
降级只能收紧、不能放开（FR-218、V-PST-1）。

另外这里**不做缓存**：加 TTL 会让已经撤销的类型还能再用一会儿，
而那正是管理员最不能接受的行为（V-PST-3）。文件很小，一个群一条记录。

原子写入方案沿用 TodayWaifu 的 twf/storage.py（GPL-3.0）。
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

PERMISSIONS_VERSION = 1

# 需求里写的是「TodayImage允许【tag名字】」，管理员照抄这个形式很正常，
# 不能让他真的授权出一个叫「【黑丝】」的类型（V-GRP-2）。
_BRACKETS = '【】[]「」（）()《》<>""\'\''

_locks: dict[str, asyncio.Lock] = {}


# ── 归一化 ────────────────────────────────────────────────────────────────────

def normalize_tag(value: Any) -> str:
    """类型名归一：去括号、去空白、casefold。与图库索引的键保持同一套规则。"""
    text = str(value or '').strip()
    # 反复剥，'【 黑丝 】' 这种括号与空格交替的写法也能剥干净
    while text:
        stripped = text.strip().strip(_BRACKETS).strip()
        if stripped == text:
            break
        text = stripped
    return text.strip().casefold()


def normalize_group_key(group_id: Any) -> str:
    """群号归一。适配器给 int 还是 str 不一定，分裂成两条记录的话，
    管理员看到的现象是「我授权了但没生效」（V-GRP-3）。"""
    return str(group_id if group_id is not None else '').strip()


def normalize_tags(values: Any) -> frozenset[str]:
    if isinstance(values, str):
        items: Iterable[Any] = values.replace(',', ' ').split()
    elif isinstance(values, (list, tuple, set, frozenset)):
        items = values
    else:
        return frozenset()
    return frozenset(tag for value in items if (tag := normalize_tag(value)))


# ── 读写 ──────────────────────────────────────────────────────────────────────

def load_permissions(path: Path) -> dict[str, dict[str, Any]]:
    """读取全部群授权。任何读失败都返回空表 —— 即「所有群都没权限」。"""
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    groups = payload.get('groups')
    if not isinstance(groups, dict):
        return {}
    return {
        normalize_group_key(key): dict(entry)
        for key, entry in groups.items()
        if isinstance(entry, dict)
    }


def save_permissions(path: Path, groups: dict[str, dict[str, Any]]) -> None:
    _atomic_write_json(path, {'version': PERMISSIONS_VERSION, 'groups': groups})


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp'
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


# ── 查询 ──────────────────────────────────────────────────────────────────────

def has_record(path: Path, group_id: Any) -> bool:
    return normalize_group_key(group_id) in load_permissions(path)


def tags_for_group(path: Path, group_id: Any, defaults: Any = None) -> frozenset[str]:
    """本群已允许的类型。

    默认值只对**还没有任何记录**的群生效：群一旦被设置过（哪怕设成空），
    调宽默认值就不该把管理员特意撤销掉的类型又放回去（CF-301）。
    """
    groups = load_permissions(path)
    key = normalize_group_key(group_id)
    entry = groups.get(key)
    if entry is None:
        return normalize_tags(defaults)
    return normalize_tags(entry.get('tags'))


def is_tag_allowed(path: Path, group_id: Any, tag: Any, defaults: Any = None) -> bool:
    normalized = normalize_tag(tag)
    if not normalized:
        return False
    return normalized in tags_for_group(path, group_id, defaults)


# ── 修改 ──────────────────────────────────────────────────────────────────────

def _lock_for(group_key: str) -> asyncio.Lock:
    lock = _locks.get(group_key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[group_key] = lock
    return lock


def clear_locks() -> None:
    """测试用：锁绑定在事件循环上，跨 asyncio.run 必须清掉。"""
    _locks.clear()


async def authorise_tag(path: Path, group_id: Any, tag: Any, operator: Any) -> bool:
    """允许一个类型。返回 True 表示本次新增，False 表示本来就已经允许。"""
    return await _mutate(path, group_id, tag, operator, add=True)


async def revoke_tag(path: Path, group_id: Any, tag: Any, operator: Any) -> bool:
    """撤销一个类型。返回 True 表示确实撤销了，False 表示本来就没允许。"""
    return await _mutate(path, group_id, tag, operator, add=False)


async def _mutate(path: Path, group_id: Any, tag: Any, operator: Any, add: bool) -> bool:
    normalized = normalize_tag(tag)
    if not normalized:
        return False
    key = normalize_group_key(group_id)

    # 持锁内重新读盘再改：两个管理员同时授权不同类型时不能丢更新（V-GRP-10）。
    async with _lock_for(key):
        groups = await asyncio.to_thread(load_permissions, path)
        entry = dict(groups.get(key) or {})
        tags = set(normalize_tags(entry.get('tags')))

        changed = (normalized not in tags) if add else (normalized in tags)
        if add:
            tags.add(normalized)
        else:
            tags.discard(normalized)

        if not changed:
            return False

        # 整条 entry 原样带过去，未知键因此得以保留（V-PST-4）。
        entry['tags'] = sorted(tags)
        entry['updated_at'] = time.time()
        entry['updated_by'] = str(operator)
        groups[key] = entry
        await asyncio.to_thread(save_permissions, path, groups)
        return True
