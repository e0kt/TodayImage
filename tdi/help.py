"""今日图片帮助命令。"""
from __future__ import annotations

from .shared import (
    Bot,
    Event,
    LOG_PREFIX,
    command_prefix,
    help_sv,
    image_root,
    is_direct_chat,
    is_master,
    load_categories,
    logger,
    plugin_enabled,
    send_text,
)
from .help_text import build_help_text


@help_sv.on_fullmatch(
    ('今日图片帮助', '图片帮助'),
    block=True,
    to_ai="""查看今日图片插件的用法。
    当用户说“今日图片帮助”“图片帮助”时调用。
    Args:
        text: 无需参数，留空。
    """,
)
async def show_help(bot: Bot, ev: Event):
    if not plugin_enabled():
        return

    # 披露级别由权限决定，不是把清单整个删掉 —— 否则主人就没法从聊天里管图库了。
    # 但权限只答了「谁在问」，还要答「谁会看到答案」：群/频道里的回复对全体成员
    # 可见，其中必然包含非主人，而 FR-110 约束的是「对非主人可见的回复」，不是
    # 「发给非主人的回复」。所以完整清单与路径只在私聊披露 (FR-110, V-DIS-2)。
    # 判私聊必须走 is_direct_chat：Discord/KOOK/QQ 频道的 user_type 是 channel,
    # 仅按 group_id 是否为空来判断会把公开频道当成私聊, 反把泄露面扩大到整个频道。
    disclose = is_master(ev) and is_direct_chat(ev)
    categories = ()
    root = None
    if disclose:
        try:
            categories, _ = await load_categories()
        except OSError as exc:
            logger.warning(f'{LOG_PREFIX} 扫描图库失败: {exc}')
        root = image_root()

    await send_text(
        bot,
        build_help_text(
            command_prefix(),
            is_master=disclose,
            categories=categories,
            image_root=root,
        ),
    )


def _register_plugin_help() -> None:
    """把插件登记进核心的全局帮助索引。失败只记日志，不影响命令本身。"""
    try:
        from pathlib import Path

        from gsuid_core.help.utils import register_help

        icon = Path(__file__).parent.parent / 'ICON.png'
        register_help('TodayImage', '今日图片帮助', str(icon) if icon.is_file() else None)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f'{LOG_PREFIX} 注册插件帮助失败: {exc}')


_register_plugin_help()
