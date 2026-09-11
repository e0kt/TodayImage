# Contract: On-Disk Storage

**Feature**: `001-daily-image-categories`

Everything the plugin owns lives under `get_res_path('TodayImage')` → `gsuid_core/data/TodayImage/`. Nothing is
shared with TodayWaifu, which owns `gsuid_core/data/TodayWaifu/`. (FR-023, I-4.)

## Layout

```text
gsuid_core/data/TodayImage/      # this IS the default image root
├── 黑丝/                        # a category -> 今日黑丝
│   ├── a.jpg
│   ├── b.png
│   └── 画师A/                   # sub-folders are scanned recursively (V-IMG-3)
│       └── c.webp
├── 白丝/                        # a category -> 今日白丝
│   └── d.jpeg
├── config.json                  # Console settings       → contracts/config.md
├── categories.json              # Per-category overrides → contracts/config.md
└── daily_records.json           # Today's pinned draws   → below
```

The image root is `data/TodayImage` **itself**, not a nested `images/` folder — that is where operators actually
put their category folders, and an extra level of nesting is a step people forget. The plugin's own state at that
level is three *files*, and categories are identified as *directories*, so the two never collide.
`RESERVED_DIRECTORY_NAMES` (`cache`, `tmp`, `logs`, `backup`) is a guard for any directory the plugin might add
here later: without it, a new plugin-owned folder would silently become a phantom image type.

**Image root rules**

- Direct sub-folders are categories; deeper folders are just storage. (V-CAT-1.)
- Dot-prefixed folders and files are skipped. (V-CAT-1, V-IMG-2.)
- Only `.jpg .jpeg .png .webp .gif .bmp` (case-folded) are images. (V-IMG-1.)
- Paths are resolved and de-duplicated, so a symlink and its target count once. (V-IMG-4.)
- Sorting is case-folded and stable, so scan order does not vary between APFS and ext4 — the seeded draw depends on
  a stable list order.
- The root is created on demand if missing. (V-CFG-2.)

## `daily_records.json`

```json
{
  "version": 1,
  "date": "2026-09-08",
  "records": {
    "123456789|qq:10001|黑丝": {
      "image": "/opt/gsuid_core/data/TodayImage/黑丝/a.jpg",
      "created_at": 1757318400.0
    },
    "direct:qq:10002|qq:10002|白丝": {
      "image": "/opt/gsuid_core/data/TodayImage/白丝/d.jpeg",
      "created_at": 1757318460.0
    }
  }
}
```

| Field | Type | Meaning |
|---|---|---|
| `version` | `int` | Schema version |
| `date` | `str` | `YYYY-MM-DD` in the reset timezone (default UTC+8, Beijing) |
| `records` | `object` | Key → record |
| `records.<key>.image` | `str` | Absolute path chosen for the day |
| `records.<key>.created_at` | `float` | Unix timestamp, diagnostics only |

**Record key**: `"{chat_key}|{user_key}|{category}"`

- `chat_key` = `group_id`, or `direct:{bot_id}:{user_id}` in a private chat
- `user_key` = `{bot_id}:{user_id}` — the `bot_id` prefix keeps identically-numbered users on different platforms
  apart
- Category names may contain `|`; the key is split on the **first two** separators so a category name containing a
  pipe still parses.

**Rules**

- **S-1** — Whole-file read, whole-file write. Volume is one entry per (user, chat, category) per day.
- **S-2** — On write, if `date` ≠ today the entire `records` object is discarded first. The file holds today only.
  Today is Beijing-midnight based, not server-local. (V-REC-2, V-REC-7, I-3.)
- **S-3** — Written atomically: `mkstemp` in the same directory → write → `flush` + `fsync` → `os.replace` → remove
  the temp file in a `finally`. Same recipe as TodayWaifu's `twf/storage.py`.
- **S-4** — Unreadable or malformed → treated as empty. A user loses one day's pin; nothing crashes. (SC-005.)
- **S-5** — Read-modify-write runs under a per-`(chat_key, category)` `asyncio.Lock`; the store is re-read inside the
  lock. (V-REC-4, FR-010.)
- **S-6** — A record whose `image` no longer resolves is treated as absent and overwritten. (V-REC-3, FR-009.)

## Uploaded file naming

`<image_root>/<类型>/img_<epoch_ms>_<index><suffix>`, with a `_<counter>` tail appended on collision — the scheme
TodayWaifu uses for both `pgr_` and `loli_` uploads. `<suffix>` comes from magic-byte sniffing, not from the
attachment's claimed name. (V-IMG-6.)

## What the plugin never writes

- Anything inside its own source tree — configuration and data must survive a plugin upgrade. (FR-022.)
- Anything under `data/TodayWaifu/`. (FR-023.)
- Any GsCore database table. (Research R6.)
