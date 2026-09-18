# Implementation Plan: 分群类型重置

**Branch**: `004-group-category-reset` | **Date**: 2026-09-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-group-category-reset/spec.md`

## Summary

新增 `TodayImage重置<类型>`：master / superuser 可以清掉**当前群**下**该类型**当天的全部绑定，
让群里每个人再抽一次、拿到**新的**图。私聊、其它类型、其它群完全不受影响。

[research.md](./research.md) 里有一条决定性发现：

> **只删记录是空操作。** 抽图种子是 `{日期}:{用户}:{会话}:{类型}`，四个分量在重置前后一字未变，
> 所以清完记录后每个人重抽会拿回**一模一样**的那张。已实跑验证。

因此本功能的技术内容不是「删记录」，而是**让种子发生变化**：引入 `(日期, 群, 类型)` 上的
**重置代数（epoch）**并混入种子。关键细节是 **epoch=0 时种子保持原样** ——
否则功能一上线就会把所有群当天的图静默换掉一遍。

另外三点：

- **`pm=1` 恰好是 master + superuser**（R2）。核心的判据是 `user_pm > sv.pm` 即拒绝，
  所以新开一个 `pm=1` 的 SV 就是权限本身。与 003 的 `pm=3` 是同机制、不同阈值，**刻意不同**：
  授权决定本群能看什么，重置会改变全群已经拿到的结果，外溢更大。
- **epoch 与记录存同一份文件、同一次原子写**（R3）。分开存的话，中间崩溃会留下
  「记录清了但种子没变」——正好是上面那个 bug 的复现。
- **重置复用抽图那把锁**（R4），否则会出现一半人留在上一轮、且两轮之间不保证不撞图。

## Technical Context

**Language/Version**: Python ≥ 3.11，仅标准库 —— 不变。

**Primary Dependencies**: 仅 `gsuid_core`。无新增第三方依赖。

**Storage**: `data/TodayImage/daily_records.json` 增加一个 `resets` 字段
（`{"<群>|<类型>": <次数>}`）。**无新文件**。随当天记录一并按日清除。

**Testing**: stdlib `unittest`。种子变化、重置后仍当日固定、多次重置、跨类型/跨群/私聊隔离、
并发、权限阈值均需覆盖。`daily_store.py` 本次**必须**改动（前三个功能都没碰过它），
因此既有 43 条测试要原样通过，作为回归护栏。

**Target Platform**: 任何跑 GsCore 的主机。

**Project Type**: 单包 GsCore 插件，仓库根即包根。

**Performance Goals**: 重置是低频管理操作，成本为一次整文件读写（当天记录，量极小）。抽图路径新增开销为
一次字典查找与一次字符串拼接。

**Constraints**:
- **未被重置过的群，行为必须逐字节不变**（epoch=0 保持原种子）。这是上线安全性的前提。
- 私聊零改动（FR-403）。
- 重置后必须仍然满足「同群同类型不撞图」（FR-407）。
- 权限阈值 `pm<=1`，且**不得**在 handler 内重复判断（沿用 003 R1 的单一事实来源原则）。
- 清记录与递增 epoch 必须原子。

**Scale/Scope**: 约 +250 行（含测试）。一个新 handler 模块、`daily_store` 的定向扩展。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitution status**: 仍是未批准的 Spec Kit 模板，沿用 001 记录的运营方决定。按模板示例条目评估。

| 模板示例原则 | 评估 |
|---|---|
| **Library-First** | **通过。** epoch 的存取、种子拼接、重置计算全部落在 PURE 的 `daily_store.py` 里，可脱离核心直接测；handler 只做参数解析与回复。 |
| **CLI Interface**（适配为命令面） | **通过。** 命令契约见 [contracts/commands.md](./contracts/commands.md)，含四种失败情形各自的回复。 |
| **Test-First** | **按构造通过。** R1 那个坑正是「不写测试就会漏」的典型 —— 实现前先写「重置后必须拿到不同图」的断言，否则空操作版本看起来完全正常。 |
| **Integration Testing** | **通过。** 新增一条契约测试断言重置 SV 的 `pm == 1`。若核心升级改了阶梯，群管理员会悄悄获得改变全群当日结果的能力 —— 与 003 同理，钉死而非假设。 |
| **Observability / Simplicity** | **通过。** 无新依赖、无新文件、无缓存。重置是不可见操作，故回复必须带条数（R5），并记 `info` 日志（谁、哪个群、哪个类型、清了几条）—— 这是唯一会影响全群结果的人工操作，值得留痕。 |

**Gate result: PASS** —— 无违规，Complexity Tracking 留空。

## Project Structure

### Documentation (this feature)

```text
specs/004-group-category-reset/
├── plan.md              # 本文件
├── spec.md              # 功能规格
├── research.md          # R1..R6
├── data-model.md        # ResetEpoch、种子、重置结果
├── quickstart.md        # 验证场景
├── contracts/
│   ├── commands.md      # 命令契约 + 权限边界
│   └── storage.md       # daily_records.json 的 resets 字段
└── tasks.md             # /speckit-tasks 产出，本阶段不生成
```

### Source Code (repository root)

```text
TodayImage/
├── tdi/
│   ├── daily_store.py   PURE  # 扩展：resets 读写、种子带 epoch、reset_group_category()
│   ├── reset_cmd.py           # 新增：TodayImage重置，挂在 pm=1 的 SV 上
│   ├── reset_text.py    PURE  # 新增：回复文案（沿用 permissions_text 的先例）
│   ├── shared.py              # 新增 pm=1 的 SV 与 reset 相关导出
│   ├── daily.py               # 不改逻辑；种子变化发生在 daily_store 内部
│   └── (其余模块不动)
└── tests/
    ├── test_reset.py          # 新增：种子变化、仍固定、多次重置、隔离、并发
    ├── test_reset_text.py     # 新增：四种回复
    ├── test_daily_store.py    # 既有 24 条必须原样通过
    ├── test_daily_draw.py     # 既有 32 条必须原样通过
    └── test_gscore_compat.py  # 新增 pm==1 断言
