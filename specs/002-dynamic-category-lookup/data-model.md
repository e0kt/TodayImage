# Phase 1 Data Model: Dynamic Category Lookup

**Feature**: `002-dynamic-category-lookup` | **Date**: 2026-09-11

Only what changes from feature 001 is described. `DailyRecord`, `Image`, `CategoryOverride` and the storage layout
are **unchanged** — see [001 data-model](../001-daily-image-categories/data-model.md).

---

## Entity: CategoryIndex (new)

A request-time lookup from a command suffix to a category folder, rebuilt from the TTL-cached directory scan.
Replaces feature 001's registered-command table.

| Field | Type | Notes |
|---|---|---|
| `entries` | `dict[str, str]` | `name.strip().casefold()` → canonical folder name |
| `built_at` | `float` | Monotonic timestamp, shared with the scan cache |

**Validation rules**

- **V-IDX-1** — Keys are `name.strip().casefold()`. Trimming and case-insensitivity (FR-102) are therefore a
  property of the key, not of a comparison loop.
- **V-IDX-2** — Lookup is **dict access only**. The suffix is never joined onto a path, so `..`, `/`, `\` and
  absolute paths cannot resolve (FR-104). This is strictly stronger than 001's directory-iteration guard.
- **V-IDX-3** — Only direct sub-folders of the image root become entries; the plugin's own JSON files are files and
  never appear.
- **V-IDX-4** — Reserved directory names (`cache`, `tmp`, `logs`, `backup`) are excluded, as in 001.
- **V-IDX-5** — On a case/whitespace collision between two folders, the stable-sort winner holds the key; the loser
  is unreachable. This is reported to masters only (FR-112), never publicly.
- **V-IDX-6** — A disabled category (`categories.json`) is **absent** from the index, so its command resolves to
  nothing and is silently ignored like any unknown name.
- **V-IDX-7** — The index is rebuilt with the scan cache, so a new folder is live within the TTL with no reload
  (FR-103). `重载图片类型` forces it immediately.
- **V-IDX-8** — A miss must cost **no** filesystem access on a warm index (FR-108, SC-106); the dynamic trigger
  fires on every `今日*` message, so misses are the common case.

---

## Entity: Blocklist (new)

Command names TodayImage must never answer.

| Field | Type | Notes |
|---|---|---|
| `base_names` | `tuple[str, ...]` | Default set plus operator additions |

**Default set** — the 16 `今日*` triggers TodayWaifu registers, reduced to 12 base names:

```text
今日老婆   今日老公   今日萝莉   今日战双老婆   今日异环老婆   今日群友离婚
今日老婆帮助   今日老婆离婚   今日老公离婚   今日萝莉离婚   今日萝莉列表   今日萝莉上传
```

**Validation rules**

- **V-BLK-1** — A command is blocked when it **equals** a base name or **starts with** one (FR-117), so
  `今日老婆离婚` is covered by `今日老婆` and future TodayWaifu suffixes are covered pre-emptively.
- **V-BLK-2** — The blocklist is evaluated **before** the index (FR-118). A blocked name never touches the
  filesystem — and blocked names are the ones most likely to be spammed.
- **V-BLK-3** — Blocklist **beats a real folder** of the same name (FR-115, US3 AS3). This is the rule most likely
  to regress silently, which is why it lives in its own tested module.
- **V-BLK-4** — Matching is `strip().casefold()` on both sides.
- **V-BLK-5** — Operator additions merge with, and cannot remove, the defaults. Shrinking the default set would let
  TodayImage start answering another plugin's command, which no console edit should be able to cause.
- **V-BLK-6** — Read per request from config, so edits apply without a restart (FR-116).
- **V-BLK-7** — A blocked command produces **no reply**, identical to an unknown one — not a "blocked" message,
  which would itself disclose the list.

---

## Entity: DisclosureLevel (new)

Governs what a reply may contain. Replaces feature 001's single "actionable plain-text reply" rule.

| Level | Audience | May contain |
|---|---|---|
| `public` | everyone | Mechanism only. **No** folder names, **no** command list, **no** filesystem paths |
| `master` | `pm=1` | Everything: folder names, counts, paths, collision reports |

**Validation rules**

- **V-DIS-1** — Every public negative — unknown, blocked, empty folder, malformed input — produces the **same**
  observable: no reply (FR-109, FR-113). Non-uniformity is the oracle this feature exists to remove.
- **V-DIS-2** — Public replies must contain no absolute or relative filesystem path (FR-110).
- **V-DIS-3** — Public help describes *how* to use the feature but never *what* exists (FR-111).
- **V-DIS-4** — Master-only commands retain full disclosure (FR-112); the restriction is by permission, not by
  removal, or the plugin becomes unmanageable from chat.
- **V-DIS-5** — Every silenced path logs at `debug` with its reason. Chat-level observability is intentionally
  traded away; log-level observability is not.

**Relationship to feature 001 SC-005**: 001 required every failure path to produce an actionable plain-text reply.
That is now true for `master` only. The reversal is deliberate, scoped, and recorded here so the older criterion is
not read as still binding on public paths.

---

## Removed from feature 001

| Entity | Why |
|---|---|
| Registered command table (`sv.TL` per folder) | Replaced by CategoryIndex; it was enumerable and needed a reload |
| `Category.commands` | Commands are no longer precomputed; resolution is by suffix |
| `ApplyReport.added/removed` | Nothing is registered or unregistered at runtime any more |

## Cross-entity invariants

- **I-201** — Exactly one trigger can answer a `今日X` message from this plugin. Per-folder registration is removed,
  not kept alongside, so a double reply is structurally impossible.
- **I-202** — Blocklist ∩ answerable commands = ∅, regardless of what folders exist.
- **I-203** — Public output never contains a string that appears only in the filesystem.
- **I-204** — Daily guarantees from 001 are untouched: `daily_store.py` is not modified and its suites run unchanged
  (FR-105, SC-107).
