# Feature Specification: TodayImage — 今日<类型> 本地图库每日抽图插件

**Feature Branch**: `001-daily-image-categories`

**Created**: 2026-09-08

**Status**: Draft

**Input**: User description: "refer to todaywaifu and https://docs.sayu-bot.com/CodePlugins/CookBook.html, build a new plugin that acts like 今日萝莉 of todaywaifu and respond to command like 今日黑丝 今日白丝 with customization of image type and send the images from local folders"

## Overview

A standalone GsCore (早柚核心 / Sayu-Bot) plugin, **TodayImage**, that reproduces the behaviour of TodayWaifu's
「今日萝莉」 command but generalises it across an arbitrary, operator-defined set of **image categories**.

Each category is a folder of images on disk. A category named `黑丝` is served by the command `今日黑丝`;
a category named `白丝` is served by `今日白丝`. Operators add a category by creating a folder — no code change.

As with 今日萝莉, a user's draw for a given category is **fixed for the whole day within a given chat**: asking
again returns the same image until the local date rolls over.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Daily draw from a category (Priority: P1)

A chat member sends `今日黑丝`. The bot replies with one image drawn from the `黑丝` local folder, together with a
short caption. If the same member sends `今日黑丝` again the same day in the same chat, they receive the identical
image. The next day they get a fresh draw.

**Why this priority**: This is the entire point of the plugin. Without it nothing else has value.

**Independent Test**: Place two images in a `黑丝` folder, send `今日黑丝` twice from the same account, confirm the
same image both times; simulate a date change and confirm a new draw. This alone is a shippable MVP.

**Acceptance Scenarios**:

1. **Given** the `黑丝` category folder contains at least one image and the category is enabled, **When** a user
   sends `今日黑丝`, **Then** the bot replies with exactly one image from that folder plus the configured caption.
2. **Given** a user already drew `今日黑丝` today in group G, **When** the same user sends `今日黑丝` again in
   group G, **Then** the bot replies with the same image as the first draw.
3. **Given** a user drew `今日黑丝` yesterday, **When** the local date has changed and the user sends `今日黑丝`,
   **Then** a new draw is performed and stored for the new day.
4. **Given** two different users in the same group, **When** both send `今日黑丝`, **Then** each user's draw is
   independent of the other's.
5. **Given** a user draws `今日黑丝` in group G and in group H on the same day, **When** both draws are compared,
   **Then** they are tracked separately per chat, matching 今日萝莉's per-chat scoping.
6. **Given** the `黑丝` category folder is empty or missing, **When** a user sends `今日黑丝`, **Then** the bot
   replies with a plain-text notice explaining that the category has no images, and stores no daily record.

---

### User Story 2 - Operator defines and customises categories (Priority: P1)

A bot operator wants a new `今日制服` command. They create a `制服` folder under the plugin's image root, drop
images in, and run the reload command. `今日制服` starts working without restarting GsCore. They can also disable a
category, give it extra command aliases, and override its caption — all from the GsCore web console.

**Why this priority**: "Customization of image type" is an explicit requirement; a hard-coded 黑丝/白丝 pair would
not satisfy it. Equal priority to US1 because the two together form the minimum useful product.

**Independent Test**: Create a new folder, invoke the reload command, and confirm the corresponding `今日X` command
answers. Disable it in config and confirm it stops answering.

**Acceptance Scenarios**:

1. **Given** GsCore is running, **When** an operator creates a new category folder with images and sends the
   reload command, **Then** `今日<新类型>` becomes usable without a GsCore restart.
2. **Given** a category is present on disk, **When** the operator disables it via the console configuration,
   **Then** its command stops responding while other categories keep working.
3. **Given** a category has configured aliases (e.g. `丝袜` for `黑丝`), **When** a user sends `今日丝袜`,
   **Then** the same category is served.
4. **Given** the operator changes the caption template for a category, **When** a user draws from it,
   **Then** the new caption text is used, with supported placeholders substituted.
5. **Given** the operator changes the command prefix from `今日` to something else, **When** a user sends
   `<新前缀><类型>`, **Then** the draw succeeds and the old prefix no longer responds.
6. **Given** a category folder name collides with a command already owned by another plugin, **When** the plugin
   loads, **Then** the collision is logged and the operator is told which category was skipped.

---

### User Story 3 - Operator manages images from chat (Priority: P2)

An authorised operator uploads images into a category directly from chat, lists what a category currently holds,
and deletes a specific image or the whole category folder — mirroring TodayWaifu's 上传萝莉图片 / 查看萝莉图片 /
删除萝莉图片 commands.

