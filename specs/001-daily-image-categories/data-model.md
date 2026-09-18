# Phase 1 Data Model: TodayImage

**Feature**: `001-daily-image-categories` | **Date**: 2026-09-08

Entities are described by their meaning and rules. Concrete on-disk shapes are in
[contracts/storage.md](./contracts/storage.md); console keys are in [contracts/config.md](./contracts/config.md).

---

## Entity: Category (图片类型)

An operator-defined collection of images, backed by exactly one direct sub-folder of the image root. The unit that
`今日<类型>` addresses.

| Field | Type | Source | Notes |
|---|---|---|---|
| `name` | `str` | Folder name, stripped | Display name and default command suffix. Identity key. |
| `directory` | `Path` | Filesystem | Absolute path to the category folder. |
| `images` | `tuple[str, ...]` | Recursive scan | Absolute paths, de-duplicated, stably sorted. |
| `enabled` | `bool` | `categories.json`, default `True` | `False` unregisters the command; the folder is untouched. |
| `aliases` | `tuple[str, ...]` | `categories.json`, default `()` | Extra suffixes; `今日<alias>` serves the same category. |
| `caption` | `str \| None` | `categories.json`, default `None` | Overrides the global caption template. |
| `commands` | `tuple[str, ...]` | Derived | `prefix + name` plus `prefix + alias` for each alias, after collision filtering. |

**Validation rules**

- **V-CAT-1** — A directory is a category only if it is a direct child of the image root, is a directory, does not
  start with `.`, and has a non-empty name after stripping whitespace. (Edge case: whitespace/dot/empty names.)
- **V-CAT-2** — Category identity is **case-folded and whitespace-stripped**. Two folders whose names collide under
  that rule are a conflict: the first in stable sort order wins, the other is skipped and reported. (Edge case:
  case/whitespace-only differences.)
- **V-CAT-3** — A category with zero images after scanning is still *registered* (its command exists) but its draw
  returns the "no images" notice. This keeps a temporarily-emptied folder from silently losing its command.
- **V-CAT-4** — An alias equal to another category's name or alias is rejected; the later one loses and is reported.
- **V-CAT-5** — A resolved command that collides with a trigger already registered by another loaded SV is dropped
  and reported. If *every* command for a category is dropped, the category is unusable and must be named in the
  reload reply. (FR-005, US2 AS6.)
- **V-CAT-6** — `enabled = False` removes all of the category's commands from the live trigger table.

**Lifecycle**: discovered on scan → filtered by V-CAT-1/2 → overrides applied from `categories.json` → commands
resolved and collision-filtered (V-CAT-4/5) → registered. Re-runs wholly on `重载图片类型`.

---

## Entity: Image

One image file inside a category, possibly nested in sub-folders.

| Field | Type | Source | Notes |
|---|---|---|---|
| `path` | `str` | Scan | Absolute, resolved. |
| `short_id` | `str` | Derived | `sha256(filename).hexdigest()[:8]` — 8 lowercase hex chars. |
| `suffix` | `str` | Filename | Case-folded; one of the accepted extensions. |

**Validation rules**

- **V-IMG-1** — Accepted extensions: `.jpg .jpeg .png .webp .gif .bmp`, compared case-folded. Everything else is
  ignored, including `.txt`, `.DS_Store`, and `Thumbs.db`. (FR-014.)
- **V-IMG-2** — Files whose name starts with `.` are ignored.
- **V-IMG-3** — Discovery is recursive (`rglob`) within the category folder. (FR-015.)
- **V-IMG-4** — De-duplication is on the **resolved** path, so a symlink and its target count once.
- **V-IMG-5** — `short_id` derives from the **file name only**, not the full path, matching TodayWaifu's
  `image_hash_id`. Two identically-named files in different sub-folders therefore share a short ID; the delete
  command must handle a short ID resolving to more than one path by reporting the ambiguity rather than guessing.
- **V-IMG-6** — On upload, the format is determined by **magic bytes** first, with the source extension as fallback;
  content that sniffs to no accepted format is rejected. (R11.)
- **V-IMG-7** — Uploads above the configured byte cap are rejected and counted as failures. (FR-020.)

**Relationships**: many Images to one Category. An Image has no independent existence — deleting the folder deletes
the images.

---

## Entity: DailyRecord

One user's pinned choice, for one category, on one local date, in one chat. This is what makes a repeat `今日黑丝`
return the same picture.

| Field | Type | Notes |
|---|---|---|
| `date` | `str` | `YYYY-MM-DD` in the configured reset timezone (default UTC+8, Beijing). Partitions the store. |
| `chat_key` | `str` | `group_id`, or `direct:{user_id}` for a private chat. |
| `user_key` | `str` | `bot_id:user_id`, so identically-numbered users on different platforms stay distinct. |
| `category` | `str` | Category `name`. |
| `image` | `str` | Absolute path chosen for the day. |
| `created_at` | `float` | Unix timestamp; diagnostics only. |

**Identity**: `(date, chat_key, user_key, category)` — the full tuple. This is what delivers FR-008: changing any one
component yields a different record, so draws are independent across users, chats and categories.

**Validation rules**

- **V-REC-1** — At most one record per identity tuple. (FR-006.)
- **V-REC-2** — A record whose `date` is not today is ignored on read and dropped on the next write (pruning).
  There is no migration or archive; the store holds today only. (FR-007.)
