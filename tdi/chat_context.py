"""判断一条消息来自私聊还是某个群/频道。

PURE 模块：只依赖标准库，不导入 gsuid_core。

**为什么单独拿出来做一个模块**：这是接入新适配器时最容易出事的一处判断。

GsCore 自己判定私聊一律用 `user_type != "direct"`（models.py:282、bot.py:735/1029/1095），
从不看 group_id。而 user_type 有四个取值：group / direct / channel / sub_channel —
Discord、KOOK、QQ 频道这类适配器用的是 channel 和 sub_channel，不是 group。

本插件最初用的是 `group_id is None`。只要某个适配器发来 user_type='channel'
而没有填 group_id，那句判断就会把一个公开频道当成私聊 ——
分群授权被整个绕过，频道里变成无授权、无限次发图。
所以这里改为与核心一致，并对缺字段的适配器做保守兜底。
"""
from __future__ import annotations

from typing import Any

# 私聊
DIRECT = 'direct'
# 群（QQ 群、Telegram 群等）
GROUP = 'group'
# 频道与子频道（Discord 服务器频道 / 线程、KOOK、QQ 频道）
CHANNEL_TYPES = frozenset({'channel', 'sub_channel'})


def is_direct_chat(event: Any) -> bool:
    """是否私聊。

    规则（顺序即优先级）：
      1. user_type == 'direct'          -> 私聊。与核心口径一致。
      2. user_type 属于频道类            -> **绝不**是私聊，哪怕没有 group_id。
                                           这是本模块存在的理由。
      3. user_type == 'group' 且无 group_id -> 私聊。user_type 默认值就是 'group'，
                                           适配器忘了给私聊改成 'direct' 时，
                                           它同时也不会有 group_id；若当成群聊，
                                           私聊会整个黑掉。
      4. 其它未知 user_type              -> 不是私聊。新适配器自造取值时必须
                                           fail closed，不能意外把闸门打开。
    """
    user_type = getattr(event, 'user_type', None)
    group_id = getattr(event, 'group_id', None)

    if user_type == DIRECT:
        return True
    if user_type in CHANNEL_TYPES:
        return False
    if user_type is None:
        # 连字段都没有：只能退回看 group_id。
        return not str(group_id or '').strip()
    if user_type == GROUP:
        return not str(group_id or '').strip()
    return False


def chat_group_key(event: Any) -> str:
    """用于分群授权与每日记录的群/频道键；私聊返回空串。

    频道类若没有 group_id，会得到空串 —— 那是一个谁也没授权过的桶，
    因此结果是「拒绝」。不理想，但方向正确（fail closed）。
    """
    if is_direct_chat(event):
        return ''
    return str(getattr(event, 'group_id', None) or '').strip()
