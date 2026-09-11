---
description: "Task list for 003 — 分群标签授权"
---

# Tasks: 分群标签授权

**Input**: Design documents from `specs/003-per-group-tag-permission/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: **INCLUDED.** This is an access control; the two failure modes that matter — failing open, and an
ordinary member widening a group — are both silent in production. Test tasks precede their implementation.

**Organization**: Grouped by user story. US1–US3 are P1 and share `tdi/dispatch.py` and `tdi/permissions_cmd.py`;
see the shared-file table before parallelising.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different files, no dependency on an incomplete task
- **[Story]**: `[US1]`–`[US4]` from spec.md
- Every task names an exact file path

## Path Conventions

Repo root is the plugin package; paths are relative to `<TodayImage>/`.
**PURE** modules import only the standard library — `tests/test_gscore_compat.py` enforces this.

**Baseline**: 168 tests (10 skipped without GsCore, 0 with it). Every one must still pass.

**Fail-closed is the default posture here.** Unlike features 001/002, where a corrupt store cost one day's pin, a
corrupt permissions file must remove access from every group. Any task that touches error handling must preserve
that direction.

---

## Phase 1: Setup

- [X] T001 [P] Add `TodayImageDefaultGroupTags` (`GsListStrConfig`, default `[]`) to `config_default.py` under a new `_DividerGroupPermission` divider, with the description from `contracts/config.md` making clear it seeds only groups that have no record yet
- [X] T002 [P] Add the breaking-change operator note to `README.md`: after this ships, every group draws nothing until an admin authorises tags, and the recommended order is decide tags → restart → `TodayImage允许` per group → verify with `TodayImage列表`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The permission store and the admin SV that all four stories build on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests (write first, confirm they FAIL)

- [X] T003 Write `tests/test_group_permissions.py` covering the store and normalisation: tag identity is `strip().casefold()` (V-GRP-1); surrounding `【】[]「」（）()` stripped before storing (V-GRP-2); `group_key` is `str(group_id).strip()` so `123` and `'123'` are one group (V-GRP-3); a group with no record authorises nothing (V-GRP-4); authorise is idempotent (V-GRP-5); revoking an unauthorised tag is reported not raised (V-GRP-6); a missing/unreadable/malformed file yields **no** authorisations rather than all (V-PST-1, FR-218); atomic write leaves no `.tmp` behind (S-303); unknown keys preserved on rewrite (V-PST-4); entries for absent groups retained (V-PST-5); `tags` stored sorted and de-duplicated (S-308); two concurrent authorisations in one group both persist (V-GRP-10, FR-217)

### Implementation

- [X] T004 Create **PURE** `tdi/group_permissions.py`: `normalize_tag`, `normalize_group_key`, `load_permissions`, `save_permissions`, `authorise_tag`, `revoke_tag`, `tags_for_group`, `is_tag_allowed`, plus a per-group `asyncio.Lock` registry and the atomic-write helper — makes T003 pass
- [X] T005 Register the new pure module in `tests/_loader.py` by adding `'group_permissions'` to `PURE_MODULES` so the purity assertions in `tests/test_gscore_compat.py` cover it
- [X] T006 Add to `tdi/shared.py`: the `今日图片-群授权` SV at `pm=3, priority=21`, a `permissions_path()` helper returning `data_root() / 'group_permissions.json'`, a `default_group_tags()` accessor reading `TodayImageDefaultGroupTags`, and exports for the new names — depends on T004
- [X] T007 Confirm `tests/test_daily_store.py` and `tests/test_daily_draw.py` still pass **unmodified**; `tdi/daily_store.py` must not be edited by this feature for the third consecutive time (I-305)

**Checkpoint**: The store exists and is tested; the admin SV is registered but owns no commands yet.

---

## Phase 3: User Story 1 - A group admin opens a tag for their group (Priority: P1) 🎯 MVP

**Goal**: `今日<类型>` works in a group only after an admin has run `TodayImage允许<类型>` there; other groups are
unaffected.

**Independent Test**: In a fresh group confirm `今日黑丝` does nothing, authorise it as an admin, confirm it works,
and confirm a second group still gets nothing. (quickstart Scenarios 1 and 2.)

### Tests for User Story 1 (write first, confirm they FAIL)

- [X] T008 [P] [US1] Extend `tests/test_dispatch.py` with the gate: a group with no record draws nothing (FR-203); an authorised tag in group A resolves while the same tag in group B does not (FR-202); the gate is evaluated **before** the index — assert with an index-lookup spy that an unauthorised tag never queries it (V-GATE-3); the blocklist still wins over an authorised tag of the same name (FR-206, V-GATE-1)
- [X] T009 [P] [US1] Extend `tests/test_dispatch.py` with the uniformity assertion: unauthorised, unknown, blocklisted and empty all return the **same** value, so adding a fourth reason to be silent adds no fourth observable (FR-205, V-GATE-4, SC-206)

### Implementation for User Story 1

- [X] T010 [US1] Extend `decide()` in **PURE** `tdi/dispatch.py` to take the chat context (`is_direct`, `group_key`) and an `allowed_tags` set, implementing the fixed order blocklist → direct bypass → group gate → index → emptiness from `contracts/commands.md` §4 — makes T008/T009 pass
- [X] T011 [US1] Extend `miss_reason()` in `tdi/dispatch.py` with an `unauthorised` reason for `debug` logging only; it must never reach a reply (V-GATE-5)
- [X] T012 [US1] Update the handler in `tdi/daily.py` to read the permissions file per request, derive `is_direct` and `group_key` from the event, and pass them into `decide()` — no caching, so a revoke applies on the next message (V-PST-3)
- [X] T013 [US1] Create `tdi/permissions_cmd.py` with `TodayImage允许<tag>` on the `pm=3` SV per `contracts/commands.md` §1, including bracket/space-tolerant argument parsing and the already-authorised, empty-argument and success replies
- [X] T014 [US1] Add `from .tdi import permissions_cmd` to `__init__.py`, placed after `help` and before `daily`, and update the import-order comment to say why

**Checkpoint**: MVP. Per-group authorisation works. Revoke, listing and the direct-chat replies are not yet done.

---

## Phase 4: User Story 2 - Only admins can change a group's tags (Priority: P1)

**Goal**: Ordinary members cannot widen or narrow any group; admins can authorise, revoke and list.

**Independent Test**: Send the authorisation commands from an ordinary account and confirm nothing changes, then
repeat as an admin. (quickstart Scenario 4.)

### Tests for User Story 2 (write first, confirm they FAIL)

- [X] T015 [P] [US2] Add a contract assertion to `tests/test_gscore_compat.py` that the `今日图片-群授权` SV has `pm == 3`. If a GsCore upgrade changed the ladder in `sv.py`, an ordinary member could silently gain the ability to widen a group's content scope — the highest-consequence regression in this feature, so it is pinned rather than assumed
- [X] T016 [P] [US2] Extend `tests/test_group_permissions.py` with revoke semantics: revoking removes only the named tag; the group's other tags are untouched; revoking the last tag leaves an empty entry rather than deleting the group record (V-GRP-6, S-309)

### Implementation for User Story 2

- [X] T017 [US2] Add `TodayImage禁止<tag>` to `tdi/permissions_cmd.py` per `contracts/commands.md` §2, sharing the argument parser with the authorise command
- [X] T018 [US2] Add `TodayImage列表` / `TodayImage权限` to `tdi/permissions_cmd.py` per `contracts/commands.md` §3, showing **this group's** tags only and never the server's folder list or another group's configuration (FR-215, V-DIS-6)
- [X] T019 [US2] Verify no handler in `tdi/permissions_cmd.py` performs its own permission check — the SV's `pm=3` is the single source of truth, and a duplicate check is how the two drift apart (research R1)

**Checkpoint**: The control is complete and enforceable. US1 + US2 are shippable together.

---

## Phase 5: User Story 3 - Direct chats are unaffected (Priority: P1)

**Goal**: Direct chats behave exactly as in feature 002, with no authorisation step and no group state consulted.

**Independent Test**: With nothing authorised anywhere, send `今日黑丝` in a direct chat and get an image; re-run
feature 002's probe set there and see identical behaviour. (quickstart Scenario 3.)

> The bypass line itself lands in T010's gate — a gate without it would break direct chats the moment US1 ships.
> This phase covers the **verification** that it holds, plus the admin commands' direct-chat replies.

### Tests for User Story 3 (write first, confirm they FAIL)

- [X] T020 [P] [US3] Extend `tests/test_dispatch.py`: with `is_direct=True` and an empty `allowed_tags`, every existing tag still resolves (FR-204); the direct path must not consult group state at all — assert by passing a sentinel that raises if the allowed-tags set is touched (V-GATE-2, I-302)
- [X] T021 [P] [US3] Add `tests/test_permissions_cmd_text.py` for the pure reply builders: the direct-chat responses for authorise, revoke and list are explanatory rather than silent (FR-214, US3 AS3)

### Implementation for User Story 3

- [X] T022 [US3] Extract the reply strings of `tdi/permissions_cmd.py` into pure builder functions so T021 can test them without GsCore, following the `help_text.py` precedent
- [X] T023 [US3] Handle `ev.group_id is None` in all three commands in `tdi/permissions_cmd.py`, replying with the direct-chat explanation from `contracts/commands.md` instead of silently doing nothing
- [X] T024 [US3] Re-run feature 002's `tests/test_non_disclosure.py` unchanged and confirm the direct-chat path is byte-identical to before this feature (SC-203, I-302)

**Checkpoint**: All three P1 stories done; groups are gated, direct chats are not.

---

## Phase 6: User Story 4 - An admin can see and audit a group's configuration (Priority: P2)

**Goal**: An admin can tell "not authorised here" from "no such folder on the server".

**Independent Test**: As an admin, authorise a tag with no matching folder and confirm the warning; list and see it
flagged. (quickstart Scenario 7.)

### Tests for User Story 4 (write first, confirm they FAIL)

- [X] T025 [P] [US4] Extend `tests/test_permissions_cmd_text.py`: authorising a tag with no matching folder produces the success reply **plus** a warning (FR-213, V-GRP-7); the list reply flags authorised tags that have no folder; an empty group's list explains how to authorise (US4 AS2)

### Implementation for User Story 4

- [X] T026 [US4] Cross-check the authorised tag against the category index in `tdi/permissions_cmd.py` and append the missing-folder warning — the check is on the tag the admin already typed, never an enumeration (V-DIS-7)
- [X] T027 [US4] Flag folder-less tags in the `TodayImage列表` output in `tdi/permissions_cmd.py`
- [X] T028 [P] [US4] Add one line to the master section of **PURE** `tdi/help_text.py` noting that groups need `TodayImage允许<类型>` and that direct chats do not, without naming any tag

**Checkpoint**: A silent `今日X` is diagnosable by an admin without any chat hint.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T029 [P] Add a `debug` log with the reason to the gated return path in `tdi/daily.py`, reusing `miss_reason`'s new `unauthorised` value (V-GATE-5, V-DIS-5)
- [X] T030 [P] Update `README.md` with the three admin commands, the deny-by-default behaviour, the direct-chat exemption, and `TodayImageDefaultGroupTags`
- [X] T031 Seed `default_group_tags()` into a group's first record in `tdi/group_permissions.py` and confirm it applies **only** where no record exists, so widening the default never re-grants a deliberately revoked tag (CF-301)
- [X] T032 Run `python -m unittest discover -s tests` and compare against the baseline of 168 tests recorded at the top of this file; every feature 001 and 002 test must still pass
- [X] T033 Verify the live SV registration with GsCore on the path: `今日图片-群授权` present at `pm=3`, and the draw SV still owning exactly one non-blocking prefix trigger from feature 002
- [X] T034 Run quickstart Scenarios 1–9 in `specs/003-per-group-tag-permission/quickstart.md` against a live core and record results there
- [X] T035 Add a pointer to `specs/002-dynamic-category-lookup/contracts/commands.md` noting that the draw gate gained a per-group authorisation step in feature 003, so the 002 order is not read as current

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup — **blocks all stories**
- **US1 (Phase 3)**: depends on Foundational
- **US2 (Phase 4)**: depends on US1's `tdi/permissions_cmd.py` (T013)
- **US3 (Phase 5)**: depends on US1's gate (T010) and on US2 having created the commands it adds replies to
- **US4 (Phase 6)**: depends on US3's pure reply builders (T022)
- **Polish (Phase 7)**: depends on all four stories

### Shared-file coordination

| File | Touched by | Rule |
|---|---|---|
| `tdi/dispatch.py` | T010, T011 (US1), T020 (US3 test only) | US1 writes the gate including the direct bypass; US3 verifies it |
| `tdi/permissions_cmd.py` | T013 (US1), T017–T019 (US2), T022–T023 (US3), T026–T027 (US4) | Four stories, one file — strictly sequential |
| `tests/test_dispatch.py` | T008, T009 (US1), T020 (US3) | Three appends to one file |
| `tests/test_group_permissions.py` | T003 (foundational), T016 (US2) | T016 appends |
| `tests/test_gscore_compat.py` | T015 (US2), T033 (polish) | Two edits |

`tdi/permissions_cmd.py` is the bottleneck: every story adds to it. Plan for one person to own that file.

### Within each story

- Tests first, failing, before implementation
- PURE modules before the GsCore-facing modules that consume them
- The gate (T010) before anything that depends on its signature

### Parallel Opportunities

- **Setup**: T001 ‖ T002
- **US1**: T008 ‖ T009
- **US2**: T015 ‖ T016
- **US3**: T020 ‖ T021
- **Polish**: T029 ‖ T030
- Cross-story parallelism is limited by `permissions_cmd.py`; the useful split is one person on the store and gate
  (T004, T010–T012), another on the command surface (T013, T017–T018, T022–T023)

---

## Parallel Example: Phase 3 (US1)

```bash
# Failing gate tests together:
Task: "Extend tests/test_dispatch.py with the per-group gate"
Task: "Extend tests/test_dispatch.py with the uniformity assertion"

