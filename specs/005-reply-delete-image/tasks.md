---
description: "Task list for 005 — 回复删图"
---

# Tasks: 回复删图

**Input**: Design documents from `specs/005-reply-delete-image/`

**Prerequisites**: [plan.md](./plan.md)、[spec.md](./spec.md)、[research.md](./research.md)、
[data-model.md](./data-model.md)、[contracts/](./contracts/)

**Tests**: **包含。** 这是本插件第一个会**永久删除文件**的功能。
最关键的性质是「任何识别不确定的情形下，图库文件数零减少」——
这类保证在人工测试里极易只覆盖成功路径，必须先写断言。

**Organization**: 按 user story 分组，三个都是 P1。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：不同文件、不依赖未完成任务
- **[Story]**：`[US1]`–`[US3]`
- 每条任务都标明确切文件路径

## Path Conventions

仓库根即插件包根，路径相对 `<TodayImage>/`。
**PURE** 模块只依赖标准库，由 `tests/test_gscore_compat.py` 强制。

**基线（实测）**：全套 **295 条**（无核心时 skip 13）。
回归护栏 `tests/test_daily_store.py` + `tests/test_daily_draw.py` 共 **43 条**，
本功能期间**一条都不许改** —— 这是 004 之后第二次改动 `tdi/daily_store.py`。

**两条贯穿全程的硬约束**：

1. **任何识别不确定都不得删除文件**（FR-503、SC-502、I-501）。
2. **不得拖慢正常抽图**。本功能改动发送路径（`wait_recall=True`），
   这是前五个特性里第一次 —— 拿不到回执必须立即放弃，不重试、不阻塞。

---

## Phase 1: Setup

- [X] T001 在 `specs/005-reply-delete-image/quickstart.md` 的「单元测试」小节记录实测基线：全套 295 条、护栏 43 条，供 T031 比对
- [X] T002 [P] 在 `config_default.py` 新增 `TodayImageDeleteMasterOnly`（`GsBoolConfig`，默认 `False`），描述按 `contracts/config.md`：默认允许群管理员，置 `True` 则收紧为仅 master，供图库不可恢复的部署使用

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 回执表、三级解析、按图片路径清理记录 —— 三个 story 全部建立在这之上

**⚠️ CRITICAL**: 本阶段完成前不得开始任何 user story

> **解析器整体放在这里**（含全部拒绝分支），而不是拆到 US1/US2。
> 「什么情况下**不能**删」是本功能的安全机制，与「能删时删哪张」不可分割；
> 拆开会出现「删除已实现但守卫尚未接上」的窗口。

### Tests（先写，确认失败）

- [X] T003 [P] 写 `tests/test_sent_index.py`：写入后可按消息 ID 取回文件路径（V-SIR-1）；超过上限按 LRU 淘汰最旧项（V-SIR-2）；一次发送返回多个 ID 时每个 ID 都指向同一文件（V-SIR-5）；查不到时返回 None 而不抛异常（V-SIR-4）；空 ID / None 不写入
- [X] T004 [P] 写 `tests/test_delete_resolve.py` 的**成功路径**：`reply_id` 命中回执表时返回 `ok` 与对应文件（三级退让第 1 级）；未命中但该会话该类型当天**恰好一条**记录时返回 `ok`（第 2 级）
- [X] T005 [P] 写 `tests/test_delete_resolve.py` 的**拒绝路径**（本功能的安全核心）：`reply_id` 为空 → `not_a_draw`；回执与记录都查不到 → `not_found`；当天该类型有多条记录且回执未命中 → `ambiguous` 且带候选；解析出的文件实际属于别的类型 → `tag_mismatch` 且带真实类型（V-DRS-2）；并断言**五种 outcome 互不相同**（V-DRS-4、SC-507），以及除 `ok` 外**任何结果都不携带可删除的文件路径**（V-DRS-1）
- [X] T006 [P] 写 `tests/test_reply_delete_store.py`：按图片**绝对路径**在当天全部记录里找出持有者，跨会话、跨用户（V-DOC-4）；同名但不同目录的文件**不得**被误匹配（V-DOC-7）；清理后每个受影响 `(会话,类型)` 的代数 +1 且该文件进入排除集（V-DOC-5）；没有任何记录持有它时返回 0 且不报错

### Implementation

