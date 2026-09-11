# Feature Specification: 动态类型解析、隐藏类型清单、屏蔽 TodayWaifu 命令

**Feature Branch**: `002-dynamic-category-lookup`

**Created**: 2026-09-11

**Status**: Draft

**Input**: User description: "发图不局限于黑丝/白丝 而是将今日【】命令自动寻找 data/todayimage 里相对应的文件夹，比如今日黑丝就会随机抽取黑丝文件夹中的文件，另外不要暴露本地允许的文件夹名字和可执行命令列表。注意到 todaywaifu 有一些今日命令如今日老婆和今日萝莉，今日战双老婆等等，将这些命令加入不回复的名单"

## Overview

Feature 001 registers **one trigger per folder**, discovered at import time. That has two consequences the operator
feels: a new folder is dead until `重载图片类型` runs, and the live command list is enumerable — the help text and
the service registry both spell out exactly which categories exist.

This feature replaces that with **one dynamic trigger**. `今日<任意文字>` is matched as a prefix, the text after
`今日` is resolved against `data/TodayImage/` at request time, and an image is sent only if a matching folder
exists. Nothing is pre-registered per folder.

Three consequences follow, and all three are the point of the feature:

1. **A new folder works immediately** — no reload, no restart.
2. **Nothing enumerates the categories.** Unknown input is answered with silence, not with "no such type", so the
   command surface cannot be probed and the help text no longer lists what exists.
3. **A blocklist is required.** A `今日` prefix trigger sees TodayWaifu's `今日老婆` / `今日萝莉` / `今日战双老婆`
   too, so those must be excluded explicitly and never answered.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Any folder becomes a command, with no reload (Priority: P1)

An operator drops a `制服` folder into `data/TodayImage/` and immediately sends `今日制服`. The bot replies with an
image from that folder. No reload command, no restart, no configuration.

**Why this priority**: This is the feature. It also removes the single biggest operational papercut in 001.

**Independent Test**: Create a folder with images while the core is running, send `今日<folder>`, get an image.

**Acceptance Scenarios**:

1. **Given** `data/TodayImage/制服/` exists with images and the core has been running since before it was created,
   **When** a user sends `今日制服`, **Then** the bot replies with one image from that folder.
2. **Given** a folder is renamed from `制服` to `校服` while the core runs, **When** a user sends `今日校服`,
   **Then** it works, and **When** a user sends `今日制服`, **Then** the bot stays silent.
3. **Given** a folder whose name contains spaces or mixed case, **When** the matching `今日` command is sent with the
   same name, **Then** it resolves (trimmed, case-insensitively).
4. **Given** the per-day rules from feature 001, **When** the same user repeats `今日制服` the same day in the same
   chat, **Then** the identical image is returned, and different users in that chat do not collide.

---

### User Story 2 - The category and command list is never disclosed (Priority: P1)

A curious group member tries `今日abc`, `今日老婆`, `今日图片帮助` and various guesses, and learns nothing about
which folders exist on the host or which admin commands are available.

**Why this priority**: Explicitly requested, and it is not additive — it changes what existing replies may contain,
so it must land with US1 rather than after.

**Independent Test**: Send a dozen non-existent `今日X` variants and the help command from a non-master account;
confirm no reply names any folder or any management command.

**Acceptance Scenarios**:

1. **Given** a folder `黑丝` exists and `不存在的` does not, **When** a user sends `今日不存在的`, **Then** the bot
   replies **nothing at all** — not an error, not a hint, not a list.
2. **Given** any set of folders, **When** a non-master user sends the help command, **Then** the reply does not
   enumerate folder names, does not enumerate admin commands, and does not print the image root path.
3. **Given** a folder exists but is empty, **When** a user sends its `今日` command, **Then** the reply must not
   confirm the folder's existence by naming it.
4. **Given** a master user sends the management listing command, **Then** the full folder list **is** shown —
   disclosure is restricted by permission, not removed outright.
5. **Given** any failure (missing folder, unreadable folder, bad config), **When** it occurs for a non-master,
   **Then** the reply never contains a filesystem path.

---

### User Story 3 - TodayWaifu's 今日 commands are never answered (Priority: P1)

With both plugins installed, `今日老婆`, `今日萝莉`, `今日战双老婆`, `今日异环老婆`, `今日老公` and their variants
behave exactly as TodayWaifu defines. TodayImage never replies to them, never double-replies alongside TodayWaifu,
and never answers them even when TodayWaifu is disabled or uninstalled.

**Why this priority**: A `今日` prefix trigger is broad by construction; without this the feature actively breaks a
plugin the operator already runs.

**Independent Test**: With both plugins loaded, send each TodayWaifu `今日` command and confirm exactly one reply,
from TodayWaifu. Then disable TodayWaifu and confirm TodayImage still stays silent on those commands.

**Acceptance Scenarios**:

1. **Given** both plugins are loaded, **When** a user sends `今日老婆`, **Then** TodayWaifu answers and TodayImage
   does not — exactly one reply.
2. **Given** TodayWaifu is disabled or uninstalled, **When** a user sends `今日萝莉`, **Then** TodayImage stays
   silent rather than treating `萝莉` as a category.
3. **Given** an operator creates a folder literally named `老婆`, **When** a user sends `今日老婆`, **Then**
   TodayImage still does not answer — the blocklist wins over a folder of the same name.
4. **Given** a blocklisted command with a suffix such as `今日老婆帮助` or `今日萝莉列表`, **When** it is sent,
   **Then** TodayImage stays silent.
5. **Given** an operator adds an entry to the blocklist in the console, **When** that command is sent,
   **Then** TodayImage stays silent, without a restart.
