# Implementation Plan: 动态类型解析、隐藏类型清单、屏蔽 TodayWaifu 命令

**Branch**: `002-dynamic-category-lookup` | **Date**: 2026-09-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-dynamic-category-lookup/spec.md`

## Summary

Replace feature 001's per-folder trigger registration with **one dynamic `今日` prefix trigger**. The suffix is
resolved against `data/TodayImage/`'s sub-folders at request time, so a new folder works with no reload and no
restart. Every public negative outcome — unknown name, blocked name, empty folder, bad input — produces **silence**,
so the folder list and command surface cannot be probed. A blocklist, checked before any filesystem access, ensures
TodayWaifu's `今日老婆` / `今日萝莉` / `今日战双老婆` and friends are never answered by this plugin.

Three findings from [research.md](./research.md) shape the work:

- **`block=False` is the load-bearing detail** (R2). Feature 001 rejected a `今日` catch-all, correctly — but it
  evaluated the *blocking* version. Measured on this host, TodayWaifu's `今日` triggers sit at priority 0–10 and
  ours at 25, so a blocking catch-all would terminate the dispatch loop ahead of any plugin at a higher number and
  silently kill their `今日X`. Non-blocking keeps ordering intact in both directions.
- **The blocklist is not redundant with priority ordering** (R3). Ordering only helps while TodayWaifu is loaded.
  The blocklist covers TodayWaifu being disabled, a folder deliberately named `老婆`, and priority changes.
- **Silence reverses feature 001's SC-005 for public paths only** (R4). That conflict is deliberate and scoped:
  master-only commands keep full diagnostics and enumeration.

**Separately**: the current "no reply" symptom is **not** a plugin bug (R0). Logs show the trigger matching, the
handler running, and GsCore handing the message to the adapter. The loss is downstream. This plan does not fix that
and must not be read as doing so — but if it is unresolved, this feature will also appear to do nothing.

## Technical Context

**Language/Version**: Python ≥ 3.11, standard library only — unchanged from feature 001.

**Primary Dependencies**: `gsuid_core` only. No new third-party dependencies.

**Storage**: Unchanged. `config.json`, `categories.json`, `daily_records.json` under `data/TodayImage/`, with
category folders as siblings.

**Testing**: stdlib `unittest`, pure modules loaded via `importlib`. `tests/test_registry_binding.py` is deleted
with its module; new suites cover suffix resolution, blocklist precedence, and non-disclosure.

**Target Platform**: Any GsCore host.

**Project Type**: Single Python package that is a GsCore plugin; repo root is the package root.

**Performance Goals**: A warm-cache resolution of an unknown suffix is a dict lookup with **zero** filesystem access
(SC-106). This matters more than in 001: the trigger now fires on every message starting with `今日`, so an unknown
suffix is the common case, not the rare one.

**Constraints**:
- Must not suppress any other plugin's `今日X` (FR-106, SC-105) — this is what forces `block=False`.
- Must not regress feature 001's daily guarantees: same image on repeat, no same-day collision within a chat,
  Beijing-midnight reset (FR-105, SC-107).
- A blocked name must never reach the filesystem (FR-118).
- The suffix must never be joined onto a path (FR-104).

**Scale/Scope**: Net **reduction** — `registry_binding.py` and its test suite are deleted. Roughly +250 / −350 lines.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitution status**: `.specify/memory/constitution.md` remains the unratified Spec Kit template, by the
operator's decision recorded in feature 001's plan. Gating therefore rests on the template's worked examples, as
before — a settled position, not an open action item.

| Template example principle | Assessment |
|---|---|
| **Library-First** | **Pass.** Suffix resolution, the blocklist rule, and help rendering all land in PURE modules with no `gsuid_core` import. The dynamic handler stays thin. |
| **CLI Interface** (adapted: command surface) | **Pass.** The surface is re-specified in [contracts/commands.md](./contracts/commands.md), including the silence contract — the deliberate reversal of 001's SC-005 is written down rather than left implicit. |
| **Test-First** | **Pass by construction.** Every new rule has a named test file; ordering is enforced by `/speckit-tasks`. |
| **Integration Testing** | **Pass, and cheaper than before.** Deleting `registry_binding` removes the plugin's only framework-internal reach (`del sv.TL[...]`), so the compat test it required goes too. The coexistence test is **strengthened** into an assertion that no TodayWaifu `今日` command is answered by us. |
| **Observability / Simplicity** | **Pass, with a caveat.** Simplicity improves: one trigger replaces N, and a whole module is deleted. Observability *degrades by design* — silence on public failures means chat no longer explains anything. Mitigation: every silent path logs at `debug` with the reason, so the operator can still diagnose from `data/logs/`. This is recorded as a tradeoff, not overlooked. |

**Gate result: PASS** — no violations requiring justification; Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/002-dynamic-category-lookup/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # R0..R6 decisions
├── data-model.md        # Resolution index, blocklist, disclosure levels
├── quickstart.md        # Validation scenarios
├── contracts/
│   ├── commands.md      # Revised command surface + silence contract
│   └── config.md        # New/changed console keys
└── tasks.md             # /speckit-tasks output — not created here
```

