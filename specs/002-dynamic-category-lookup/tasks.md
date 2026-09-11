---
description: "Task list for 002 — 动态类型解析、隐藏类型清单、屏蔽 TodayWaifu 命令"
---

# Tasks: 动态类型解析、隐藏类型清单、屏蔽 TodayWaifu 命令

**Input**: Design documents from `specs/002-dynamic-category-lookup/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: **INCLUDED.** The project's suite is established and the design adds rules that regress silently —
blocklist-beats-folder (V-BLK-3) and check ordering (FR-118) in particular. Test tasks precede their implementation.

**Organization**: Grouped by user story. All three stories are P1; see the dependency notes — they are separately
*testable* but share `tdi/daily.py`, so they are not freely parallel.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different files, no dependency on an incomplete task
- **[Story]**: `[US1]`–`[US3]` from spec.md
- Every task names an exact file path

## Path Conventions

Repo root is the plugin package. Paths are relative to `<TodayImage>/`.
**PURE** modules import only the standard library — `tests/test_gscore_compat.py` enforces this.

**This is a modification feature.** Deletions are real tasks, not cleanup: leaving `tdi/registry_binding.py` in
place while the dynamic trigger lands would register each folder's command **twice** and produce double replies
(I-201). T016–T018 are therefore load-bearing, not tidying.

---

## Phase 1: Setup

**Purpose**: Pin the baseline so a regression in feature 001's behaviour is detectable

- [X] T001 Record the pre-change baseline in `specs/002-dynamic-category-lookup/quickstart.md` under a new "Baseline" heading: `python -m unittest discover -s tests` currently reports **130 tests, 8 skipped** with GsCore absent, and **130 / 0 skipped** with it available
- [X] T002 [P] Add `TodayImageBlocklist` (`GsListStrConfig`) to `config_default.py` with the 12 default base names from `contracts/config.md`, placed under a new `_DividerBlocklist` divider

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The two pure rules — suffix resolution and blocklist matching — that all three stories build on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests (write first, confirm they FAIL)

- [X] T003 [P] Write `tests/test_category_index.py`: index keys are `strip().casefold()` (V-IDX-1); lookup resolves regardless of case/surrounding space (FR-102); `..`, `/`, `\` and absolute paths all miss because the suffix is only ever a dict key (V-IDX-2, FR-104); reserved names excluded (V-IDX-4); disabled categories absent (V-IDX-6); case/whitespace collision keeps the stable-sort winner (V-IDX-5)
- [X] T004 [P] Write `tests/test_blocklist.py`: exact match blocks; a command extending a base name blocks (`今日老婆离婚` via `今日老婆`, V-BLK-1); matching is `strip().casefold()` on both sides (V-BLK-4); operator entries merge with and cannot remove defaults (V-BLK-5); an empty configured list still blocks the defaults (CF-5); blank entries ignored

### Implementation

- [X] T005 [P] Add `build_category_index(scan_rows)` to **PURE** `tdi/gallery.py`, returning `dict[casefolded_name, canonical_name]` — makes T003 pass
- [X] T006 [P] Create **PURE** `tdi/blocklist.py` with `DEFAULT_BLOCKLIST` and `is_blocked(command, extra)`, merging extras over the immutable defaults — makes T004 pass
- [X] T007 Register the new pure modules in `tests/_loader.py` by adding `'blocklist'` and `'dispatch'` to `PURE_MODULES`, so the purity test in `tests/test_gscore_compat.py` covers them
- [X] T008 Add `category_index()` and `configured_blocklist()` accessors to `tdi/shared.py`, building the index from the existing TTL-cached scan so a miss costs no filesystem access (FR-108, V-IDX-8) — depends on T005, T006
- [X] T009 Confirm `tests/test_daily_store.py` and `tests/test_daily_draw.py` still pass **unmodified** — `tdi/daily_store.py` must not be edited by this feature (I-204, SC-107)

**Checkpoint**: Pure rules exist and are tested; feature 001's daily guarantees demonstrably intact.

---

## Phase 3: User Story 1 - Any folder becomes a command, with no reload (Priority: P1) 🎯 MVP

**Goal**: `今日<任意文件夹名>` resolves at request time; a folder added while the core runs works with no reload
and no restart.

**Independent Test**: Create a folder with images while the core is running, send `今日<名字>`, receive an image —
without issuing any reload. (quickstart Scenario 1.)

### Tests for User Story 1 (write first, confirm they FAIL)

- [X] T010 [P] [US1] Write `tests/test_dispatch.py` for the ordered decision in `contracts/commands.md` §1: blocklist is consulted **before** the index (FR-118) — assert with an index-lookup spy that a blocked command never queries it; an unresolved suffix returns "no reply"; an empty-but-existing folder returns "no reply" (V-DIS-1, FR-113); a resolved non-empty folder returns its canonical name
- [X] T011 [P] [US1] Extend `tests/test_gscore_compat.py` with a non-blocking assertion: the draw SV's dynamic trigger must have `block=False`, since `block=True` would terminate the dispatch loop ahead of any plugin at a higher priority number and kill their `今日X` (FR-106, SC-105)

### Implementation for User Story 1

- [X] T012 [US1] Create **PURE** `tdi/dispatch.py` with `decide(command, suffix, index, blocked_bases)` returning the canonical folder name or `None`, implementing the fixed order from `contracts/commands.md` §1 — makes T010 pass
- [X] T013 [US1] Rewrite the trigger in `tdi/daily.py` as a single `on_prefix(command_prefix(), block=False)` handler that reads the suffix from `ev.text` and delegates to `dispatch.decide(...)`, replacing `handle_category_command`'s keyword lookup
- [X] T014 [US1] Remove import-time per-folder registration from `tdi/daily.py`: delete `_register_on_import`, `refresh_commands_sync`, `refresh_commands`, `apply_report`, `_KEYWORD_MAP` and `_recover_category`
- [X] T015 [US1] Keep the draw path intact in `tdi/daily.py`: the resolved category still flows through `draw_category_image` into `daily_store.resolve_daily_image` with `unique_per_chat` and the Beijing date unchanged (FR-105)
- [X] T016 [US1] Delete `tdi/registry_binding.py` — leaving it would double-register every folder's command alongside the dynamic trigger (I-201)
- [X] T017 [US1] Delete `tests/test_registry_binding.py` and remove `'registry_binding'` handling from `tests/_loader.py`
- [X] T018 [US1] Remove the `TL`-mutation contract test from `tests/test_gscore_compat.py` (`test_runtime_registration_and_the_internal_unregister_both_work`) and the `del sv.TL` guard in `test_only_the_internal_reach_touches_TL_directly`; the plugin no longer touches framework internals, so both now assert nothing
- [X] T019 [US1] Demote `重载图片类型` in `tdi/manage.py` to cache invalidation: drop the added/removed command diff, keep the refreshed category count, and state that it is optional because new folders go live within the cache TTL (contracts §5)
- [X] T020 [US1] Update `__init__.py` if the `manage`/`daily` import order assumptions changed — `daily` no longer registers at import, so confirm the documented order comment still reflects reality

**Checkpoint**: MVP. Any folder works, no reload. Disclosure and blocklist not yet applied.

---

## Phase 4: User Story 2 - The category and command list is never disclosed (Priority: P1)

**Goal**: Public replies reveal neither folder names, nor management commands, nor filesystem paths; every public
negative is silence.

**Independent Test**: From a non-master account send 20+ unknown/malformed `今日X` variants plus the help command;
confirm zero replies and zero disclosure. Then confirm a master still sees the full listing. (quickstart Scenario 2.)

### Tests for User Story 2 (write first, confirm they FAIL)

- [X] T021 [P] [US2] Rewrite `tests/test_help_text.py` for the two disclosure levels: public output contains no folder name, no image-root path, no management command, and no counts (V-DIS-2, V-DIS-3); master output contains all of them (V-DIS-4); both describe the mechanism (FR-111)
- [X] T022 [P] [US2] Add `tests/test_non_disclosure.py` asserting that the strings returned for unknown, blocked, empty-folder and malformed input are **byte-identical** to one another — the uniformity is the requirement, not merely the individual silences (V-DIS-1, FR-113)

### Implementation for User Story 2

- [X] T023 [US2] Rewrite **PURE** `tdi/help_text.py` as `build_help_text(prefix, *, is_master, categories=None, image_root=None)` producing mechanism-only text for the public case and the full listing for masters — makes T021 pass
- [X] T024 [US2] Pass the viewer's permission into the renderer in `tdi/help.py`, determining master status via the existing `is_master` helper in `tdi/shared.py`
- [X] T025 [US2] Remove the public disclosure paths in `tdi/daily.py`: delete `_empty_hint` and every reply on a resolution failure, so the handler returns silently (FR-109)
- [X] T026 [US2] Audit `tdi/manage.py` so any reply reachable before an authorisation check contains no folder name and no path; keep full detail after the master/whitelist gate (FR-112)
- [X] T027 [US2] Confirm `tdi/shared.py::send_image_reply` and the error replies added in feature 001 T050 carry no filesystem paths, replacing the two that name a directory with a generic message

**Checkpoint**: Nothing public discloses the gallery. US1 + US2 are shippable together.

---

## Phase 5: User Story 3 - TodayWaifu's 今日 commands are never answered (Priority: P1)

**Goal**: `今日老婆` / `今日萝莉` / `今日战双老婆` and friends are never answered by TodayImage — with TodayWaifu
loaded, unloaded, or with a same-named folder present.

**Independent Test**: With both plugins loaded, each TodayWaifu `今日` command yields exactly one reply, from
TodayWaifu; then disable TodayWaifu and confirm TodayImage still stays silent. (quickstart Scenario 3.)

### Tests for User Story 3 (write first, confirm they FAIL)

- [X] T028 [P] [US3] Extend `tests/test_blocklist.py` with the precedence case: a blocked name resolves to no reply **even when a folder of exactly that name exists** (V-BLK-3, US3 AS3) — the rule most likely to regress silently
- [X] T029 [P] [US3] Extend `tests/test_gscore_compat.py::test_does_not_collide_with_todaywaifu` into an assertion that, with both plugins loaded, every `今日*` keyword registered by TodayWaifu is reported blocked by `tdi/blocklist.py` — so a future TodayWaifu command that we fail to block fails the test (SC-103)

### Implementation for User Story 3

- [X] T030 [US3] Wire `is_blocked` into `tdi/dispatch.py::decide` as the first check after the master switch, before any index lookup (FR-118, V-BLK-2) — makes T028 pass
- [X] T031 [US3] Read the blocklist per request in `tdi/shared.py::configured_blocklist`, merging `TodayImageBlocklist` over the immutable defaults so console edits apply without a restart and cannot remove a default (FR-116, V-BLK-5)
- [X] T032 [US3] Verify against the live registry that every `今日*` trigger TodayWaifu registers is covered by a default base name, and reconcile `tdi/blocklist.py` and `contracts/config.md` if the two have drifted

**Checkpoint**: All three stories complete and independently verifiable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T033 [P] Add a `debug` log with the reason to every silent return in `tdi/dispatch.py` and `tdi/daily.py` — chat observability is deliberately traded away, log observability is not (V-DIS-5)
- [X] T034 [P] Update `README.md`: folders resolve dynamically with no reload, unknown names are silent by design, the blocklist and its console key, and remove the category-listing example from the public-facing section
- [X] T035 Re-run the full suite and compare against the T001 baseline, accounting for the deleted `test_registry_binding.py` and the two removed compat tests; every remaining feature 001 test must still pass
- [X] T036 Run quickstart Scenario 4 in `specs/002-dynamic-category-lookup/quickstart.md` — the structural assertion that the dynamic trigger is non-blocking and other plugins are unaffected
- [ ] T037 Run quickstart Scenarios 1, 2, 3, 5 and 6 in `specs/002-dynamic-category-lookup/quickstart.md` against a live core and record results in that file
- [X] T038 Update `specs/001-daily-image-categories/contracts/commands.md` with a pointer noting that SC-005's "always reply" rule is superseded for public paths by feature 002's silence contract, so the older document is not read as still binding

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup — **blocks all stories**
- **US1 (Phase 3)**: depends on Foundational
- **US2 (Phase 4)**: depends on Foundational; T025 also depends on US1's T013 having created the handler
- **US3 (Phase 5)**: depends on US1's `tdi/dispatch.py` (T012)
- **Polish (Phase 6)**: depends on all three stories

### Story independence — read this before parallelising

All three stories are P1 and the spec requires them to ship together, but they are not freely parallel:

| File | Touched by | Rule |
|---|---|---|
| `tdi/dispatch.py` | T012 (US1) creates, T030 (US3) extends | US3's check slots into the order US1 establishes — sequence, don't parallelise |
| `tdi/daily.py` | T013–T015 (US1), T025 (US2) | US1 rewrites the handler; US2 then strips its failure replies |
| `tests/test_gscore_compat.py` | T011 (US1), T018 (US1), T029 (US3) | Three separate edits to one file; all sequential |
| `tests/test_blocklist.py` | T004 (foundational), T028 (US3) | T028 appends a case |
| `tdi/manage.py` | T019 (US1), T026 (US2) | Reload demotion first, then the disclosure audit |

**US2 is the most separable**: T021/T023/T024 live in `tests/test_help_text.py`, `tdi/help_text.py` and
`tdi/help.py`, none of which US1 or US3 touch. A second person can take US2's help work in parallel with US1.

### Within each story

- Tests are written first and must fail before implementation
- PURE modules before the GsCore-facing modules that consume them
- Deletions (T016–T018) come **after** the dynamic trigger works, so the plugin is never in a state with neither mechanism

### Parallel Opportunities

- **Foundational**: T003 ‖ T004, then T005 ‖ T006
- **US1**: T010 ‖ T011
- **US2**: T021 ‖ T022; the whole of US2's help work ‖ US1
- **US3**: T028 ‖ T029
- **Polish**: T033 ‖ T034

---

## Parallel Example: Phase 2 Foundational

```bash
# Failing tests for the two pure rules:
Task: "Write tests/test_category_index.py"
Task: "Write tests/test_blocklist.py"

