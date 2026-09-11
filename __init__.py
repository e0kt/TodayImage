"""TodayImage —— 基于 GsCore 的「今日<类型>」本地图库每日抽图插件。

入口文件：声明插件并按固定顺序导入各功能模块以触发命令注册。
业务逻辑全部在 tdi/ 子包里。
"""
from gsuid_core.sv import Plugins

Plugins(
    name='TodayImage',
    disable_force_prefix=True,
    allow_empty_prefix=True,
)

# 导入顺序即命令注册顺序，不能随意调整：
#   shared 必须最先，它初始化各个 SV 实例；
#   help 必须排在 manage 之前，否则「今日图片帮助」会被 manage 里的 on_command 前缀触发器截走；
#   daily 只注册一个动态前缀触发器，类型在收到消息时才解析，不再逐个文件夹注册；
#   permissions_cmd 的命令以 TodayImage 开头，和「今日」前缀不冲突，放在 daily 之前即可。
from .tdi import shared   # noqa: E402,F401  公共层：SV 实例与配置
from .tdi import help     # noqa: E402,F401  帮助（须早于 manage）
from .tdi import manage   # noqa: E402,F401  上传 / 查看 / 删除 / 重载
from .tdi import permissions_cmd  # noqa: E402,F401  分群授权（TodayImage允许/禁止/列表）
from .tdi import daily    # noqa: E402,F401  今日<类型> 抽图