6. **Given** any other plugin owns a `今日X` command, **When** it is sent, **Then** that plugin still receives and
   handles it — TodayImage must not suppress other plugins' commands.

---

### Edge Cases

- **`今日` alone**, with no suffix → no reply (a prefix trigger must not fire on the bare prefix).
- **`今日黑丝吗` / `今日黑丝 额外文字`** → the suffix is not an exact folder name; no reply. Trailing whitespace is
  trimmed before matching.
- **Blocklisted name that is also a real folder** → blocklist wins (US3 AS3).
- **Folder created, then deleted, mid-day** → a pinned record pointing at the deleted folder re-draws; if the whole
  folder is gone, silence.
- **Folder name that collides with the plugin's own management commands** (e.g. a folder named `图片帮助`) → the
  management command wins; the folder is unreachable.
- **Very many folders** → resolution must not become a per-message full-tree walk.
- **Name differing only by case or surrounding whitespace** → resolves to the same folder.
- **A user probing rapidly with many unknown `今日X`** → each is silent and cheap; no scan storm.
- **Plugin's own JSON state files** (`config.json` etc.) are files, not folders, and must never resolve.

## Requirements *(mandatory)*

### Functional Requirements

**Dynamic resolution**

- **FR-101**: The plugin MUST match `今日<文字>` with a single dynamic trigger rather than one trigger per folder.
- **FR-102**: The text after the prefix MUST be resolved against the direct sub-folders of the image root at request
  time, trimmed and case-insensitively.
- **FR-103**: A folder added, renamed, or removed while the core is running MUST take effect without a restart and
  without a reload command, subject only to the cache freshness in FR-108.
- **FR-104**: Resolution MUST NOT traverse outside the image root; `..`, path separators, and absolute paths MUST
  never resolve.
- **FR-105**: A resolved folder MUST retain feature 001's per-day semantics: fixed per (day, chat, user, category),
  no two users in one chat sharing an image, and a Beijing-midnight reset.
- **FR-106**: The plugin MUST NOT suppress `今日X` commands owned by other plugins.
- **FR-107**: The bare prefix `今日`, and any suffix that is not an exact folder name, MUST NOT produce a reply.
- **FR-108**: Folder resolution MUST be served from a bounded cache so repeated or hostile input does not trigger a
  filesystem walk per message.

**Non-disclosure**

- **FR-109**: An unresolved `今日X` MUST produce **no reply whatsoever**.
- **FR-110**: Replies available to non-master users MUST NOT enumerate folder names or management commands, and MUST
  NOT contain filesystem paths.
- **FR-111**: The public help MUST still explain *how* the feature works without revealing *what* exists.
- **FR-112**: Master-only commands MAY continue to enumerate folders and paths; the restriction is by permission.
- **FR-113**: An empty but existing folder MUST NOT be distinguishable from a non-existent one by a non-master.

**Blocklist**

- **FR-114**: The plugin MUST ship a default blocklist covering TodayWaifu's `今日` commands, at minimum:
  `今日老婆`, `今日老公`, `今日萝莉`, `今日战双老婆`, `今日异环老婆`, and their `帮助` / `列表` / `离婚` / `上传`
  variants.
- **FR-115**: A blocklisted command MUST produce no reply even when a folder of that name exists.
- **FR-116**: The blocklist MUST be operator-extendable from the console and MUST take effect without a restart.
- **FR-117**: Blocklist matching MUST cover both the exact command and any command extending a blocked base name.
- **FR-118**: The blocklist MUST be matched before folder resolution, so a blocked name never touches the filesystem.

### Key Entities

- **Image Root**: `data/TodayImage/`; its direct sub-folders are the categories. Unchanged from 001.
- **Category Resolution**: a request-time lookup from command suffix → folder, cached, case/whitespace-insensitive.
- **Blocklist**: an ordered set of command names TodayImage must never answer; default set plus operator additions.
- **Daily Record**: unchanged from feature 001.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-101**: A folder created while the core runs is usable within the cache TTL, with no reload and no restart.
- **SC-102**: Across a probe of at least 20 unknown, blocklisted, and malformed `今日X` inputs, zero replies are
  produced and zero folder names or paths are disclosed.
- **SC-103**: With both plugins loaded, every TodayWaifu `今日` command produces exactly one reply, from TodayWaifu.
- **SC-104**: With TodayWaifu unloaded, every command in the default blocklist still produces zero replies from
  TodayImage.
- **SC-105**: No other plugin's `今日X` command stops working when TodayImage is installed.
- **SC-106**: Resolution of an unknown suffix costs no filesystem walk on a warm cache.
- **SC-107**: Feature 001's daily guarantees (same-image-on-repeat, no same-day collisions within a chat,
  Beijing reset) continue to hold.

## Assumptions

- The command prefix stays operator-configurable (default `今日`), and the dynamic trigger follows it.
- "不要暴露" is read as: **public** output discloses nothing; **master-only** commands may still enumerate, since the
  operator needs to see the folder list to manage it (FR-112). Removing it for masters too would make the plugin
  unmanageable from chat.
- Silence is the correct response to unknown input, accepting that a typo also yields silence. An "unknown type"
  reply is exactly the probing oracle the requirement forbids.
- Per-folder trigger registration from feature 001 is **removed**, not kept alongside; two mechanisms answering the
  same message is the double-reply bug this feature must avoid.
- `重载图片类型` is retained as a cache-invalidation command for operators who do not want to wait out the TTL, but
  is no longer required for correctness.
- The blocklist covers the `今日` command space only. TodayWaifu commands without that prefix (e.g. `来点老婆`)
  are unreachable by this plugin's trigger and need no entry.
- Feature 001's storage, config and coexistence guarantees remain in force; this feature changes the command
  surface, not the data model.
