# Quickstart & Validation: Dynamic Category Lookup

**Feature**: `002-dynamic-category-lookup` | **Date**: 2026-09-11

Contracts: [commands](./contracts/commands.md) · [config](./contracts/config.md) · [data model](./data-model.md).

## Prerequisites

- TodayImage already installed (symlinked at `gsuid_core/gsuid_core/plugins/TodayImage`) and loading.
- TodayWaifu installed and enabled — required for Scenario 3.
- Your account registered as a GsCore master.

> **Read this before judging any result.** Per [research R0](./research.md), the *current* build already reaches the
> handler and hands its reply to the adapter, yet nothing arrives in QQ — the loss is downstream of GsCore. If that
> is still unresolved, **every scenario below will look like a failure**. Confirm delivery works first by checking
> `data/logs/` for `🤖 [发送消息to]` on a request you made, and by getting *any* image out of the bot.

## Baseline (recorded before any 002 change)

`python -m unittest discover -s tests` at the end of feature 001:

| Condition | Result |
|---|---|
| GsCore absent (dev checkout) | **130 tests, 8 skipped, OK** |
| GsCore available (`PYTHONPATH=...`) | **130 tests, 0 skipped, OK** |

After 002 the count changes legitimately: `test_registry_binding.py` (11 tests) is deleted along with its module,
and two `test_gscore_compat.py` assertions about `sv.TL` mutation are removed. Every *other* 001 test must still
pass unchanged — that is the regression check in T035.

## Unit tests

```bash
cd <TodayImage>
python -m unittest discover -s tests -v
```

Expected: green, with `test_registry_binding.py` **gone** and `test_category_index.py` / `test_blocklist.py`
present. Feature 001's `test_daily_draw.py` and `test_daily_store.py` must pass **unmodified** — that is the
SC-107 check that the daily guarantees did not regress.

---

## Scenario 1 — A new folder works with no reload (US1 · FR-103 · SC-101)

```bash
mkdir -p <gsuid_core>/data/TodayImage/制服
cp ~/pics/*.jpg <gsuid_core>/data/TodayImage/制服/
```

| Step | Send | Expect |
|---|---|---|
| 1 | `今日制服` | An image — **without** any reload or restart |
| 2 | `今日制服` again | The identical image |
| 3 | rename `制服` → `校服`, then `今日校服` | An image |
| 4 | `今日制服` | **Silence** |

If step 1 needs a wait, that is the scan-cache TTL (default 300 s); `重载图片类型` forces it. Needing a *restart*
is a failure.

## Scenario 2 — Nothing is disclosed (US2 · FR-109/110/113 · SC-102)

From a **non-master** account:

| Send | Expect |
|---|---|
| `今日不存在的` | **No reply** |
| `今日` | **No reply** |
| `今日黑丝吗` | **No reply** |
| `今日../../etc` | **No reply** |
| `今日` + 20 random guesses | **No reply**, every time |
| `今日图片帮助` | Mechanism only — no folder names, no counts, no admin commands, no paths |
| `今日<一个存在但空的文件夹>` | **No reply** — identical to a non-existent one |

**Pass condition**: every negative is byte-identical (nothing), and no reply anywhere contains
`/Users/...`, `data/TodayImage`, or a folder name.

Then from a **master** account: `查看图片` **does** list folders, counts and the path (FR-112), and
`今日图片帮助` shows the extra master block.

## Scenario 3 — TodayWaifu is never answered by us (US3 · FR-114/115 · SC-103/104)

With both plugins loaded:

| Send | Expect |
|---|---|
| `今日老婆` | Exactly **one** reply, from TodayWaifu |
| `今日萝莉` | Exactly one reply, from TodayWaifu |
| `今日战双老婆` | Exactly one reply, from TodayWaifu |
| `今日异环老婆` / `今日老公` / `今日老婆帮助` / `今日萝莉列表` | Exactly one reply, from TodayWaifu |

Two replies to any of these is a failure.

**Blocklist beats a real folder** (V-BLK-3, US3 AS3):

