# Contract: Configuration

**Feature**: `001-daily-image-categories`

Two configuration surfaces:

1. **`config.json`** — a fixed key set rendered as a form by the GsCore web console, declared as `CONFIG_DEFAULT` and
   loaded through `StringConfig`.
2. **`categories.json`** — per-category overrides, keyed by category name. Kept out of the console config because
   the key set is discovered at runtime and unbounded (research R10).

## Console configuration (`config.json`)

```python
TodayImageConfig = StringConfig(
    'TodayImage',
    get_res_path('TodayImage') / 'config.json',
    CONFIG_DEFAULT,
)
TodayImageConfig.plugin_name = 'TodayImage'   # required: Path.resolve() through a symlink breaks auto-detection
```

Access is `TodayImageConfig.get_config(key).data`, wrapped in typed helpers (`_cfg_bool`, `_cfg_int`, `_cfg_str`)
that coerce and fall back rather than raise — a hand-edited `config.json` must never crash a handler.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `_DividerBasic` | `GsDivider` | 基础设置 | Console section header |
| `TodayImageEnabled` | `GsBoolConfig` | `True` | Master switch (FR-024, V-CFG-1) |
| `TodayImageRoot` | `GsStrConfig` | `''` | Image root; empty → `data/TodayImage` itself (V-CFG-2) |
| `TodayImageCommandPrefix` | `GsStrConfig` | `'今日'` | Command prefix; empty → default (V-CFG-3, V-CFG-4) |
| `_DividerDisplay` | `GsDivider` | 展示设置 | |
| `TodayImageTextTemplate` | `GsStrConfig` | `'你今天的{类型}来啦！'` | Global caption; `{类型}` placeholder (FR-012) |
| `TodayImageUniquePerDay` | `GsBoolConfig` | `True` | No two users in one chat share an image on the same day for the same category; falls back to reuse when the gallery is smaller than the audience |
| `TodayImageResetUtcOffset` | `GsIntConfig` | `8` (max 14) | UTC offset whose midnight ends the day. `8` = Beijing. Deliberately **not** the server's local timezone |
| `TodayImageAtUser` | `GsBoolConfig` | `True` | At-mention the requester in group chats (FR-013) |
| `TodayImageListForwardThreshold` | `GsIntConfig` | `10` (max 100) | Image count above which 查看图片 uses a forwarded node message |
| `_DividerUpload` | `GsDivider` | 上传设置 | |
| `TodayImageUploadWhitelist` | `GsListStrConfig` | `[]` | User IDs allowed to upload; masters are always allowed (FR-017) |
| `TodayImageUploadMaxMB` | `GsIntConfig` | `10` (max 50) | Per-image upload cap (FR-020) |
| `_DividerPerformance` | `GsDivider` | 性能设置 | |
| `TodayImageScanCacheTTL` | `GsIntConfig` | `300` (max 3600) | Directory-scan cache TTL in seconds; `0` = scan every time (FR-025, V-CFG-5) |

**Rules**

- Every value is read through a coercing helper. A malformed value logs a warning and uses the default; it never
  propagates an exception into a handler. (SC-005.)
- `TodayImageCommandPrefix` and `TodayImageRoot` only take effect on `重载图片类型`; the reload reply says so.
  (V-CFG-4.)
- The config file lives under `get_res_path('TodayImage')`, outside the plugin source tree, so it survives a plugin
  upgrade or reinstall. (FR-022.)

## Per-category overrides (`categories.json`)

Path: `get_res_path('TodayImage') / 'categories.json'`.

```json
{
  "version": 1,
  "categories": {
    "黑丝": {
      "enabled": true,
      "aliases": ["丝袜"],
      "caption": "今天的黑丝，请收好~"
    },
    "白丝": {
      "enabled": true,
      "aliases": [],
      "caption": null
    },
    "测试": {
      "enabled": false,
      "aliases": [],
      "caption": null
    }
  }
}
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `version` | `int` | `1` | Schema version; an unknown version is read best-effort with a warning |
| `categories.<name>.enabled` | `bool` | `true` | `false` unregisters every command for the category (V-CAT-6) |
| `categories.<name>.aliases` | `list[str]` | `[]` | Extra command suffixes (FR-003) |
| `categories.<name>.caption` | `str \| null` | `null` | Overrides `TodayImageTextTemplate`; `null` = use global |

**Rules**

- **C-1** — A category folder with no entry here uses all defaults. The file is optional; an absent file means "all
  defaults". (V-OVR-2.)
- **C-2** — An entry naming a folder that no longer exists is **kept**, not pruned, so temporarily moving a folder
  aside does not lose its settings. (V-OVR-1.)
- **C-3** — Unknown keys inside an entry are preserved on rewrite. (V-OVR-3.)
- **C-4** — Unparseable JSON → treated as empty, warning logged, plugin still starts with every category on
  defaults. (V-OVR-2, SC-005.)
- **C-5** — Written atomically (temp file in the same directory + `os.replace`), same as every other store here.
- **C-6** — Hand-editable. The plugin re-reads it on `重载图片类型`, so an operator can edit it over SSH and reload
  from chat.
