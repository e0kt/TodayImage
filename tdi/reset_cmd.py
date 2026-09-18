"""分群类型重置命令。

权限完全交给 SV 的 pm=1：核心的 _sv_authorized 会在处理函数之前拒绝 user_pm > 1 的人，
即只放行 master(0) 与 superuser(1)。这里**刻意不再自己判断一遍** ——
两处判断正是日后口径漂移的来源（沿用 003 研究 R1）。

与 TodayImage允许（pm=3，群管理员可用）的权限差异是有意的：
授权决定「本群能看什么」，重置会改变**全群所有人当天已经拿到的结果**，外溢更大。
"""
from __future__ import annotations

from .shared import (
    Bot,
    Event,
    LOG_PREFIX,
    category_index,
    chat_group_key,
    is_direct_chat,
    logger,
    normalize_tag,
    plugin_enabled,
    records_path,
    reset_group_category,
    reset_utc_offset,
    reset_sv,
    send_text,
)
from .daily_store import current_date
from .reset_text import DIRECT_CHAT, USAGE, reset_reply


@reset_sv.on_command(
    ('TodayImage重置', 'todayimage重置'),
    block=True,
    to_ai="""重置本群某个图片类型的每日绑定，让群里的人可以重新抽一张新的图。
    当机器人主人说“TodayImage重置黑丝”“让大家重新抽黑丝”时调用。
    Args:
        text: 类型名称，例如 "黑丝"。
    """,
)
async def reset_category(bot: Bot, ev: Event):
    if not plugin_enabled():
        return
    if is_direct_chat(ev):
        return await send_text(bot, DIRECT_CHAT)

    category = normalize_tag(ev.text)
    if not category:
        return await send_text(bot, USAGE)

    chat_key = chat_group_key(ev)
    today = current_date(reset_utc_offset())
    cleared, epoch = await reset_group_category(records_path(), today, chat_key, category)

    index = await category_index()
    exists = category in index

    # 这是本插件唯一一个会改变全群当日结果的人工操作，值得留痕。
    logger.info(
        f'{LOG_PREFIX} 群/频道 {chat_key} 重置 {category}：'
        f'清除 {cleared} 条，代数 {epoch}（操作者 {ev.user_id}）'
    )
    await send_text(bot, reset_reply(category, cleared=cleared, folder_exists=exists))
