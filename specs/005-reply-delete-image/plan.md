# Implementation Plan: 回复删图

**Branch**: `005-reply-delete-image` | **Date**: 2026-09-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-reply-delete-image/spec.md`

## Summary

对机器人发出的抽图**回复** `删除<标签>`，把该图片从本地图库删除，并让当天抽到它的人重新抽一次。
用途是纠正 wd14 打标错误导致的发错图。

[research.md](./research.md) 里有一条实测结论决定了整个设计：

> **适配器不会把被回复的图片给我们。** 生产日志里，回复事件只有 `reply_id` 和被回复消息的**文本**，
> `image` / `image_list` / `image_id` **全空**。所以「哪一张」拿不到内容、也没法做哈希比对，
> 只能靠 `reply_id` 反查 —— 而这要求在**发送时**就记下「消息 ID → 文件路径」。

由此引出四个决定：

- **发图改用 `wait_recall=True`**（R2）。`bot.send` 只有这样才返回消息 ID。
  代价是适配器不回执时每次发图最多多等 10 秒，但核心有熔断（连续超时后 latch 为不支持，
  之后立即返回）。实现上必须确保「拿不到 ID 绝不拖慢后续发送」。
- **不确定一律不删**（R3）。三级解析：回执表命中 → 当日记录唯一 → 否则拒绝并列候选。
  这是不可逆且全局的操作，误删的代价远高于"功能暂时不可用"。
- **重抽直接复用 004**（R4）。清记录 + 代数 +1 + 排除集，范围从"整个类型"收窄为
  "持有该图的那些记录"，并且**跨会话** —— 图库全局，别的群抽到同一张也要能重抽。
- **先删文件后清记录**（R5）。这个顺序由失败模式决定：中间崩溃留下"文件没了但记录还在"，
  既有逻辑会自愈（记录指向的文件不存在 → 重抽）；反过来则可能让人**又抽回那张错图**。

## Technical Context

**Language/Version**: Python ≥ 3.11，仅标准库 —— 不变。

**Primary Dependencies**: 仅 `gsuid_core`。

**Storage**: **不新增落盘文件。** 回执表是内存里的有界 LRU（R7）；删除后的重抽复用
`daily_records.json` 既有的 `resets` / `excludes` 字段。

**Testing**: stdlib `unittest`。识别的三级退让、标签不符拒绝、跨会话重抽、失败时零删除
均需覆盖。本功能会改动 `tdi/daily_store.py`（新增按图片路径清理），既有 43 条护栏测试
要一条不改地通过。

**Target Platform**: 任何跑 GsCore 的主机。

**Project Type**: 单包 GsCore 插件。

**Performance Goals**: 删除是低频操作。真正的性能风险在**发送路径**：
`wait_recall=True` 在适配器不支持时会引入等待。必须确认熔断生效，且熔断后零额外开销。

**Constraints**:
- **任何识别不确定都不得删除文件**（FR-503）；失败时图库文件数零减少（SC-502）。
- 删除必须**立即**生效，不能等扫描缓存过期（FR-511）。
- 重抽必须覆盖**所有**持有该图的记录，跨群、跨用户（FR-507）。
- 默认权限 `pm<=3`，可配置**收紧**到 `pm<=1`（FR-512/513）。
- 不得拖慢正常抽图 —— 回执拿不到时要立即放弃。

**Scale/Scope**: 约 +350 行（含测试）。一个新 handler 模块、一个内存回执表、
`daily_store` 的定向扩展。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitution status**: 仍是未批准的 Spec Kit 模板，沿用 001 记录的运营方决定。

| 模板示例原则 | 评估 |
|---|---|
| **Library-State** | **通过。** 回执表、三级解析、按路径清理记录都落在 PURE 模块，可脱离核心测；handler 只做参数解析与回复。 |
| **CLI Interface**（适配为命令面） | **通过。** 命令契约见 [contracts/commands.md](./contracts/commands.md)，含四种失败各自的回复。 |
| **Test-First** | **按构造通过。** 最关键的断言是「失败时零删除」—— 这类破坏性操作一旦写错，人工测试很容易只覆盖成功路径。 |
| **Integration Testing** | **通过。** 新增契约测试断言 `wait_recall=True` 确实被传下去，以及权限收紧函数的行为。 |
| **Observability / Simplicity** | **通过，但有一处代价。** 无新依赖、无新落盘文件。代价是发送路径引入了回执等待 —— 这是识别能力的唯一来源，已在 R2 权衡并要求熔断后零开销。每次删除记 `info` 日志（FR-514）。 |

**Gate result: PASS** —— 无违规，Complexity Tracking 留空。

**一处需明示的偏离**：本功能会在 handler 内**自查权限**，而 003 R1 明确说过要避免。
原因是需求要求阈值**可配置**，而 SV 的 `pm` 是注册期常量，两者无法同时满足。
取舍见 research R6：SV `pm=3` 定义上界，handler 内只**收紧**、永不放宽到 SV 之外，
且判断集中在一个函数里由测试钉死。

## Project Structure

### Documentation (this feature)

```text
specs/005-reply-delete-image/
├── plan.md              # 本文件
├── spec.md              # 功能规格
├── research.md          # R1..R7
├── data-model.md        # SentImageRef、解析结果、删除结果
├── quickstart.md        # 验证场景
├── contracts/
│   ├── commands.md      # 命令契约 + 三级解析 + 权限
│   └── config.md        # 新增配置项
└── tasks.md             # /speckit-tasks 产出
```

### Source Code (repository root)

```text
TodayImage/
├── tdi/
│   ├── sent_index.py     PURE  # 新增：消息ID -> 文件 的有界 LRU
│   ├── delete_resolve.py PURE  # 新增：三级解析，返回「删哪个」或「为何不能删」
│   ├── delete_text.py    PURE  # 新增：回复文案
│   ├── delete_cmd.py           # 新增：回复删图命令，pm=3 粗筛 + 内部收紧
│   ├── daily_store.py    PURE  # 扩展：按图片路径找记录、跨会话清理并 +代数
│   ├── daily.py                # 发图改 wait_recall=True，把消息ID记进 sent_index
│   ├── shared.py               # 新 SV、配置访问器
│   └── (其余不动)
└── tests/
    ├── test_sent_index.py      # 新增
    ├── test_delete_resolve.py  # 新增：三级退让、零删除保证
    ├── test_delete_text.py     # 新增：四种失败回复互不相同
    ├── test_daily_store.py     # 既有，必须原样通过
    ├── test_daily_draw.py      # 既有，必须原样通过
    └── test_gscore_compat.py   # 新增 wait_recall 与权限断言
