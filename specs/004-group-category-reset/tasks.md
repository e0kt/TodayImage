---
description: "Task list for 004 — 分群类型重置"
---

# Tasks: 分群类型重置

**Input**: Design documents from `specs/004-group-category-reset/`

**Prerequisites**: [plan.md](./plan.md)、[spec.md](./spec.md)、[research.md](./research.md)、
[data-model.md](./data-model.md)、[contracts/](./contracts/)

**Tests**: **包含，且顺序至关重要。** 本功能按字面实现（只删记录）会是一个**空操作**：
命令有回复、记录确实被清了、人工测试看起来一切正常，但所有人重抽会拿回一模一样的图（research R1 已实跑验证）。
**唯一能抓住它的是「重置后图必须不同」这条断言**，所以它必须先写、先红。

**Organization**: 按 user story 分组。US1/US2 为 P1，US3 为 P2。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：不同文件、不依赖未完成任务
- **[Story]**：`[US1]`–`[US3]`
- 每条任务都标明确切文件路径

## Path Conventions

仓库根即插件包根，路径相对 `<TodayImage>/`。
**PURE** 模块只依赖标准库，由 `tests/test_gscore_compat.py` 强制。

**基线（实测）**：全套 **243 条**（无核心时 skip 11）。
回归护栏 `tests/test_daily_store.py` + `tests/test_daily_draw.py` 共 **43 条**，
本功能期间**一条都不许改**，必须原样通过 —— 这是前四个功能里第一次改动 `tdi/daily_store.py`。

---

## Phase 1: Setup

- [X] T001 在 `specs/004-group-category-reset/quickstart.md` 的「单元测试」小节记录实测基线：全套 243 条、护栏 43 条，供 T026 比对
- [X] T002 [P] 在 `specs/004-group-category-reset/plan.md` 把 Technical Context 里估算的「56 条」更正为实测的 43 条，避免后续按错误数字验收

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 重置代数的存取、带 epoch 的种子、批量清除 —— 三个 user story 全部建立在这之上

**⚠️ CRITICAL**: 本阶段完成前不得开始任何 user story

### Tests（先写，确认失败）

- [X] T003 在 `tests/test_reset.py` 写 epoch 存储与生命周期用例：缺省为 0（V-EPO-2）；键为 `<群>|<类型>` 且只切**第一个**分隔符，故类型名含 `|` 仍可还原（V-EPO-1）；每次重置 +1 且同日可反复（V-EPO-3）；写入时 `date` 非今日则 `records` 与 `resets` **一并**丢弃（V-EPO-4、I-405）；老文件缺 `resets` 字段读作空表、无需迁移（S-402）；读文件损坏时 `resets` 视为空表（S-405）
- [X] T004 [P] 在 `tests/test_reset.py` 写**本功能最关键**的种子用例：`epoch=0` 时种子与改动前**逐字节相同**（V-SEED-1、I-401）——直接断言字符串等于 `'{日期}:{用户}:{会话}:{类型}'`；`epoch>=1` 时追加 `:r{epoch}`；同一用户在 epoch 递增后 `pick_image` 选出**不同**的图（V-SEED-2、FR-402）；不同 epoch 产生不同种子，故同一秒两次重置也有效（V-SEED-4）
- [X] T005 [P] 在 `tests/test_reset.py` 写批量清除用例：只删除 `chat_key` 与 `category` **同时**匹配的条目；其它类型、其它群的条目不受影响（FR-403）；返回被清除的条数（FR-412）；当天无绑定时返回 0 且不报错（V-RES-1、FR-413）

### Implementation