- [X] T007 [P] 创建 **PURE** `tdi/sent_index.py`：有界 LRU，`remember(message_ids, image, category, chat_key, user_key)` 与 `lookup(message_id)`，仅内存不落盘（V-SIR-3）—— 使 T003 通过
- [X] T008 创建 **PURE** `tdi/delete_resolve.py`：`resolve(reply_id, tag, sent_index_snapshot, today_records, index)` 返回 `DeleteResolution`，实现 `contracts/commands.md` 的三级退让。纯函数、不碰文件系统，因此拒绝分支可穷举测试 —— 使 T004、T005 通过
- [X] T009 扩展 **PURE** `tdi/daily_store.py`：`records_holding_image(records, image)` 与 `clear_records_for_image(path, date, image)`，后者复用 004 的代数与排除集机制，对每个受影响 `(会话,类型)` 各自 +1 并把该文件加入排除集 —— 使 T006 通过
- [X] T010 在 `tests/_loader.py` 的 `PURE_MODULES` 加入 `'sent_index'`、`'delete_resolve'`、`'delete_text'`，使纯净性断言覆盖新模块
- [X] T011 确认 `tests/test_daily_store.py` 与 `tests/test_daily_draw.py` 共 43 条**未经修改**且全部通过 —— 本阶段改动了 `daily_store.py`

**Checkpoint**: 解析与清理的纯逻辑成立且被测试覆盖；尚未有任何命令、也尚未删过任何文件。

---

## Phase 3: User Story 1 - 回复即删并让对方重抽 (Priority: P1) 🎯 MVP

**Goal**: 对一张抽图回复 `删除<标签>`，文件从图库消失，当天抽到它的人（跨群跨用户）能重新抽到**另一张**。

**Independent Test**: 让一个账号抽一张记下来；回复删除；确认文件消失且该账号再抽拿到别的图。
（quickstart 场景 2）

### Tests for User Story 1（先写，确认失败）

- [X] T012 [P] [US1] 在 `tests/test_reply_delete_store.py` 写端到端用例：两个会话的用户抽到同一张图 → 按路径清理 → 两人再抽都拿到**不同**的图（FR-508、SC-504），且新一轮内不撞图
- [X] T013 [P] [US1] 在 `tests/test_reply_delete_store.py` 写"删除后永不再抽到"用例：被删文件进入排除集后，即便仍出现在候选列表里也不会被选中（FR-509、I-502）；以及图库被删到只剩 0 张时抽取静默而非报错

### Implementation for User Story 1

- [X] T014 [US1] 创建 **PURE** `tdi/delete_text.py`，实现成功与"文件已不存在"两种回复，文案以 `contracts/commands.md` 的表格为准
- [X] T015 [US1] 创建 `tdi/delete_cmd.py`：把 `删除` 注册到新的 `pm=3` SV 上（T017 创建），要求 `ev.reply_id` 非空，解析标签（容忍两侧括号与空白，FR-505），调用 `delete_resolve`
- [X] T016 [US1] 在 `tdi/delete_cmd.py` 实现执行顺序：**先删文件、再清记录**（V-DOC-1、research R5）；文件删除失败则整个操作中止且记录一条不动（V-DOC-2）；文件本就不存在时仍清理记录（V-DOC-3）；完成后**立即**失效目录扫描缓存（V-DOC-6、FR-511）
- [X] T017 [US1] 在 `tdi/shared.py` 注册 `今日图片-删图` SV（`pm=3`, `priority=21`）并导出所需名字；`pm=3` 同时是默认权限与**硬上界**
- [X] T018 [US1] 修改 `tdi/message_delivery.py` 与 `tdi/shared.py::send_image_reply`，抽图改用 `bot.send(..., wait_recall=True)`，把返回的消息 ID 连同文件路径写入 `sent_index`。**拿不到 ID 必须立即放弃**：不重试、不报错、不影响本次发送的结果（V-SIR-1、plan 约束 2）
- [X] T019 [US1] 在 `__init__.py` 追加 `from .tdi import delete_cmd`，置于 `reset_cmd` 之后、`daily` 之前，并更新导入顺序注释

**Checkpoint**: MVP。删除与重抽可用。拒绝分支的回复与权限尚未接上。

---

## Phase 4: User Story 2 - 认不出是哪张图时要说清楚 (Priority: P1)

**Goal**: 识别失败时明确告知并给出替代做法，**且绝不删除任何文件**。

**Independent Test**: 逐一触发四种失败，每次之后数图库文件数，必须不变。（quickstart 场景 4）

