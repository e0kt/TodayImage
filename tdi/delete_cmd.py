"""回复删图：对一张抽图回复「删除<标签>」，从图库删掉并让持有者重抽。

**权限**：SV 的 pm=3 是硬上界（普通群友进不来）；handler 内按配置可再收紧到 pm<=1。
这是本项目第一次在 handler 内自查权限（003 R1 说过要避免）—— 偏离是有意的：
需求要求阈值可配置，而 SV 的 pm 是注册期常量。判定集中在 shared.can_delete_image 一处。

**安全性质**：解析结果非 ok 时**直接返回**，绝不进入任何文件操作。
这是不可逆且全局的操作，不确定时一律偏向不动作。
"""
from __future__ import annotations

from .shared import (
    Bot,
    Event,
    LOG_PREFIX,
    Path,
    asyncio,
    can_delete_image,
    category_index,
    delete_recent_window,
    chat_group_key,
    image_short_id,
    invalidate_scan_cache,
    load_categories,
    logger,
    normalize_tag,
    plugin_enabled,
    records_path,
    reset_utc_offset,
    sent_index,
    delete_sv,
    send_text,
)
from .daily_store import clear_records_for_image, current_date, load_records
from .image_input import collect_image_refs, read_image_bytes
from .image_match import find_exact, find_similar
from .delete_resolve import AMBIGUOUS, NOT_A_DRAW, NOT_FOUND, OK, TAG_MISMATCH, resolve
from .delete_text import (
    MASTER_ONLY,
    NOT_A_DRAW as TEXT_NOT_A_DRAW,
    NOT_FOUND as TEXT_NOT_FOUND,
    ambiguous_reply,
    missing_file_reply,
    success_reply,
    tag_mismatch_reply,
)


async def _category_of_map() -> dict[str, str]:
    """图片绝对路径 -> 所属类型。用于校验标签是否写对。"""
    categories, _ = await load_categories()
    return {image: c.name for c in categories for image in c.images}


async def _match_replied_image(ev: Event, tag: str, records: dict) -> str | None:
    """把被回复的那张图比对回本地文件。

    适配器会把被回复的图放进 ev.image / ev.image_list（早期调研只采样了
    回复文字消息的事件，误判为拿不到）。拿到图本身就不必依赖发送回执 ——
    本部署的 OneBot 适配器根本不返回消息 ID，而内存表又会被重启清空。

    先在**该类型**内做字节级比对；QQ 若重新编码则退到感知哈希，
    但只对当天该会话的少数候选做，几万张图逐一解码不可接受。
    """
    refs = collect_image_refs(ev)
    if not refs:
        return None

    data = await asyncio.to_thread(read_image_bytes, refs[0], 32 * 1024 * 1024)
    if data is None:
        return None
    blob = data[0]

    categories, _ = await load_categories()
    pool = [c.images for c in categories if normalize_tag(c.name) == tag]
    if not pool:
        return None

    hit = await asyncio.to_thread(find_exact, blob, pool[0])
    if hit:
        logger.debug(f'{LOG_PREFIX} 被回复的图字节级命中 {hit}')
        return hit

    # 退到感知哈希，候选限定在当天该会话该类型的记录内
    from .daily_store import parse_key

    narrow = []
    for key, entry in records.items():
        parsed = parse_key(key)
        if parsed is None:
            continue
        row_chat, _u, row_cat = parsed
        if row_chat == chat_group_key(ev) and normalize_tag(row_cat) == tag:
            image = entry.get('image')
            if isinstance(image, str) and image:
                narrow.append(image)
    if not narrow:
        return None

    hit = await asyncio.to_thread(find_similar, blob, narrow, 8)
    if hit:
        logger.debug(f'{LOG_PREFIX} 被回复的图感知哈希命中 {hit}')
    return hit


@delete_sv.on_command(
    ('删除',),
    block=True,
    to_ai="""删除图库里一张打错标签的图片，并让抽到它的人重新抽。
    必须对机器人发出的那张图回复本命令。
    当管理员说“删除黑丝”并回复了一张图时调用。
    Args:
        text: 类型名称，例如 "黑丝"。
    """,
)
async def delete_by_reply(bot: Bot, ev: Event):
    if not plugin_enabled():
        return
    if not can_delete_image(ev):
        return await send_text(bot, MASTER_ONLY)

    tag = normalize_tag(ev.text)
    today = current_date(reset_utc_offset())
    records = await asyncio.to_thread(load_records, records_path(), today)
    category_of = await _category_of_map()

    matched = await _match_replied_image(ev, tag, records)

    resolution = resolve(
        ev.reply_id, tag, sent_index, records, category_of.get, chat_group_key(ev),
        recent_window=delete_recent_window(),
        matched_image=matched,
    )

    # ── 拒绝分支：一律直接返回，不进入任何文件操作（FR-503、I-501）──
    if resolution.outcome == NOT_A_DRAW:
        return await send_text(bot, TEXT_NOT_A_DRAW)
    if resolution.outcome == NOT_FOUND:
        return await send_text(bot, TEXT_NOT_FOUND)
    if resolution.outcome == AMBIGUOUS:
        return await send_text(
            bot, ambiguous_reply(image_short_id(p) for p in resolution.candidates)
        )
    if resolution.outcome == TAG_MISMATCH:
        return await send_text(
            bot, tag_mismatch_reply(resolution.actual_category or '?', tag)
        )
    if resolution.outcome != OK or not resolution.image:
        return await send_text(bot, TEXT_NOT_FOUND)

    image = resolution.image
    target = Path(image)

    # ── 先删文件，再清记录 ──
    # 顺序由失败模式决定：中间崩溃留下「文件没了但记录还在」，既有逻辑会自愈
    # （记录指向的文件不存在 -> 重抽）；反过来则可能让人又抽回那张错图。
    existed = target.is_file()
    if existed:
        try:
            await asyncio.to_thread(target.unlink)
        except OSError as exc:
            logger.warning(f'{LOG_PREFIX} 删除图片失败 {image}: {exc}')
            return await send_text(bot, f'删除失败：{exc}')

    cleared, chats = await clear_records_for_image(records_path(), today, image)
    invalidate_scan_cache()

    logger.info(
        f'{LOG_PREFIX} 删图 {image}（操作者 {ev.user_id}，会话 {chat_group_key(ev) or "direct"}，'
        f'文件已删={existed}，清理 {cleared} 条记录，影响 {chats} 个会话，'
        f'兜底={resolution.by_recency}）'
    )

    if not existed:
        return await send_text(bot, missing_file_reply(tag, affected=cleared))
    await send_text(
        bot, success_reply(tag, affected=cleared, by_recency=resolution.by_recency)
    )
