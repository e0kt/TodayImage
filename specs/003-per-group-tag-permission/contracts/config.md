# Contract: Configuration Changes

**Feature**: `003-per-group-tag-permission`

Only deltas from [002 contracts/config.md](../../002-dynamic-category-lookup/contracts/config.md).

## New key

| Key | Type | Default | Meaning |
|---|---|---|---|
| `TodayImageDefaultGroupTags` | `GsListStrConfig` | `[]` (empty) | Tags auto-granted to a group that has **no record yet** |

**Rules**

- **CF-301** — Applies **only** to groups with no entry in `group_permissions.json`. Once a group has any record —
  including one with an empty tag list — this setting no longer affects it. Otherwise an operator widening the
  default would silently re-grant tags an admin had deliberately revoked.
- **CF-302** — Default is **empty**, i.e. deny-by-default (FR-203). The setting exists so an operator can opt into
  seeding new groups, not so the safe default can be skipped by accident.
- **CF-303** — Entries are normalised exactly like an authorised tag: brackets stripped, `strip().casefold()`.
- **CF-304** — Changing it never revokes anything; it only affects groups that have not been configured yet.
- **CF-305** — Read per request, like the permission store. No restart, no reload.

## Unchanged keys

Everything from features 001 and 002, including `TodayImageBlocklist`, which remains **above** group authorisation
in precedence: a group cannot authorise its way past the blocklist (FR-206).

## Operator note — this is a breaking change

Shipping this feature stops every currently-working group until an admin authorises tags there. That is the
requested behaviour, but it should reach the operator as a deliberate step, not as user reports:

1. Decide the tag set for each group **before** restarting.
2. Restart the core (which also applies feature 002 — see the plan's deployment note).
3. In each group, have an admin run `TodayImage允许<类型>` for each intended tag.
4. Verify with `TodayImage列表` in that group.

Setting `TodayImageDefaultGroupTags` before the restart does **not** cover existing groups either way — it only
applies to groups with no record, which is every group on first run. Operators wanting the old behaviour
temporarily can seed it there, then tighten per group; that is a deliberate choice, and it is why the setting
exists rather than being a hard-coded default.