### Tests for User Story 2（先写，确认失败）

- [X] T020 [P] [US2] 写 `tests/test_delete_text.py`：`not_found` / `ambiguous` / `tag_mismatch` / `not_a_draw` / 权限不足 五种回复互不相同且可操作（SC-507）；`ambiguous` 的回复里包含候选图片 ID；`tag_mismatch` 的回复里包含**实际**类型
- [X] T021 [P] [US2] 在 `tests/test_delete_text.py` 增加源码断言：`tdi/delete_cmd.py` 里文件删除调用**只出现在** `ok` 分支内（用 AST 检查删除调用所在的分支），防止日后改动把删除挪到守卫之外

### Implementation for User Story 2

- [X] T022 [US2] 在 **PURE** `tdi/delete_text.py` 补齐五种失败回复 —— 使 T020 通过
- [X] T023 [US2] 在 `tdi/delete_cmd.py` 接上五条拒绝分支，每条都在 `delete_resolve` 返回非 `ok` 时**直接返回**，不进入任何文件操作（FR-503、I-501）
- [X] T024 [US2] 在 `tdi/delete_cmd.py` 处理"被回复的文件已不在磁盘"：报告该情况但**仍然**清理记录让人能重抽（US2 AS4、V-DOC-3）

**Checkpoint**: 安全性质完整。US1 + US2 可一并交付。

---

## Phase 5: User Story 3 - 权限与留痕 (Priority: P1)

**Goal**: 群管理员及以上可用（默认），可配置收紧为仅 master；普通群友在任何配置下都进不来；每次删除留痕。

**Independent Test**: 用普通群友、群管理员（两种配置）、master 各试一次。（quickstart 场景 6）

### Tests for User Story 3（先写，确认失败）

- [X] T025 [P] [US3] 在 `tests/test_gscore_compat.py` 增加契约断言：`今日图片-删图` SV 的 `pm == 3`，且 `删除` 只注册在该 SV 上。`pm=3` 是硬上界，普通群友（`pm=6`）在任何配置下都不得进入
- [X] T026 [P] [US3] 写 `tests/test_delete_permission.py` 针对权限判定的纯函数：默认配置下 `pm=3` 通过、`pm=6` 不通过；收紧配置下 `pm=3` 不通过而 `pm<=1` 通过；断言该函数**只能收紧、永不放宽**到 SV 的 `pm=3` 之外（CF-504）

### Implementation for User Story 3

- [X] T027 [US3] 在 `tdi/shared.py` 增加 `delete_master_only()` 配置访问器与一个集中的权限判定函数，每次请求现读（CF-503）
- [X] T028 [US3] 在 `tdi/delete_cmd.py` 调用该判定函数，不通过时回复"当前配置下只有机器人主人可以删除图库文件" —— 这是本项目**第一次**在 handler 内自查权限，判定必须集中在 T027 那一个函数里（research R6、plan 偏离说明）
- [X] T029 [US3] 在 `tdi/delete_cmd.py` 为每次成功删除记一条 `info` 日志：操作者、会话、被删文件、清理记录数、受影响会话数（FR-514、SC-506）

**Checkpoint**: 三个 story 全部完成。

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T030 [P] 在 `README.md` 增加「回复删图」说明：用法、默认权限、`TodayImageDeleteMasterOnly`、以及识别失败时改用 `删除图片 <类型> <图片ID>`
- [X] T031 运行 `python -m unittest discover -s tests` 与基线 295 条比对，确认新增用例之外全部通过，且 43 条护栏未经修改仍然通过（T011 的最终复核）
- [X] T032 在装有 GsCore 的环境下跑一次全套，确认 `今日图片-删图` 以 `pm=3` 实际注册，且 002 的抽图触发器仍是唯一的非阻断前缀触发器
- [X] T033 执行 `specs/005-reply-delete-image/quickstart.md` 的**场景 1（抽图有没有变慢）**并把 duration 记录回该文件。**这条应先于功能验证** —— 发送路径的改动影响每一次抽图，比删除功能本身重要
- [X] T034 执行 `specs/005-reply-delete-image/quickstart.md` 的场景 2–8 并记录结果，其中场景 4 每一项都要复核图库文件数未变
- [X] T035 在 `specs/004-group-category-reset/data-model.md` 增加一条指引，说明 ResetEpoch / ResetExclusion 自 005 起也会被「按图片路径清理」触发，避免旧文档被读成只有整类型重置会用到

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：无依赖
- **Foundational (Phase 2)**：依赖 Setup —— **阻塞全部 user story**
- **US1 (Phase 3)**：依赖 T008（解析器）与 T009（按路径清理）
- **US2 (Phase 4)**：依赖 US1 的 T014（`delete_text.py`）与 T015（命令骨架）
- **US3 (Phase 5)**：依赖 US1 的 T015/T017（命令与 SV 已存在）
- **Polish (Phase 6)**：依赖全部三个 story