- [X] T006 扩展 **PURE** `tdi/daily_store.py` 的存储层：`load_records` / `save_records` 读写新增的 `resets` 字段，缺失时视为空表；`save_records` 在跨日丢弃 `records` 时**同时**丢弃 `resets`；新增 `reset_epoch(records_payload, chat_key, category)` 取值 —— 使 T003 通过
- [X] T007 修改 **PURE** `tdi/daily_store.py` 的 `draw_seed()`，增加可选 `epoch` 参数：为 0 时返回与现状完全相同的四段式字符串，≥1 时追加 `:r{epoch}` —— 使 T004 通过。**这是本功能的全部技术内容**
- [X] T008 在 **PURE** `tdi/daily_store.py` 新增 `reset_group_category(path, date, chat_key, category)`：持既有的 per-`(chat_key, category)` 锁，删除匹配条目、`resets` 计数 +1，两者在**同一次原子写**内落盘（I-402、S-404），返回 `(cleared, epoch)` —— 使 T005 通过
- [X] T009 让 `resolve_daily_image()` 在 `tdi/daily_store.py` 中把当前 epoch 传入 `draw_seed()`，读取与抽图在同一把锁内完成，消除「一半人旧轮、一半人新轮」的窗口（FR-408、research R4）
- [X] T010 在 `tdi/shared.py` 注册 `今日图片-重置` SV（`pm=1`, `priority=21`），并导出 `reset_group_category`、`permissions`/records 路径等所需名字。**不得**复用 003 的 `今日图片-群授权`(pm=3)：权限是 SV 级的，混用会逼出第二处权限判断（research R2）
- [X] T011 确认 `tests/test_daily_store.py` 与 `tests/test_daily_draw.py` 共 43 条**未经修改**且全部通过 —— 本阶段改动了 `daily_store.py`，这 43 条是唯一的回归护栏

**Checkpoint**: 种子机制成立且未重置的群行为逐字节不变；命令尚未存在。

---

## Phase 3: User Story 1 - 重置后全群拿到新图 (Priority: P1) 🎯 MVP

**Goal**: master 发 `TodayImage重置<类型>` 后，群里此前抽过该类型的人再抽都拿到**新**图，且重新进入当日固定。

**Independent Test**: 两个账号各抽一次记下图 → 重置 → 两人再抽，确认都变了且各自稳定。（quickstart 场景 1、2）

### Tests for User Story 1（先写，确认失败）

- [X] T012 [P] [US1] 在 `tests/test_reset.py` 写端到端重置用例：两用户各抽一次 → 调用 `reset_group_category` → 两人再抽，**都必须与之前不同**（FR-402、SC-401）。**这条是本功能的验收核心**，空操作实现只会在这里失败
- [X] T013 [P] [US1] 在 `tests/test_reset.py` 写「重置放开的是一轮而非取消固定」用例：重置后同一用户连抽 5 次得到**同一张**（FR-404、SC-402）；以及多次重置用例：连续重置 5 次，每轮与上一轮都不同（FR-405、SC-403）
- [X] T014 [P] [US1] 在 `tests/test_reset.py` 写隔离与去重用例：重置 `黑丝` 不影响 `白丝`、不影响其它群、不影响私聊（FR-403、SC-404、I-403）；重置后新一轮内多用户互不撞图（FR-407、SC-406）

### Implementation for User Story 1

- [X] T015 [US1] 创建 **PURE** `tdi/reset_text.py`，实现成功回复的构建（含清除条数），沿用 `tdi/permissions_text.py` 的先例以便脱离核心测试
- [X] T016 [US1] 创建 `tdi/reset_cmd.py`：把 `TodayImage重置` 注册到 T010 的 `pm=1` SV 上，解析类型名（容忍两侧括号与空白，沿用既有归一化，FR-414），调用 `reset_group_category`，回复清除条数
- [X] T017 [US1] 在 `tdi/reset_cmd.py` 使用 `chat_context.is_direct_chat` 与 `chat_group_key` 取会话身份，**不得**用 `group_id` 判私聊 —— 频道型平台上那样判会出错（`tests/test_chat_context.py` 有调用点断言）
- [X] T018 [US1] 在 `tdi/reset_cmd.py` 用 `current_date(reset_utc_offset())` 取日期，与抽图同一口径，使重置状态随当天记录在次日一并失效（FR-406）
- [X] T019 [US1] 在 `__init__.py` 追加 `from .tdi import reset_cmd`，置于 `permissions_cmd` 之后、`daily` 之前，并更新导入顺序注释说明理由
- [X] T020 [US1] 在 `tests/_loader.py` 的 `PURE_MODULES` 加入 `'reset_text'`，使纯净性断言覆盖新模块

**Checkpoint**: MVP。重置真正有效。权限阈值与四种失败回复尚未验证/完成。

---

## Phase 4: User Story 2 - 只有 master / superuser 能重置 (Priority: P1)