**Why this priority**: Convenient and expected by anyone used to TodayWaifu, but the plugin is fully usable if the
operator manages folders over SSH/FTP instead.

**Independent Test**: From a whitelisted account, send the upload command with an attached image, then the list
command, and confirm the new image appears with a stable short ID; delete it by that ID.

**Acceptance Scenarios**:

1. **Given** a user on the upload whitelist (or a bot master), **When** they send the upload command naming an
   existing category with images attached, **Then** the images are saved into that category folder and the reply
   lists each saved image's short ID.
2. **Given** a user NOT on the whitelist and not a master, **When** they send the upload command, **Then** the bot
   refuses and saves nothing.
3. **Given** an operator names a category that does not exist, **When** they upload, **Then** the bot reports the
   category is unknown and saves nothing.
4. **Given** a category holds images, **When** an operator sends the list command for it, **Then** the bot returns
   each image with its short ID, using a forwarded/merged message when the count is large.
5. **Given** an operator supplies a valid short ID, **When** they send the delete command, **Then** only that image
   is removed and subsequent draws no longer select it.
6. **Given** an operator sends the delete command with no ID, **When** the command is confirmed, **Then** every
   image in that category is removed and the count deleted is reported.
7. **Given** a non-image or oversized attachment, **When** an operator uploads it, **Then** it is rejected and
   counted as a failure in the reply, without corrupting the category.

---

### User Story 4 - Discoverability and help (Priority: P3)

A user who does not know the available categories sends a help/list command and receives the set of currently
usable `今日X` commands.

**Why this priority**: Quality-of-life. The plugin works without it.

**Independent Test**: With two categories on disk, send the help command and confirm both appear.

**Acceptance Scenarios**:

1. **Given** two enabled categories, **When** a user sends the plugin's help command, **Then** both `今日X`
   commands are listed along with the management commands.
2. **Given** no categories exist on disk yet, **When** a user sends the help command, **Then** the bot explains how
   to create a category folder.

---

### Edge Cases

- **Empty / missing category folder** → plain-text notice, no daily record written (US1 AS6).
- **Image deleted after the daily record was written** → the stored path no longer resolves; the plugin must
  re-draw for that day rather than erroring, and persist the replacement.
- **All images in a category deleted after a draw** → plain-text notice on re-ask.
- **Concurrent first draws** by the same user (double-tap / two adapters) → exactly one daily record is persisted
  and both replies show the same image.
- **Category folder named with leading/trailing whitespace, a dot prefix, or an empty name** → skipped, not
  registered as a command.
