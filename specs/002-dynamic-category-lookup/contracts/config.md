# Contract: Configuration Changes

**Feature**: `002-dynamic-category-lookup`

Only deltas from [001 contracts/config.md](../../001-daily-image-categories/contracts/config.md).

## New key

| Key | Type | Default | Meaning |
|---|---|---|---|
| `TodayImageBlocklist` | `GsListStrConfig` | the 12 base names below | Command names TodayImage must never answer |

**Default value**

```python
[
    '今日老婆', '今日老公', '今日萝莉', '今日战双老婆', '今日异环老婆', '今日群友离婚',
    '今日老婆帮助', '今日老婆离婚', '今日老公离婚', '今日萝莉离婚', '今日萝莉列表', '今日萝莉上传',
]
```

Derived from live inspection of TodayWaifu's registered triggers on this host, not from memory.

**Rules**

- **CF-1** — Entries are **base names**: a command matches when it equals one or starts with one (V-BLK-1).
  `今日老婆` therefore also covers `今日老婆离婚` and any future suffix.
- **CF-2** — Operator entries **merge with** the defaults and cannot remove them (V-BLK-5). A console edit must not
  be able to make TodayImage start answering another plugin's command.
- **CF-3** — Read per request, so edits apply with no restart (FR-116).
- **CF-4** — Matched `strip().casefold()` on both sides.
- **CF-5** — Blank entries are ignored; an empty list means "defaults only", never "block nothing".

## Changed behaviour, same keys

| Key | Change |
|---|---|
| `TodayImageCommandPrefix` | Now drives the single dynamic trigger. Changing it still needs a restart — the trigger keyword is fixed at registration, unlike the folder set |
| `TodayImageScanCacheTTL` | Now also bounds how soon a **new folder** goes live (FR-103). Lower = faster pickup, more scans. `0` scans every message — with a dynamic trigger that is a real cost, so it is debug-only |
| `TodayImageRoot` | Unchanged, but no longer appears in public output |

## Unchanged keys

`TodayImageEnabled`, `TodayImageTextTemplate`, `TodayImageAtUser`, `TodayImageListForwardThreshold`,
`TodayImageUploadWhitelist`, `TodayImageUploadMaxMB`, `TodayImageUniquePerDay`, `TodayImageResetUtcOffset`.