**Goal**: `pm<=1` 可用；群主（2）、群管理员（3）、普通群友（6）一律不可用且不改动存储。

**Independent Test**: 用普通群友、群管理员、master 各发一次同样的命令，只有最后一个生效。（quickstart 场景 4）

### Tests for User Story 2（先写，确认失败）

- [X] T021 [P] [US2] 在 `tests/test_gscore_compat.py` 增加契约断言：`今日图片-重置` SV 的 `pm == 1`，且 `TodayImage重置` 只注册在该 SV 上、不出现在任何 `pm` 更宽松的 SV 里。核心升级若改了权限阶梯，群管理员会悄悄获得改变全群当日结果的能力 —— 与 003 同理，钉死而非假设（FR-409、FR-410、SC-405）
- [X] T022 [P] [US2] 在 `tests/test_reset_text.py` 增加源码断言：`tdi/reset_cmd.py` 中**不出现** `user_pm` / `is_master` 等自查权限的写法（用 AST 扫描，避免被文档字符串误伤），SV 的 `pm=1` 是唯一事实来源（research R2、沿用 003 R1）

### Implementation for User Story 2

- [X] T023 [US2] 核对 `tdi/reset_cmd.py` 未做任何自有权限判断，并更新 `tests/test_gscore_compat.py` 中断言「全部已注册服务」的用例，把 `今日图片-重置` 纳入预期集合（否则该用例会因新增服务而失败）

**Checkpoint**: 权限边界成立且被钉死。US1 + US2 可一并交付。

---

## Phase 5: User Story 3 - 命令自身的可用性 (Priority: P2)

**Goal**: 空参数、当天无绑定、私聊、类型不存在四种情形各自给出不同且可读的回复。

**Independent Test**: 依次触发四种情形，确认四种回复彼此不同。（quickstart 场景 6）

### Tests for User Story 3（先写，确认失败）

- [X] T024 [P] [US3] 在 `tests/test_reset_text.py` 写四种回复用例：清除 N 条含条数（FR-412）；清除 0 条时说明「本来就没有」而非报错（FR-413、V-RES-1）；类型在服务器上不存在时追加提示但不阻止执行（FR-417、V-RES-3）；私聊给出解释而非静默（FR-415）；空参数给用法（FR-416）；并断言四者**互不相同**（SC-407）

### Implementation for User Story 3

- [X] T025 [US3] 在 **PURE** `tdi/reset_text.py` 补齐四种回复的构建函数，文案以 `contracts/commands.md` 的表格为准 —— 使 T024 通过
- [X] T026 [US3] 在 `tdi/reset_cmd.py` 接上四条分支：私聊解释、空参数用法、清 0 条的措辞、以及用 `category_index()` 判断类型是否存在并追加提示。注意清 0 条时**代数仍要 +1**（V-RES-2）

**Checkpoint**: 三个 story 全部完成。

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T027 [P] 在 `tdi/reset_cmd.py` 为每次成功重置记一条 `info` 日志（操作者、群、类型、清除条数、新代数）——这是本插件唯一会改变全群当日结果的人工操作，值得留痕（contracts/commands.md「日志」）
- [X] T028 [P] 在 `README.md` 增加 `TodayImage重置<类型>` 的说明：作用范围、`pm<=1` 的权限边界、以及它与 `TodayImage允许`（`pm<=3`）权限不同的原因
- [X] T029 运行 `python -m unittest discover -s tests` 与基线 243 条比对，确认新增用例之外全部通过，且 `tests/test_daily_store.py`、`tests/test_daily_draw.py` 共 43 条未经修改仍然通过（T011 的最终复核）
- [X] T030 在装有 GsCore 的环境下跑一次全套，确认 `今日图片-重置` 以 `pm=1` 实际注册，且 002 的抽图触发器仍是唯一的非阻断前缀触发器
- [X] T031 执行 `specs/004-group-category-reset/quickstart.md` 的场景 8（升级兼容）：未执行任何重置时，同一用户当天拿到的图与改动前**完全相同**，并把结果记录回该文件
- [X] T032 执行 `specs/004-group-category-reset/quickstart.md` 的场景 1–7、9 并把结果记录回该文件
- [X] T033 在 `specs/001-daily-image-categories/data-model.md` 的 DailyRecord 小节加一条指引，说明抽图种子自 004 起可能带 `:r{epoch}` 后缀，避免旧文档被读成现状

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：无依赖
- **Foundational (Phase 2)**：依赖 Setup —— **阻塞全部 user story**
- **US1 (Phase 3)**：依赖 Foundational 的 T007（种子）与 T008（重置函数）
- **US2 (Phase 4)**：依赖 US1 的 T016（命令已存在才能断言它挂在哪个 SV）
- **US3 (Phase 5)**：依赖 US1 的 T015（`reset_text.py` 已存在）
- **Polish (Phase 6)**：依赖全部三个 story

