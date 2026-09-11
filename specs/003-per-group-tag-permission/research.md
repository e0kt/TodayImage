# Phase 0 Research: 分群标签授权

**Feature**: `003-per-group-tag-permission` | **Date**: 2026-09-11

Sources: the local GsCore checkout (`sv.py`, `handler.py`, `models.py`), this bot's own event logs, and the
existing TodayImage code from features 001/002.

---

## R1. What "admin用户" means, and why no custom permission code is needed

**Decision**: Register the authorisation commands on an SV with `pm=3`. GsCore then refuses the command for anyone
below group-admin, before our handler runs.

**Rationale**: `gsuid_core/sv.py:278` documents the ladder verbatim:

```text
权限 0=master，1=superuser，2=群主，3=群管理员，6=普通用户
```

and `_sv_authorized` (`handler.py:179`) enforces `user_pm > _sv.pm → reject`. Lower is more privileged, so `pm=3`
admits 群管理员(3), 群主(2), superuser(1) and master(0) while rejecting 普通用户(6) — exactly the set the request
names.

This is not theoretical on this deployment. `get_user_pml` (`handler.py`) trusts the adapter's `user_pm` except for
the master/superuser override, and this bot's own logs contain a real spread:

| `user_pm` | occurrences in `data/logs/2026-09-1*.log` |
|---|---|
| 6 (普通用户) | 169 |
| 3 (群管理员) | 33 |
| 0 (master) | 49 |

So the OneBot adapter does populate group-admin status, and the gate works without us maintaining a list.

**Alternatives considered**:
- **A console list of admin user IDs.** Works, but the operator would have to maintain it per group, by hand,
  forever — exactly the chore this feature is meant to remove.
- **Checking `pm` inside the handler.** Same outcome, but duplicates framework logic and silently diverges if
  GsCore changes the ladder. `pm=3` on the SV keeps one source of truth.

---

## R2. Where the gate goes in the decision order

**Decision**: Extend `dispatch.decide` to take the chat context, and evaluate in this fixed order:

```text
1. blocklist            -> silent   (unchanged; not overridable per group)
2. direct chat?         -> skip the gate entirely
3. group authorisation  -> silent if the tag is not authorised here
4. category index       -> silent on miss
5. empty folder         -> silent
```

**Rationale**: Three constraints fix this order.

- **Blocklist stays first** (FR-206). If the gate ran first, a group could authorise a tag named `老婆` and reach
  a TodayWaifu command. The two controls stack; the blocklist is the stricter one and must not be reachable.
- **The direct-chat check must precede the gate** (FR-204), not be folded into it, so a direct chat never consults
  group state at all. Anything else risks a direct chat inheriting some "default group" behaviour.
- **The gate precedes the index lookup** because authorisation is about *permission, not existence* (Assumptions).
  A tag may be authorised before its folder exists, or remain authorised after deletion. Checking permission first
  also means an unauthorised group cannot use timing to infer whether a folder exists.

All five outcomes return the same value, preserving feature 002's uniform silence (FR-205, SC-206).

**Alternatives considered**:
- **Gate after the index**, using the canonical folder name. Marginally tidier normalisation, but it makes
  "authorise a tag that doesn't exist yet" impossible to express and leaks existence through timing.
- **A separate `is_allowed()` call in the handler**, leaving `decide` untouched. Rejected: the ordering *is* the
  contract, and splitting it across two files is how orderings drift.

---

## R3. Deny-by-default, and the migration it forces

**Decision**: A group with no record authorises nothing. Ship a console setting, `TodayImageDefaultGroupTags`,
defaulting to **empty**, applied only to groups with no record yet.

**Rationale**: The request is explicit — a group gains access only after an admin acts — so the default must be
closed. Failing open would make a corrupt or missing permissions file silently disable the whole control, which is
the worst possible failure for a safety feature (FR-218).

This is a **breaking change and must be called out, not buried**: the group currently using `今日黑丝` (20000001 in
the logs) will stop working the moment this ships, until an admin authorises the tags. That is intended, but an
operator discovering it from user complaints rather than from the release note is a bad outcome. The default-tags
setting exists so an operator who wants the old behaviour for **new** groups can opt into it deliberately, rather
than having it as a silent default.

**Alternatives considered**:
- **Grandfather existing groups** by seeding every currently-active group at first run. Rejected: "which groups are
  active" is not knowable from the plugin's own state (feature 001/002 never recorded group ids outside daily
  records, which are pruned daily), and guessing would authorise groups the operator never reviewed.
- **Allow-by-default with an opt-in strict mode.** Directly contradicts the request.

---

## R4. Storage

**Decision**: `data/TodayImage/group_permissions.json`, one entry per group, written atomically, read through the
same fail-closed pattern as the other stores.

```json
{
  "version": 1,
  "groups": {
    "20000001": {
      "tags": ["黑丝"],
      "updated_at": 1757560000.0,
      "updated_by": "10000002"
    }
  }
}
```

**Rationale**: Consistent with `daily_records.json` and `categories.json` — same `mkstemp` + `fsync` + `os.replace`
recipe already proven in this codebase, same "unreadable ⇒ treat as empty" degradation. Volume is tiny (one entry
per group, a handful of tags) so a whole-file read/write is right and a database is not.