# Then, sequentially, the gate and the command:
Task: "Extend decide() in tdi/dispatch.py with the chat context and gate"
Task: "Create tdi/permissions_cmd.py with TodayImage允许"
```

---

## Implementation Strategy

### MVP (US1 only)

Phases 1–3. Per-group authorisation works, but there is no revoke, no listing, and the admin commands do not
explain themselves in a direct chat. **Do not ship US1 alone** — a control you can switch on but not off is worse
than no control. It is the right point to validate Scenarios 1 and 2.

### Incremental Delivery

1. Setup + Foundational → store tested, SV registered, 001's daily suites still green
2. **+ US1** → the gate works → validate Scenarios 1, 2
3. **+ US2** → revoke, list, and pinned `pm=3` enforcement → validate Scenario 4
4. **+ US3** → direct chats verified untouched, admin commands explain themselves there → Scenario 3
5. **+ US4** → admin diagnosis → Scenario 7
6. **+ Polish** → logging, docs, full regression, live verification

### Deployment order — read before shipping

This feature stacks on feature 002, which is **implemented but not yet running** (the live core predates it). One
restart applies both, so per-group gating and dynamic resolution appear in the same moment. **Decide each group's
tag set before restarting**, or every group goes dark in the gap between the restart and the first
`TodayImage允许`.

---

## Notes

- `tdi/daily_store.py` must not be edited — third feature running (I-305)
- Fail **closed** everywhere: a corrupt or missing permissions file authorises nothing (FR-218)
- The blocklist is not overridable per group; the two controls stack (FR-206)
- **Still unresolved, and not caused by this feature**: replies leave GsCore but never arrive in QQ
  ([002 research R0](../002-dynamic-category-lookup/research.md)). While that stands, every live scenario here will
  look like a failure
