# Contract: Group Authorisation Commands

**Feature**: `003-per-group-tag-permission`

Extends [002 contracts/commands.md](../../002-dynamic-category-lookup/contracts/commands.md). The silence contract
is preserved and **extended**: "not authorised in this group" joins unknown / blocklisted / empty as a reason to
say nothing.

## New SV

| SV name | `pm` | priority | Owns |
|---|---|---|---|
| `今日图片-群授权` | **3** | 21 | `TodayImage允许` / `TodayImage禁止` / `TodayImage列表` |

`pm=3` **is** the admin gate. GsCore's `_sv_authorized` rejects `user_pm > 3` before the handler runs, and the
ladder is `0=master, 1=superuser, 2=群主, 3=群管理员, 6=普通用户` (`gsuid_core/sv.py:278`). No permission code of
our own, and no operator-maintained admin list.

---

## 1. `TodayImage允许<tag>` — authorise a tag for this group

- **Trigger**: `on_command('TodayImage允许', block=True)`; the tag arrives in `ev.text`.
- **Auth**: group admin and above, enforced by the SV's `pm`.
- **Args**: accepted as `TodayImage允许黑丝`, `TodayImage允许 黑丝`, or `TodayImage允许【黑丝】` — surrounding
  whitespace and `【】[]「」（）()` are stripped before matching (FR-212, V-GRP-2).

| Condition | Reply |
|---|---|
| Success, folder exists | `已允许本群使用【<tag>】。` |
| Success, **no such folder** | `已允许本群使用【<tag>】。注意：服务器上目前没有这个类型的文件夹，建好后即可使用。` |
| Already authorised | `本群已经允许【<tag>】了。` |
| Empty argument | `用法：TodayImage允许<类型名>，例如 TodayImage允许黑丝` |
| Sent in a direct chat | `这个命令只能在群里使用，用来设置该群可以发送的图片类型。私聊不受限制。` |
| Ordinary member | *(no reply — the SV rejects before the handler runs)* |

---

## 2. `TodayImage禁止<tag>` — revoke a tag for this group

- **Trigger**: `on_command('TodayImage禁止', block=True)`. Same auth and parsing as above.

| Condition | Reply |
|---|---|
| Success | `已禁止本群使用【<tag>】。` |
| Was not authorised | `本群本来就没有允许【<tag>】。` |
| Empty argument | `用法：TodayImage禁止<类型名>，例如 TodayImage禁止黑丝` |
| Sent in a direct chat | Same explanation as above |

Revocation takes effect on the **next message** — permissions are read per request and never cached (V-PST-3).

---

## 3. `TodayImage列表` — show this group's authorised tags

- **Trigger**: `on_command(('TodayImage列表', 'TodayImage权限'), block=True)`.

| Condition | Reply |
|---|---|
| Has tags | `本群已允许：黑丝、白丝` (+ a note naming any authorised tag with no folder) |
| Nothing authorised | `本群还没有允许任何类型。使用「TodayImage允许<类型名>」开启。` |
| Sent in a direct chat | `私聊不受类型限制，无需设置。` |

**Discloses this group only.** It never lists the server's folders, and never another group's configuration
(FR-215, V-DIS-6). That is the difference between this and the master-only `查看图片`.

---

## 4. `今日<类型>` — the draw, with the gate added

Unchanged except for one new step. Full order (contracts must not reorder it — see V-GATE-1..3):

1. Master switch off → return
2. **Blocklist** → return *(before everything; a group cannot authorise its way to `今日老婆`)*
3. **Direct chat → skip straight to step 4** *(direct chats are never gated)*
4. **Group gate** → tag not authorised for this group → return
5. Index lookup → miss → return
6. Folder empty → return
7. Draw and send

| Condition | Reply |
|---|---|
| Authorised (or direct chat), resolves, non-empty | at-mention + caption + image, exactly as before |
| Anything else | **nothing** |

An unauthorised request is **indistinguishable** from an unknown tag, a blocklisted command and an empty folder
(V-GATE-4). A member must not be able to learn that a tag exists but is merely switched off here.

Every gated return logs at `debug` with its reason. Admin diagnosis goes through `TodayImage列表`, not through chat
replies (SC-207).

---

## Cross-cutting rules

- **Direct chats are never gated** (FR-204). The bypass precedes the gate, so group state is not even read there.
- **The blocklist is not overridable per group** (FR-206). The controls stack.
- **Deny-by-default**: a group with no record draws nothing (FR-203).
- **Fail closed**: an unreadable permissions file authorises nothing (FR-218).
- **Ordinary members learn nothing** from any command here (V-DIS-8).
