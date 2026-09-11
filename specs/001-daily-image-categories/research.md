# Phase 0 Research: TodayImage

**Feature**: `001-daily-image-categories` | **Date**: 2026-09-08

All unknowns in Technical Context are resolved below. Findings come from two sources:

1. **The GsCore CookBook** — <https://docs.sayu-bot.com/CodePlugins/CookBook.html>
2. **Direct source reading** of the local GsCore checkout at `<gsuid_core>`
   (framework `gsuid_core/sv.py`, `trigger.py`, `handler.py`, `segment.py`, `data_store.py`, `server.py`)
   and the reference plugin `gsuid_core/plugins/TodayWaifu` (especially `twf/loli.py`, the 今日萝莉 implementation).

Source reading was used in preference to the CookBook wherever the two could disagree, because the CookBook is a
tutorial and the local checkout is the code this plugin will actually run against.

---

## R1. Plugin packaging & load mechanics

**Decision**: The repository root **is** the plugin package. `TodayImage/__init__.py` declares
`Plugins(name='TodayImage', ...)` and then imports the feature modules; the repo is installed by placing/cloning it
at `gsuid_core/plugins/TodayImage`.

**Rationale**: `GsServer._load_plugin` (`gsuid_core/server.py:400-440`) walks `gsuid_core/plugins/*`. For a
directory it checks, in order, `__full__.py`, `__nest__.py` / `<stem>/`, then `__init__.py`; the last case loads the
directory as a single plugin package. It also runs `check_pyproject()` on a `pyproject.toml` if present, which is
how a plugin declares extra Python dependencies. TodayWaifu uses exactly this `__init__.py` shape.

**Alternatives considered**:
- `__full__.py` multi-plugin layout — for repos that ship several independent plugins; unnecessary here.
- A single-file `TodayImage.py` plugin — supported by the loader, but forecloses the pure-module/unit-test split
  that R9 depends on.

---

## R2. Command registration API

**Decision**: Use `SV(...)` service objects and their `on_fullmatch` / `on_command` / `on_prefix` decorators.
Draw commands (`今日黑丝`) use `on_fullmatch(..., block=True)`; management commands that take an argument
(`上传图片 黑丝`) use `on_command(..., block=True)`.

**Rationale**: `SV._on` (`gsuid_core/sv.py:316`) builds a `Trigger` per keyword × plugin prefix and files it under
`sv.TL[type][keyword]`. Matching semantics live in `gsuid_core/trigger.py`:

| Trigger type | Match rule |
|---|---|
| `fullmatch` | `raw_text == prefix + keyword` |
| `command` | `raw_text.startswith(prefix + keyword)`, remainder lands in `ev.text` |
| `prefix` | `startswith` **and not** an exact match |
| `suffix` / `keyword` / `regex` | ends-with / contains / regex |

`fullmatch` is the right primitive for a bare `今日黑丝`: it cannot be shadowed by a longer message and it will not
swallow another plugin's `今日黑丝的历史`.

**Alternatives considered**:
- **One `on_prefix('今日')` catch-all** that resolves the category at runtime. Rejected: with `block=True` it would
  swallow every other plugin's `今日*` command (including TodayWaifu's 今日老婆/今日萝莉), and with `block=False`
  it would double-answer. The blast radius is unacceptable for a plugin meant to coexist (FR-023, SC-006).
- **`on_regex('^今日(.+)$')`** — same shadowing problem, plus regex triggers run for every message.

---

## R3. Dynamic (restart-free) category commands — the central design question

**Decision**: Register category triggers **at import time from the current folder scan**, and additionally expose a
reload command that (a) deletes stale keys from `sv.TL['fullmatch']` and (b) re-invokes
`sv.on_fullmatch(name, block=True)(handler)` for the new set. A single dedicated SV
(`今日图片-每日抽取`) owns these dynamic triggers so the mutation is contained.

**Rationale**: `handler.py:486-500` re-reads `SL.lst` and each `_sv.TL` on **every inbound message** — there is no
compiled/frozen routing table. Therefore a trigger added after startup takes effect on the very next message. And
`SV.on_fullmatch` is an ordinary decorator factory, so `sv.on_fullmatch('今日制服', block=True)(handler)` is a
legitimate runtime call that reuses the framework's own prefix-expansion logic rather than reimplementing it.

The only framework-internal reach is **removal**, which has no public API and requires `del sv.TL['fullmatch'][k]`.
This is one dictionary, mutated in one function, and is pinned by a compatibility test (R9) that fails loudly if a
GsCore upgrade changes the `TL` shape.