- **Category name that collides with an existing GsCore command** (e.g. another plugin's `今日老婆`) → skipped with
  a warning (US2 AS6).
- **Nested sub-folders inside a category** (e.g. `黑丝/画师A/`) → images are discovered recursively.
- **Non-image files inside a category** (`.txt`, `.DS_Store`, `Thumbs.db`) → ignored.
- **Very large category** (thousands of files) → directory scanning must be cached so peak-hour traffic does not
  re-walk the tree on every command.
- **Private chat vs group chat** → the at-mention prefix is omitted in private chats.
- **Date rollover mid-request** → a request that begins before midnight and completes after must not produce a
  record attributed to the wrong day in a way that corrupts state.
- **Two categories whose names differ only by case or surrounding whitespace** → treated as the same command;
  the collision is reported rather than silently shadowing.

## Requirements *(mandatory)*

### Functional Requirements

**Command surface**

- **FR-001**: The plugin MUST expose one draw command per enabled category, formed as `<配置前缀><类型名>`, with
  the prefix defaulting to `今日` — yielding `今日黑丝`, `今日白丝`, etc.
- **FR-002**: The plugin MUST derive the set of categories from the sub-folders of a configurable local image root
  directory, so that adding a folder adds a command.
- **FR-003**: The plugin MUST allow an operator to add command aliases for a category, and to disable individual
  categories, without deleting the folder.
- **FR-004**: The plugin MUST provide a reload command that re-scans the image root and updates the live command
  set without restarting GsCore.
- **FR-005**: The plugin MUST NOT register a command that would shadow a command already registered by another
  loaded plugin or by the plugin itself; such a category MUST be skipped and logged.

**Daily draw semantics**

- **FR-006**: A draw MUST be deterministic per (local date, user, chat, category): repeat invocations on the same
  day in the same chat MUST return the identical image.
- **FR-007**: The daily record MUST reset when the server's local date changes.
- **FR-008**: Draws MUST be independent across users, across chats, and across categories.
- **FR-009**: If the image recorded for today no longer exists on disk, the plugin MUST silently re-draw and
  persist the replacement rather than failing.
- **FR-010**: Concurrent first draws for the same (date, user, chat, category) MUST result in exactly one
  persisted record, with every concurrent reply showing that record's image.

**Image delivery**

- **FR-011**: The plugin MUST send the drawn image as an image message, read from the local file, together with a
  configurable caption.
- **FR-012**: The caption template MUST be configurable globally and overridable per category, supporting at least
  a `{类型}` / category-name placeholder.
- **FR-013**: In group chats the plugin MUST optionally at-mention the requester, controlled by configuration; in
  private chats the at-mention MUST be omitted.
- **FR-014**: The plugin MUST recognise the common image extensions `.jpg .jpeg .png .webp .gif .bmp`
  (case-insensitively) and ignore all other files.
- **FR-015**: Image discovery MUST be recursive within a category folder.

**Management**

- **FR-016**: An authorised user MUST be able to upload one or more images into a named existing category from
  chat, receiving per-image short IDs in the reply and a count of any rejected attachments.
- **FR-017**: Upload authorisation MUST be limited to GsCore masters plus a configurable whitelist.
- **FR-018**: An authorised user MUST be able to list a category's images with their short IDs.
- **FR-019**: An authorised user MUST be able to delete a single image by short ID, or all images in a category.
- **FR-020**: Uploaded content MUST be validated as an image and rejected above a configurable size limit.
- **FR-021**: The plugin MUST expose a help command listing the currently available category commands and the
  management commands.

**Configuration & isolation**

- **FR-022**: All configuration MUST be editable from the GsCore web console and MUST persist across plugin
  upgrades (i.e. stored outside the plugin source tree).
- **FR-023**: The plugin MUST be installable alongside TodayWaifu without conflicting with its commands,
  configuration, or stored data.
- **FR-024**: The plugin MUST provide a master switch that disables every command it owns.
- **FR-025**: Directory scans MUST be cached with a bounded time-to-live so that repeated commands do not re-walk
  the image tree on every message.

### Key Entities

- **Category (图片类型)**: A named collection of images backed by one folder under the image root. Attributes:
  display name (= folder name), enabled flag, alias list, caption override, resolved command names, image list.
- **Image**: A file on disk inside a category. Attributes: absolute path, short ID derived from the file name,
  extension.
- **Daily Record**: One user's fixed choice for one category on one local date in one chat. Attributes: date,
  chat key, user key, category name, chosen image path, timestamp.
- **Plugin Configuration**: Operator-controlled settings — master switch, image root path, command prefix,
  caption template, at-mention flag, upload whitelist, upload size limit, cache TTL, per-category overrides.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given a folder of images, an operator can go from zero to a working `今日<类型>` command in under
  two minutes and without restarting GsCore.
- **SC-002**: 100% of repeat invocations by the same user, in the same chat, for the same category, on the same
  local date return the identical image.
- **SC-003**: A draw against a warm cache replies in under 1 second for a category holding up to 5,000 images.
- **SC-004**: Adding a category requires zero code edits and zero edits to files inside the plugin's source tree.
- **SC-005**: Every failure path — missing folder, empty folder, deleted image, unauthorised upload, bad upload,
  unknown category — produces an actionable plain-text reply rather than a silent drop or a stack trace.
- **SC-006**: With TodayWaifu installed and enabled in the same GsCore instance, all TodayWaifu commands and all
  TodayImage commands continue to behave as they do in isolation.

## Assumptions

- The plugin targets GsCore (早柚核心) and follows the CookBook plugin conventions: a `Plugins(...)` declaration,
  `SV`-registered triggers, console-editable `StringConfig` settings, and `MessageSegment` replies.
- "Acts like 今日萝莉" is read as: one image per user per day per chat, fixed for the day, drawn from a local
  folder, delivered with a caption and optional at-mention. TodayWaifu's social mechanics around 今日萝莉 —
  抢 (steal), 送 (gift), 离婚 (divorce) — are **out of scope** for this feature.
- Remote/HTTP image sources are **out of scope**; local folders only. The design should not preclude adding a
  remote source later.
- The plugin is a new, independent plugin living in this repository; it does not modify TodayWaifu, and it does not
  read or write TodayWaifu's configuration or daily records.
- The bot deployment already has GsCore installed and at least one adapter connected; the operator has filesystem
  access to the GsCore data directory.
- Command matching is exact-name based (`今日黑丝`), not fuzzy or natural-language.
- The default set of categories ships empty; `黑丝` and `白丝` are examples the operator creates, not bundled
  content. No image content is distributed with the plugin.
