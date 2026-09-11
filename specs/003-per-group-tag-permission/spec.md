# Feature Specification: 分群标签授权

**Feature Branch**: `003-per-group-tag-permission`

**Created**: 2026-09-11

**Status**: Draft

**Input**: User description: "新的需求，我需要确定对应群可以发的图，在每个群发送新请求 如今日黑丝 今日白丝之前，需要admin用户发送 TodayImage允许【tag名字】才获得访问的权限，这样我可以针对不同群聊去设置不同的发图尺度和类别 同时私聊不受影响"

## Overview

After feature 002, any folder under `data/TodayImage/` is drawable from **any** chat. That is wrong for a bot in
multiple groups: the acceptable content in one group is not acceptable in another.

This feature adds a **per-group allowlist of tags**. In a group, `今日<类型>` works only after a group admin has run
`TodayImage允许<类型>` in **that** group. Each group is configured independently, so the operator can run a strict
group and a permissive one from one bot. **Direct chats are unaffected** and keep working exactly as today.

The allowlist is **deny-by-default**: a group that has authorised nothing can draw nothing. That is what makes the
feature a safety control rather than a convenience, and it is a **breaking change** for groups that work today —
see Assumptions.

Unauthorised requests stay **silent**, inheriting feature 002's disclosure contract: a user must not be able to
discover which tags exist, nor which are merely unauthorised here, by watching for different replies.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A group admin opens a tag for their group (Priority: P1)

An admin of group A sends `TodayImage允许黑丝`. From then on, members of group A can use `今日黑丝`. Members of
group B, where nothing has been authorised, still get nothing from `今日黑丝`.

**Why this priority**: This is the feature. Without it nothing else has value.

**Independent Test**: In a fresh group, confirm `今日黑丝` does nothing; have an admin authorise `黑丝`; confirm it
now works; confirm a second group is unaffected.

**Acceptance Scenarios**:

1. **Given** group A has authorised nothing, **When** a member sends `今日黑丝`, **Then** there is no reply.
2. **Given** an admin of group A sends `TodayImage允许黑丝`, **Then** the bot confirms, and a subsequent `今日黑丝`
   in group A returns an image.
3. **Given** group A has authorised `黑丝`, **When** a member of group A sends `今日白丝`, **Then** there is no
   reply — authorisation is per tag, not per group-wide toggle.
4. **Given** group A has authorised `黑丝`, **When** a member of group **B** sends `今日黑丝`, **Then** there is no
   reply — authorisation does not leak between groups.
5. **Given** a tag is authorised, **When** the bot restarts, **Then** it is still authorised.
6. **Given** an admin authorises a tag that is already authorised, **Then** the bot reports it was already allowed
   and nothing is duplicated.
7. **Given** the admin writes the command with the bracket form `TodayImage允许【黑丝】` or with a space
   `TodayImage允许 黑丝`, **Then** it is accepted identically.

---

### User Story 2 - Only admins can change a group's tags (Priority: P1)

An ordinary member cannot widen what their group is allowed to see. Group admins, group owners, superusers and the
bot master can.

**Why this priority**: An allowlist any member can edit is not a control.

**Independent Test**: From an ordinary account, send `TodayImage允许黑丝` in a group and confirm nothing changes.
Repeat as an admin and confirm it does.

**Acceptance Scenarios**:

1. **Given** an ordinary member (`user_pm=6`), **When** they send `TodayImage允许黑丝`, **Then** the tag is not
   authorised.
2. **Given** a group admin (`user_pm=3`) or group owner (`user_pm=2`), **When** they send it, **Then** it succeeds.
3. **Given** the bot master (`user_pm=0`) or a superuser (`user_pm=1`), **When** they send it, **Then** it succeeds.
4. **Given** an admin revokes a tag with `TodayImage禁止黑丝`, **Then** `今日黑丝` stops working in that group.
5. **Given** an admin lists the group's tags, **Then** they see exactly what is authorised **for this group**.

---

### User Story 3 - Direct chats are unaffected (Priority: P1)

A user messaging the bot privately keeps the behaviour of feature 002: every existing tag is drawable, with no
authorisation step.

**Why this priority**: Explicitly required, and it is the escape hatch that keeps the bot usable while groups are
being configured.

**Independent Test**: Without authorising anything anywhere, send `今日黑丝` in a direct chat and get an image.

**Acceptance Scenarios**:

1. **Given** no group has authorised anything, **When** a user sends `今日黑丝` in a direct chat, **Then** they
   receive an image.
2. **Given** a tag is revoked in every group, **When** it is requested in a direct chat, **Then** it still works.
3. **Given** a direct chat, **When** the authorisation commands are sent there, **Then** the bot explains they only
   apply inside a group rather than silently doing nothing.
4. **Given** feature 001's per-day rules, **When** a tag is drawn in a direct chat, **Then** the daily pin and the
   Beijing reset behave exactly as before.

---

### User Story 4 - An admin can see and audit a group's configuration (Priority: P2)

An admin lists what their group currently allows, and can tell the difference between "this tag is not authorised
here" and "this tag does not exist on the server".

**Why this priority**: Without it, a silent `今日黑丝` is undiagnosable — but the plugin is usable without it.

**Independent Test**: As an admin, list the group's tags before and after an authorisation and see the change.

**Acceptance Scenarios**:

1. **Given** a group with two authorised tags, **When** an admin lists them, **Then** both are shown.
2. **Given** a group with nothing authorised, **When** an admin lists, **Then** the reply says so and explains how
   to authorise.
