# Contract: group_permissions.json

**Feature**: `003-per-group-tag-permission`

New file alongside the existing stores. Layout of `data/TodayImage/` is otherwise unchanged from
[002 contracts/storage.md](../../002-dynamic-category-lookup/contracts/storage.md).

```text
gsuid_core/data/TodayImage/
├── 黑丝/ 白丝/ …              # categories (unchanged)
├── config.json                # console settings
├── categories.json            # per-category overrides
├── daily_records.json         # today's pinned draws
└── group_permissions.json     # NEW — per-group authorised tags
```

## Schema

```json
{
  "version": 1,
  "groups": {
    "20000001": {
      "tags": ["黑丝"],
      "updated_at": 1757560000.0,
      "updated_by": "10000002"
    },
    "123456789": {
      "tags": [],
      "updated_at": 1757561111.0,
      "updated_by": "10000002"
    }
  }
}
```

| Field | Type | Meaning |
|---|---|---|
| `version` | `int` | Schema version |
| `groups` | `object` | `group_key` → entry |
| `groups.<key>.tags` | `list[str]` | Normalised (`strip().casefold()`, brackets stripped) authorised tags |
| `groups.<key>.updated_at` | `float` | Unix timestamp of the last change |
| `groups.<key>.updated_by` | `str` | User id of the admin who last changed it |

**`group_key`** is `str(group_id).strip()`. Adapters differ on int vs string, and a group silently splitting into
two records presents to the admin as "my authorisation didn't take effect" (FR-219, V-GRP-3).

## Rules

- **S-301** — Whole-file read and write. One entry per group, a handful of tags each; no query workload.
- **S-302** — **Fail closed.** Missing, unreadable or malformed ⇒ treated as `{}` ⇒ every group authorises nothing
  (FR-218, V-PST-1). This inverts feature 001's storage posture, where a corrupt file cost only a day's pin: here
  degradation must remove access, never grant it.
- **S-303** — Atomic write: `mkstemp` in the same directory → write → `flush` + `fsync` → `os.replace`, with the
  temp file removed in a `finally`. Same recipe as every other store here.
- **S-304** — Read-modify-write under a per-group `asyncio.Lock`, re-reading inside the lock, so simultaneous
  authorisations in one group cannot lose an update (FR-217, V-GRP-10).
- **S-305** — Read **per request**, never cached (V-PST-3). A TTL would let a revoked tag keep working.
- **S-306** — Unknown keys inside a group entry are preserved on rewrite (V-PST-4).
- **S-307** — Entries for groups the bot has left are retained, not pruned (V-PST-5): re-joining must not silently
  reset a group's content scope.
- **S-308** — `tags` is stored sorted and de-duplicated, so the file is readable and diffable by hand.
- **S-309** — An entry with an empty `tags` list is meaningful and distinct from no entry only for audit purposes;
  both authorise nothing.

## Hand editing

The file is designed to be edited over SSH: sorted tags, one group per key, no derived fields. Changes take effect
on the next message, since nothing is cached. Malformed JSON disables **all** groups rather than the edited one —
fail-closed applies to the whole document, so verify with `python -m json.tool` after editing.