### Source Code (repository root)

```text
TodayImage/
├── __init__.py                  # import order unchanged: shared → help → manage → daily
├── config_default.py            # + TodayImageBlocklist
├── today_image_config.py        # unchanged
├── tdi/
│   ├── shared.py                # + category_index(), blocklist(); - registry wiring
│   ├── gallery.py        PURE   # + build_category_index()
│   ├── blocklist.py      PURE   # NEW: is_blocked() base-name matching
│   ├── category_registry.py PURE# retained for overrides; command resolution removed
│   ├── daily_store.py    PURE   # UNCHANGED
│   ├── image_input.py    PURE   # unchanged
│   ├── file_cache.py     PURE   # unchanged
│   ├── upload_access.py  PURE   # unchanged
│   ├── help_text.py      PURE   # rewritten: public vs master rendering
│   ├── message_delivery.py      # unchanged
│   ├── registry_binding.py      # DELETED
│   ├── daily.py                 # rewritten: single prefix handler
│   ├── manage.py                # reload demoted to cache invalidation
│   └── help.py                  # passes viewer permission to the renderer
└── tests/
    ├── test_category_index.py   # NEW: suffix resolution, case/space, traversal
    ├── test_blocklist.py        # NEW: defaults, prefix matching, precedence
    ├── test_help_text.py        # REWRITTEN: non-disclosure
    ├── test_registry_binding.py # DELETED
    ├── test_gscore_compat.py    # trimmed; coexistence assertion strengthened
    └── (all other 001 suites unchanged)
```

**Structure Decision**: Unchanged layout; the change is subtractive. The one new PURE module, `tdi/blocklist.py`,
exists because blocklist precedence is a rule worth testing in isolation — it must beat a real folder of the same
name (FR-115), and that is easy to regress silently.

`tdi/daily_store.py` is deliberately **untouched**. The daily guarantees are the part of 001 most likely to be
broken by accident during this rewrite, and leaving the module alone is the cheapest way to protect them; SC-107 is
verified by re-running its existing suites unmodified.

## Design Highlights

1. **One trigger, resolved late** (R1). `on_prefix(前缀, block=False)` puts the suffix in `ev.text`; a
   `casefold → folder` map built from the cached scan turns it into a folder. The bare prefix does not fire, per
   `_check_prefix`. A new folder is live within the cache TTL with no operator action.

2. **Dict lookup is the path-safety mechanism** (R5). The suffix is only ever a map key, never joined onto a path,
   so `..`, separators and absolute paths miss by construction — stronger than 001's directory-iteration guard.

3. **Blocklist before filesystem** (R3). Base names matched by equality-or-prefix, checked first, so the most-likely
   spam targets cost nothing and a folder named `老婆` cannot override the rule.

4. **Silence is uniform** (R4). Unknown, blocked, empty and malformed all produce the same observable: nothing.
   Anything less uniform reintroduces the oracle. Each path logs at `debug` so operators keep diagnosis.

## Constitution Re-Check (post-design)

Re-evaluated after Phase 1. **PASS, unchanged.** The design deletes a module and the framework-internal reach it
required; it adds one small PURE module. The single principled cost — reduced chat-level observability — is
deliberate, scoped to public output, and mitigated by debug logging.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Table intentionally empty.

## Phase Status

- [x] Phase 0 — Research complete → [research.md](./research.md)
- [x] Phase 1 — Design complete → [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)
- [ ] Phase 2 — Task breakdown (`/speckit-tasks`)
