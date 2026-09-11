# Implementation Plan: TodayImage — 今日<类型> 本地图库每日抽图插件

**Branch**: `001-daily-image-categories` | **Date**: 2026-09-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-daily-image-categories/spec.md`

## Summary

Build **TodayImage**, a standalone GsCore (早柚核心) plugin that generalises TodayWaifu's 今日萝莉 command across an
arbitrary set of operator-defined image categories. Each sub-folder of a local image root becomes a category, and
each category gets a `今日<类型>` command — `今日黑丝`, `今日白丝`, `今日制服`. A user's draw is fixed for the day
within a chat, exactly as 今日萝莉 behaves.

The technical approach, established in [research.md](./research.md):

- **Categories come from the filesystem.** A cached recursive scan of the image root yields the category set;
  a `重载图片类型` command re-scans and re-registers commands live, with no GsCore restart. This is possible
  because `gsuid_core/handler.py` re-reads every `SV.TL` on every inbound message, so `SV.on_fullmatch(...)` called
  at runtime takes effect on the next message.
- **Draws are seeded, then pinned.** `random.Random('{date}:{user}:{chat}:{category}')` picks the image — the same
  scheme 今日萝莉 uses — and the result is persisted so a mid-day upload or delete cannot reshuffle anyone's draw.
- **Everything stays out of TodayWaifu's way.** Separate SV names, separate `data/TodayImage/` tree, SV priority 20+
  so an incumbent plugin wins any keyword collision, and proactive collision detection against `SL.lst` that reports
  the conflict instead of silently shadowing.
- **Logic is testable without a bot.** Gallery scanning, category resolution, the daily-record store, image decoding
  and caching are pure modules with no `gsuid_core` import, loaded directly by stdlib `unittest`.

## Technical Context

**Language/Version**: Python ≥ 3.11 — pinned by GsCore's `requires-python = ">=3.11,<4.0"`. `from __future__ import
annotations` in every module so PEP 604 unions are usable in runtime-evaluated positions.

**Primary Dependencies**: `gsuid_core` only (supplied by the host installation). **No new third-party
dependencies** — no Pillow, no `watchdog`, no `httpx`. Consequently the plugin ships no `pyproject.toml`
dependency block for GsCore's `check_pyproject()` to act on.

**Storage**: JSON files under `get_res_path('TodayImage')` → `gsuid_core/data/TodayImage/`:
`config.json` (console-managed settings), `categories.json` (per-category overrides), `daily_records.json`
(today's draws, pruned on write). Images live under a configurable root defaulting to
`gsuid_core/data/TodayImage/` itself — the same directory as the JSON state, since categories are directories and
state is files. No database.

**Testing**: stdlib `unittest`. Pure modules are loaded with `importlib.util.spec_from_file_location`, so the suite
runs green with GsCore absent. One compatibility test pins the framework internals the reload path depends on and
skips cleanly when `gsuid_core` cannot be imported.

**Target Platform**: Any host running GsCore — Linux/macOS/Windows, Python 3.11+.

**Project Type**: Single Python package that *is* a GsCore plugin; the repository root is the package root, mirroring
TodayWaifu's layout.

**Performance Goals**: Warm-cache draw replies in < 1 s for a category of 5,000 images (SC-003). No command performs
a full directory walk — scans are TTL-cached (default 300 s) and explicitly invalidated on mutation. Image bytes are
served from an mtime-keyed LRU bounded by both entry count and total bytes.

**Constraints**:
- Must coexist with TodayWaifu in one GsCore instance with zero behaviour change to either (FR-023, SC-006).
- Adding a category must require no code edit, no edit inside the plugin source tree, and no restart (SC-001, SC-004).
- Every failure path must produce an actionable plain-text reply, never a silent drop or a stack trace (SC-005).
- Exactly one framework-internal reach is permitted (`del sv.TL['fullmatch'][key]` for trigger removal); it is
  confined to one function and pinned by a compatibility test.

**Scale/Scope**: Tens of categories, thousands of images per category, hundreds of daily users per bot. Roughly
1,200–1,500 lines of implementation across 11 modules, plus tests.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitution status**: `.specify/memory/constitution.md` is the **unmodified Spec Kit template** — every principle
is still a `[PRINCIPLE_N_NAME]` / `[PRINCIPLE_N_DESCRIPTION]` placeholder. There are therefore **no ratified project
principles to gate against**, and no gate can be said to pass or fail on their authority.

Rather than treat that as a free pass, this plan is checked against the template's own worked examples, which
represent the project's default expectations until a real constitution is ratified:

| Template example principle | Assessment |
|---|---|
| **Library-First** — self-contained, independently testable, documented | **Pass.** The substance of the plugin lives in pure modules (`tdi/gallery.py`, `category_registry.py`, `daily_store.py`, `image_input.py`, `file_cache.py`) that import nothing from GsCore and are unit-testable in isolation. GsCore-facing modules are thin adapters over them. |
| **CLI Interface** — text in/out | **Not applicable, adapted.** A chat bot plugin has no CLI; the equivalent contract is the command surface, specified in [contracts/commands.md](./contracts/commands.md) with exact trigger types, arguments, authorisation and reply text. |
| **Test-First (NON-NEGOTIABLE)** | **Pass by construction.** Every logic-bearing module in the source layout below has a named test file; the module boundary was chosen to make that possible without mocking GsCore. The two exceptions are deliberate: `tdi/help.py` is presentation-only (covered by quickstart Scenario 4) and `tdi/__init__.py` is empty. Enforcement belongs to `/speckit-tasks`, which must order each test before its implementation. |
| **Integration Testing** — new library contract tests, contract changes | **Pass.** `tests/test_gscore_compat.py` is exactly a contract test against the framework surface the reload path depends on (`SV.TL` shape, `SV.on_fullmatch` as a decorator factory, `SL.lst`), and it is the tripwire for a GsCore upgrade breaking this plugin. |
| **Observability / Simplicity (YAGNI)** | **Pass.** Every log line carries the `[今日图片]` prefix, following TodayWaifu's convention. Simplicity drove the concrete rejections recorded in research.md: no database (R6), no `watchdog` (R7), no Pillow-rendered help (R12), no ported XWUID `BotHook` workaround (R8), and 抢/送/离婚 excluded from scope. |

**Gate result: PASS** — no violations to justify, so the Complexity Tracking table below stays empty.

**Decision (2026-09-08, operator)**: the constitution stays as the unratified template for this feature. Gating
therefore rests on the template-example assessment above, which is deliberate and settled — not an open action item.
Ratifying real principles via `/speckit-constitution` remains available for a later feature; it is not a
prerequisite for implementing this one.

## Project Structure

### Documentation (this feature)

```text
specs/001-daily-image-categories/
├── plan.md              # This file (/speckit-plan command output)
├── spec.md              # Feature specification
├── research.md          # Phase 0 output — R1..R12 decisions
├── data-model.md        # Phase 1 output — entities, files, state
├── quickstart.md        # Phase 1 output — install + validation walkthrough
├── contracts/
│   ├── commands.md      # Chat command surface (the plugin's public interface)
│   ├── config.md        # Console configuration keys + categories.json schema
│   └── storage.md       # On-disk JSON schemas + image-root layout
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

