"""分群标签授权命令。

权限完全交给 SV 的 pm=3：核心的 _sv_authorized 会在这些处理函数之前
拒绝 user_pm > 3 的人。这里**刻意不再自己判断一遍**——
两处判断正是日后口径漂移的来源（研究 R1）。
"""
from __future__ import annotations

from .shared import (
    Bot,
    Event,
    LOG_PREFIX,
    allowed_tags_for,
    category_index,
    group_permission_sv,
    logger,
    normalize_tag,
    permissions_path,
    plugin_enabled,
    send_text,
)
from .group_permissions import authorise_tag, revoke_tag
from .permissions_text import (
    DIRECT_CHAT_LIST,
    DIRECT_CHAT_SETTING,
    USAGE_ALLOW,
    USAGE_DENY,
    allow_reply,
    deny_reply,
    list_reply,
)


async def _folder_exists(tag: str) -> bool:
    index = await category_index()
    return tag in index


@group_permission_sv.on_command(
    ('TodayImage允许', 'todayimage允许'),
    block=True,
    to_ai="""允许本群使用某个图片类型。
    当群管理员说“TodayImage允许黑丝”“允许本群发黑丝”时调用。
    Args:
        text: 类型名称，例如 "黑丝"。
    """,
)
async def allow_tag(bot: Bot, ev: Event):
    if not plugin_enabled():
        return
    if ev.group_id is None:
        return await send_text(bot, DIRECT_CHAT_SETTING)

    tag = normalize_tag(ev.text)
    if not tag:
        return await send_text(bot, USAGE_ALLOW)

    added = await authorise_tag(permissions_path(), ev.group_id, tag, ev.user_id)
    exists = await _folder_exists(tag)
    logger.info(f'{LOG_PREFIX} 群 {ev.group_id} 允许 {tag}（操作者 {ev.user_id}，新增={added}）')
    await send_text(bot, allow_reply(tag, newly_added=added, folder_exists=exists))


@group_permission_sv.on_command(
    ('TodayImage禁止', 'todayimage禁止'),
    block=True,
    to_ai="""禁止本群使用某个图片类型。
    当群管理员说“TodayImage禁止黑丝”“别在本群发黑丝了”时调用。
    Args:
        text: 类型名称，例如 "黑丝"。
    """,
)
async def deny_tag(bot: Bot, ev: Event):
    if not plugin_enabled():
        return
    if ev.group_id is None:
        return await send_text(bot, DIRECT_CHAT_SETTING)

    tag = normalize_tag(ev.text)
    if not tag:
        return await send_text(bot, USAGE_DENY)

    removed = await revoke_tag(permissions_path(), ev.group_id, tag, ev.user_id)
    logger.info(f'{LOG_PREFIX} 群 {ev.group_id} 禁止 {tag}（操作者 {ev.user_id}，生效={removed}）')
    await send_text(bot, deny_reply(tag, removed=removed))


@group_permission_sv.on_command(
    ('TodayImage列表', 'TodayImage权限', 'todayimage列表'),
    block=True,
    to_ai="""查看本群已允许的图片类型。
    当群管理员说“TodayImage列表”“本群能发哪些”时调用。
    Args:
        text: 无需参数，留空。
    """,
)
async def list_tags(bot: Bot, ev: Event):
    if not plugin_enabled():
        return
    if ev.group_id is None:
        return await send_text(bot, DIRECT_CHAT_LIST)

    tags = allowed_tags_for(ev.group_id)
    index = await category_index()
    missing = [tag for tag in tags if tag not in index]
    await send_text(bot, list_reply(tags, missing))