**Alternatives considered**:
- **Restart-only**: register once at import, require a GsCore restart to pick up new folders. Rejected against
  SC-001 ("under two minutes, without restarting GsCore"), and it is a poor operator experience for a plugin whose
  whole premise is "drop in a folder".
- **Permanent triggers + runtime enabled-check**: register every keyword ever seen and no-op when disabled.
  Rejected: a `block=True` no-op silently eats the message for other plugins, and `block=False` cannot be undone.
- **Pre-registering a fixed pool of placeholder keywords**: rejected as unworkable — keywords are arbitrary
  operator-chosen Chinese words.

**Ordering note**: `handler.py:530` sorts matched triggers by `(not trigger.prefix, sv.priority)` — prefixed
triggers first, then ascending SV priority — and stops at the first `block=True`. TodayWaifu occupies priorities
0–10. TodayImage uses **priority 20+** so that, in the event of a keyword collision, the incumbent plugin wins and
TodayImage's handler never runs. Collisions are also detected proactively at registration (R4).

---

## R4. Command-collision detection

**Decision**: Before registering a category keyword, scan `SL.lst` (`gsuid_core.sv.SL`) for an existing trigger
whose effective match string equals the candidate keyword. On collision, skip that category, log a warning naming
both the category and the owning SV, and surface it in the reload command's reply.

**Rationale**: `SL.lst` is the framework's live registry of every loaded `SV`, and each `SV.TL[type]` is keyed by
the prefix-expanded match string — so the check is a dictionary lookup across loaded services, not a heuristic.
Doing this at registration turns a silent, confusing shadowing bug (US2 AS6) into an actionable message.

**Alternatives considered**: rely on priority ordering alone. Rejected — it makes the failure invisible; the
operator sees "my `今日老婆` folder does nothing" with no explanation.

---

## R5. Deterministic daily draw

**Decision**: Seed `random.Random(f'{date.today().isoformat()}:{user_id}:{group_id or "direct"}:{category}')` to
pick the image, **and** persist the result as the day's authoritative record.

**Rationale**: This is 今日萝莉's own scheme — `_daily_rng` in `twf/shared.py:1278` builds exactly this seed, and
`twf/loli.py::_roll_loli_record` calls `.choice()` on it. Seeding alone gives stability, per-user independence, and
per-chat independence for free, with no storage read on the happy path.

Persistence is still required on top of it, for one reason: a seeded choice is an **index into a list**, so if the
image list changes mid-day (an upload or delete, US3) every user's draw silently reshuffles. FR-006 promises the
image does not change. The persisted record pins the actual chosen path, making the draw stable against gallery
edits. Persistence also gives FR-009 (recorded file vanished → re-draw and re-persist) somewhere to write the
replacement.

**Alternatives considered**:
- **Stateless, seed-only** (no storage at all). Genuinely attractive: no store, no lock, no concurrency case,
  and FR-010 becomes vacuous. Rejected because it breaks FR-006 exactly when US3 is used, and US3 is a shipped
  feature — the two would fight each other in production.
- **Store-only with `random.choice`** (unseeded). Rejected: loses the free per-user/per-chat determinism and makes
  the first draw untestable without mocking.

---

## R6. Daily-record storage

**Decision**: A single JSON document at `get_res_path('TodayImage') / 'daily_records.json'`, written atomically
(temp file in the same directory + `os.replace` + `fsync`), guarded by one `asyncio.Lock` per (chat, category)
during the read-modify-write, and pruned of non-current dates on write.

**Rationale**: `get_res_path` (`gsuid_core/data_store.py:8`) resolves under `gsuid_core/data/`, i.e. outside the
plugin source tree, which satisfies FR-022 (survives plugin upgrade) and FR-023 (TodayWaifu writes
`data/TodayWaifu/`, TodayImage writes `data/TodayImage/` — no shared files). The atomic-write recipe is lifted
from TodayWaifu's `twf/storage.py`, which is already proven against this exact failure mode.

Holding the lock across the re-read means the FR-010 concurrency case reduces to TodayWaifu's proven pattern in
`twf/loli.py::_send_loli_image`: the second racer re-reads under lock, finds the first racer's record, and returns
that image instead of its own.

Volume is small — one entry per (user, chat, category) per day, pruned daily — so a single JSON file is
appropriate; there is no query workload to justify a database.

**Alternatives considered**:
- **GsCore's SQLModel/`Bind` database layer** (the CookBook's `Bind` section; TodayWaifu's `twf/models.py`).
  Rejected as unjustified complexity: no relational queries, no cross-plugin joins, no web-console CRUD
  requirement for records, and it would add a migration surface.
