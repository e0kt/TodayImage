"""TodayImage 的配置实例。

配置文件放在 GsCore 的 data 目录下，而不是插件目录里，
这样插件升级/重装/删除重拉都不会把用户的设置带走。
"""
from __future__ import annotations

from gsuid_core.data_store import get_res_path
from gsuid_core.utils.plugins_config.gs_config import StringConfig

from .config_default import CONFIG_DEFAULT

CONFIG_PATH = get_res_path('TodayImage') / 'config.json'

TodayImageConfig = StringConfig(
    'TodayImage',
    CONFIG_PATH,
    CONFIG_DEFAULT,
)

# 以软链接方式挂进 plugins/ 时，Path.resolve() 会跟到仓库真实路径，
# 导致 webconsole 自动推断的 plugin_name 落到仓库目录名上、配置关联不到本插件。
# 开发期用软链接安装是常规做法，所以这里手动补回正确值。
TodayImageConfig.plugin_name = 'TodayImage'
