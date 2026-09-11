"""今日图片帮助命令。"""
from __future__ import annotations

from .shared import (
    Bot,
    Event,
    LOG_PREFIX,
    command_prefix,
    help_sv,
    image_root,
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
    master = is_master(ev)
    categories = ()
    root = None
    if master:
        try:
            categories, _ = await load_categories()
        except OSError as exc:
            logger.warning(f'{LOG_PREFIX} 扫描图库失败: {exc}')
        root = image_root()

    await send_text(
        bot,
        build_help_text(
            command_prefix(),
            is_master=master,
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