The repository root is the plugin package: GsCore's loader treats a directory under `gsuid_core/plugins/` that
contains `__init__.py` as one plugin package (`gsuid_core/server.py:428-440`). Install by symlinking or cloning this
repo to `gsuid_core/plugins/TodayImage`.

```text
TodayImage/                      # = gsuid_core/plugins/TodayImage
├── __init__.py                  # Plugins('TodayImage') + ordered module imports
├── config_default.py            # CONFIG_DEFAULT: GsStrConfig/GsBoolConfig/GsIntConfig/GsListStrConfig/GsDivider
├── today_image_config.py        # StringConfig instance; explicit plugin_name (symlink-safe)
├── help.json                    # Command metadata (text help today; image help later)
├── ICON.png                     # register_help icon
├── README.md                    # Operator-facing docs
├── tdi/
│   ├── __init__.py
│   ├── shared.py                # SV instances, config accessors, constants, common imports
│   ├── gallery.py               # PURE  scan_category_directories / find_category_directory / image_short_id
│   ├── category_registry.py     # PURE  folders + overrides -> Category list; alias expansion; collision inputs
│   ├── daily_store.py           # PURE  daily_records.json read/write/prune (atomic)
│   ├── image_input.py           # PURE  adapter image refs -> validated bytes + suffix
│   ├── file_cache.py            # PURE  mtime-keyed bounded LRU byte cache
│   ├── message_delivery.py      # safe_send; strip at-mentions in direct chats
│   ├── registry_binding.py      # GsCore-facing: register/unregister dynamic triggers, collision detection
│   ├── daily.py                 # Draw flow: seeded pick -> pin under lock -> send
│   ├── manage.py                # 上传 / 查看 / 删除 / 重载 commands
│   └── help.py                  # Text help command + register_help
└── tests/
    ├── test_gallery.py
    ├── test_category_registry.py
    ├── test_daily_store.py
    ├── test_image_input.py
    ├── test_file_cache.py
    ├── test_daily_draw.py       # seeded determinism, re-draw on missing file, concurrency
    ├── test_message_delivery.py # at-mention stripping in direct chats
    ├── test_registry_binding.py # add/remove/collision, with a stubbed SV
    └── test_gscore_compat.py    # framework contract; skipped when gsuid_core is absent
```