### 共享文件协调

| 文件 | 涉及任务 | 规则 |
|---|---|---|
| `tdi/daily_store.py` | T006、T007、T008、T009 | 全部在 Foundational，严格串行；改完立即跑 T011 |
| `tdi/reset_cmd.py` | T016–T018（US1）、T023（US2）、T026（US3） | 三个 story 共用一个文件，必须串行 |
| `tdi/reset_text.py` | T015（US1）、T025（US3） | US1 建骨架，US3 补齐 |
| `tests/test_reset.py` | T003–T005（Foundational）、T012–T014（US1） | 六次追加，同一文件 |
| `tests/test_gscore_compat.py` | T021、T023（US2）、T030（Polish） | 三处改动 |

`tdi/reset_cmd.py` 是瓶颈，建议一人独占。

### 各 story 内部

- 测试先写、先红，再实现
- PURE 模块先于消费它的核心侧模块
- **T004（epoch=0 种子不变）必须在 T007 之前**，否则无法证明兼容性没被破坏

### Parallel Opportunities

- **Setup**：T001 ‖ T002
- **Foundational 测试**：T004 ‖ T005（T003 先，因其定义存储形态）
- **US1 测试**：T012 ‖ T013 ‖ T014
- **US2**：T021 ‖ T022
- **Polish**：T027 ‖ T028
- 跨 story 并行受 `reset_cmd.py` 限制；可行的切分是一人做 `daily_store` 与种子（T006–T009），另一人做命令面（T015–T019）

---

## Parallel Example: Phase 2 Foundational

```bash
# 先定存储形态：
Task: "tests/test_reset.py 写 epoch 存储与生命周期用例"

# 然后并行写另外两组失败测试：
Task: "tests/test_reset.py 写 epoch=0 种子不变 + epoch>=1 选到新图的用例"
Task: "tests/test_reset.py 写批量清除用例"

# 实现按 T006 -> T007 -> T008 -> T009 串行（同一文件）
```

---

## Implementation Strategy

### MVP（仅 US1）

Phase 1–3。重置真正有效，但权限阈值尚未被测试钉死，四种失败回复也不完整。
**不建议只发 US1** —— 一个能改变全群当日结果、而权限边界未经验证的命令，风险高于它带来的便利。
US1 是验证 quickstart 场景 1、2 的停靠点。

### Incremental Delivery

1. Setup + Foundational → 种子机制成立；43 条护栏仍绿；**未重置的群行为逐字节不变**
2. **+ US1** → 重置真正有效 → 验证场景 1、2、3、5、7
3. **+ US2** → 权限边界被契约测试钉死 → 验证场景 4
4. **+ US3** → 四种回复完整 → 验证场景 6
5. **+ Polish** → 日志、文档、全量回归、实机验证

### 部署顺序

002、003 至今未重启生效，本功能叠在其上。一次重启会同时应用三者。
**T031（升级兼容）应在重启前就跑完** —— 它验证的正是「上线不会把所有群当天的图静默换掉」。

---

## Notes

- **本功能第一次改动 `tdi/daily_store.py`**。前三个功能都刻意没碰它；护栏是那 43 条测试一条不改地通过
- **epoch=0 的种子必须逐字节不变**（V-SEED-1）。这是上线安全性的前提，不是优化
- 清 0 条时代数**仍要 +1**（V-RES-2），否则会留下难以察觉的空洞
- 权限只由 SV 的 `pm=1` 决定，handler 内不得重复判断
- **仍未解决、且非本功能引入**：消息离开 GsCore 后未送达 QQ（[002 research R0](../002-dynamic-category-lookup/research.md)）。
  在此之前场景 1–7、9 在真实聊天中都会看起来像失败
