"""TodayImage 的公共层：SV 实例、配置取值、路径解析与图库缓存。

本模块直接依赖 gsuid_core，只有在核心里加载时才可导入；
纯逻辑一律放在 gallery / category_registry / daily_store / image_input / file_cache 里。
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from gsuid_core.bot import Bot
from gsuid_core.config import core_config
from gsuid_core.data_store import get_res_path
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SL, Plugins, SV

from ..today_image_config import TodayImageConfig
from .category_registry import Category, normalize_prefix, read_overrides, resolve_categories
from .file_cache import read_file_bytes_cached
from .blocklist import is_blocked
from .chat_context import chat_group_key, is_direct_chat
from .group_permissions import is_tag_allowed, normalize_group_key, normalize_tag, tags_for_group
from .gallery import (
    IMAGE_EXTENSIONS,
    RESERVED_DIRECTORY_NAMES,
    build_category_index,
    find_category_directory,
    image_short_id,
    lookup_category,
    resolve_short_id,
    scan_category_directories,
)
from .message_delivery import adapt_mentions_for_platform, safe_send, send_text
from .upload_access import can_upload_images

LOG_PREFIX = '[今日图片]'

Plugins(
    name='TodayImage',
    disable_force_prefix=True,
    allow_empty_prefix=True,
)

# SV 拆分是为了让运营方能在控制台单独关掉某一类能力。
# priority 数字越小越先执行；本插件全部从 20 起步，这样一旦命令撞车，
# 先注册的插件（TodayWaifu 占 0–10）必然胜出，我们的处理函数根本不会被调用。
help_sv = SV('今日图片-帮助', priority=20)
gallery_manage_sv = SV('今日图片-图库管理', pm=1, priority=21)
image_upload_sv = SV('今日图片-图片上传', priority=21)
daily_image_sv = SV('今日图片-每日抽取', priority=25)
# pm=3 就是「admin 用户」这道闸门本身：核心的 _sv_authorized 会在我们的处理函数之前
# 拒绝 user_pm > 3 的人。权限阶梯见 gsuid_core/sv.py:278 —
#   0=master, 1=superuser, 2=群主, 3=群管理员, 6=普通用户
# 不自己维护管理员名单，也不在 handler 里重复判断（研究 R1）。
group_permission_sv = SV('今日图片-群授权', pm=3, priority=21)


# ── 配置取值 ──────────────────────────────────────────────────────────────────
# 一律强制转换 + 兜底：手改坏了 config.json 也只退回默认值，不把异常抛进命令处理函数。

def _cfg(key: str) -> Any:
    try:
        return TodayImageConfig.get_config(key).data
    except Exception as exc:  # noqa: BLE001
        logger.warning(f'{LOG_PREFIX} 读取配置 {key} 失败，使用默认值: {exc}')
        return None


def cfg_bool(key: str, default: bool = False) -> bool:
    value = _cfg(key)
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


def cfg_int(key: str, default: int, minimum: int = 0) -> int:
    try:
        value = int(_cfg(key))
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


def cfg_str(key: str, default: str = '') -> str:
    value = _cfg(key)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def cfg_list(key: str) -> frozenset[str]:
    value = _cfg(key)
    if isinstance(value, str):
        items: Any = value.replace(',', ' ').split()
    elif isinstance(value, (list, tuple, set, frozenset)):
        items = value
    else:
        return frozenset()
    return frozenset(text for item in items if (text := str(item).strip()))


def plugin_enabled() -> bool:
    return cfg_bool('TodayImageEnabled', True)


def command_prefix() -> str:
    return normalize_prefix(cfg_str('TodayImageCommandPrefix', '今日'))


def at_user_enabled() -> bool:
    return cfg_bool('TodayImageAtUser', True)


def forward_threshold() -> int:
    return cfg_int('TodayImageListForwardThreshold', 10, minimum=1)


def upload_max_bytes() -> int:
    return cfg_int('TodayImageUploadMaxMB', 10, minimum=1) * 1024 * 1024


def scan_cache_ttl() -> float:
    return float(cfg_int('TodayImageScanCacheTTL', 300, minimum=0))


def direct_unlimited() -> bool:
    """私聊是否不限次数（每次重抽）。群聊不受影响。"""
    return cfg_bool('TodayImageDirectUnlimited', True)


def unique_per_day() -> bool:
    return cfg_bool('TodayImageUniquePerDay', True)


def reset_utc_offset() -> int:
    """每日重置所用的时区偏移，默认 +8（北京时间）。"""
    value = _cfg('TodayImageResetUtcOffset')
    try:
        offset = int(value)
    except (TypeError, ValueError):
        return 8
    return offset if -12 <= offset <= 14 else 8


def caption_for(category: Category) -> str:
    template = category.caption or cfg_str('TodayImageTextTemplate', '你今天的{类型}来啦！')
    try:
        return template.replace('{类型}', category.name)
    except Exception:  # noqa: BLE001
        return f'你今天的{category.name}来啦！'


# ── 路径 ──────────────────────────────────────────────────────────────────────

def data_root() -> Path:
    return get_res_path('TodayImage')


def image_root() -> Path:
    """图片根目录，默认就是 data/TodayImage 本身。

    插件在这一层只写 config.json / categories.json / daily_records.json 三个**文件**，
    而类型是按「一级子目录」识别的，所以配置文件不会被误认成图片类型；
    以防万一，仍用 RESERVED_DIRECTORY_NAMES 把插件自用目录名排除在外。
    """
    configured = cfg_str('TodayImageRoot', '')
    if configured:
        path = Path(configured).expanduser()
    else:
        path = data_root()
    path.mkdir(parents=True, exist_ok=True)
    return path


def overrides_path() -> Path:
    return data_root() / 'categories.json'


def records_path() -> Path:
    return data_root() / 'daily_records.json'


def permissions_path() -> Path:
    return data_root() / 'group_permissions.json'


def default_group_tags() -> Any:
    """新群的默认类型；只对还没有任何授权记录的群生效（CF-301）。"""
    return _cfg('TodayImageDefaultGroupTags')


def allowed_tags_for(group_id: Any) -> frozenset[str]:
    return tags_for_group(permissions_path(), group_id, default_group_tags())


# ── 图库缓存 ──────────────────────────────────────────────────────────────────
# 全量 rglob 在图多时是昂贵操作：不缓存的话，整点高峰每条命令都要重扫一遍目录，
# 会把核心拖垮（研究 R7）。TTL 之外，上传/删除/重载都会立即失效缓存。

_scan_cache: tuple[float, tuple[Category, ...], tuple[str, ...]] | None = None


def invalidate_scan_cache() -> None:
    global _scan_cache
    _scan_cache = None


def _scan_now() -> tuple[tuple[Category, ...], tuple[str, ...]]:
    root = image_root()
    rows = scan_category_directories(root, IMAGE_EXTENSIONS, RESERVED_DIRECTORY_NAMES)
    overrides = read_overrides(overrides_path())
    return resolve_categories(rows, overrides, command_prefix())


def scan_categories_sync(force: bool = False) -> tuple[tuple[Category, ...], tuple[str, ...]]:
    """同步扫描，供 import 期的首次命令注册使用（那时还没有事件循环）。"""
    global _scan_cache
    ttl = scan_cache_ttl()
    now = time.monotonic()
    if not force and ttl > 0 and _scan_cache is not None and now - _scan_cache[0] < ttl:
        return _scan_cache[1], _scan_cache[2]
    categories, skips = _scan_now()
    _scan_cache = (now, categories, skips)
    return categories, skips


async def load_categories(force: bool = False) -> tuple[tuple[Category, ...], tuple[str, ...]]:
    """取当前类型列表，带 TTL 缓存。扫描放线程池，避免阻塞事件循环。"""
    global _scan_cache
    ttl = scan_cache_ttl()
    now = time.monotonic()
    if not force and ttl > 0 and _scan_cache is not None and now - _scan_cache[0] < ttl:
        return _scan_cache[1], _scan_cache[2]

    categories, skips = await asyncio.to_thread(_scan_now)
    _scan_cache = (now, categories, skips)
    logger.debug(f'{LOG_PREFIX} 扫描图库完成，共 {len(categories)} 个类型，跳过 {len(skips)} 项')
    return categories, skips


def configured_blocklist() -> Any:
    """每次请求现读，所以控制台改完不用重启（FR-116）。"""
    return _cfg('TodayImageBlocklist')


async def category_index() -> dict[str, str]:
    """「归一化类型名 -> 原始类型名」映射，由 TTL 缓存的扫描结果构建。

    动态触发器会对**每一条**以命令前缀开头的消息触发，所以查不到才是常态。
    映射必须走缓存，否则「今日」+随便打的字就成了目录遍历放大器（FR-108）。
    """
    categories, _ = await load_categories()
    return build_category_index(
        tuple((c.name, c.images) for c in categories if c.enabled)
    )


async def find_category(name: str) -> Category | None:
    categories, _ = await load_categories()
    target = name.strip().casefold()
    for category in categories:
        if category.name.casefold() == target:
            return category
    return None


# ── 权限 ──────────────────────────────────────────────────────────────────────

def is_master(ev: Event) -> bool:
    try:
        masters = core_config.get_config('masters')
    except Exception:  # noqa: BLE001
        masters = []
    return str(ev.user_id) in {str(master) for master in masters}


def can_upload(ev: Event) -> bool:
    """主人天然有权限，无需再往白名单里加自己（FR-017）。"""
    return is_master(ev) or can_upload_images(
        ev.user_id, (), _cfg('TodayImageUploadWhitelist')
    )


# ── 发送 ──────────────────────────────────────────────────────────────────────

async def send_image_reply(bot: Bot, ev: Event, text: str, image_path: str) -> None:
    """带可选 at 的图片回复。

    图片字节走 mtime 缓存后再交给 MessageSegment.image；
    直接传 Path 会让核心每次自己读盘，这层缓存就白做了（研究 R8）。
    """
    messages: list[Any] = []
    if not is_direct_chat(ev) and at_user_enabled():
        messages.append(MessageSegment.at(ev.user_id))
        messages.append('\n')
    if text:
        messages.append(text)
    image_bytes = await asyncio.to_thread(read_file_bytes_cached, Path(image_path))
    messages.append(MessageSegment.image(image_bytes))
    await safe_send(bot, messages)


__all__ = [
    'Bot', 'Category', 'Event', 'LOG_PREFIX', 'MessageSegment', 'Path', 'SL', 'SV',
    'adapt_mentions_for_platform', 'asyncio', 'at_user_enabled', 'can_upload', 'caption_for',
    'cfg_bool', 'cfg_int', 'cfg_list', 'cfg_str', 'command_prefix', 'daily_image_sv', 'data_root',
    'find_category', 'find_category_directory', 'forward_threshold', 'gallery_manage_sv',
    'help_sv', 'image_root', 'image_short_id', 'image_upload_sv', 'invalidate_scan_cache',
    'is_master', 'load_categories', 'logger', 'overrides_path', 'plugin_enabled',
    'allowed_tags_for', 'build_category_index', 'category_index', 'chat_group_key',
    'configured_blocklist',
    'default_group_tags', 'direct_unlimited', 'group_permission_sv', 'is_blocked',
    'is_direct_chat',
    'is_tag_allowed',
    'normalize_group_key', 'normalize_tag', 'permissions_path', 'tags_for_group',
    'lookup_category',
    'read_file_bytes_cached', 'records_path', 'reset_utc_offset', 'resolve_short_id',
    'safe_send', 'unique_per_day',
    'scan_categories_sync',
    'scan_category_directories', 'send_image_reply', 'send_text', 'time', 'upload_max_bytes',
]