**Structure Decision**: Single-package plugin, repo root = package root, mirroring TodayWaifu. The `tdi/` subpackage
holds all logic so `__init__.py` stays a declaration plus an ordered import list — the ordering matters because
GsCore registers triggers as a side effect of import, and `shared` must initialise the SVs before any module
decorates against them.

**Development vs. install location (2026-09-08, operator)**: the plugin is developed **in this repository**
(`<TodayImage>`) and installed into GsCore separately, by symlinking or cloning the repo to
`gsuid_core/plugins/TodayImage`. Two consequences for implementation:

- The test suite must run from this repository with **no GsCore on `sys.path`** — which is what the pure-module
  split and the `importlib`-based test loader (research R9) are for. `python -m unittest discover -s tests` is the
  development loop; a connected bot is only needed for the quickstart scenarios.
- Installing via symlink is the expected path, so the plugin must survive `Path.resolve()` following the link. That
  is why `today_image_config.py` sets `plugin_name` explicitly (research R10) — without it the web console fails to
  associate the settings with this plugin.

The **pure / GsCore-facing split** is the load-bearing decision in this layout. The five modules marked `PURE` import
only the standard library; they are what the `unittest` suite exercises directly via `importlib`. The four
GsCore-facing modules are deliberately thin, so the code that cannot be unit-tested without a running bot is the code
that contains the least logic.

**Import order in `__init__.py`** (side-effectful, therefore fixed):

```text
shared  →  help  →  manage  →  daily
```

`help` precedes `manage` and `daily` so that `今日图片帮助` is registered before any `on_command` prefix trigger that
could otherwise claim it; this is the same hazard TodayWaifu documents in its own `__init__.py`.

## Design Highlights

Full detail lives in [research.md](./research.md); the four decisions that shape the code:

1. **Dynamic triggers via the public decorator (R3).** `registry_binding.register_categories()` calls
   `sv.on_fullmatch(keyword, block=True)(handler)` at runtime, reusing the framework's own prefix expansion.
   Removal is the single internal reach — `del sv.TL['fullmatch'][keyword]` — isolated in one function and pinned by
   `tests/test_gscore_compat.py`.

2. **Seeded draw pinned by a persisted record (R5, R6).** The seed reproduces 今日萝莉's determinism for free; the
   record defends FR-006 against the mid-day gallery edits that US3 makes possible. The read-modify-write is held
   under a per-(chat, category) `asyncio.Lock`, so the FR-010 race resolves the way TodayWaifu's
   `_send_loli_image` resolves it: the loser re-reads under the lock and returns the winner's image.

3. **Coexistence is designed in, not hoped for (R2, R4).** `on_fullmatch` rather than a `今日` prefix catch-all
   (a `block=True` prefix trigger would swallow TodayWaifu's 今日老婆); SV priority 20+ so incumbents win;
   collision detection against `SL.lst` at registration so a shadowed category is reported, not silently dead.

4. **Caching is a correctness requirement, not an optimisation (R7).** TodayWaifu's source records that an uncached
   `rglob` per command drags the core down at the midnight peak. The TTL scan cache plus the mtime-keyed byte cache
   are what make SC-003 reachable.

## Constitution Re-Check (post-design)

Re-evaluated after Phase 1. **No change: PASS.** The design added no database, no third-party dependency, and no
service boundary. The pure/GsCore-facing split strengthens the Library-First and Test-First positions rather than
weakening them, and the one framework-internal dependency introduced by R3 is bounded to a single function and
covered by a contract test. Complexity Tracking remains empty.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Table intentionally empty.

## Phase Status

- [x] Phase 0 — Research complete → [research.md](./research.md)
- [x] Phase 1 — Design complete → [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)
- [ ] Phase 2 — Task breakdown (run `/speckit-tasks`)
