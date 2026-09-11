"""图库管理命令：重载 / 上传 / 查看 / 删除。"""
from __future__ import annotations

import re
from typing import Any

from .shared import (
    Bot,
    Event,
    LOG_PREFIX,
    MessageSegment,
    Path,
    asyncio,
    can_upload,
    find_category,
    find_category_directory,
    forward_threshold,
    gallery_manage_sv,
    image_root,
    image_short_id,
    image_upload_sv,
    invalidate_scan_cache,
    load_categories,
    logger,
    plugin_enabled,
    resolve_short_id,
    safe_send,
    send_text,
    time,
    upload_max_bytes,
)
from .image_input import collect_image_refs, read_image_bytes

_SHORT_ID_RE = re.compile(r'^[0-9a-f]{8}$', re.IGNORECASE)


def _clean(text: Any) -> str:
    return str(text or '').strip().strip('"“”‘’')


# ── 重载 ──────────────────────────────────────────────────────────────────────

@gallery_manage_sv.on_fullmatch(
    ('重载图片类型', '刷新图片类型'),
    block=True,
    to_ai="""重新扫描图片目录并刷新今日<类型>命令。
    当用户说“重载图片类型”“刷新图片类型”“新加的文件夹不生效”时调用。
    Args:
        text: 无需参数，留空。
    """,
)
async def reload_categories(bot: Bot, ev: Event):
    if not plugin_enabled():
        return

    # 类型现在是收到消息时才解析的，新建文件夹在缓存 TTL 内自动生效，
    # 这条命令因此只是「立刻失效缓存」，不再是正确性的前提（contracts §5）。
    invalidate_scan_cache()
    try:
        categories, skips = await load_categories(force=True)
    except OSError as exc:
        logger.warning(f'{LOG_PREFIX} 重新扫描图库失败: {exc}')
        return await send_text(bot, f'重新扫描失败：{exc}')

    usable = [c for c in categories if c.enabled]
    lines = [f'已刷新，当前共 {len(usable)} 个可用图片类型。']
    if skips:
        # 本命令是主人专用（pm=1），因此可以列出细节（FR-112）。
        lines.append('以下项被跳过：')
        lines.extend(f'· {note}' for note in skips)
    lines.append('提示：新建文件夹本来就会在缓存过期后自动生效，此命令只是立即刷新。')
    lines.append('修改命令前缀需要重启核心。')
    await send_text(bot, '\n'.join(lines))


# ── 上传 ──────────────────────────────────────────────────────────────────────

def _unique_image_path(category_dir: Path, suffix: str, index: int) -> Path:
    stamp = int(time.time() * 1000)
    counter = 0
    while True:
        tail = f'_{counter}' if counter else ''
        path = category_dir / f'img_{stamp}_{index}{tail}{suffix}'
        if not path.exists():
            return path
        counter += 1


def _save_image(category_dir: Path, source: str, index: int) -> Path | None:
    result = read_image_bytes(source, upload_max_bytes())
    if result is None:
        return None
    data, suffix = result
    path = _unique_image_path(category_dir, suffix, index)
    path.write_bytes(data)
    return path


@image_upload_sv.on_command(('上传图片', '图片上传'), block=True)
async def upload_image(bot: Bot, ev: Event):
    if not plugin_enabled():
        return
    if not can_upload(ev):
        return await send_text(bot, '你不在图片上传白名单中。')

    name = _clean(ev.text)
    if not name:
        return await send_text(bot, '请输入类型名称，例如：上传图片 黑丝，并附带图片。')

    category_dir = find_category_directory(image_root(), name)
    if category_dir is None:
        return await send_text(
            bot,
            f'不存在图片类型【{name}】，请先创建对应文件夹或使用「重载图片类型」。',
        )

    refs = collect_image_refs(ev)
    if not refs:
        return await send_text(bot, f'请同时发送图片和命令，例如：上传图片 {category_dir.name}')

    saved: list[Path] = []
    failed = 0
    for index, ref in enumerate(refs, 1):
        path = await asyncio.to_thread(_save_image, category_dir, ref, index)
        if path is None:
            failed += 1
        else:
            saved.append(path)

    if not saved:
        return await send_text(
            bot, f'【{category_dir.name}】上传图片失败，请确认消息里附带的是图片。'
        )

    invalidate_scan_cache()
    ids = [image_short_id(path) for path in saved]
    lines = [
        f'【{category_dir.name}】上传成功',
        f'成功：{len(saved)} 张',
        f'图片ID：{", ".join(ids)}',
    ]
    if failed:
        lines.append(f'失败：{failed} 张')
    await send_text(bot, '\n'.join(lines))