# Then the implementations:
Task: "Add build_category_index() to tdi/gallery.py"
Task: "Create tdi/blocklist.py"
# (tdi/shared.py accessors follow both)
```

---

## Implementation Strategy

### MVP (US1 only)

Phases 1–3. At that point any folder resolves with no reload — but replies still disclose folder names, and
TodayWaifu commands are only protected by priority ordering, which holds solely while TodayWaifu is loaded.
**Do not ship US1 alone**; it is the right stopping point to validate, not to release.

### Incremental Delivery

1. Setup + Foundational → pure rules tested; 001's daily suites still green
2. **+ US1** → dynamic resolution, `registry_binding` deleted → validate Scenario 1
3. **+ US2** → nothing public discloses the gallery → validate Scenario 2
4. **+ US3** → blocklist independent of load order and of folder names → validate Scenario 3
5. **+ Polish** → debug logging, docs, full regression against the T001 baseline

### Parallel Team Strategy

Everyone lands Phase 2 together. Then Dev A takes US1 then US3 (they share `dispatch.py`), Dev B takes US2's help
work. The shared-file table above is the coordination contract.

---

## Notes

- `tdi/daily_store.py` must not be edited. It carries the daily guarantees most at risk from this rewrite, and
  leaving it alone is the cheapest way to protect them (I-204)
- `[P]` = different files, no dependency on an incomplete task
- Verify each test fails before implementing
- **Separate and unresolved**: replies currently leave GsCore but never arrive in QQ ([research R0](./research.md)).
  Nothing in this feature addresses that, and while it stands every live scenario here will look like a failure
