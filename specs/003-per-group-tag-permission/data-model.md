# Phase 1 Data Model: 分群标签授权

**Feature**: `003-per-group-tag-permission` | **Date**: 2026-09-11

Only deltas from features 001/002. `DailyRecord`, `CategoryIndex`, `Blocklist` and the image layout are unchanged.

---

## Entity: GroupPermission (new)

One group's authorised tag set.

| Field | Type | Notes |
|---|---|---|
| `group_key` | `str` | `str(group_id).strip()` — the map key |
| `tags` | `set[str]` | Normalised tag names authorised for this group |
| `updated_at` | `float` | Unix timestamp of the last change |
| `updated_by` | `str` | User id of the admin who last changed it |

**Validation rules**

- **V-GRP-1** — Tag identity is `strip().casefold()`, the same normalisation feature 002's category index uses, so
  an authorisation matches a folder regardless of case or surrounding whitespace (FR-212).
- **V-GRP-2** — Before normalisation, surrounding brackets `【】[]「」（）()` are stripped. The request literally
  wrote `【tag名字】`; an admin copying that form must not end up authorising a tag called `【黑丝】`.
- **V-GRP-3** — `group_key` is `str(group_id).strip()`. Adapters differ on int vs string; a group splitting into
  two records would present as "my authorisation didn't take effect" (FR-219).
- **V-GRP-4** — A group with **no record** authorises nothing (FR-203). Absence is not permission.
- **V-GRP-5** — Authorising an already-authorised tag is idempotent and reported as such (US1 AS6).
- **V-GRP-6** — Revoking a tag that was never authorised is reported, not an error.
- **V-GRP-7** — A tag may be authorised with **no matching folder**; permission and existence are independent. The
  admin is warned (FR-213), and the tag starts working if the folder later appears (US4 AS3).
- **V-GRP-8** — Deleting a folder does **not** revoke its tag. The draw simply resolves to nothing.
- **V-GRP-9** — `updated_at` / `updated_by` are diagnostic only and are never shown to non-admins.
- **V-GRP-10** — Read-modify-write runs under a per-group `asyncio.Lock` with a re-read inside the lock, so two
  admins authorising different tags at once cannot lose an update (FR-217).

---

## Entity: GateDecision (extends feature 002)

`dispatch.decide` gains the chat context. The order below **is** the contract and must not be reordered.

| Step | Condition | Outcome |
|---|---|---|
| 1 | command is blocklisted | no reply |
| 2 | chat is direct | **skip the gate**, continue at step 4 |
| 3 | tag not authorised for this group | no reply |
| 4 | tag does not resolve in the index | no reply |
| 5 | resolved folder is empty | no reply |
| 6 | otherwise | draw and send |

**Validation rules**

- **V-GATE-1** — The blocklist stays **first** (FR-206). A group must not be able to authorise a tag named `老婆`
  and thereby reach a TodayWaifu command. The two controls stack; the stricter one wins.
- **V-GATE-2** — The direct-chat bypass precedes the gate rather than being folded into it (FR-204), so a direct
  chat never consults group state and cannot inherit a "default group" behaviour.
- **V-GATE-3** — The gate precedes the index lookup. Authorisation is about permission, not existence (V-GRP-7),
  and checking permission first stops an unauthorised group inferring folder existence from timing.
- **V-GATE-4** — Every negative outcome returns the **same** value. Unauthorised joins unknown, blocked and empty as
  mutually indistinguishable (FR-205, SC-206). Adding a fourth reason to be silent must not add a fourth observable.
- **V-GATE-5** — The reason is available separately for `debug` logging only, never for a reply (carried over from
  feature 002's `miss_reason`).

---

## Entity: PermissionStore (new)

The on-disk document. Schema in [contracts/storage.md](./contracts/storage.md).

**Validation rules**

- **V-PST-1** — A missing, unreadable or malformed file is treated as **empty**, which authorises nothing
  (FR-218). For a control that limits what a group may see, degradation must remove access, never grant it — the
  opposite of feature 001's stores, where an unreadable file merely cost one day's pin.
- **V-PST-2** — Written atomically: `mkstemp` in the same directory → `fsync` → `os.replace`, matching the other
  stores in this plugin.
- **V-PST-3** — Read per request and never cached (FR-207 aside). A TTL would let a revoked tag keep working, which
  is the one behaviour an admin would least tolerate.
- **V-PST-4** — Unknown keys inside a group entry are preserved on rewrite, so a newer version's fields survive a
  downgrade.
- **V-PST-5** — Entries for groups the bot has left are retained, not pruned; re-joining should not silently reset a
  group's content scope.

---

## Entity: DisclosureLevel (extends feature 002)

A third audience is added between `public` and `master`.

| Level | Audience | May contain |
|---|---|---|
| `public` | everyone | Mechanism only. No tags, no commands, no paths |
| `group admin` | `user_pm <= 3` | **This group's** authorised tags; whether a named tag has a folder |
| `master` | `pm=1` commands | Everything: the server's folder list, counts, paths |

**Validation rules**

- **V-DIS-6** — A group admin may see their own group's tags but **not** the server's folder list, and **not** any
  other group's configuration (FR-215).
- **V-DIS-7** — `TodayImage允许X` may warn that `X` has no folder. This is a property of the tag the admin already
  typed, not an enumeration, and the command is `pm=3` — a group admin learning that a tag they named exists on a
  bot they administer is not a meaningful disclosure.
- **V-DIS-8** — An ordinary member gets nothing from any command in this feature (US4 AS4).

---

## Cross-entity invariants

- **I-301** — Blocklist ∩ drawable = ∅, for every group, regardless of authorisation.
- **I-302** — A direct chat's behaviour is byte-identical to feature 002; no group state is read on that path.
- **I-303** — A group with no record draws nothing.
- **I-304** — Every gated negative is indistinguishable from every other negative to a non-admin.
- **I-305** — Daily semantics are untouched: `tdi/daily_store.py` is not modified and its suites run unchanged.