3. **Given** an admin authorises a tag with no matching folder on the server, **Then** the bot accepts it but warns
   that no such folder currently exists.
4. **Given** an ordinary member sends the list command, **Then** they learn nothing.

---

### Edge Cases

- **Empty tag** (`TodayImage允许` with nothing after) → usage hint to the admin, no change.
- **Tag differing by case or whitespace** → treated as the same tag as the stored one.
- **Bracket forms** `【】`, `[]`, `「」` around the tag → stripped.
- **Revoking a tag that was never authorised** → reported as such, not an error.
- **A folder deleted after its tag was authorised** → the authorisation remains (it is about permission, not
  existence), and the draw is silent because the tag no longer resolves.
- **A tag authorised before its folder exists** → works as soon as the folder appears, with no second command.
- **Group ID appearing as both string and int** across adapters → must be the same group.
- **Authorisation commands sent in a direct chat** → explained, not silently ignored (US3 AS3).
- **A blocklisted command** (`今日老婆`) → stays blocked regardless of any group authorisation; the blocklist is not
  overridable per group.
- **Concurrent authorisations in one group** → both persist; no lost update.
- **Corrupt permissions file** → treated as empty, which fails closed (groups allow nothing) rather than open.

## Requirements *(mandatory)*

### Functional Requirements

**Gate**

- **FR-201**: In a group, a tag MUST be drawable only if that group has authorised it.
- **FR-202**: Authorisation MUST be per group and per tag; it MUST NOT leak between groups.
- **FR-203**: Groups MUST be deny-by-default: a group with no authorisations can draw nothing.
- **FR-204**: Direct chats MUST NOT be gated; every existing tag stays drawable there (FR-206 aside).
- **FR-205**: An unauthorised request in a group MUST produce **no reply**, indistinguishable from an unknown tag,
  a blocklisted command, or an empty folder — feature 002's silence contract is preserved.
- **FR-206**: The blocklist MUST take precedence over any group authorisation; a group MUST NOT be able to
  authorise its way to a blocklisted command.
- **FR-207**: The gate MUST be evaluated without a filesystem access beyond the existing cached lookups.

**Admin commands**

- **FR-208**: `TodayImage允许<tag>` MUST authorise a tag for the current group.
- **FR-209**: `TodayImage禁止<tag>` MUST revoke it.
- **FR-210**: A list command MUST show the tags authorised for the current group.
- **FR-211**: These commands MUST be restricted to group admins and above (`user_pm <= 3`: group admin, group
  owner, superuser, master).
- **FR-212**: Tag arguments MUST be accepted with or without surrounding brackets and whitespace, and matched
  case-insensitively.
- **FR-213**: Authorising a tag with no matching folder MUST succeed but warn the admin.
- **FR-214**: Authorisation commands used in a direct chat MUST reply explaining they apply only within a group.
- **FR-215**: Admin replies MAY name tags for **their own group**; they MUST NOT enumerate the server's folders or
  other groups' configuration.

**Persistence**

- **FR-216**: Authorisations MUST survive a bot restart.
- **FR-217**: Writes MUST be atomic and MUST NOT lose a concurrent update within the same group.
- **FR-218**: A missing or corrupt permissions file MUST be treated as empty — failing **closed**, never open.
- **FR-219**: Group identity MUST be normalised so an adapter sending a numeric vs string group id refers to one
  group.

### Key Entities

- **GroupPermission**: one group's authorised tag set, with an audit trail of who changed it and when.
- **Tag**: a normalised category name; the same identity used by feature 002's category index.
- **Gate Decision**: the per-request outcome combining blocklist, group authorisation, tag resolution and emptiness.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-201**: A tag authorised in group A is drawable in A and produces no reply in group B, in the same minute.
- **SC-202**: A group with no authorisations produces zero replies across every tag on the server.
- **SC-203**: Direct chats behave identically before and after this feature, verified by feature 002's scenarios.
- **SC-204**: An ordinary member cannot change any group's authorisations by any command in this feature.
- **SC-205**: Authorisations survive a restart with no manual step.
- **SC-206**: Unauthorised, unknown, blocklisted and empty requests remain mutually indistinguishable to a
  non-admin.
- **SC-207**: An admin can determine why a tag is not working in their group using only admin commands.

## Assumptions

- **"admin用户" maps to GsCore `user_pm <= 3`** — group admin (3), group owner (2), superuser (1), master (0).
  GsCore documents these levels in `sv.py` and real events on this bot carry `user_pm` of 0, 3 and 6, so the
  distinction is available from the adapter and does not need a separate list.
- **Deny-by-default is a breaking change.** Groups that work today will stop until an admin authorises tags. That is
  inherent to the request ("需要 admin 发送…才获得访问权限") and is the safe direction. A console setting will allow
  seeding the default tag set for **new** groups, defaulting to empty.
- **"tag名字" is the category/folder name** from feature 002 — the same identity, normalised the same way. The
  brackets in `【tag名字】` are read as a placeholder marker, but the literal bracket form is accepted too.
- Authorisation is about **permission, not existence**: a tag may be authorised before its folder exists or after it
  is deleted. The two are resolved independently at draw time.
- Per-group authorisation does not change per-day semantics; the daily pin remains keyed by chat, so a group and a
  direct chat already have independent draws.
- The command name keeps the user's `TodayImage` prefix, which cannot collide with the `今日` dynamic trigger.
- Group authorisation cannot override the blocklist; those two controls stack rather than compete.
