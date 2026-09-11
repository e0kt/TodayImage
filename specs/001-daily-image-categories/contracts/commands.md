# Contract: Chat Command Surface

**Feature**: `001-daily-image-categories`

The command surface is this plugin's public interface — the bot equivalent of a CLI. Every entry below fixes the
trigger type, the argument shape, who may invoke it, and what the bot replies.

Notation: `<类型>` is a category name, `«前缀»` is the configured command prefix (default `今日`).

## SV registry

Services are split so an operator can disable one capability from the console without losing the others.
Priorities start at 20 so that, on any keyword collision, a plugin registered at a lower number (TodayWaifu occupies
0–10) wins and TodayImage's handler never runs (research R3).

| SV name | `pm` | priority | Owns |
|---|---|---|---|
| `今日图片-帮助` | 6 | 20 | `«前缀»图片帮助` |
| `今日图片-图库管理` | 1 (master) | 21 | 查看 / 删除 / 重载 |
| `今日图片-图片上传` | 6 (whitelist-checked in handler) | 21 | 上传 |
| `今日图片-每日抽取` | 6 | 25 | the dynamic `«前缀»<类型>` commands |

`Plugins('TodayImage', disable_force_prefix=True, allow_empty_prefix=True)` — commands are usable bare, with no
global bot prefix, matching TodayWaifu.

---

## 1. `«前缀»<类型>` — daily draw

- **Trigger**: `on_fullmatch(keyword, block=True)`, registered dynamically per category and per alias. The keyword
  is `«前缀» + <类型>`, default prefix `今日` — hence `今日黑丝`, `今日白丝`. (FR-001.)
- **Auth**: none.
- **Args**: none. Exact match only; `今日黑丝吗` does not trigger.
- **AI tool**: declares `to_ai` so the command is reachable through GsCore's AI bridge.

| Condition | Reply |
|---|---|
| Success | *(group, if at-mention on)* at-mention + newline, then caption, then the image |
| Category has no images | `【<类型>】还没有图片，请先把图片放进 <路径> 或使用「上传图片 <类型>」。` |
| Master switch off | *(no reply — the handler returns immediately)* |

The image is read from the local file and sent as an image segment alongside the caption. (FR-011.)

Caption default `你今天的{类型}来啦！`; placeholder `{类型}` = category name. Per-category override wins over the
global template. (FR-012.)

**Behaviour**: fixed per `(date, chat, user, category)`; see [data-model.md](../data-model.md) → DailyRecord.

---

## 2. `上传图片 <类型>` — upload

- **Trigger**: `on_command(('上传图片', '图片上传'), block=True)`; category name arrives in `ev.text`.
- **Auth**: GsCore master **or** a user on `TodayImageUploadWhitelist`. Masters need no whitelist entry.
- **Args**: `ev.text` = category name (quotes and whitespace stripped); one or more images attached to the message.

| Condition | Reply |
|---|---|
| Success | `【<类型>】上传成功` / `成功：N 张` / `图片ID：aaaaaaaa, bbbbbbbb` (+ `失败：M 张` when any were rejected) |
| Not authorised | `你不在图片上传白名单中。` |
| No category given | `请输入类型名称，例如：上传图片 黑丝，并附带图片。` |
| Unknown category | `不存在图片类型【<类型>】，请先创建对应文件夹或使用「重载图片类型」。` |
| No image attached | `请同时发送图片和命令，例如：上传图片 <类型>` |
| All attachments rejected | `【<类型>】上传图片失败，请确认消息里附带的是图片。` |

**Side effects**: files written as `<类型>/img_<epoch_ms>_<index><suffix>`; the scan cache for that category is
invalidated. Never creates a category folder — the folder must already exist (US3 AS3).

---

## 3. `查看图片 <类型>` — list

- **Trigger**: a single `on_command(('查看图片', '图片列表'), block=True)`. `_check_command` is a `startswith`
  test, so this one trigger serves both the bare form (`ev.text` empty → category overview) and the argument
  form. Registering an `on_fullmatch` alongside it would make the bare message match **two** triggers in the
  same SV, leaving which one runs to `block` ordering and dict insertion order — avoided deliberately.
