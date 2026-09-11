# Phase 0 Research: Dynamic Category Lookup

**Feature**: `002-dynamic-category-lookup` | **Date**: 2026-09-11

Sources: the local GsCore checkout (`sv.py`, `trigger.py`, `handler.py`), the installed TodayWaifu plugin, and
live inspection of the registered trigger table on this machine.

---

## R0. Why the current build appears dead — and why it is not a matching bug

**Finding**: `今日黑丝` **does** reach the handler and the handler **does** send. The plugin is not broken in the way
it looks from chat.

Evidence from `data/logs/2026-09-10.log`, one complete request:

```text
⚡ [收到事件]   raw_text='今日黑丝'  user_type='direct'
⚡ [命令触发]   trigger=["今日黑丝","fullmatch","今日黑丝"]
📝 [TraceStart] command=今日黑丝
🤖 [发送消息to] onebot - direct - 10000001
📝 [TraceEnd]   command=今日黑丝 duration=47ms
```

The trigger matched, the handler ran, and GsCore handed a message to the OneBot adapter. Nothing failed inside the
plugin. The reply is being lost **downstream of GsCore** — at the NoneBot2/OneBot adapter or at QQ itself, which is
the expected signature of image-send risk control on that platform.

**Consequence for this feature**: the redesign below must not be justified as a fix for that symptom. It is not one.
The two are independent, and the delivery problem is recorded as a separate follow-up (see Open Issue at the end).
Planning them as one thing would have hidden a real bug behind a refactor.

---

## R1. One dynamic trigger instead of one trigger per folder

**Decision**: Register a single `on_prefix(<前缀>, block=False)` trigger on the draw SV, and resolve the remaining
text to a folder at request time. Delete feature 001's per-folder registration and the `registry_binding` runtime
`TL` mutation entirely.

**Rationale**:

`Trigger._check_prefix` (`gsuid_core/trigger.py:48`) is `msg.startswith(prefix + keyword) and not fullmatch`, and
`Trigger.get_command` sets `ev.text = raw_text.replace(keyword, '', 1)`. So one `今日` prefix trigger yields the
suffix directly in `ev.text`, and — usefully — the bare word `今日` does **not** fire it, satisfying FR-107 for free.

This inverts the decision recorded in feature 001 research R2/R3, which rejected a `今日` catch-all. That rejection
was correct **for `block=True`**, which is what R2 evaluated: a blocking catch-all swallows every other plugin's
`今日X`. With `block=False` the objection does not apply — see R2 — and the benefits are large:

- A new folder works with no reload and no restart (FR-103, SC-101). Feature 001 needed `重载图片类型` because the
  trigger set was a snapshot of the filesystem.
- The framework-internal `del sv.TL['fullmatch'][kw]` reach disappears, and with it the upgrade-fragility that
  `tests/test_gscore_compat.py` was written to guard.
- Nothing enumerates the categories in the service registry, which is half of FR-110.

**Alternatives considered**:
- **Keep per-folder registration, add a reload-on-timer.** Retains the enumerable registry (fails FR-110) and keeps
  the internal `TL` mutation.
- **`on_regex('^今日(.+)$')`.** Equivalent matching, but regex triggers are evaluated against every message and the
  capture lands in `regex_group` rather than `ev.text`; no benefit over `on_prefix`.
- **Both mechanisms at once.** Rejected outright: two triggers matching one message is a double-reply bug.

---

## R2. Why `block=False` is required, and why it is sufficient

**Decision**: `block=False` on the dynamic trigger, with the handler returning silently when the suffix does not
resolve.

**Rationale** — the dispatch loop (`gsuid_core/handler.py:530-571`):

```python
sorted_event = sorted(command_triggers.items(), key=lambda x: (not x[0].prefix, x[1]))
for trigger, _ in sorted_event:
    ...enqueue...
    if trigger.block:
        break
```

Only *matched* triggers are sorted, ordering is by `(has-plugin-prefix, sv.priority)`, and the loop stops after the
first `block=True`. Both plugins run with an empty plugin prefix, so ordering is by SV priority alone.

