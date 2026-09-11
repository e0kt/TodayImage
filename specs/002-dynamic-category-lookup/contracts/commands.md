# Contract: Revised Command Surface

**Feature**: `002-dynamic-category-lookup`

Supersedes [001 contracts/commands.md](../../001-daily-image-categories/contracts/commands.md) §1 and §6.
Sections 2–5 (upload / list / delete / reload) are unchanged except where noted.

## The silence contract

> Every public negative outcome produces **no reply at all**.

Unknown name, blocklisted name, empty folder, malformed input and disabled category are **indistinguishable** from
one another and from a message the plugin never saw. Any difference between them re-creates the probing oracle this
feature removes (V-DIS-1).

This **reverses feature 001's SC-005** for public paths. SC-005 still governs `pm=1` commands.
Every silenced path logs at `debug` with its reason — diagnosis moves from chat to `data/logs/` (V-DIS-5).

---

## 1. `今日<类型>` — dynamic draw (rewritten)

- **Trigger**: a single `on_prefix(«前缀», block=False)` on `今日图片-每日抽取` (priority 25).
  **Not** one trigger per folder; feature 001's per-folder registration is deleted.
- **Auth**: none.
- **Args**: `ev.text` is the suffix after the prefix.

### Why `block=False`

`handler.py` sorts matched triggers by `(has-prefix, sv.priority)` and stops at the first `block=True`. TodayWaifu's
`今日` triggers sit at priority 0–10; ours at 25.

| Message | Outcome |
|---|---|
| `今日老婆` | TodayWaifu (p2/p10, blocking) runs and breaks the loop — we never execute |
| `今日黑丝` | only our trigger matches — we answer |
| `今日X` owned by a plugin at priority > 25 | we run first, resolve nothing, **do not block**; their handler still runs |

With `block=True` the third row breaks: we would terminate the loop and silently kill their command (FR-106).

> **Extended by feature 003.** The order below gained a per-group authorisation step between the blocklist and
> the index, plus a direct-chat bypass ahead of it. See
> [003 contracts/commands.md](../../003-per-group-tag-permission/contracts/commands.md) §4 for the current order.

### Resolution order (must not be reordered)

1. Master switch off → return.
2. **Blocklist** → return (before any filesystem access, V-BLK-2).
3. Index lookup on `suffix.strip().casefold()` → miss → return.
4. Folder empty → return (V-DIS-1; an "empty" reply would confirm the folder exists).
5. Draw and send, per feature 001 semantics (FR-105).

| Condition | Reply |
|---|---|
| Resolved, has images | *(group, if at-mention on)* at-mention + newline, caption, image |
| Anything else | **nothing** |

Caption behaviour, at-mention, per-day pinning, per-chat de-duplication and the Beijing reset are **unchanged**.

---

## 6. `今日图片帮助` — help (rewritten)

- **Trigger**: `on_fullmatch(('今日图片帮助', '图片帮助'), block=True)`, priority 20.
- **Auth**: none — but output depends on the viewer.

| Viewer | Reply |
|---|---|
| Public | How the feature works: send `«前缀»<类型>`, one image per person per day per chat, resets at Beijing midnight. **No** folder names, **no** counts, **no** admin commands, **no** paths |
| Master | The public text plus the folder list with counts, the image root path, and any collision reports |

Feature 001's help listed every live command and printed the image root unconditionally; both are now master-only
(FR-110, FR-111, V-DIS-3).

---

## 3. `查看图片 [<类型>]` — list (unchanged, master-only)

Still `pm=1`, still enumerates folders, counts and the image root. This is the sanctioned disclosure channel
(FR-112, V-DIS-4). Removing it would leave the operator unable to manage the gallery from chat.

## 5. `重载图片类型` — reload (demoted)

No longer required for correctness — a new folder is live within the cache TTL on its own (FR-103). Retained so an
operator can force the index immediately. Reply reports the refreshed category **count**; the full listing stays in
`查看图片`. Master-only, so it may name skipped categories.

---

## Cross-cutting rules

- **Master switch off** → nothing in the plugin responds.
- **No public reply may contain a filesystem path** (V-DIS-2).
- **We never suppress another plugin's `今日X`** (FR-106, SC-105) — guaranteed by `block=False`.
- **Blocklist beats folders** (V-BLK-3).
- **Every silent return logs at `debug`** with its reason (V-DIS-5).