- **One JSON file per date** — simpler pruning, but multiplies file handles and makes the "did I already draw?"
  read a directory stat. Not worth it at this volume.

---

## R7. Gallery scanning and caching

**Decision**: A pure `scan_category_directories(root, extensions)` returning a stably-sorted tuple of
`(name, (absolute image paths...))`, wrapped in a TTL cache (default 300 s, operator-configurable) plus explicit
invalidation on upload/delete/reload. Per-file bytes are read through an mtime-keyed LRU byte cache bounded by both
entry count and total bytes.

**Rationale**: TodayWaifu learned this the hard way — the comment above `_loli_image_paths` in `twf/loli.py` records
that an uncached `rglob` "在图多时是昂贵操作，0 点高峰每条指令都扫会拖垮核心" (an expensive full scan that drags
the core down at the midnight peak when every command triggers one). `twf/folder_gallery.py` and `twf/file_cache.py`
are the fixes, and both are dependency-free modules that port cleanly. The `(path, mtime_ns, size)` cache key means
a replaced image is picked up without a manual flush. Bounding the byte cache by total bytes as well as entry count
prevents a handful of large images from consuming the core's memory. This is what makes SC-003 achievable.

Scanning rules, matching `scan_named_role_directories`: skip dot-prefixed files and directories, skip names that are
empty after stripping, recurse with `rglob`, filter on case-folded extension, de-duplicate on the resolved path, and
sort case-insensitively so ordering is stable across filesystems (APFS vs ext4).

**Alternatives considered**:
- **`watchdog` filesystem events** — a new third-party dependency and a background thread for a folder that changes
  a few times a week. Rejected as disproportionate.
- **No TTL, explicit invalidation only** — misses out-of-band edits (SSH/FTP), which the spec explicitly supports.

---

## R8. Sending a local image

**Decision**: `MessageSegment.image(bytes)`, where the bytes come from the mtime-cached reader. Compose the reply as
a list: optional `MessageSegment.at(user_id)` + `'\n'` (group chats only, config-gated), then the caption text, then
the image segment. Send through a small `safe_send` wrapper that strips `at` segments in private chats.

**Rationale**: `MessageSegment.image` (`gsuid_core/segment.py:94`) accepts `str | Image.Image | bytes | Path`.
Passing **bytes** is what lets the mtime cache do its job — passing a `Path` would push the read down into the
framework on every send and defeat the cache. `twf/shared.py::_send_loli_result_image` is precisely this shape and
is the closest analogue to what this feature needs. The private-chat `at`-stripping comes from
`twf/message_delivery.py::remove_private_mentions`; some adapters render a stray at-mention as literal noise in a
DM. TodayWaifu's XWUID `BotHook` fallback in that same module is **not** ported — it is a workaround for a specific
third-party plugin that TodayImage has no relationship with.

**Alternatives considered**: `MessageSegment.image(Path)` — simpler, but re-reads from disk on every send.

---

## R9. Testing strategy

**Decision**: `unittest` (stdlib), with the plugin split into **pure modules** (no `gsuid_core` import: gallery
scanning, category resolution, daily-record store, image decoding, caches) and **thin GsCore-facing modules**
(trigger registration, message sending). Tests load pure modules directly via
`importlib.util.spec_from_file_location`, so the suite runs with no GsCore installed and no bot connected. One
**compatibility test** asserts the framework contract this plugin leans on: `SV.TL` is a
`dict[str, dict[str, Trigger]]`, `SV.on_fullmatch` is a decorator factory, and `SL.lst` maps names to SVs — skipped
cleanly when `gsuid_core` is not importable.

**Rationale**: This is exactly how `TodayWaifu/tests/test_folder_gallery.py` is written, and it is the only way to
get a fast test loop for a plugin whose runtime is a websocket bot. The compatibility test is what makes R3's one
internal reach safe over time: a GsCore upgrade that reshapes `TL` fails a test instead of silently breaking reload
in production.

**Alternatives considered**:
- `pytest` — nicer, but adds a dependency for a plugin whose only hard requirement is GsCore itself.
- Mocking the whole `gsuid_core` package — brittle, and it tests the mock rather than the plugin.

---

## R10. Configuration surface

**Decision**: `StringConfig('TodayImage', get_res_path('TodayImage') / 'config.json', CONFIG_DEFAULT)` with typed
`GsStrConfig` / `GsBoolConfig` / `GsIntConfig` / `GsListStrConfig` / `GsDivider` entries, plus a separate
**per-category override file** (`categories.json`) holding enable flags, aliases, and caption overrides keyed by
category name.

