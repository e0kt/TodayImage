# Quickstart & Validation: TodayImage

**Feature**: `001-daily-image-categories` | **Date**: 2026-09-08

Runnable scenarios that prove the feature works end to end. Contracts:
[commands](./contracts/commands.md) · [config](./contracts/config.md) · [storage](./contracts/storage.md).
Entity rules and validation IDs: [data-model.md](./data-model.md).

## Prerequisites

- A working GsCore install with at least one adapter connected (this machine: `<gsuid_core>`).
- Python ≥ 3.11 (GsCore's floor).
- Your account registered as a GsCore **master** (`masters` in the core config) — management commands require it.
- No extra Python packages: TodayImage depends only on GsCore.

## Install

```bash
# Symlink the repo into GsCore's plugin directory (a clone works equally well)
ln -s <TodayImage> \
      <gsuid_core>/gsuid_core/plugins/TodayImage

# Restart GsCore once so the plugin package is imported
```

A directory under `plugins/` containing `__init__.py` is loaded as a single plugin package
(`gsuid_core/server.py:431`). The initial restart is required only for the **first** install — from then on, adding
categories uses `重载图片类型` with no restart.

Confirm load: the startup log shows `TodayImage`, and the web console lists the four `今日图片-*` services.

## Run the unit tests (no GsCore or bot needed)

```bash
cd <TodayImage>
python -m unittest discover -s tests -v
```

Expected: all pass. `tests/test_gscore_compat.py` runs against the real framework when `gsuid_core` is importable
and **skips** otherwise — a skip there is a pass, an error is not.

---

## Scenario 1 — Daily draw is fixed for the day (US1 · FR-006 · SC-002)

```bash
mkdir -p <gsuid_core>/data/TodayImage/黑丝
cp ~/pics/*.jpg <gsuid_core>/data/TodayImage/黑丝/
```

Then in chat:

| Step | Send | Expect |
|---|---|---|
| 1 | `重载图片类型` | Reply reports `今日黑丝` registered |
| 2 | `今日黑丝` | Caption + one image from the folder |
| 3 | `今日黑丝` again | **The identical image** |
| 4 | `今日黑丝` from a second account | Independently drawn — usually a different image |

Verify the pin was persisted:

```bash
cat <gsuid_core>/data/TodayImage/daily_records.json
```

Expect `date` = today and one `records` entry per (chat, user, category); see
[storage.md](./contracts/storage.md) for the key format.

Force a rollover without waiting for midnight — edit `date` in that file to yesterday's date, then send `今日黑丝`
again: a **new** draw is written under today's date and the stale records are gone (V-REC-2, FR-007).

## Scenario 2 — Add a category with no restart (US2 · FR-002/FR-004 · SC-001/SC-004)

```bash
mkdir -p <gsuid_core>/data/TodayImage/白丝
cp ~/more-pics/*.png <gsuid_core>/data/TodayImage/白丝/
```

| Step | Send | Expect |
|---|---|---|
| 1 | `今日白丝` | No response — not yet registered |
| 2 | `重载图片类型` | Reply lists `今日白丝` under added commands |
| 3 | `今日白丝` | Caption + an image from `白丝/` |

**Pass condition for SC-001/SC-004**: GsCore was never restarted, and nothing inside the plugin source tree was
edited.

## Scenario 3 — Customise a category (US2 · FR-003/FR-012)

Edit `<gsuid_core>/data/TodayImage/categories.json` (schema:
[config.md](./contracts/config.md)):

```json
{
  "version": 1,
  "categories": {
    "黑丝": { "enabled": true, "aliases": ["丝袜"], "caption": "今天的黑丝，请收好~" },
    "白丝": { "enabled": false, "aliases": [], "caption": null }
  }
}
```

| Step | Send | Expect |
|---|---|---|
| 1 | `重载图片类型` | `今日丝袜` added; `今日白丝` removed |
| 2 | `今日丝袜` | Serves the **黑丝** category |
| 3 | `今日黑丝` | The custom caption `今天的黑丝，请收好~` |
| 4 | `今日白丝` | No response — disabled, folder untouched on disk |

Then set `TodayImageCommandPrefix` to `每日` in the web console and `重载图片类型`: `每日黑丝` works, `今日黑丝` no
longer responds (V-CFG-3/V-CFG-4). Set it back before continuing.

## Scenario 4 — Manage images from chat (US3 · FR-016/FR-018/FR-019)

| Step | Send | Expect |
|---|---|---|
| 1 | `上传图片 黑丝` + attached image | `上传成功` with an 8-hex `图片ID` per image |
| 2 | `查看图片 黑丝` | Each image with its ID (forwarded message past the threshold) |
| 3 | `删除图片 黑丝 <id>` | `已删除图片：<id>`; the file is gone from disk |
| 4 | `上传图片 不存在的类型` | `不存在图片类型【不存在的类型】` — nothing written |
| 5 | `上传图片 黑丝` **from a non-master, non-whitelisted account** | `你不在图片上传白名单中。` — nothing written |
| 6 | `上传图片 黑丝` with a `.txt` attached | Counted as a failure; the category is unchanged |

After step 3, confirm the deleted image is no longer drawn — if it was today's pinned choice, the next `今日黑丝`
re-draws and re-pins rather than erroring (V-REC-3, FR-009).

## Scenario 5 — Failure paths reply, never crash (SC-005)

| Send | Expect |
|---|---|
| `今日黑丝` with the folder emptied | `【黑丝】还没有图片…` — and **no** record written (V-REC-5) |
| `删除图片 黑丝 zzz` | The 8-hex-ID usage hint |
| `今日黑丝` after corrupting `daily_records.json` to `{`  | A normal draw; warning logged, file rewritten (S-4) |
| `今日黑丝` after corrupting `categories.json` | A normal draw on default settings (V-OVR-2) |
| Any command with `TodayImageEnabled` off | No response at all (V-CFG-1) |

No case may produce a traceback in the reply or an unhandled exception in the log.

## Scenario 6 — Coexistence with TodayWaifu (FR-023 · SC-006)

With both plugins enabled in the same GsCore instance:

| Send | Expect |
|---|---|
| `今日老婆` | TodayWaifu answers, unchanged |
| `今日萝莉` | TodayWaifu answers, unchanged |
| `今日黑丝` | TodayImage answers |
| `今日老婆帮助` | TodayWaifu's help, not TodayImage's |
| `今日图片帮助` | TodayImage's help |

Collision check — create a folder named `老婆` and `重载图片类型`. Expect: the reload reply **names 老婆 as skipped**
because `今日老婆` belongs to another service, and `今日老婆` keeps working as TodayWaifu's command (V-CAT-5,
US2 AS6). A silent skip here is a defect.

