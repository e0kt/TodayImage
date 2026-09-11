# Quickstart & Validation: 分群标签授权

**Feature**: `003-per-group-tag-permission` | **Date**: 2026-09-11

Contracts: [commands](./contracts/commands.md) · [config](./contracts/config.md) · [storage](./contracts/storage.md).

## Prerequisites

- TodayImage installed and **restarted** so features 002 and 003 are both live.
- Two groups available, and an account that is admin in at least one.
- An ordinary (non-admin) account in the same group, for the negative tests.

> **Read before judging any result.** Two unresolved issues from earlier features apply here:
> 1. Feature 002 was never restarted into the running core, so the live bot is still on feature 001.
> 2. Per [002 research R0](../002-dynamic-category-lookup/research.md), replies leave GsCore but do not arrive in
>    QQ. Until that is fixed, **a correctly-authorised draw still looks like a failure.**
>
> Confirm delivery works at all before concluding this feature is broken.

## Unit tests

```bash
cd <TodayImage>
python -m unittest discover -s tests -v
```

Expected: green, with `test_group_permissions.py` present and feature 001's `test_daily_store.py` /
`test_daily_draw.py` passing **unmodified**.

---

## Scenario 1 — Deny by default (US1 · FR-203 · SC-202)

In a group where nothing has been authorised, from any account:

| Send | Expect |
|---|---|
| `今日黑丝` | **No reply** |
| `今日白丝` | **No reply** |
| any other real tag | **No reply** |

A reply here means the gate is not applied, or is failing open.

## Scenario 2 — An admin opens one tag (US1 · FR-201/202)

As a **group admin** in group A:

| Step | Send | Expect |
|---|---|---|
| 1 | `TodayImage允许黑丝` | `已允许本群使用【黑丝】。` |
| 2 | `今日黑丝` | An image |
| 3 | `今日白丝` | **No reply** — per tag, not per group |
| 4 | `TodayImage允许黑丝` again | `本群已经允许【黑丝】了。` |
| 5 | `TodayImage允许【白丝】` (brackets) | Accepted; the tag is `白丝`, not `【白丝】` |
| 6 | `TodayImage允许 白丝` (space) | Reported as already allowed |

Then in **group B**, where nothing was authorised: `今日黑丝` → **no reply** (FR-202, SC-201).

## Scenario 3 — Direct chats are untouched (US3 · FR-204 · SC-203)

With **nothing authorised in any group**, in a direct chat with the bot:

| Send | Expect |
|---|---|
| `今日黑丝` | An image |
| `今日白丝` | An image |
| `TodayImage允许黑丝` | `这个命令只能在群里使用…` — explained, not silently ignored |
| `TodayImage列表` | `私聊不受类型限制，无需设置。` |

Repeat feature 002's Scenario 2 probes in the direct chat and confirm they behave exactly as before.

## Scenario 4 — Only admins can widen a group (US2 · FR-211 · SC-204)

From an **ordinary member** (`user_pm=6`) in group A:

| Send | Expect |
|---|---|
| `TodayImage允许白丝` | **No reply**, and `今日白丝` still does nothing afterwards |
| `TodayImage禁止黑丝` | **No reply**, and `今日黑丝` still works afterwards |
| `TodayImage列表` | **No reply** |

Verify on disk that `group_permissions.json` did not change.

## Scenario 5 — Revocation is immediate (US2 AS4 · V-PST-3)

As an admin in group A, with `黑丝` authorised:

| Step | Send | Expect |
|---|---|---|
| 1 | `今日黑丝` | An image |
| 2 | `TodayImage禁止黑丝` | `已禁止本群使用【黑丝】。` |
| 3 | `今日黑丝` **immediately** | **No reply** — no TTL to wait out |

## Scenario 6 — The blocklist still wins (FR-206 · V-GATE-1)

As an admin in group A:

| Send | Expect |
|---|---|
| `TodayImage允许老婆` | Accepted (it is just a tag name) |
| `今日老婆` | TodayWaifu answers; **TodayImage does not** — exactly one reply |

A group must not be able to authorise its way to a blocklisted command. Revoke afterwards.

## Scenario 7 — Audit and diagnosis (US4 · SC-207)

As an admin in group A:

| Send | Expect |
|---|---|
| `TodayImage列表` | `本群已允许：黑丝` |
| `TodayImage允许不存在的类型` | Accepted, **with a warning** that no such folder exists |
| `TodayImage列表` | Shows it, noting it has no folder |

This is the path an admin uses when `今日X` is silent — chat replies will not explain it.

## Scenario 8 — Fail closed (FR-218 · V-PST-1)

```bash
cd <gsuid_core>/data/TodayImage
cp group_permissions.json group_permissions.json.bak
printf '{ broken' > group_permissions.json
```

| Send | Expect |
|---|---|
| `今日黑丝` in an authorised group | **No reply** — corruption removes access, never grants it |
| `今日黑丝` in a direct chat | Still works — direct chats never read this file |

```bash
mv group_permissions.json.bak group_permissions.json   # restore
```

## Scenario 9 — Persistence (FR-216 · SC-205)

Authorise a tag, restart the core, send `今日<tag>` in that group → still works, with no repeated command.

## Dry-run results (recorded 2026-09-11, real install, no bot)

Scenarios 1–8 exercised against the live index, blocklist and a temporary permissions file:

| situation | 群A | 群B | 私聊 |
|---|---|---|---|
| before any authorisation | silent (`unauthorised`) | silent | **image** |
| after `TodayImage允许【黑丝】` in 群A | `今日黑丝` **image**, `今日白丝` silent | silent | image |
| 群A also authorises `老婆` | `今日老婆` silent (`blocked`) — blocklist wins | — | — |
| after `TodayImage禁止黑丝` | silent immediately, no TTL | — | image |
| permissions file corrupted | silent (**fail closed**) | silent | image (never reads the file) |

The bracket form `【黑丝】` normalised to `黑丝` as intended. Services registered:
`今日图片-群授权` at **pm=3**, alongside the four from features 001/002.

**Still to run against a live bot**: the human half of each scenario (an actual ordinary-member attempt, and
end-to-end image delivery) — blocked by the delivery problem in
[002 research R0](../002-dynamic-category-lookup/research.md).

## Validation checklist

- [ ] Unit tests pass; 001's daily suites unmodified
- [ ] S1: a group with no record draws nothing
- [ ] S2: per-tag, per-group authorisation; bracket and space forms accepted; group B unaffected
- [ ] S3: direct chats identical to feature 002; authorisation commands explained there
- [ ] S4: an ordinary member cannot widen or narrow anything
- [ ] S5: revocation takes effect on the next message
- [ ] S6: the blocklist beats any group authorisation
- [ ] S7: an admin can diagnose a silent tag without any chat hint
- [ ] S8: a corrupt permissions file fails closed, and direct chats are unaffected
- [ ] S9: authorisations survive a restart