**Rationale**: The CookBook's config section and TodayWaifu's `daily_wife_config.py` both use `StringConfig` with a
`get_res_path`-rooted path, which is what makes settings appear in the GsCore web console and survive upgrades
(FR-022). Categories are deliberately **not** `StringConfig` keys: the key set is discovered at runtime and grows
without bound, whereas `CONFIG_DEFAULT` is a static dict the console renders as a fixed form. A separate JSON map
keyed by category name is the honest data shape.

TodayWaifu sets `DailyWifeConfig.plugin_name = 'TodayWaifu'` explicitly, with a comment explaining that
`Path.resolve()` follows a junction/symlink and breaks the console's automatic plugin-name detection. TodayImage
does the same, since installing the plugin as a symlink into `plugins/` is a normal dev workflow on macOS.

**Alternatives considered**:
- **Everything in `config.json` with prefixed keys** (`Category_黑丝_Enabled`). Rejected: unbounded key growth in a
  form the console renders as static fields.
- **A per-category `.meta.json` inside each folder**. Attractive (config travels with the images) but mixes
  operator config into a directory the plugin also deletes from during 删除 (US3 AS6). Rejected on that hazard.

---

## R11. Upload handling

**Decision**: Port TodayWaifu's `twf/image_input.py` verbatim in behaviour: collect refs from `ev.content`,
`ev.image_list`, and `ev.image`; accept `data:image/...`, `base64://`, `link://`, `http(s)://`, and plain paths;
sniff the real format from magic bytes with the filename extension only as a fallback; reject anything above the
configured byte cap; derive the short ID as `sha256(filename)[:8]`.

**Rationale**: Adapters differ in where they hang an attached image — QQ, Telegram, and Discord adapters populate
different `Event` fields (`gsuid_core/models.py` declares `image`, `image_list`, `image_id`, plus `content`
segments). `collect_image_refs` checks all three and de-duplicates via `dict.fromkeys`. Magic-byte sniffing matters
because several adapters hand over a URL with no extension at all. This module is already dependency-free and
already handles the adapter matrix; reimplementing it would only reintroduce bugs it has fixed.

**Authorisation**: masters (from `core_config.get_config('masters')`) **or** the configured whitelist, per
`twf/shared.py::_can_upload_images` — masters never need to add themselves to a list.

**Alternatives considered**: reading `ev.image` only. Rejected — it works on one adapter and silently fails on the
rest.

---

## R12. Help output

**Decision**: A plain-text help reply listing the live category commands and the management commands, plus a
`register_help('TodayImage', '今日图片帮助', icon)` call guarded by `try/except` so a failure only logs.

**Rationale**: TodayWaifu's image-rendered help (`twf/help.py`) pulls in Pillow, `help.json`, a `texture2d/` icon
set, a background image, and a bespoke cache — several hundred lines and a binary asset pipeline for a plugin whose
command list is a handful of lines of text. Text help also has the property that matters most here: it reflects the
**current** category set, which an offline-rendered image would have to invalidate on every reload.
`register_help` still slots the plugin into the core's global help index. A `help.json` is shipped so an
image-rendered help can be added later without restructuring.

**Alternatives considered**: full `get_new_help` image rendering — deferred, not precluded.

---

## Resolved Technical Context

| Item | Resolution |
|---|---|
| Language/Version | Python ≥ 3.11 (GsCore `pyproject.toml`: `requires-python = ">=3.11,<4.0"`); `from __future__ import annotations` throughout |
| Primary dependency | `gsuid_core` (framework, provided by the host install) — **no** new third-party dependencies |
| Storage | JSON under `gsuid_core/data/TodayImage/` (`config.json`, `categories.json`, `daily_records.json`); images under a configurable root defaulting to `data/TodayImage/` itself |
| Testing | stdlib `unittest`, pure modules loaded via `importlib`, runnable without GsCore |
| Target platform | Wherever GsCore runs — Linux/macOS/Windows server, Python 3.11+ |
| Project type | Single Python package that is a GsCore plugin (repo root = package root) |
| Performance goals | Warm-cache draw < 1 s at 5,000 images/category (SC-003); no full directory walk per command |
| Constraints | Must coexist with TodayWaifu (separate commands, config, data); no new dependencies; no GsCore restart to add a category |
| Scale/scope | Tens of categories, thousands of images per category, hundreds of daily users per bot |
