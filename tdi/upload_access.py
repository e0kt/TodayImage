"""上传权限判定。

PURE 模块：只依赖标准库，不导入 gsuid_core。

从 shared 里拆出来，是因为「谁能上传」是一条值得单独测的规则，
而 shared 依赖核心、没法脱离核心加载。
"""
from __future__ import annotations

from typing import Any


def normalized_user_ids(values: Any) -> frozenset[str]:
    """白名单既可能是列表，也可能是用户在控制台里逗号/空格分隔写成的一行。"""
    if isinstance(values, str):
        items: Any = values.replace(',', ' ').split()
    elif isinstance(values, (list, tuple, set, frozenset)):
        items = values
    else:
        return frozenset()
    return frozenset(text for value in items if (text := str(value).strip()))


def can_upload_images(user_id: Any, master_ids: Any, whitelist_ids: Any) -> bool:
    """主人天然有权限，不需要再把自己加进白名单（FR-017）。"""
    normalized = str(user_id).strip()
    if not normalized:
        return False
    return (
        normalized in normalized_user_ids(master_ids)
        or normalized in normalized_user_ids(whitelist_ids)
    )
