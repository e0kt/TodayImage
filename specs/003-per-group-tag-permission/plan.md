# Implementation Plan: 分群标签授权

**Branch**: `003-per-group-tag-permission` | **Date**: 2026-09-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-per-group-tag-permission/spec.md`

## Summary

Add a **per-group allowlist of tags** on top of feature 002's dynamic resolution. In a group, `今日<类型>` works only
after a group admin has run `TodayImage允许<类型>` in that group. **Direct chats are not gated.** Groups are
deny-by-default, so one bot can serve a strict group and a permissive one.

Four decisions from [research.md](./research.md) shape the work:

- **No custom permission code** (R1). GsCore's `pm` ladder already encodes 群管理员=3 / 群主=2 / superuser=1 /
  master=0, and `_sv_authorized` rejects anyone above the SV's `pm` before our handler runs. Registering the
  commands on a `pm=3` SV *is* the gate. This bot's own logs contain real `user_pm` values of 0, 3 and 6, so the
  adapter genuinely supplies group-admin status.
- **The decision order is the contract** (R2): blocklist → direct-chat bypass → group gate → index → emptiness.
  The blocklist stays first so a group cannot authorise its way to `今日老婆`; the gate precedes the index because
  authorisation is about permission, not existence.
- **Deny-by-default is a breaking change** (R3) and is called out rather than buried: the group currently using
  `今日黑丝` stops working until an admin authorises it. That is the requested direction, but it needs to reach the
  operator as a release note, not as user complaints.
- **Permissions are never cached** (R7). A revoke must take effect when the admin says so, not after a TTL.

## Technical Context

**Language/Version**: Python ≥ 3.11, standard library only — unchanged.

**Primary Dependencies**: `gsuid_core` only.

**Storage**: New `data/TodayImage/group_permissions.json` alongside the existing files. Atomic write, fail-closed
read, per-group `asyncio.Lock`. No database.

**Testing**: stdlib `unittest`, pure modules via `importlib`. The permission store and the extended decision are
both pure and directly testable; the admin handlers stay thin.

**Target Platform**: Any GsCore host.

**Project Type**: Single Python package that is a GsCore plugin.

**Performance Goals**: The gate adds one small JSON read per group draw. Deliberately uncached (R7) — correctness of
a revoke outweighs the I/O, and the file holds one entry per group.

**Constraints**:
- Direct chats must be untouched (FR-204, SC-203) — the bypass precedes the gate, so a direct chat never consults
  group state.
- The blocklist must remain unreachable by group authorisation (FR-206).
- Unauthorised must stay indistinguishable from unknown/blocked/empty (FR-205, SC-206).
- Fail **closed**: a corrupt permissions file authorises nothing (FR-218).
- Feature 001's daily semantics must not regress; `tdi/daily_store.py` is untouched for the third feature running.

**Scale/Scope**: Roughly +300 lines across two new modules, one extended module, and their tests.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitution status**: still the unratified Spec Kit template, by the operator's standing decision from feature
001. Gating rests on the template's worked examples.

| Template example principle | Assessment |
|---|---|
| **Library-First** | **Pass.** The permission store and the extended decision are PURE modules with no `gsuid_core` import; the admin commands are a thin handler layer. |
| **CLI Interface** (adapted: command surface) | **Pass.** Three new commands specified in [contracts/commands.md](./contracts/commands.md), including exactly what an admin may be told and what remains undisclosed. |
| **Test-First** | **Pass by construction.** The gate, the deny-by-default behaviour, the direct-chat bypass and the blocklist precedence each get a named test before implementation. |
| **Integration Testing** | **Pass.** A contract test asserts the authorisation SV's `pm` is 3 — if a GsCore upgrade changed the ladder, an ordinary member could otherwise silently gain the ability to widen a group's content scope. That is the highest-consequence regression in this feature, so it is pinned rather than assumed. |
| **Observability / Simplicity** | **Pass, same tradeoff as 002.** Public silence is extended to unauthorised requests, so chat explains less; every gated path logs at `debug` with its reason, and admins get a diagnostic path through `TodayImage列表` (SC-207). No new dependency; no cache to invalidate. |

**Gate result: PASS** — no violations; Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/003-per-group-tag-permission/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # R1..R7 decisions
├── data-model.md        # GroupPermission, gate decision, normalisation
├── quickstart.md        # Validation scenarios
├── contracts/
│   ├── commands.md      # The three admin commands + the extended draw gate
│   ├── config.md        # TodayImageDefaultGroupTags
│   └── storage.md       # group_permissions.json schema
└── tasks.md             # /speckit-tasks output — not created here
```

### Source Code (repository root)

```text
TodayImage/
├── config_default.py            # + TodayImageDefaultGroupTags
├── tdi/
│   ├── group_permissions.py PURE# NEW: load/save/authorise/revoke, normalisation
│   ├── dispatch.py       PURE   # EXTENDED: chat context + gate, order fixed
│   ├── permissions_cmd.py       # NEW: the three admin commands on a pm=3 SV
│   ├── shared.py                # + the pm=3 SV, permissions path, accessors
│   ├── daily.py                 # passes chat context into decide()
│   ├── daily_store.py    PURE   # UNCHANGED (third feature running)
│   ├── blocklist.py      PURE   # unchanged
│   ├── gallery.py        PURE   # unchanged
│   └── help_text.py      PURE   # + a line telling admins a group needs authorisation
└── tests/
    ├── test_group_permissions.py # NEW: store, normalisation, fail-closed, concurrency
    ├── test_dispatch.py          # EXTENDED: gate order, direct bypass, deny-by-default
    ├── test_gscore_compat.py     # + the pm=3 assertion
    └── (all other suites unchanged)
```

**Structure Decision**: The permission store is its own PURE module rather than an addition to
`category_registry.py`, because groups are an orthogonal axis to category config — merging them would make both
files harder to hand-edit, and the operator will want to read this one.

`tdi/daily_store.py` remains untouched for the third consecutive feature. It carries the daily guarantees, and
re-running its suites unmodified stays the cheapest proof that they did not regress.

## Design Highlights

1. **The framework is the gate** (R1). `pm=3` on the authorisation SV means GsCore rejects ordinary members before
   our code runs. One source of truth for the permission ladder, pinned by a contract test.

2. **Order over cleverness** (R2). `decide` gains the chat context and evaluates blocklist → direct bypass → gate →
   index → emptiness. Each step returns the same "no reply" value, so adding a fourth reason to be silent does not
   create a fourth observable (FR-205).

3. **Fail closed** (R3, R4). A missing, empty or corrupt permissions file authorises nothing. For a control whose
   purpose is limiting what a group can see, degradation must remove access, never grant it.

4. **No cache** (R7). Permissions are read per request. A TTL would let a revoked tag keep working, which is the one
   behaviour an admin would least tolerate.

## Constitution Re-Check (post-design)

Re-evaluated after Phase 1. **PASS, unchanged.** Two new PURE modules, one thin handler module, no new dependency,
no database, no cache. The one elevated risk — an upgrade changing the `pm` ladder and silently opening the gate —
is covered by an explicit contract test rather than left to assumption.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Table intentionally empty.

## Phase Status

- [x] Phase 0 — Research complete → [research.md](./research.md)
- [x] Phase 1 — Design complete → [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)
- [ ] Phase 2 — Task breakdown (`/speckit-tasks`)

## Deployment note

Feature 002 is implemented but **not yet running**: the live core (PID 82210) started before it landed. This feature
stacks on 002, so a restart applies both at once — and both the dynamic-resolution change and this gate will become
visible in the same moment. Plan the group authorisations **before** restarting, or the groups go dark in between.