`updated_at` / `updated_by` are kept because this is a permission control: when a group's content scope changes, the
operator will eventually want to know who widened it. They are diagnostic only and never shown to non-admins.

**Group id normalisation** (FR-219): keys are `str(group_id).strip()`. Adapters differ on int vs string, and a
group that silently splits into two records would fail open-ish in a confusing way — the admin would see their
authorisation "not take effect".

**Concurrency** (FR-217): read-modify-write under a per-group `asyncio.Lock`, re-reading inside the lock — the same
pattern feature 001 used for the daily pin, and for the same reason: two admins authorising different tags at once
must not lose one.

**Alternatives considered**:
- **Reuse `categories.json`.** Rejected: that file is per-category operator config; groups are an orthogonal axis,
  and merging them would make either file hard to hand-edit.
- **GsCore's database layer.** No queries, no joins, no console CRUD requirement — unjustified.

---

## R5. Command surface and argument parsing

**Decision**: `TodayImage允许<tag>` / `TodayImage禁止<tag>` / `TodayImage列表`, registered with `on_command` on a
`pm=3` SV. The argument is normalised by stripping whitespace and any of `【】[]「」（）()` before matching.

**Rationale**: The user named the command, so it keeps their name. Practically it also cannot collide with the
`今日` dynamic trigger from feature 002, and starting with ASCII `TodayImage` makes it unambiguous next to the
Chinese command space.

`on_command` is a `startswith` test, so one trigger serves `TodayImage允许黑丝`, `TodayImage允许 黑丝` and
`TodayImage允许【黑丝】`, with the remainder arriving in `ev.text`. The bracket stripping matters because the request
literally wrote `【tag名字】` — an admin copying that form should not get a tag named `【黑丝】` (FR-212).

Normalisation reuses feature 002's `strip().casefold()` identity so a tag authorised as `黑丝` matches a folder
named `黑丝 ` or `黑絲`-cased variants the same way the index does.

**Alternatives considered**:
- **`on_prefix`** — would not match the bare `TodayImage列表`; `on_command` handles both shapes.
- **A single `TodayImage权限 <add|del> <tag>` verb.** Fewer triggers, more to type and remember; the user proposed
  the direct form.

---

## R6. What admins may be told, without reopening the oracle

**Decision**: Admin replies may name **their own group's** tags and confirm whether a just-authorised tag has a
matching folder. They may **not** enumerate the server's folder list or any other group's configuration.

**Rationale**: Feature 002 removed public enumeration because a difference in replies lets anyone map the host's
folders. That reasoning applies to the *public*; a group admin authorising content for their own group must be able
to see what they have authorised, or the feature is unusable (FR-215, SC-207).

The one leak to avoid is **folder enumeration by probing the authorise command**: `TodayImage允许X` warning "no such
folder" turns an admin command into a directory oracle. Contained by two facts: the command is `pm=3`, and the
warning is a property of the tag the admin already typed, not a list. A group admin learning that `黑丝` exists on a
bot they administer is not a meaningful disclosure; a random member enumerating all folders is.

**Alternatives considered**:
- **Never warn about a missing folder.** Safer in theory, but then "I authorised it and nothing happens" has no
  diagnostic path at all, which SC-207 requires.
- **Restrict these commands to master only.** Defeats the purpose — per-group scope is exactly what group admins
  should own.

---

## R7. Interaction with features 001 and 002

| Concern | Resolution |
|---|---|
| Daily pin | Unchanged. Already keyed by chat, so a group and a direct chat are independent. `daily_store.py` is untouched again. |
| Blocklist | Unchanged and still first (FR-206). |
| Silence contract | Extended, not weakened: unauthorised joins the set of mutually indistinguishable negatives. |
| Category index | Unchanged; the gate consults the authorisation set, not the filesystem. |
| Direct chats | Untouched code path — the gate is skipped before it is consulted. |
| `重载图片类型` | Unchanged; permissions are read per request and never cached, so no reload is involved. |

**Not cached** (FR-207): the permissions file is small and read per request. Caching it would add an invalidation
path where a revoke could keep working for a TTL — unacceptable for a control whose whole point is to take effect
when the admin says so.

---

## Resolved Technical Context

| Item | Resolution |
|---|---|
| Language/Version | Unchanged: Python ≥ 3.11, stdlib only |
| Admin gate | SV `pm=3`, enforced by GsCore before our handler runs |
| Decision order | blocklist → direct-chat bypass → group gate → index → emptiness |
| Storage | `data/TodayImage/group_permissions.json`, atomic write, fail closed, per-group `asyncio.Lock` |
| Default | Deny-by-default; `TodayImageDefaultGroupTags` (empty) seeds only groups with no record |
| Commands | `TodayImage允许` / `TodayImage禁止` / `TodayImage列表` via `on_command`, bracket-tolerant |
| Testing | stdlib `unittest`; new pure modules for the permission store and the extended decision |
| Constraints | Must not regress 001's daily semantics or 002's silence contract; direct chats untouched |

## Open Issue (carried forward, still unresolved)

Feature 002's research R0 recorded that replies leave GsCore but do not arrive in QQ, and **feature 002 has not yet
been restarted into the running core** (PID 82210 started 2026-09-09 22:53, before 002 landed). Both facts matter
here: until the core is restarted this feature cannot be observed at all, and until the delivery problem is
resolved a correctly-gated draw will still look like a failure. Neither is caused by this feature.
