#!/usr/bin/env python3
"""从机器人推送的图片反查 Immich 里的高清源图。

**为什么不需要以图搜图**：data/TodayImage/ 下的文件名就是 Immich 的 asset id
（UUID v4），而 Immich 的存储路径是可计算的：

    <upload>/<ownerId>/<uuid[0:2]>/<uuid[2:4]>/<uuid>.<ext>

所以拿到文件名就能直接算出原图路径，不必做哈希比对，也不受平台重新编码的影响。

用法：
    python tools/find_original.py 000252bc-fb1b-4f38-ba86-bf2d4c1da6c3
    python tools/find_original.py 000252bc-....jpg
    python tools/find_original.py data/TodayImage/黑丝/000252bc-....jpg
    python tools/find_original.py --category 黑丝 --all      # 整个类型对一遍
    python tools/find_original.py <id> --reveal              # 在访达中显示

环境变量：
    IMMICH_UPLOAD   Immich upload 目录，默认 ~/docker/immich/library/upload
    TODAYIMAGE_DATA 图库目录，默认 <gsuid_core>/data/TodayImage

本脚本只适用于「图库由 Immich 导出」的部署，与插件本身无关，不需要可直接删除。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

UUID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}

DEFAULT_UPLOAD = Path(os.environ.get(
    'IMMICH_UPLOAD', Path.home() / 'docker/immich/library/upload'))


def asset_id_of(text: str) -> str | None:
    """从 UUID、文件名或完整路径里取出 asset id。"""
    m = UUID_RE.search(str(text))
    return m.group(0).lower() if m else None


def original_of(asset_id: str, upload: Path) -> Path | None:
    """算出原图路径。遍历各 owner 目录，因为 ownerId 事先不一定知道。"""
    if not upload.is_dir():
        return None
    for owner in upload.iterdir():
        if not owner.is_dir():
            continue
        folder = owner / asset_id[:2] / asset_id[2:4]
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if path.stem == asset_id and path.suffix.lower() in IMAGE_SUFFIXES:
                return path
    return None


def sidecar_of(original: Path) -> Path | None:
    """wd14 写的 XMP，里面有这张图的标签。"""
    xmp = original.with_name(original.name + '.xmp')
    return xmp if xmp.is_file() else None


def describe(path: Path) -> str:
    size = path.stat().st_size / 1024
    try:
        from PIL import Image
        with Image.open(path) as im:
            return f'{im.size[0]}x{im.size[1]}  {size:,.0f}KB'
    except Exception:
        return f'{size:,.0f}KB'


def report(query: str, upload: Path, reveal: bool = False) -> bool:
    asset_id = asset_id_of(query)
    if asset_id is None:
        print(f'✗ 认不出 asset id：{query}', file=sys.stderr)
        print('  文件名应形如 000252bc-fb1b-4f38-ba86-bf2d4c1da6c3.jpg', file=sys.stderr)
        return False

    original = original_of(asset_id, upload)
    if original is None:
        print(f'✗ {asset_id}  在 Immich 里找不到（可能已删除，或 upload 路径不对）')
        return False

    print(f'✓ {asset_id}')
    print(f'  原图  {original}')
    print(f'        {describe(original)}')

    served = Path(query)
    if served.is_file() and served.resolve() != original.resolve():
        print(f'  推送  {describe(served)}')

    xmp = sidecar_of(original)
    if xmp:
        print(f'  标签  {xmp.name}')

    if reveal and sys.platform == 'darwin':
        subprocess.run(['open', '-R', str(original)], check=False)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description='反查 Immich 高清源图')
    parser.add_argument('query', nargs='*', help='asset id / 文件名 / 路径')
    parser.add_argument('--category', help='对某个类型目录整体反查')
    parser.add_argument('--all', action='store_true', help='与 --category 连用，列出全部')
    parser.add_argument('--upload', type=Path, default=DEFAULT_UPLOAD, help='Immich upload 目录')
    parser.add_argument('--reveal', action='store_true', help='在访达中显示（macOS）')
    args = parser.parse_args()

    if not args.upload.is_dir():
        print(f'✗ Immich upload 目录不存在：{args.upload}', file=sys.stderr)
        print('  用 --upload 或环境变量 IMMICH_UPLOAD 指定', file=sys.stderr)
        return 2

    queries = list(args.query)
    if args.category:
        data = Path(os.environ.get(
            'TODAYIMAGE_DATA',
            Path.home() / 'programming/gsuid_core/data/TodayImage'))
        folder = data / args.category
        if not folder.is_dir():
            print(f'✗ 类型目录不存在：{folder}', file=sys.stderr)
            return 2
        found = sorted(p for p in folder.rglob('*')
                       if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
                       and not p.name.startswith('.'))
        queries += [str(p) for p in (found if args.all else found[:10])]
        if not args.all and len(found) > 10:
            print(f'（{folder.name} 共 {len(found)} 张，只查前 10 张；加 --all 查全部）\n')

    if not queries:
        parser.print_help()
        return 2

    ok = sum(report(q, args.upload, args.reveal) for q in queries)
    if len(queries) > 1:
        print(f'\n{ok}/{len(queries)} 找到原图')
    return 0 if ok == len(queries) else 1


if __name__ == '__main__':
    raise SystemExit(main())