```

**Structure Decision**：解析逻辑单独成 `delete_resolve.py` 而不是塞进 handler，
因为「什么情况下**不能**删」是本功能最该被单独测试的部分 —— 它决定会不会误删文件。
把它做成纯函数，测试就能穷举各种不确定情形并断言结果永远是「拒绝」。

`daily_store.py` 本次再次改动（004 之后第二次）。护栏仍是既有 43 条测试一条不改地通过。

## Design Highlights

1. **识别靠发送时的回执，不靠图片内容**（R1/R2）。这是被适配器行为强制的，不是选择。
   代价落在发送路径上，用核心的熔断机制兜底。

2. **三级退让，不确定就拒绝**（R3）。回执表命中 → 当日记录唯一 → 拒绝并列候选。
   破坏性操作偏向不动作。

3. **重抽复用 004、且跨会话**（R4）。图库全局，同一张图可能被多个群抽到，
   必须扫描当天全部记录而不只是命令所在的会话。

4. **删除顺序由失败模式决定**（R5）。先文件后记录，中间态自愈；反过来会让人又抽回错图。

## Constitution Re-Check (post-design)

Phase 1 之后重新评估：**PASS，不变。** 无新依赖、无新落盘文件。
两处升高的风险都已显式处理：发送路径的回执等待（熔断 + 测试断言）、
handler 内自查权限（集中一处 + 测试钉死 + 只收紧不放宽）。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

无违规，表格留空。

## Phase Status

- [x] Phase 0 — Research 完成 → [research.md](./research.md)
- [x] Phase 1 — Design 完成 → [data-model.md](./data-model.md)、[contracts/](./contracts/)、[quickstart.md](./quickstart.md)
- [ ] Phase 2 — 任务拆解（`/speckit-tasks`）

## Deployment note

本功能改动**发送路径**（`wait_recall=True`），这是前五个功能里第一次。
上线后首先要确认的不是删除能否工作，而是**正常抽图有没有变慢** ——
若适配器不支持回执，探测期会有最多 10 秒的等待，熔断后才恢复。
quickstart 场景 1 就是测这个，建议先于功能本身验证。
