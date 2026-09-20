# Contract: 配置变更

**Feature**: `005-reply-delete-image`

## 新增

| 键 | 类型 | 默认 | 含义 |
|---|---|---|---|
| `TodayImageDeleteMasterOnly` | `GsBoolConfig` | `False` | 是否把回复删图**收紧**为仅 master / superuser |

**规则**

- **CF-501** — 默认 `False`，即群管理员及以上（`pm<=3`）可删。
  错标本身就是全局的，能发现的人修掉它对所有群都是净收益。
- **CF-502** — 置为 `True` 后仅 `pm<=1` 可删。适用于**图库即原始数据、删除不可恢复**的部署。
  在图库由 Immich 等外部库导出的部署中不必打开 —— 原图仍在，重新导出即可恢复。
- **CF-503** — 每次请求现读，改完不用重启。
- **CF-504** — 该项只能**收紧**，不能放宽。无论配置如何，`pm>3` 都进不来 —— SV 的 `pm=3` 是硬上界。

## 不新增落盘文件

回执表仅存内存（research R7）。重抽复用 `daily_records.json` 既有的 `resets` / `excludes`
字段，无 schema 变更。

## 未变但需注意

| 键 | 说明 |
|---|---|
| `TodayImageScanCacheTTL` | 删除后会**立即**失效缓存，不受此项影响 |
| `TodayImageUploadMaxMB` | 与删除无关 |
