"""帮助文案的纯渲染逻辑。

PURE 模块：只依赖标准库，不导入 gsuid_core。

两级披露（V-DIS-3 / V-DIS-4）：
- 公开：只讲怎么用，不讲有什么。不出现文件夹名、数量、管理命令和任何路径。
- 主人：在公开文案之外附上完整清单与图片根目录。

公开文案与本机有多少个文件夹无关 —— 否则帮助本身就泄露了「这台机器有没有图库」。
"""
from __future__ import annotations

from typing import Any, Iterable

MANAGEMENT_COMMANDS = (
    '上传图片 <类型>（附带图片）',
    '查看图片 [<类型>]',
    '删除图片 <类型> [图片ID]',
    '重载图片类型',
)


def build_help_text(
    prefix: str,
    *,
    is_master: bool = False,
    categories: Iterable[Any] | None = None,
    image_root: Any = None,
) -> str:
    lines = [
        '【今日图片】',
        '',
        f'发送「{prefix}<类型>」即可抽取当天该类型的图片。',
        '每人每天每个类型固定一张，次日（北京时间 0 点）重抽；',
        '同一个群里，不同的人不会抽到同一张。',
    ]

    if not is_master:
        # 公开分支到此为止：可用类型有哪些，属于「有什么」，不对外说（FR-110）。
        return '\n'.join(lines)

    lines.append('')
    lines.append('—— 以下仅主人可见 ——')

    rows = list(categories or [])
    usable = [c for c in rows if getattr(c, 'enabled', True)]
    disabled = [c for c in rows if not getattr(c, 'enabled', True)]

    if usable:
        lines.append('')
        lines.append('当前类型：')
        for category in usable:
            alias = f'，别名：{"、".join(category.aliases)}' if getattr(category, 'aliases', ()) else ''
            lines.append(f'· {prefix}{category.name} — {len(category.images)} 张{alias}')
    else:
        lines.append('')
        lines.append('当前没有可用类型。')

    if disabled:
        lines.append(f'已停用：{"、".join(c.name for c in disabled)}')

    if image_root is not None:
        lines.append('')
        lines.append('新增类型：在下面的目录里建文件夹，名字即类型名，放入图片即可，')
        lines.append('无需重启，也不必重载（缓存过期后自动生效）：')
        lines.append(f'  {image_root}')

    lines.append('')
    lines.append('分群授权：群聊里每个类型都要群管理员先发送「TodayImage允许<类型名>」才能用，')
    lines.append('「TodayImage禁止<类型名>」撤销，「TodayImage列表」查看本群已允许的类型。私聊不受限制。')

    lines.append('')
    lines.append('管理命令：')
    lines.extend(f'· {command}' for command in MANAGEMENT_COMMANDS)
    return '\n'.join(lines)