Measured on this machine, TodayWaifu's `今日` triggers sit at **priority 0–10**; TodayImage's draw SV is at **25**.
So for a TodayWaifu command:

| message | matched | order | outcome |
|---|---|---|---|
| `今日老婆` | TodayWaifu fullmatch (p10, block) + TodayWaifu prefix (p2, block) + our prefix (p25) | p2 → break | TodayWaifu answers; we never run |
| `今日黑丝` | our prefix (p25) only | — | we answer |
| `今日天气` (hypothetical plugin at p30, block) | ours (p25) then theirs (p30) | ours runs, does **not** block, theirs runs | both fine; we stay silent |

`block=True` would break the third row — we would sort first and terminate the loop, killing a `今日` command owned
by any plugin at a higher priority number. That is the shadowing hazard from 001 R2, and `block=False` is what
removes it (FR-106, SC-105).

**Cost accepted**: with `block=False` we cannot stop anyone else either, so if two plugins both claim `今日黑丝`,
both answer. That is the correct failure mode — visible and additive, rather than silent suppression.

---

## R3. The blocklist: contents, precedence, and why it is still needed

**Decision**: Match the full command text against a blocklist **before** any filesystem access. Default entries
below, operator-extendable via a console list config, applied per-request so edits need no restart.

**Default set**, taken from live inspection rather than from memory — all 16 `今日*` triggers currently registered
by TodayWaifu on this machine:

```text
今日老婆      今日老公      今日萝莉      今日战双老婆   今日异环老婆
今日老婆帮助   今日老婆离婚   今日老公离婚   今日萝莉离婚   今日群友离婚
今日萝莉列表   今日萝莉上传
```

Stored as **base names** and matched by `command == base or command.startswith(base)`, so `今日老婆离婚` is covered
by `今日老婆` and future TodayWaifu suffixes are covered pre-emptively (FR-117).

**Rationale**: R2 shows priority ordering already prevents a double reply *while TodayWaifu is loaded*. The
blocklist covers the three cases ordering does not:

1. **TodayWaifu disabled or uninstalled** — nothing else matches, so a folder named `萝莉` would make us answer
   `今日萝莉`. The user explicitly does not want that (US3 AS2).
2. **A folder deliberately named `老婆`** — blocklist must win over a real folder (FR-115, US3 AS3).
3. **Priority ordering changing** under a GsCore upgrade or an operator's console edit — the blocklist does not
   depend on it.

Checking the blocklist first also means a blocked name never touches the filesystem (FR-118), which matters because
the blocked names are exactly the ones a curious user is most likely to spam.

**Alternatives considered**:
- **Rely on priority ordering alone.** Free, but fails all three cases above.
- **Auto-derive the blocklist by scanning `SL.lst` at startup.** Tempting, and it would self-update. Rejected: it
  inverts the dependency (we would silently stop answering a category because some unrelated plugin registered a
  colliding name), it is empty when TodayWaifu loads after us, and it cannot express case 2. A static default list
  plus operator additions is predictable; scanning is not.

---

## R4. Non-disclosure: silence as the contract

**Decision**: An unresolved, blocked, empty-folder, or malformed `今日X` produces **no reply at all**. The public
help explains the mechanism without naming folders or printing paths. Master-only commands keep full disclosure.

**Rationale**: Feature 001 replied `不存在图片类型【X】` for an unknown name and printed the image root in both the
help and the empty-category hint. Together those form a probing oracle: a user can enumerate the host's folder names
by difference in replies, and learn the absolute filesystem path for free. FR-109/FR-110/FR-113 close that by making
every negative outcome produce the *same* observable: nothing.

This is a direct reversal of feature 001's SC-005 ("every failure path produces an actionable plain-text reply").
The two requirements genuinely conflict, and this feature's requirement wins for **public** paths only; SC-005 is
preserved for master-only commands, where the operator both needs the diagnostic and is already trusted with the
listing. That split is recorded in the contract so the older criterion is not read as still binding everywhere.