### 共享文件协调

| 文件 | 涉及任务 | 规则 |
|---|---|---|
| `tdi/delete_cmd.py` | T015/T016（US1）、T023/T024（US2）、T028/T029（US3） | 三个 story 共用一个文件，必须串行；建议一人独占 |
| `tdi/delete_text.py` | T014（US1）、T022（US2） | US1 建骨架，US2 补齐失败文案 |
| `tdi/daily_store.py` | T009（Foundational） | 仅此一处改动；改完立即跑 T011 |
| `tests/test_delete_resolve.py` | T004、T005（Foundational） | 两次追加 |
| `tests/test_reply_delete_store.py` | T006（Foundational）、T012/T013（US1） | 三次追加 |
| `tests/test_delete_text.py` | T020、T021（US2） | 两次追加 |
| `tests/test_gscore_compat.py` | T025（US3）、T032（Polish） | 两处改动 |

### 各 story 内部

- 测试先写、先红，再实现
- PURE 模块先于消费它的核心侧模块
- **T005（拒绝路径）必须在 T016（实际删文件）之前** —— 守卫要先于破坏性操作存在

### Parallel Opportunities

- **Setup**：T001 ‖ T002
- **Foundational 测试**：T003 ‖ T004 ‖ T005 ‖ T006
- **Foundational 实现**：T007 ‖（T008 → T009）
- **US1 测试**：T012 ‖ T013
- **US2 测试**：T020 ‖ T021
- **US3 测试**：T025 ‖ T026
- 跨 story 并行受 `delete_cmd.py` 限制；可行的切分是一人做纯逻辑（T007–T009），
  另一人做命令面（T014–T019）

---

## Parallel Example: Phase 2 Foundational

```bash
# 四组失败测试可以同时写：
Task: "tests/test_sent_index.py 回执表用例"
Task: "tests/test_delete_resolve.py 成功路径"
Task: "tests/test_delete_resolve.py 拒绝路径"
Task: "tests/test_reply_delete_store.py 按路径清理用例"

# 实现：sent_index 可并行；delete_resolve -> daily_store 串行
Task: "创建 PURE tdi/sent_index.py"
```

---

## Implementation Strategy

### MVP（仅 US1）

Phase 1–3。删除与重抽可用，但**拒绝分支还没接上回复、权限也还没判** ——
此时一个识别失败可能走到未定义的路径，而这是会删文件的命令。
**不要只发 US1**，它是验证 quickstart 场景 2 的停靠点。

### Incremental Delivery

1. Setup + Foundational → 纯逻辑成立；43 条护栏仍绿；**还没删过任何文件**
2. **+ US1** → 删除与重抽可用 → 验证场景 2、3
3. **+ US2** → 安全性质完整，失败时零删除 → 验证场景 4、5
4. **+ US3** → 权限与留痕 → 验证场景 6
5. **+ Polish** → 文档、全量回归、实机验证（场景 1 先跑）

### 部署注意

本功能是前五个特性里**第一个改动发送路径**的。上线后首先要确认的不是删除能否工作，
而是**正常抽图有没有变慢**：适配器若不支持回执，探测期每次发图最多多等 10 秒，
熔断后才恢复。T033 就是测这个，**应先于功能验证**。

---

## Notes

- **任何识别不确定都不得删除文件**。这条比功能可用性重要得多
- **先删文件后清记录**，顺序由失败模式决定（research R5）：中间崩溃留下的状态会自愈，
  反过来则可能让人又抽回那张错图
- 按**完整路径**删除，不按 8 位短 ID —— 短 ID 由文件名派生，不同子目录下可能重复
- `pm=3` 是硬上界；配置只能**收紧**、不能放宽
- **仍未解决、非本功能引入**：`wait_recall` 依赖的适配器 `echo` 能力在本机从未被验证过。
  若不支持，本功能会退化为「总是提示改用 `删除图片`」，这**不是缺陷**（research 开放问题）
