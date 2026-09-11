"""把「目录扫描结果 + 用户覆盖设置」解析成可注册的图片类型。

PURE 模块：只依赖标准库，不导入 gsuid_core。

类型的启用/别名/文案不放进控制台的 config.json，因为类型是运行时从目录发现的、
数量无上界，而控制台把 CONFIG_DEFAULT 当成一张固定表单来渲染。
所以单独用一个按类型名索引的 categories.json（研究 R10）。
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_COMMAND_PREFIX = '今日'
OVERRIDES_VERSION = 1


@dataclass(frozen=True)
class Category:
    name: str
    images: tuple[str, ...] = ()
    enabled: bool = True
    aliases: tuple[str, ...] = ()
    caption: str | None = None
    commands: tuple[str, ...] = field(default=())


def normalize_prefix(prefix: Any) -> str:
    """空前缀会让裸类型名变成命令，和日常聊天冲突，所以退回默认（V-CFG-3）。"""
    text = str(prefix or '').strip()
    return text or DEFAULT_COMMAND_PREFIX


def _identity(name: str) -> str:
    return name.strip().casefold()


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().casefold()
        if text in {'true', '1', 'yes', 'y', 'on', 'enable', 'enabled', '开启'}:
            return True
        if text in {'false', '0', 'no', 'n', 'off', 'disable', 'disabled', '关闭'}:
            return False
    return default


def _as_aliases(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        items: list[Any] = value.replace(',', ' ').split()
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        return ()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def resolve_categories(
    scan_rows: tuple[tuple[str, tuple[str, ...]], ...],
    overrides: dict[str, dict[str, Any]],
    prefix: Any,
) -> tuple[tuple[Category, ...], tuple[str, ...]]:
    """解析出可用类型，并返回被跳过项的说明。

    跳过说明必须一路带到「重载图片类型」的回复里 —— 静默丢掉一个类型，
    正是这条命令要防的故障：用户只会看到「我建的文件夹没反应」而毫无线索（V-CAT-5）。
    """
    command_prefix = normalize_prefix(prefix)
    categories: list[Category] = []
    skips: list[str] = []

    seen_identity: dict[str, str] = {}
    claimed_commands: dict[str, str] = {}

    # 第一遍：只收集类型本体，并先把「类型自己的名字」占为命令。
    # 别名的认领必须放到第二遍，否则某个类型的别名会仅凭扫描顺序抢走
    # 另一个类型自己的命令 —— 别名任何时候都不该压过真实类型名。
    pending: list[tuple[str, tuple[str, ...], bool, tuple[str, ...], str | None]] = []

    for raw_name, images in scan_rows:
        name = str(raw_name).strip()
        if not name or name.startswith('.'):
            continue  # V-CAT-1

        identity = _identity(name)
        if identity in seen_identity:
            skips.append(
                f'类型【{name}】与已有类型【{seen_identity[identity]}】重名（忽略大小写和空格），已跳过'
            )
            continue
        seen_identity[identity] = name

        entry = overrides.get(name) or {}
        if not isinstance(entry, dict):
            entry = {}

        enabled = _as_bool(entry.get('enabled'), True)
        aliases = _as_aliases(entry.get('aliases'))
        caption_raw = entry.get('caption')
        caption = str(caption_raw) if isinstance(caption_raw, str) and caption_raw.strip() else None

        if enabled:
            claimed_commands.setdefault(f'{command_prefix}{name}'.casefold(), name)
        pending.append((name, tuple(images), enabled, aliases, caption))

    # 第二遍：按类型本名 + 别名的顺序落实命令。
    for name, images, enabled, aliases, caption in pending:
        commands: tuple[str, ...] = ()
        if enabled:
            identity = _identity(name)
            resolved: list[str] = [f'{command_prefix}{name}']
            for alias in aliases:
                if _identity(alias) == identity:
                    continue
                command = f'{command_prefix}{alias}'
                key = command.casefold()
                owner = claimed_commands.get(key)
                if owner is not None:
                    skips.append(
                        f'类型【{name}】的别名命令「{command}」与【{owner}】冲突，已跳过该别名'
                    )
                    continue
                claimed_commands[key] = name
                resolved.append(command)
            commands = tuple(resolved)

        categories.append(
            Category(
                name=name,
                images=images,
                enabled=enabled,
                aliases=aliases,
                caption=caption,
                commands=commands,
            )
        )

    return tuple(categories), tuple(skips)


def read_overrides(path: Path) -> dict[str, dict[str, Any]]:
    """读取 categories.json；读不出来就当空表，插件必须照常启动（V-OVR-2）。"""
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    categories = payload.get('categories')
    if not isinstance(categories, dict):
        return {}
    return {
        str(name): dict(entry)
        for name, entry in categories.items()
        if isinstance(entry, dict)
    }


def write_overrides(path: Path, overrides: dict[str, dict[str, Any]]) -> None:
    """原子写入。整份 overrides 原样写回，未知键因此得以保留（V-OVR-3），
    不再存在的文件夹的条目也不清理（V-OVR-1）—— 临时挪走目录不该丢设置。
    """
    payload = {'version': OVERRIDES_VERSION, 'categories': overrides}
    _atomic_write_json(path, payload)


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