An empty-but-existing folder must be indistinguishable from a missing one (FR-113) — otherwise the "no images"
message becomes the oracle instead.

**Alternatives considered**:
- **Reply only to masters on failure.** Keeps diagnostics, but a master-visible difference is still a difference;
  simpler to route diagnosis through logs, which is where an operator should look anyway.
- **Rate-limit instead of silencing.** Slows probing, does not prevent it, and adds state.

---

## R5. Resolution cost and cache shape

**Decision**: Keep the TTL-cached scan from feature 001, and resolve a suffix via a prebuilt `casefold → folder`
map built from that cached scan. Unknown suffixes are answered from the map, never from the filesystem.

**Rationale**: The dynamic trigger fires on **every** message starting with `今日`, including hostile or accidental
ones, where feature 001 only ran on an exact registered keyword. Without a cache, `今日` + random text becomes a
filesystem-walk amplifier. Measured earlier in this project: a cold scan of 5,000 images is ~88 ms and the real
gallery ~4.7 ms; a warm map lookup is a dict hit (FR-108, SC-106).

The map is keyed on `name.strip().casefold()`, which delivers FR-102's trimming and case-insensitivity as a property
of the key rather than a scan-time comparison.

**Path-safety** (FR-104) falls out of the same design: the suffix is used as a **dict key**, never joined onto a
path, so `..`, `/` and absolute paths simply miss. This is strictly safer than 001's `find_category_directory`,
which iterated the directory to avoid traversal.

---

## R6. What feature 001 code is removed, kept, and changed

**Decision**:

| Module | Disposition |
|---|---|
| `tdi/registry_binding.py` | **Removed.** Its only purpose was per-folder register/unregister. |
| `tests/test_registry_binding.py` | **Removed** with it. |
| `tdi/gallery.py` | **Kept**, plus a `casefold → name` index builder. `find_category_directory` stays for uploads. |
| `tdi/daily_store.py` | **Unchanged.** Daily semantics are untouched (FR-105, SC-107). |
| `tdi/daily.py` | **Rewritten**: one prefix handler, blocklist check, silent miss. |
| `tdi/help_text.py` | **Rewritten**: no enumeration, no paths, master/public split. |
| `tdi/manage.py` | **Kept.** `重载图片类型` demoted to cache invalidation; listing stays master-only. |
| `tests/test_gscore_compat.py` | **Trimmed**: the `TL`-mutation contract test goes with `registry_binding`; the purity and coexistence tests stay. |

**Rationale**: Leaving `registry_binding` in place while adding the dynamic trigger would register a folder's
commands *twice* — once statically, once dynamically — producing exactly the double reply FR-106 and the spec's
assumptions forbid.

---

## Resolved Technical Context

| Item | Resolution |
|---|---|
| Language/Version | Unchanged: Python ≥ 3.11, stdlib only |
| Trigger | One `on_prefix(prefix, block=False)` on `今日图片-每日抽取` (priority 25) |
| Resolution | `casefold → folder name` map from the TTL-cached scan; dict lookup, never a path join |
| Blocklist | 12 default base names + console list config; prefix-matched; checked before the filesystem |
| Disclosure | Silence on every public negative; enumeration retained for `pm=1` commands only |
| Storage | Unchanged from feature 001 |
| Testing | stdlib `unittest`; `registry_binding` tests removed, blocklist/resolution/non-disclosure tests added |
| Constraints | Must not suppress other plugins' `今日X`; must not regress 001's daily guarantees |

## Open Issue (out of scope, tracked here so it is not lost)

**Replies leave GsCore but do not arrive in QQ.** Per R0, the handler sends successfully and the adapter logs
`🤖 [发送消息to]`, yet nothing appears in chat. This is downstream of the plugin and unaffected by anything in this
feature. Likely candidates in order: OneBot image risk-control on the QQ account, adapter-side base64 size limits,
or the adapter's own send failing silently. Diagnosis belongs in the adapter logs, not here — but note that if this
is not resolved, **this feature will also appear to do nothing**, and that must not be mistaken for a design fault.
