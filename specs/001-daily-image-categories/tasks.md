---
description: "Task list for TodayImage — 今日<类型> 本地图库每日抽图插件"
---

# Tasks: TodayImage — 今日<类型> 本地图库每日抽图插件

**Input**: Design documents from `specs/001-daily-image-categories/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: **INCLUDED.** The design commits to a test suite — research R9 fixes the pure-module/`importlib`
strategy, plan.md names a test file per logic-bearing module, and quickstart.md's development loop is
`python -m unittest discover -s tests`. Test tasks are therefore ordered **before** the implementation they cover.

**Organization**: Grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `[US1]`–`[US4]`, mapping to spec.md user stories
- Every task names an exact file path

## Path Conventions

The **repository root is the plugin package** (plan.md → Structure Decision). Paths below are relative to
`<TodayImage>/`. There is no `src/` directory: `tdi/` holds the logic, `tests/` the suite.
Installation into `gsuid_core/plugins/TodayImage` is a symlink step, not a build step.

**Module purity rule** (research R9): modules marked **PURE** must import **only the standard library** — no
`gsuid_core` import, directly or transitively. This is what lets their tests run with GsCore absent. Any task that
adds a `gsuid_core` import to a PURE module is a defect.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeleton and the test harness every later phase relies on

- [X] T001 Create the package skeleton: empty `tdi/__init__.py`, `tests/__init__.py`, and a placeholder `__init__.py` at the repo root (contents land in T020)
- [X] T002 [P] Create `README.md` covering install-by-symlink, the `今日<类型>` concept, and the category-folder layout from `contracts/storage.md`
- [X] T003 [P] Create `.gitignore` for `__pycache__/`, `*.pyc`, `.DS_Store`
- [X] T004 [P] Create `tests/_loader.py` exposing `load_pure_module(name)` that loads a `tdi/*.py` file via `importlib.util.spec_from_file_location`, so pure-module tests never import the package (and so never pull in `gsuid_core`)
- [X] T005 [P] Create `help.json` with the command metadata from `contracts/commands.md` (name, desc, eg, need_admin per command), shaped like TodayWaifu's `help.json` so an image-rendered help can be added later without restructuring

**Note on `ICON.png`**: operator-supplied binary, not a code task. `tdi/help.py` (T054) must call `register_help`
inside `try/except` so a missing icon only logs.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Configuration, the pure core, the SV registry, and command binding — every user story needs these

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Configuration

- [X] T006 Implement `CONFIG_DEFAULT` in `config_default.py` with all 13 keys, types and defaults from `contracts/config.md` (`GsDivider`/`GsBoolConfig`/`GsStrConfig`/`GsIntConfig`/`GsListStrConfig`)
- [X] T007 Implement `today_image_config.py`: `StringConfig('TodayImage', get_res_path('TodayImage') / 'config.json', CONFIG_DEFAULT)` plus the explicit `TodayImageConfig.plugin_name = 'TodayImage'` assignment required for symlink installs (research R10) — depends on T006

### Tests for the pure core (write first, confirm they FAIL)

- [X] T008 [P] Write `tests/test_file_cache.py`: mtime/size cache key invalidates on file change, LRU evicts by entry count **and** by total bytes, `clear_file_caches()` resets both counters
- [X] T009 [P] Write `tests/test_gallery.py`: recursive discovery (V-IMG-3), extension filter case-folded (V-IMG-1), dot-prefixed files and dirs skipped (V-CAT-1/V-IMG-2), resolved-path de-duplication (V-IMG-4), stable case-folded ordering, missing root created and returns empty, `image_short_id` is 8 lowercase hex from the **file name** (V-IMG-5)
- [X] T010 [P] Write `tests/test_category_registry.py`: overrides applied, `enabled=False` yields no commands (V-CAT-6), aliases expand to extra commands, case/whitespace-equal folder names conflict with the stable-sort winner kept (V-CAT-2), alias colliding with another category is dropped and reported (V-CAT-4), empty category still registers (V-CAT-3), malformed `categories.json` degrades to defaults (V-OVR-2), unknown keys preserved on rewrite (V-OVR-3), entries for absent folders retained (V-OVR-1)
- [X] T011 [P] Write `tests/test_message_delivery.py`: `at` segments and their trailing newline stripped for `user_type == 'direct'`, group messages passed through untouched

### Pure core implementation

- [X] T012 [P] Implement **PURE** `tdi/file_cache.py`: `read_file_bytes_cached(path)` keyed on `(path, st_mtime_ns, st_size)`, bounded by both `MAX_ENTRIES` and `MAX_BYTES`, plus `clear_file_caches()` — makes T008 pass
- [X] T013 [P] Implement **PURE** `tdi/gallery.py`: `scan_category_directories(root, extensions)`, `find_category_directory(root, name)`, `image_short_id(path)` — makes T009 pass
- [X] T014 Implement **PURE** `tdi/category_registry.py`: `Category` dataclass and `resolve_categories(scan_rows, overrides, prefix)` applying V-CAT-1..V-CAT-4, returning resolved categories **and** a list of skip reasons for the reload reply; plus atomic `categories.json` read/write — makes T010 pass; depends on T013
- [X] T015 [P] Implement `tdi/message_delivery.py`: `safe_send(bot, message)` and `adapt_mentions_for_platform` — makes T011 pass. Port TodayWaifu's private-chat mention stripping but **not** its XWUID `BotHook` fallback (research R8)

### GsCore-facing foundation

- [X] T016 Implement `tdi/shared.py`: the four `SV` instances from `contracts/commands.md` at priorities 20/21/21/25, `Plugins('TodayImage', disable_force_prefix=True, allow_empty_prefix=True)`, `LOG_PREFIX = '[今日图片]'`, coercing config accessors (`_cfg_bool`/`_cfg_int`/`_cfg_str`) that fall back on malformed values rather than raising (V-CFG-1..V-CFG-5), image-root resolution, and the TTL-cached category scan — depends on T007, T012, T013, T014
- [X] T017 Write `tests/test_registry_binding.py` against a **stubbed** SV object (no GsCore import): commands added, stale commands removed, a keyword already owned by another service is skipped and reported (V-CAT-5), and re-registering the same keyword is idempotent
- [X] T018 Implement `tdi/registry_binding.py`: `register_categories(sv, categories)` calling `sv.on_fullmatch(kw, block=True)(handler)` at runtime, `unregister(sv, keywords)` doing the one framework-internal `del sv.TL['fullmatch'][kw]`, and `find_conflicts(keywords)` scanning `gsuid_core.sv.SL.lst` — makes T017 pass; depends on T016
- [X] T019 Write `tests/test_gscore_compat.py`: assert `SV.TL` is `dict[str, dict[str, Trigger]]`, `SV.on_fullmatch` is a decorator factory, and `SL.lst` maps names to SVs — wrapped in `unittest.skipUnless(gsuid_core importable)`. This is the tripwire for a GsCore upgrade breaking T018
- [X] T020 Implement the root `__init__.py`: `Plugins('TodayImage', ...)` declaration followed by `from .tdi import shared`. Later phases append imports in the fixed order `shared → help → manage → daily` (plan.md); each such edit touches this one file, so those tasks are never `[P]` with each other

**Checkpoint**: Foundation ready — `python -m unittest discover -s tests` passes with GsCore absent, and the plugin
imports cleanly inside GsCore while registering no category commands yet.

---

## Phase 3: User Story 1 - Daily draw from a category (Priority: P1) 🎯 MVP

**Goal**: `今日黑丝` returns one image from the `黑丝` folder, identical on repeat within the same day and chat.

**Independent Test**: Drop two images in a `黑丝` folder, restart GsCore, send `今日黑丝` twice — same image both
times; roll `daily_records.json`'s `date` back a day and send again — a new draw. (quickstart Scenario 1.)

### Tests for User Story 1 (write first, confirm they FAIL)

- [X] T021 [P] [US1] Write `tests/test_daily_store.py`: record key format `{chat_key}|{user_key}|{category}` split on the **first two** separators so a category name containing `|` still parses, stale-date records dropped on write (V-REC-2/S-2), atomic write leaves no `.tmp` behind (S-3), malformed JSON degrades to empty (S-4)
- [X] T022 [P] [US1] Write `tests/test_daily_draw.py`: the seed `'{date}:{user_key}:{chat_key}:{category}'` is stable across calls and differs across user/chat/category (FR-008), a record whose image no longer exists triggers a re-draw and re-persist (V-REC-3), a zero-image category writes **no** record (V-REC-5), and two concurrent first draws persist exactly one record with both callers seeing it (V-REC-4/FR-010)

### Implementation for User Story 1

- [X] T023 [US1] Implement **PURE** `tdi/daily_store.py`: load/save/prune of `daily_records.json` per `contracts/storage.md`, atomic write via `mkstemp` + `fsync` + `os.replace` — makes T021 pass
- [X] T024 [US1] Implement the draw flow in `tdi/daily.py`: capture today's date **once** for both seed and record (V-REC-6), read the store, fall through to a seeded `random.Random(...).choice(...)`, then re-read and write under a per-`(chat_key, category)` `asyncio.Lock` yielding to a concurrent winner — makes T022 pass; depends on T023
- [X] T025 [US1] Implement the category-command handler in `tdi/daily.py`: resolve the invoked keyword to its category, honour the master switch, and send via `MessageSegment.image(bytes)` from the mtime cache with the optional at-mention and the resolved caption (`{类型}` substituted, per-category override winning) — contracts/commands.md §1
- [X] T026 [US1] Wire import-time registration in `tdi/daily.py`: scan the image root, resolve categories, and call `registry_binding.register_categories(...)` so category commands exist on startup
- [X] T027 [US1] Implement the US1 failure replies in `tdi/daily.py`: empty/missing category returns the `【<类型>】还没有图片…` notice and writes no record; master switch off registers nothing (V-CFG-1)
- [X] T028 [US1] Append `from .tdi import daily` to the root `__init__.py` (import order `shared → daily` for now) — same file as T020, not `[P]`

**Checkpoint**: MVP. `今日黑丝` works end to end and is stable for the day; adding a category still needs a restart.

---

## Phase 4: User Story 2 - Operator defines and customises categories (Priority: P1)

**Goal**: A new folder becomes a live `今日<类型>` command via `重载图片类型`, with no GsCore restart; categories can
be disabled, aliased, re-captioned, and the prefix changed.

**Independent Test**: Create a `白丝` folder, confirm `今日白丝` is dead, send `重载图片类型`, confirm it answers —
with GsCore never restarted. (quickstart Scenarios 2 and 3.)

### Tests for User Story 2 (write first, confirm they FAIL)

- [X] T029 [P] [US2] Extend `tests/test_category_registry.py` with prefix-change resolution: changing the prefix re-resolves every command name, and an empty prefix falls back to `今日` rather than registering bare category names (V-CFG-3)
- [X] T030 [P] [US2] Extend `tests/test_registry_binding.py` with a reload diff: given a previous and a current keyword set, the binding reports added, removed and skipped keywords, and the live table ends up holding exactly the current set

### Implementation for User Story 2

- [X] T031 [US2] Implement `reload_categories()` in `tdi/registry_binding.py`: re-scan, re-resolve, diff against the live keyword set, unregister the removed, register the added, and return an added/removed/skipped report — depends on T030
- [X] T032 [US2] Implement the `重载图片类型` / `刷新图片类型` command in `tdi/manage.py` per contracts/commands.md §5, invalidating the scan cache first and replying with the registered count, the added and removed commands, and **every** skipped category with its reason — a silent skip is the defect this command exists to prevent (V-CAT-5)
- [X] T033 [US2] Wire per-category customisation through the draw path in `tdi/daily.py` and `tdi/category_registry.py`: `enabled=False` unregisters, aliases resolve to the same category, and a per-category `caption` overrides the global template — verify against T029's resolution rules
- [X] T034 [US2] Make prefix and image-root changes take effect on reload in `tdi/shared.py` (root resolution) and `tdi/manage.py` (reply wording), so both settings are documented as reload-gated (V-CFG-4)
- [X] T035 [US2] Append `from .tdi import manage` to the root `__init__.py` **before** the `daily` import (final order `shared → help → manage → daily`) — same file as T020/T028, not `[P]`

**Checkpoint**: Categories are fully operator-controlled and restart-free. US1 and US2 together satisfy SC-001 and
SC-004.

---

## Phase 5: User Story 3 - Manage images from chat (Priority: P2)

**Goal**: An authorised operator uploads, lists and deletes category images from chat.

**Independent Test**: From a master account, upload an image to `黑丝`, list the category and see its 8-hex ID,
delete by that ID, confirm the file is gone. (quickstart Scenario 4.)

### Tests for User Story 3 (write first, confirm they FAIL)

- [X] T036 [P] [US3] Write `tests/test_image_input.py`: refs collected from `content` / `image_list` / `image` and de-duplicated, `data:image/`, `base64://`, `link://`, `http(s)://` and plain-path sources decoded, format taken from **magic bytes** with the extension only as fallback (V-IMG-6), oversize and non-image content rejected (V-IMG-7)
- [X] T037 [P] [US3] Write `tests/test_upload_access.py`: a master is authorised without a whitelist entry, a whitelisted ID is authorised, everyone else is refused, and the whitelist parses from both a list and a comma/space-separated string
- [X] T038 [P] [US3] Extend `tests/test_gallery.py` with short-ID resolution: an ID matching exactly one file resolves, an ID matching several returns the ambiguity rather than an arbitrary pick (V-IMG-5), and an unmatched ID resolves to nothing

### Implementation for User Story 3

- [X] T039 [P] [US3] Implement **PURE** `tdi/image_input.py`: `collect_image_refs`, `detect_image_suffix`, `read_image_bytes(source, max_bytes)`, porting TodayWaifu's adapter matrix handling (research R11) — makes T036 pass
- [X] T040 [P] [US3] Implement the authorisation helper in `tdi/shared.py`: master (`core_config.get_config('masters')`) **or** `TodayImageUploadWhitelist` — makes T037 pass
- [X] T041 [US3] Implement short-ID resolution in `tdi/gallery.py` returning all matches so callers can detect ambiguity — makes T038 pass
- [X] T042 [US3] Implement `上传图片 <类型>` in `tdi/manage.py` per contracts/commands.md §2: authorisation gate, existing-category requirement (never creates a folder), `img_<epoch_ms>_<index><suffix>` naming with a collision counter, scan-cache invalidation, and a reply listing saved IDs plus a failure count
- [X] T043 [US3] Implement `查看图片 [<类型>]` in `tdi/manage.py` per contracts/commands.md §3 as a **single** `on_command` — the bare form (`ev.text` empty) gives the category overview, the argument form lists images, switching to a forwarded `MessageSegment.node` past `TodayImageListForwardThreshold`
- [X] T044 [US3] Implement `删除图片 <类型> [图片ID]` in `tdi/manage.py` per contracts/commands.md §4: single-ID delete, the ambiguity refusal from T041, delete-all with no ID, malformed-ID hint, and scan-cache invalidation — never removes the category folder itself
- [X] T045 [US3] Add a regression case to `tests/test_daily_draw.py` covering delete-then-draw: after T044 removes today's pinned file, `tdi/daily.py` re-draws and re-pins (V-REC-3) rather than erroring

**Checkpoint**: US1, US2 and US3 all work independently.

---

## Phase 6: User Story 4 - Discoverability and help (Priority: P3)

**Goal**: `今日图片帮助` lists the live category commands and the management commands.

**Independent Test**: With two categories present, send the help command and see both. (quickstart Scenario 4/§6.)

- [X] T046 [P] [US4] Write `tests/test_help_text.py` against a pure text builder: the rendered help lists every live category command and every management command, and with zero categories explains how to create a folder instead of printing an empty list (US4 AS2)
- [X] T047 [US4] Implement the pure help-text builder plus the `今日图片帮助` / `图片帮助` command in `tdi/help.py` per contracts/commands.md §6 — makes T046 pass
- [X] T048 [US4] Call `register_help('TodayImage', '今日图片帮助', icon)` in `tdi/help.py` inside `try/except`, so a missing `ICON.png` or a help-registry change only logs
- [X] T049 [US4] Append `from .tdi import help` to the root `__init__.py` immediately after `shared`, completing the required order `shared → help → manage → daily` — same file as T020/T028/T035, not `[P]`

**Checkpoint**: All four user stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T050 [P] Audit every handler for the SC-005 guarantee: no path raises out of a handler, and every failure replies with the exact plain text in `contracts/commands.md`
- [X] T051 [P] Audit logging across every module in `tdi/`: each message carries `LOG_PREFIX` from `tdi/shared.py`, with folder scans and reload diffs at `debug`/`info` and degraded-config paths at `warning`
- [X] T052 Verify the module purity rule holds: assert in `tests/test_gscore_compat.py` that importing each PURE module leaves `gsuid_core` out of `sys.modules`
- [X] T053 [P] Update `README.md` with the finished command table, the console settings from `contracts/config.md`, and the `categories.json` example
- [X] T054 Run Scenario 6 (coexistence) from `specs/001-daily-image-categories/quickstart.md`: confirm TodayWaifu's `今日老婆`/`今日萝莉` are unaffected, and that a folder named `老婆` is reported as skipped rather than silently dropped
- [X] T055 Run Scenario 7 (performance) from `specs/001-daily-image-categories/quickstart.md`: 5,000 images in one category, warm-cache draw under 1 s with no re-scan between calls (SC-003)
- [ ] T056 Run the full validation checklist in `specs/001-daily-image-categories/quickstart.md` and record the results in that file

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup — **blocks every user story**
- **US1 (Phase 3)**: depends on Foundational. No dependency on US2–US4
- **US2 (Phase 4)**: depends on Foundational. Independently testable, but only meaningful once US1's draw exists — implement after US1
- **US3 (Phase 5)**: depends on Foundational. Independent of US1/US2 except for T045's verification
- **US4 (Phase 6)**: depends on Foundational. Lists whatever commands exist, so it is genuinely independent
- **Polish (Phase 7)**: depends on all desired stories

### Shared-file coordination (breaks naive parallelism)

Two files are touched by more than one phase. Tasks against them are **never** `[P]` with each other:

| File | Tasks | Rule |
|---|---|---|
| `__init__.py` | T020 → T028 → T035 → T049 | Sequential edits; final import order must be `shared → help → manage → daily`. `help` before `manage` keeps `今日图片帮助` from being claimed by an `on_command` prefix trigger (plan.md) |
| `tdi/manage.py` | T032 (US2), T042/T043/T044 (US3) | US2's reload lands first; US3 appends its three commands. Same file across two stories — sequence, don't parallelise |
| `tdi/gallery.py` | T013 (foundational), T041 (US3) | T041 extends the module; it must not alter T013's signatures |
| `tdi/shared.py` | T016 (foundational), T040 (US3) | T040 appends the auth helper only |

### Within each user story

- Tests are written **first** and must fail before the implementation task begins
- Pure modules before the GsCore-facing modules that consume them
- Handlers before the `__init__.py` import that activates them

### Parallel Opportunities

- **Setup**: T002, T003, T004, T005 all parallel
- **Foundational tests**: T008, T009, T010, T011 all parallel
- **Foundational implementation**: T012, T013, T015 parallel; T014 waits on T013; T016 waits on T007/T012/T013/T014
- **US1**: T021 and T022 parallel
- **US3**: T036, T037, T038 parallel; then T039 and T040 parallel
- **Cross-story**: once Phase 2 is done, US1, US3 and US4 can be built by different people at once; US2 wants US1 in place first

---

## Parallel Example: Phase 2 Foundational

```bash
# Write the failing pure-core tests together:
Task: "Write tests/test_file_cache.py"
Task: "Write tests/test_gallery.py"
Task: "Write tests/test_category_registry.py"
Task: "Write tests/test_message_delivery.py"

# Then the implementations that turn them green:
Task: "Implement PURE tdi/file_cache.py"
Task: "Implement PURE tdi/gallery.py"
Task: "Implement tdi/message_delivery.py"
# (tdi/category_registry.py follows tdi/gallery.py; tdi/shared.py follows all of them)
```

## Parallel Example: User Story 3

```bash
# Failing tests together:
Task: "Write tests/test_image_input.py"
Task: "Write tests/test_upload_access.py"
Task: "Extend tests/test_gallery.py with short-ID resolution"

# Then the two independent implementations:
Task: "Implement PURE tdi/image_input.py"
Task: "Implement the authorisation helper in tdi/shared.py"
# (the three manage.py commands are one file — sequential)
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1
4. **STOP and VALIDATE**: quickstart Scenario 1 — repeat draws identical, new day re-draws, users independent
5. Shippable: `今日黑丝` works. Adding a category still needs a GsCore restart, which US2 removes

### Incremental Delivery

1. Setup + Foundational → suite green with GsCore absent, plugin imports cleanly
2. **+ US1** → daily draw works → **MVP**
3. **+ US2** → restart-free categories, aliases, captions, prefix → satisfies SC-001/SC-004
4. **+ US3** → chat-based image management
5. **+ US4** → help
6. **+ Polish** → coexistence, performance and the full quickstart checklist

### Parallel Team Strategy

Everyone lands Phase 2 together — it is the widest blocking phase and its purity rule is the thing most easily
broken by an inattentive edit. After that: Dev A takes US1 then US2 (they share the draw path and `manage.py`),
Dev B takes US3, Dev C takes US4. The shared-file table above is the coordination contract.

---

## Notes

- `[P]` = different files, no dependency on an incomplete task
- Verify each test **fails** before writing its implementation
- The PURE modules (`gallery`, `category_registry`, `daily_store`, `image_input`, `file_cache`) must never import
  `gsuid_core` — T052 enforces it
- `tdi/registry_binding.py` holds the plugin's **only** framework-internal reach
  (`del sv.TL['fullmatch'][kw]`); keep it in that one function so T019 stays a meaningful tripwire
- Commit after each task or logical group; stop at any checkpoint to validate a story independently
