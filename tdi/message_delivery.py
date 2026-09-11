"""消息发送的平台适配层。

模块级不硬依赖 gsuid_core：导入被 try/except 包住，缺核心时也能加载，
这样 remove_private_mentions 这段纯逻辑可以脱离核心直接测。
"""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - 取决于运行环境是否有核心
    from gsuid_core.models import Message as _CoreMessage
except Exception:  # noqa: BLE001 - 缺核心时降级，不影响纯逻辑测试
    _CoreMessage = None

LOG_PREFIX = '[今日图片]'


def remove_private_mentions(message: Any, message_cls: Any = None) -> Any:
    """去掉私聊里的 at 段以及紧随其后的换行。

    部分适配器会把私聊里的 at 渲染成一串没有意义的字面文本，
    所以私聊一律不带 at（FR-013）。
    """
    cls = message_cls if message_cls is not None else _CoreMessage
    if cls is None:
        return message

    items = message if isinstance(message, list) else [message]
    result: list[Any] = []
    skip_linebreak = False
    for item in items:
        if isinstance(item, cls) and getattr(item, 'type', None) == 'at':
            skip_linebreak = True
            continue
        if skip_linebreak and isinstance(item, str) and item in ('\n', '\r\n'):
            skip_linebreak = False
            continue
        skip_linebreak = False
        result.append(item)

    if isinstance(message, list):
        return result
    return result[0] if result else ''


def adapt_mentions_for_platform(bot: Any, message: Any) -> Any:
    if getattr(bot.ev, 'user_type', None) == 'direct':
        return remove_private_mentions(message)
    return message


async def safe_send(bot: Any, message: Any, *args: Any, **kwargs: Any) -> Any:
    return await bot.send(adapt_mentions_for_platform(bot, message), *args, **kwargs)


async def send_text(bot: Any, text: str, *args: Any, **kwargs: Any) -> Any:
    return await safe_send(bot, text, *args, **kwargs)