- **V-REC-7** — "Today" is computed at a **fixed UTC offset** (`TodayImageResetUtcOffset`, default `+8`), never from
  the server's local clock. A bot hosted outside China would otherwise reset at its own local midnight — e.g. a
  US-Pacific host would roll the day over at 3pm Beijing. China observes no DST, so a fixed offset is exact and
  avoids depending on system tzdata.
- **V-REC-8** — When `TodayImageUniquePerDay` is on, a draw excludes images already pinned **today, in this chat, for
  this category** by other users, so two people never receive the same picture. If every image is taken (more users
  than images) the full gallery is restored for that draw: handing out a repeat is better than refusing to answer.
  The exclusion set is computed **inside** the lock — computing it outside would let concurrent first draws read the
  same snapshot and pick the same image, which is exactly the bug the feature exists to prevent.
- **V-REC-3** — If `image` no longer resolves to a file, the record is treated as absent: re-draw from the current
  image list and overwrite. (FR-009; the "image deleted after draw" edge case.)
- **V-REC-4** — Creation is read-modify-write under a per-`(chat_key, category)` `asyncio.Lock`. Inside the lock the
  store is re-read; if another coroutine already wrote a valid record for the identity, that record is returned and
  the caller's own pick is discarded. (FR-010; the concurrent-first-draw edge case.)
- **V-REC-5** — A category with zero images writes **no** record. (FR-006 vacuously; US1 AS6.)
- **V-REC-6** — The date is captured **once** at the start of a draw and reused for both the seed and the record, so
  a request spanning midnight cannot seed against one date and persist under another. (Date-rollover edge case.)

> **自 feature 004 起有变**：抽图种子在该 (日期, 群, 类型) 被重置过时会追加 `:r{epoch}` 后缀，
> 且重置会写下一个排除集，使重抽必定换图。未被重置时种子与下述格式逐字节一致。
> 见 [004 data-model](../004-group-category-reset/data-model.md)。

**Derivation of `image`**: `random.Random(f'{date}:{user_key}:{chat_key}:{category}').choice(images)` — the seed
scheme 今日萝莉 uses (`twf/shared.py::_daily_rng`). The record pins the outcome so a mid-day gallery edit cannot
reshuffle it (research R5).

---

## Entity: CategoryOverride

The operator's per-category settings. Stored separately from console config because the key set is discovered at
runtime and unbounded (research R10).

| Field | Type | Default | Notes |
|---|---|---|---|
| `enabled` | `bool` | `True` | |
| `aliases` | `list[str]` | `[]` | |
| `caption` | `str \| null` | `null` | `null` means "use the global template". |

**Validation rules**

- **V-OVR-1** — An override for a folder that does not exist is retained (not pruned), so temporarily moving a
  folder aside does not silently discard its settings.
- **V-OVR-2** — A malformed or unreadable `categories.json` is treated as empty, with a warning logged. The plugin
  must still start and serve every category with defaults. (SC-005.)
- **V-OVR-3** — Unknown keys inside an entry are preserved on rewrite, so a newer plugin version's settings survive
  a downgrade.

---

## Entity: PluginConfiguration

Console-managed global settings. Full key list, types and defaults: [contracts/config.md](./contracts/config.md).
Grouped as: master switch · image root · command prefix · caption template · at-mention flag · upload whitelist ·
upload size cap · scan cache TTL.

**Validation rules**

- **V-CFG-1** — The master switch off makes every command in the plugin a no-op, including management commands.
  (FR-024.)
- **V-CFG-2** — An empty image-root setting falls back to `get_res_path('TodayImage')` itself — the same directory
  that holds the plugin's JSON state — created on demand. Categories are directories and the state is files, so they
  cannot collide; `RESERVED_DIRECTORY_NAMES` additionally excludes any directory the plugin may own there later.
- **V-CFG-3** — An empty command prefix is rejected in favour of the default `今日`; a bare category name as a
  command would collide with ordinary conversation.
- **V-CFG-4** — Changing the prefix or the image root requires a `重载图片类型` to take effect, since both change the
  resolved command set. The reload reply states what changed.
- **V-CFG-5** — A non-numeric or negative cache TTL falls back to the default; `0` is legal and means "scan every
  time" (useful while debugging).

---

## State: draw flow

```text
今日<类型>
  │
  ├─ master switch off ─────────────────────────────► silent no-op            (V-CFG-1)
  ├─ category disabled / unknown ───────────────────► command isn't registered
  │
  ├─ capture today's date once                                                (V-REC-6)
  ├─ load images (TTL-cached scan)
  │     └─ empty ───────────────────────────────────► "no images" notice, no record (V-CAT-3, V-REC-5)
  │
  ├─ read store
  │     ├─ record exists, file present ─────────────► send that image         (V-REC-1)
  │     └─ record exists, file missing ─────────────► fall through to draw    (V-REC-3)
  │
  └─ draw: seeded pick
        └─ acquire (chat_key, category) lock                                  (V-REC-4)
              ├─ re-read store
              │     └─ someone else won ────────────► send their image, discard own pick
              └─ write record, prune stale dates ───► send own image          (V-REC-2)
```

## Cross-entity invariants

- **I-1** — Every registered command maps to exactly one enabled Category. No command is registered twice, and no
  category is reachable through a command another SV already owns. (V-CAT-4/5.)
- **I-2** — Every stored DailyRecord names a category that existed at write time; a record for a since-deleted
  category is inert and is pruned by the daily date sweep.
- **I-3** — The store contains records for today's date only after any write. (V-REC-2.)
- **I-4** — No entity is shared with TodayWaifu. Distinct SV names, distinct `data/` subtree, distinct config file.
  (FR-023, SC-006.)
