"""图库目录扫描。

PURE 模块：只依赖标准库，不导入 gsuid_core。

「根目录下的一级文件夹 = 一个图片类型」。扫描规则要在不同文件系统上给出一致结果，
因为每日抽图用的是「按种子选列表下标」，列表顺序一变，所有人的当天结果就都变了。
所以这里排序统一 casefold，且按 resolve 后的路径去重。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}

# 图片根目录默认就是 data/TodayImage 本身，和插件自己的数据文件同层。
# 配置是文件、不是目录，本来就扫不到；但万一以后插件要在这层建目录，
# 名字必须先登记在这里，否则会凭空多出一个图片类型。
RESERVED_DIRECTORY_NAMES = frozenset({'cache', 'tmp', 'logs', 'backup'})


def _is_visible(path: Path) -> bool:
    return not path.name.startswith('.')


def scan_category_directories(
    root: Path,
    image_extensions: set[str],
    reserved: frozenset[str] | set[str] | None = None,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """扫描「类型名/图片」目录，返回稳定排序后的 (类型名, 图片路径) 列表。

    空文件夹也会被返回：类型的命令要保留，抽图时再回复「暂无图片」，
    否则临时清空一个目录会让命令悄悄消失（V-CAT-3）。
    """
    root.mkdir(parents=True, exist_ok=True)
    extensions = {suffix.casefold() for suffix in image_extensions}
    excluded = {name.casefold() for name in (reserved or ())}
    result: list[tuple[str, tuple[str, ...]]] = []

    category_dirs = sorted(
        (path for path in root.iterdir() if path.is_dir() and _is_visible(path)),
        key=lambda path: path.name.casefold(),
    )
    for category_dir in category_dirs:
        name = category_dir.name.strip()
        if not name or name.casefold() in excluded:
            continue

        seen: set[str] = set()
        images: list[str] = []
        for path in sorted(category_dir.rglob('*'), key=lambda item: str(item).casefold()):
            if not path.is_file() or not _is_visible(path):
                continue
            if path.suffix.casefold() not in extensions:
                continue
            resolved = str(path.resolve())
            key = resolved.casefold()
            if key not in seen:
                seen.add(key)
                images.append(resolved)

        result.append((name, tuple(images)))
    return tuple(result)


def find_category_directory(root: Path, name: str) -> Path | None:
    """在根目录下按名字安全地定位一个已存在的一级类型目录。

    只遍历一级子目录、不做路径拼接，所以 '../黑丝' 这类输入无法穿越出根目录。
    """
    target = name.strip().casefold()
    if not target or not root.is_dir():
        return None
    for path in root.iterdir():
        if path.is_dir() and _is_visible(path) and path.name.strip().casefold() == target:
            return path
    return None


def image_short_id(path: Path | str) -> str:
    """图片的 8 位短 ID。

    只取文件名而不取完整路径：这样用户看到的 ID 和图片在哪个子目录无关。
    代价是不同子目录下的同名文件会共享 ID，调用方必须用 resolve_short_id
    检查是否命中多个再决定怎么处理（V-IMG-5）。
    """
    return hashlib.sha256(Path(path).name.encode('utf-8')).hexdigest()[:8]


def resolve_short_id(paths: tuple[str, ...], short_id: str) -> tuple[str, ...]:
    """返回短 ID 命中的全部路径，好让调用方能识别歧义而不是随便挑一个。"""
    target = short_id.strip().casefold()
    if not target:
        return ()
    return tuple(path for path in paths if image_short_id(path) == target)


# ── 命令后缀 -> 类型目录 ───────────────────────────────────────────────────────

def build_category_index(
    scan_rows: tuple[tuple[str, tuple[str, ...]], ...],
) -> dict[str, str]:
    """建立「归一化后的类型名 -> 原始类型名」映射。

    键统一 strip + casefold，于是「大小写与空格不敏感」是键本身的性质，
    不需要每次查询再遍历比较。

    这层映射也是路径安全的实现方式：后缀只当字典键用，从不与路径拼接，
    所以 '../x'、'/etc/passwd' 这类输入天然查不到，不必额外过滤（V-IDX-2）。
    """
    index: dict[str, str] = {}
    for raw_name, _images in scan_rows:
        name = str(raw_name).strip()
        if not name:
            continue
        key = name.casefold()
        # 大小写/空格撞名时保留稳定排序的先来者，后来者不可达（V-IDX-5）。
        index.setdefault(key, name)
    return index


def lookup_category(index: dict[str, str], suffix: str) -> str | None:
    key = str(suffix or '').strip().casefold()
    if not key:
        return None
    return index.get(key)
