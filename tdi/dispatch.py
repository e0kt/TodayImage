"""判断一条「<前缀><文字>」消息该做什么。

PURE 模块：只依赖标准库，不导入 gsuid_core。

这里的判断顺序是契约的一部分，不可调换：

  1. 黑名单      —— 必须最先。否则某个群把一个叫「老婆」的类型授权一下，
                    就能碰到 TodayWaifu 的命令（FR-206、V-GATE-1）。
                    同时被屏蔽的名字也就不会去碰文件系统（FR-118）。
  2. 私聊旁路    —— 必须在群授权之前，而不是揉进授权逻辑里，
                    这样私聊根本不读群状态（FR-204、V-GATE-2）。
  3. 群授权      —— 在查索引之前。授权是关于「权限」而不是「存在性」：
                    类型可以先授权后建文件夹。先查权限也让未授权的群
                    无法靠时间差推断某个文件夹是否存在（V-GATE-3）。
  4. 索引
  5. 空文件夹

所有否定结果一律返回 None。不区分「不存在」「被屏蔽」「空文件夹」是刻意的：
只要它们在外部可区分，就重新构成了一个可以逐个试探出本地有哪些文件夹的探针（V-DIS-1）。
"""
from __future__ import annotations

from typing import Any, Callable

from .blocklist import is_blocked
from .gallery import lookup_category
from .group_permissions import normalize_tag


def decide(
    command: str,
    suffix: str,
    index: dict[str, str],
    images_of: Callable[[str], Any],
    extra_blocklist: Any = None,
    *,
    allow_blocklist: Any = None,
    is_direct: bool = False,
    allowed_tags: Any = None,
) -> str | None:
    """返回要抽图的类型名；任何不该回复的情况都返回 None。

    Args:
        command: 完整命令原文（如「今日老婆」），用于匹配黑名单。
        suffix: 前缀之后的部分（如「老婆」），用于查索引与群授权。
        index: 归一化类型名 -> 原始类型名。
        images_of: 原始类型名 -> 图片列表；仅用于判断是否为空。
        extra_blocklist: 运营方在控制台补充的屏蔽项。
        is_direct: 是否私聊。私聊不受分群授权限制。
        allowed_tags: 本群已授权的类型集合（已归一化）。私聊时不会被读取。
    """
    # 1. 黑名单优先于一切：优先于同名的真实文件夹，也优先于群授权。
    if is_blocked(command, extra_blocklist, allow_blocklist):
        return None

    # 2. 私聊旁路必须在这里，早于任何对群状态的访问。
    if not is_direct:
        # 3. 群授权。注意这一步在查索引之前 —— 授权与文件夹是否存在互不相干。
        if not _is_allowed(suffix, allowed_tags):
            return None

    # 4. 后缀只作字典键使用，从不拼进路径，所以穿越类输入天然查不到（V-IDX-2）。
    name = lookup_category(index, suffix)
    if name is None:
        return None

    # 5. 空文件夹必须与不存在表现一致，否则「暂无图片」本身就成了存在性提示（FR-113）。
    images = images_of(name)
    if not images:
        return None

    return name


def _is_allowed(suffix: str, allowed_tags: Any) -> bool:
    tag = normalize_tag(suffix)
    if not tag:
        return False
    if not allowed_tags:
        return False
    return tag in allowed_tags


def miss_reason(
    command: str,
    suffix: str,
    index: dict[str, str],
    images_of: Callable[[str], Any],
    extra_blocklist: Any = None,
    *,
    allow_blocklist: Any = None,
    is_direct: bool = False,
    allowed_tags: Any = None,
) -> str:
    """给日志用的原因说明。

    聊天层的可观测性是刻意放弃的，日志层的不是 —— 运营方仍然需要能查（V-DIS-5）。
    这个函数只应该喂给 logger，绝不能出现在回复里。
    """
    if is_blocked(command, extra_blocklist, allow_blocklist):
        return 'blocked'
    if not is_direct and not _is_allowed(suffix, allowed_tags):
        return 'unauthorised'
    name = lookup_category(index, suffix)
    if name is None:
        return 'unknown'
    if not images_of(name):
        return 'empty'
    return 'ok'