# ── 查看 ──────────────────────────────────────────────────────────────────────

@gallery_manage_sv.on_command(
    ('查看图片', '图片列表'),
    block=True,
    to_ai="""查看图片类型或某个类型下的图片。
    当用户说“查看图片”“图片列表”“黑丝有哪些图”时调用。
    Args:
        text: 类型名称，例如 "黑丝"；留空则列出全部类型。
    """,
)
async def list_images(bot: Bot, ev: Event):
    """单个 on_command 同时服务「查看图片」和「查看图片 黑丝」。

    on_command 判定本身就是 startswith，裸命令时 ev.text 为空即可区分；
    再叠一个 on_fullmatch 会让裸消息在同一个 SV 里命中两个触发器，
    最终谁执行取决于 block 顺序和字典插入顺序 —— 刻意不这么做。
    """
    if not plugin_enabled():
        return

    name = _clean(ev.text)
    if not name:
        try:
            categories, _ = await load_categories()
        except OSError as exc:
            logger.warning(f'{LOG_PREFIX} 扫描图库失败: {exc}')
            return await send_text(bot, f'扫描图片目录失败：{exc}')
        if not categories:
            return await send_text(
                bot,
                f'还没有任何图片类型。\n在 {image_root()} 下新建文件夹（例如「黑丝」），'
                f'放入图片后发送「重载图片类型」即可。',
            )
        lines = ['当前图片类型：']
        for category in categories:
            flag = '' if category.enabled else '（已停用）'
            alias = f'，别名：{"、".join(category.aliases)}' if category.aliases else ''
            commands = '、'.join(category.commands) if category.commands else '（无命令）'
            lines.append(f'· {category.name}{flag} — {len(category.images)} 张 → {commands}{alias}')
        lines.append('')
        lines.append(f'新增类型：在 {image_root()} 下建文件夹，放图后发送「重载图片类型」。')
        return await send_text(bot, '\n'.join(lines))

    category = await find_category(name)
    if category is None:
        return await send_text(bot, f'不存在图片类型【{name}】。')
    if not category.images:
        return await send_text(bot, f'【{category.name}】暂无图片。')

    nodes: list[Any] = []
    for path in category.images:
        nodes.append(f'图片ID：{image_short_id(path)}')
        nodes.append(MessageSegment.image(Path(path)))

    if len(category.images) > forward_threshold():
        return await safe_send(bot, MessageSegment.node(nodes))
    await safe_send(bot, nodes)


# ── 删除 ──────────────────────────────────────────────────────────────────────

@gallery_manage_sv.on_command('删除图片', block=True)
async def delete_image(bot: Bot, ev: Event):
    if not plugin_enabled():
        return

    parts = _clean(ev.text).split()
    if not parts:
        return await send_text(
            bot, '请输入类型名称，例如：删除图片 黑丝 abcd1234\n不加ID则删除该类型全部图片'
        )

    name, short_id = parts[0], (parts[1] if len(parts) > 1 else '')
    category = await find_category(name)
    if category is None:
        return await send_text(bot, f'不存在图片类型【{name}】。')

    if not short_id:
        count = 0
        for path in category.images:
            try:
                await asyncio.to_thread(Path(path).unlink)
                count += 1
            except OSError as exc:
                logger.warning(f'{LOG_PREFIX} 删除失败 {path}: {exc}')
        invalidate_scan_cache()
        return await send_text(bot, f'已删除【{category.name}】全部图片，共 {count} 张。')

    if not _SHORT_ID_RE.match(short_id):
        return await send_text(
            bot,
            f'请提供 8 位图片ID，例如：删除图片 {category.name} abcd1234\n不加ID则删除该类型全部图片',
        )

    matches = resolve_short_id(category.images, short_id)
    if not matches:
        return await send_text(bot, f'未找到图片ID：{short_id}')
    if len(matches) > 1:
        # 短 ID 取自文件名，不同子目录下的同名文件会撞 ID。
        # 这时随便删一个是危险的，交回给人处理（V-IMG-5）。
        return await send_text(
            bot, f'图片ID {short_id} 匹配到 {len(matches)} 个文件，请直接在文件系统中删除。'
        )

    try:
        await asyncio.to_thread(Path(matches[0]).unlink)
    except OSError as exc:
        logger.warning(f'{LOG_PREFIX} 删除图片失败 {matches[0]}: {exc}')
        return await send_text(bot, f'删除失败：{short_id}')

    invalidate_scan_cache()
    await send_text(bot, f'已删除图片：{short_id}')
