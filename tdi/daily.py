"""今日<类型> 的抽图命令。

只注册**一个**动态前缀触发器，类型在收到消息时才解析。
这样新建文件夹立刻可用，不需要重载，更不需要重启（研究 R1）。

触发器必须 block=False。核心按 (是否带插件前缀, SV 优先级) 排序已匹配的触发器，
遇到第一个 block=True 就停止派发；若这里设成 True，任何优先级数字比我们大的插件
的「今日X」命令都会被我们提前截断（FR-106、研究 R2）。
"""
from __future__ import annotations

from .shared import (
    Bot,
    Category,
    Event,
    LOG_PREFIX,
    Path,
    allowed_tags_for,
    caption_for,
    category_index,
    command_prefix,
    configured_blocklist,
    daily_image_sv,
    find_category,
    logger,
    plugin_enabled,
    records_path,
    reset_utc_offset,
    send_image_reply,
    unique_per_day,
)
from .daily_store import current_date, resolve_daily_image
from .dispatch import decide, miss_reason


def user_key(ev: Event) -> str:
    """带上 bot_id，避免不同平台上编号相同的两个用户被当成同一个人。"""
    return f'{ev.bot_id}:{ev.user_id}'


def chat_key(ev: Event) -> str:
    if ev.group_id is not None:
        return str(ev.group_id)
    return f'direct:{ev.bot_id}:{ev.user_id}'


async def draw_category_image(ev: Event, category: Category) -> str | None:
    """抽出（或取回）该用户当天在该类型下的图片。

    今天的日期在这里取一次并一路传下去：若在下游各处各取一次，
    跨零点的请求可能用 A 日的种子写进 B 日的记录（V-REC-6）。

    日期按配置的时区偏移算（默认北京时间），而不是服务器本地时间。
    """
    today = current_date(reset_utc_offset())
    return await resolve_daily_image(
        records_path(),
        today,
        chat_key(ev),
        user_key(ev),
        category.name,
        category.images,
        unique_per_chat=unique_per_day(),
    )


@daily_image_sv.on_prefix(
    command_prefix(),
    block=False,
    to_ai="""随机抽取当前用户今天的某类图片。
    当用户说“今日<类型>”（例如“今日黑丝”）时调用。类型由服务器上的图片文件夹决定。
    Args:
        text: 图片类型名称，例如 "黑丝"。
    """,
)
async def daily_image(bot: Bot, ev: Event):
    if not plugin_enabled():
        return

    command = str(ev.raw_text or '').strip()
    suffix = str(ev.text or '').strip()

    extra = configured_blocklist()

    # 分群授权每次现读，不做缓存：加 TTL 会让已撤销的类型还能再用一会儿，
    # 而那正是管理员最不能接受的行为（V-PST-3）。私聊压根不读这张表。
    is_direct = ev.group_id is None
    allowed = frozenset() if is_direct else allowed_tags_for(ev.group_id)

    # 全部走 TTL 缓存，不碰文件系统：动态触发器对每一条「今日*」消息都会触发，
    # 查不到才是常态，不能让随手打的字变成目录遍历放大器（FR-108）。
    categories = await _load_categories()
    by_name = {category.name: category for category in categories}
    index = await category_index()

    def images_of(name: str):
        category = by_name.get(name)
        return category.images if category is not None else None

    name = decide(
        command, suffix, index, images_of, extra,
        is_direct=is_direct, allowed_tags=allowed,
    )
    if name is None:
        # 未知 / 被屏蔽 / 未授权 / 空文件夹 / 畸形输入 一律静默，彼此在外部不可区分
        # —— 多一种沉默的理由，不能多出一种可观察的差别（V-GATE-4）。
        # 聊天层不解释，但日志层必须能查（V-DIS-5）。
        logger.debug(
            f'{LOG_PREFIX} 不回复 {command!r}: '
            f'{miss_reason(command, suffix, index, images_of, extra, is_direct=is_direct, allowed_tags=allowed)}'
        )
        return

    category = by_name[name]
    try:
        image = await draw_category_image(ev, category)
    except OSError as exc:
        logger.warning(f'{LOG_PREFIX} 读写每日记录失败: {exc}')
        return

    if image is None or not Path(image).is_file():
        logger.debug(f'{LOG_PREFIX} 不回复 {command!r}: 抽中的图片不可用')
        return

    logger.debug(f'{LOG_PREFIX} 用户 {ev.user_id} 抽到 {category.name}: {image}')
    try:
        await send_image_reply(bot, ev, caption_for(category), image)
    except OSError as exc:
        logger.warning(f'{LOG_PREFIX} 读取图片失败 {image}: {exc}')


async def _load_categories() -> tuple[Category, ...]:
    from .shared import load_categories

    categories, _ = await load_categories()
    return categories