```

**Structure Decision**：`daily_store.py` 本次必须改 —— 前三个功能都刻意没碰它，正是为了保护每日语义；
现在改动目标本身就是每日语义，绕开它反而会把同一套逻辑分裂到两处。
**保护方式改为：既有 43 条测试（`test_daily_store.py` + `test_daily_draw.py`，实测）一条不改，必须全绿。**

回复文案单独拆 `reset_text.py`，与 003 的 `permissions_text.py` 同一理由：
四种失败回复是容易写错又值得单独断言的东西，且拆出来后可脱离核心测。

新开 SV 而非复用 003 的：权限是 SV 级的，两个不同阈值的命令无法共存于一个 SV；
挂在 pm=3 的 SV 上再自查 pm 会产生两处权限判断，正是 003 R1 明确避免的漂移来源。

## Design Highlights

1. **epoch 混入种子，且 0 时保持原样**（R1）。这是功能成立的全部技术内容，也是唯一可能悄悄失效的地方 ——
   空操作版本在人工测试中看起来完全正常，只有断言「重置后图必须不同」才能抓住。

2. **epoch 与记录同文件同写**（R3）。两者生命周期一致（当天），原子性要求强（分开写会复现 R1 的 bug），
   体量极小。放一起是这三点的交集，不是图省事。

3. **`pm=1` 即权限**（R2）。核心在 handler 之前拦下，插件内不写第二处判断。

4. **重置持抽图的同一把锁**（R4），消除「一半人新轮、一半人旧轮且互相撞图」的窗口。

## Constitution Re-Check (post-design)

Phase 1 之后重新评估：**PASS，不变。** 无新依赖、无新存储文件、无缓存。
唯一升高的风险是权限阶梯被上游改动，已由契约测试钉死。
本次必须改动 `daily_store.py`，护栏是既有 43 条测试原样通过。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

无违规，表格留空。

## Phase Status

- [x] Phase 0 — Research 完成 → [research.md](./research.md)
- [x] Phase 1 — Design 完成 → [data-model.md](./data-model.md)、[contracts/](./contracts/)、[quickstart.md](./quickstart.md)
- [ ] Phase 2 — 任务拆解（`/speckit-tasks`）

## Deployment note

002、003 至今**未重启生效**，线上仍是 001。本功能叠在它们之上，一次重启会同时应用三者。
在此之前无法在真实聊天中验证 —— 加上消息送达问题（002 R0），届时也可能看起来毫无反应。