Confirm the data trees stay separate:

```bash
ls <gsuid_core>/data/TodayImage
ls <gsuid_core>/data/TodayWaifu   # untouched by TodayImage
```

## Scenario 7 — Performance (SC-003)

```bash
# 5,000 small files in one category
python - <<'PY'
from pathlib import Path
d = Path('<gsuid_core>/data/TodayImage/压测')
d.mkdir(parents=True, exist_ok=True)
png = bytes.fromhex('89504e470d0a1a0a')
for i in range(5000):
    (d / f'{i}.png').write_bytes(png)
PY
```

Send `重载图片类型`, then `今日压测` twice. The **second** call (warm cache) must reply in under 1 second, and the
log must show no directory re-scan between the two — the TTL scan cache and the mtime byte cache are doing their
job (FR-025, research R7).

## Validation checklist

- [ ] `python -m unittest discover -s tests` passes (compat test passes or skips)
- [ ] S1: repeat draws identical; new day re-draws; users independent
- [ ] S2: new category live without a GsCore restart
- [ ] S3: alias, disable, caption override, prefix change all take effect on reload
- [ ] S4: upload / list / delete work; unauthorised and malformed uploads rejected
- [ ] S5: every failure path replies in plain text, no traceback
- [ ] S6: TodayWaifu unaffected; collisions reported, not silent
- [ ] S7: warm-cache draw < 1 s at 5,000 images