- **Auth**: master (`pm=1` on the owning SV).

| Condition | Reply |
|---|---|
| No argument | One line per category: name, image count, enabled flag, aliases |
| With `<类型>`, has images | Alternating `图片ID：<short_id>` and the image; sent as a forwarded/merged node message once the count exceeds the forward threshold (default 10) |
| With `<类型>`, empty | `【<类型>】暂无图片。` |
| Unknown category | `不存在图片类型【<类型>】。` |

---

## 4. `删除图片 <类型> [图片ID]` — delete

- **Trigger**: `on_command('删除图片', block=True)`.
- **Auth**: master.
- **Args**: `ev.text` = `<类型>` optionally followed by an 8-hex-character short ID.

| Condition | Reply |
|---|---|
| Valid ID, unique match | `已删除图片：<short_id>` |
| Valid ID, matches several files | `图片ID <short_id> 匹配到 N 个文件，请直接在文件系统中删除。` — deletes nothing (V-IMG-5) |
| Valid ID, no match | `未找到图片ID：<short_id>` |
| No ID | Deletes every image in the category: `已删除【<类型>】全部图片，共 N 张。` |
| Malformed ID | `请提供 8 位图片ID，例如：删除图片 黑丝 abcd1234\n不加ID则删除该类型全部图片` |
| Unknown category | `不存在图片类型【<类型>】。` |

**Side effects**: removes files only — never the category folder itself, so the command survives. Invalidates the
scan cache. Daily records pointing at a deleted file re-draw on next use (V-REC-3).

---

## 5. `重载图片类型` — reload

- **Trigger**: `on_fullmatch(('重载图片类型', '刷新图片类型'), block=True)`.
- **Auth**: master.
- **Effect**: re-scans the image root, re-applies `categories.json`, re-resolves commands, and updates the live
  trigger table — added commands registered, removed/disabled ones unregistered. No GsCore restart. (FR-004, SC-001.)

Reply reports, in order: registered command count, added commands, removed commands, and skipped categories with the
reason (collision with another plugin, alias conflict, duplicate name). Skips are always shown — a silently dropped
category is the failure mode this command exists to prevent (V-CAT-5).

---

## 6. `«前缀»图片帮助` — help

- **Trigger**: `on_fullmatch(('今日图片帮助', '图片帮助'), block=True)`, priority 20 so it is registered before any
  `on_command` prefix trigger that could claim it.
- **Auth**: none.
- **Reply**: the live `«前缀»<类型>` command list plus the management commands. When no category exists, explains how
  to create one instead of printing an empty list. (FR-021, US4 AS2.)
- Also calls `register_help('TodayImage', '今日图片帮助', icon)` at import, wrapped in `try/except` so a failure only
  logs.

---

> **Superseded in part by feature 002.** The rule below that every failure path must reply with actionable plain
> text (SC-005) now applies to **master-gated commands only**. Feature 002's silence contract makes every *public*
> negative — unknown type, blocklisted command, empty folder, malformed input — produce no reply at all, so the
> command surface cannot be probed. See
> [002 contracts/commands.md](../../002-dynamic-category-lookup/contracts/commands.md). The per-folder `on_fullmatch`
> registration described in §1 is also replaced there by a single dynamic prefix trigger.

## Cross-cutting rules

- **Master switch** (`TodayImageEnabled`) off → no command in this plugin responds. (FR-024.)
  **Implementation note**: category commands are registered at import *regardless* of the switch, and every handler
  returns immediately when it is off. Gating *registration* on the switch was the obvious reading, but it traps the
  operator: after turning the switch back on in the console the commands would still be unregistered, so they would
  need a core restart — and "I changed the setting and nothing happened" is the hardest class of problem to diagnose.
  The user-visible behaviour is identical either way (no reply).
- **Private chats** → at-mention segments are stripped before sending. (FR-013.)
- **Blocking** → every command uses `block=True`, so a handled message stops there. Combined with `on_fullmatch`
  (never a `今日` prefix catch-all) and priority 20+, this cannot swallow another plugin's command. (FR-023, SC-006.)
- **Errors** → every failure path replies with actionable plain text. No path may raise out of a handler or reply
  with a traceback. (SC-005.)
