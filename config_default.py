"""TodayImage 的控制台配置默认值。

键名、类型与默认值见 specs/001-daily-image-categories/contracts/config.md。
类型不在这里做校验：读取一律走 tdi/shared.py 里的强制转换取值器，
手改坏了 config.json 也只会退回默认值，不会把异常抛进命令处理函数。
"""
from __future__ import annotations

from typing import Dict

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsBoolConfig,
    GsDivider,
    GsIntConfig,
    GsListStrConfig,
    GsStrConfig,
)

CONFIG_DEFAULT: Dict[str, GSC] = {
    '_DividerBasic': GsDivider('基础设置', ''),
    'TodayImageEnabled': GsBoolConfig(
        '启用今日图片',
        '总开关。关闭后本插件的所有命令都不再响应（包括管理命令）',
        True,
    ),
    'TodayImageRoot': GsStrConfig(
        '图片根目录',
        '根目录下的每个一级文件夹即一个图片类型，文件夹名就是命令后缀。'
        '留空时使用 gsuid_core/data/TodayImage/images',
        '',
    ),
    'TodayImageCommandPrefix': GsStrConfig(
        '命令前缀',
        '与类型名拼成命令，默认「今日」即「今日黑丝」。留空会退回「今日」，'
        '因为裸类型名做命令会和日常聊天冲突。修改后需要「重载图片类型」才生效',
        '今日',
    ),

    '_DividerDisplay': GsDivider('展示设置', ''),
    'TodayImageTextTemplate': GsStrConfig(
        '抽图文案模板',
        '可用变量：{类型} 类型名。可在 categories.json 里为单个类型单独覆盖',
        '你今天的{类型}来啦！',
    ),
    'TodayImageAtUser': GsBoolConfig(
        '群聊中艾特发送者',
        '开启后在群里发图时艾特请求者；私聊始终不艾特',
        True,
    ),
    'TodayImageListForwardThreshold': GsIntConfig(
        '图片列表转发阈值',
        '「查看图片」列出的图片数量超过该值时改用合并转发，避免刷屏',
        10,
        100,
    ),

    'TodayImageUniquePerDay': GsBoolConfig(
        '同群同类型不重复',
        '开启后，同一个群里同一天同一类型不会有两个人抽到同一张图；'
        '图片数少于人数时会自动退回允许重复，不会因为「没得挑」而不回复',
        True,
    ),
    'TodayImageResetUtcOffset': GsIntConfig(
        '每日重置时区(UTC偏移小时)',
        '每天几点重置抽图，按该时区的 0 点计算。默认 8 即北京时间 0 点；'
        '不跟随服务器所在时区，机器放在海外也不会漂',
        8,
        14,
    ),

    '_DividerUpload': GsDivider('上传设置', ''),
    'TodayImageUploadWhitelist': GsListStrConfig(
        '图片上传白名单',
        '允许使用「上传图片」的用户 ID。机器人主人无需加入白名单',
        [],
    ),
    'TodayImageUploadMaxMB': GsIntConfig(
        '单张图片大小上限(MB)',
        '超过该体积的上传会被拒绝并计入失败数',
        10,
        50,
    ),

    'TodayImageDirectUnlimited': GsBoolConfig(
        '私聊不限次数',
        '开启后私聊每次都重新随机一张，不锁定当天那一张，也不写入每日记录。'
        '关闭则私聊与群聊一致：每人每天每类型固定一张。群聊始终固定，不受此项影响',
        True,
    ),

    '_DividerGroupPermission': GsDivider('分群授权', ''),
    'TodayImageDefaultGroupTags': GsListStrConfig(
        '新群默认允许的类型',
        '只对**还没有任何授权记录**的群生效。群一旦被设置过（哪怕设成空），这里就不再影响它，'
        '否则调宽默认值会把管理员特意撤销掉的类型又悄悄放回去。'
        '留空即默认全部不允许，需要群管理员发送「TodayImage允许<类型名>」逐个开启',
        [],
    ),

    '_DividerBlocklist': GsDivider('命令屏蔽', ''),
    'TodayImageBlocklist': GsListStrConfig(
        '不回复的命令',
        '这些命令本插件一律不回复，即使存在同名文件夹。默认已包含 TodayWaifu 的今日系列命令。'
        '按前缀匹配，所以「今日老婆」也会覆盖「今日老婆离婚」。'
        '这里填写的内容与默认名单合并，不能删除默认项',
        [],
    ),

    '_DividerPerformance': GsDivider('性能设置', ''),
    'TodayImageScanCacheTTL': GsIntConfig(
        '目录扫描缓存时间(秒)',
        '图片目录扫描结果的缓存时长。图多时全量扫描很贵，不缓存会在整点高峰拖垮核心。'
        '上传/删除/重载会立即失效缓存，0 表示每次都重新扫描（调试用）',
        300,
        3600,
    ),
}