```bash
mkdir -p <gsuid_core>/data/TodayImage/老婆
cp ~/pics/*.jpg <gsuid_core>/data/TodayImage/老婆/
```

Send `今日老婆` → still exactly one reply, from TodayWaifu. TodayImage must not answer even though the folder
exists. Remove the folder afterwards.

**With TodayWaifu disabled** (SC-104) — disable it in the console, then send `今日萝莉`, `今日老婆`,
`今日战双老婆`: **no reply at all**. TodayImage must not fall back to treating `萝莉` as a category. Re-enable
afterwards.

**Operator extension** (FR-116): add `今日天气` to `TodayImageBlocklist` in the console, create a `天气` folder,
send `今日天气` → no reply, **without a restart**.

## Scenario 4 — Other plugins keep working (FR-106 · SC-105)

This is what `block=False` protects. Confirm a `今日X` command owned by any **other** plugin still responds while
TodayImage is installed. If none exists, assert it structurally instead:

```bash
cd <gsuid_core>
PYTHONPATH=.:./gsuid_core .venv/bin/python - <<'PY'
import plugins.TodayWaifu, plugins.TodayImage
from gsuid_core.sv import SL
for name, sv in SL.lst.items():
    if '今日图片-每日抽取' not in name: continue
    for ttype, table in sv.TL.items():
        for kw, trig in table.items():
            print(f'{ttype} {kw!r} block={trig.block} priority={sv.priority}')
            assert not trig.block, 'FAIL: the dynamic trigger must not block'
print('OK: dynamic trigger is non-blocking')
PY
```

## Scenario 5 — Daily guarantees did not regress (FR-105 · SC-107)

| Send | Expect |
|---|---|
| `今日黑丝` twice, same account, same chat | Identical image |
| `今日黑丝` from two accounts in one group | Different images |
| Roll `daily_records.json`'s `date` back a day, resend | A fresh draw |

Backed by feature 001's unmodified `test_daily_draw.py`.

## Scenario 6 — Misses are cheap (FR-108 · SC-106)

Send 30 unknown `今日X` messages in quick succession. In `data/logs/`, confirm each logs a `debug` miss and that
**no** directory scan is logged between them — the index is answering from cache.

## Dry-run results (recorded 2026-09-11, real gallery, no bot)

Scenarios 2, 3 and 6 were exercised against the live index and blocklist without a connected adapter, since the
decision is pure once the index and blocklist are resolved:

| message | reply | log reason |
|---|---|---|
| `今日黑丝` / `今日白丝` | image | `ok` |
| `今日老婆` / `今日萝莉` / `今日战双老婆` / `今日异环老婆` / `今日老公` / `今日老婆帮助` | **silent** | `blocked` |
| `今日不存在` / `今日abc` / `今日` / `今日../黑丝` / `今日/etc/passwd` / `今日黑丝吗` | **silent** | `unknown` |
| `今日 黑丝 ` (spaced) | image | `ok` |

All negatives返回同一个值 — the uniformity assertion holds. Scenario 4's structural check passed:
the draw SV owns exactly one `prefix` trigger, `block=False`, and no `fullmatch` table.

**Still to run against a live bot**: Scenario 1 (create a folder mid-run), Scenario 5 (daily semantics end to end),
and the human half of Scenarios 2/3 — blocked by the delivery problem in [research R0](./research.md).

## Validation checklist

- [ ] Unit tests pass; `test_registry_binding.py` removed; 001's daily suites pass unmodified
- [ ] S1: new folder live with no reload, no restart
- [ ] S2: 20+ probes produce zero replies and zero disclosure; master still sees the list
- [ ] S3: every TodayWaifu `今日` command gets exactly one reply, from TodayWaifu — including with a same-named folder present, and with TodayWaifu disabled
- [ ] S4: the dynamic trigger is non-blocking; other plugins unaffected
- [ ] S5: same-image-on-repeat, no same-day collisions, Beijing reset
- [ ] S6: unknown suffixes cost no filesystem scan
