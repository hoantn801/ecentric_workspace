# ERP Shell v1 (Phase 1B — Approval Center pilot)

Shared shell chrome (sidebar / nav registry / mobile drawer / user card / logout)
for eCentric website pages. **Opt-in per page; UX only; zero business logic.**

## Opt-in contract
A page activates the shell by carrying exactly one marker node where its
sidebar used to be (first child of the page's `248px 1fr` grid root):

```html
<aside class="ec-shell-mount" data-ec-shell="1" aria-label="Điều hướng eCentric">
  <nav class="ec-shell-fallback"> <a href="/home">Trang chủ</a> … </nav>
</aside>
```

- No marker → `ec_shell.js` is a hard no-op (asset loads site-wide via
  `web_include_js`, same pattern as `notification_center.bundle.js`).
- The static fallback links inside the mount are what users see if the shell
  is kill-switched, boot fails, or JS is blocked. Keep them navigable.
- Optional: a page may mark its own hamburger with `data-ec-shell-open="1"`
  (hub + dashboard do) — this suppresses the floating mobile burger.
- Phase 1B pilot pages (the only opted-in pages): `/approvals`,
  `/approvals/leave`, `/approvals/hr-activity`, `/approvals/dashboard`.

## Kill switch
`site_config.json`: `"ec_shell_disabled": 1` → boot returns `{enabled:false}`
→ pilot pages keep their static fallback nav. Default (absent/falsy) = enabled.
Fail-closed **for the shell only**: any boot error/network failure/non-internal
user = same fallback. Never affects Notification Center, page content, or any
backend permission. Flip needs no deploy (site config change + page reload).

## Navigation registry
- `shell/nav.py` — pure composer + validator (dup key/route → ValueError;
  deterministic order). Item contract documented in the module docstring.
- Module providers: `approval_center/nav.py` (approval-owned). Register new
  providers in `shell/nav.py:_providers()`.
- Served by `shell/api.py:get_shell_boot` (GET, whitelisted, Guest rejected,
  System User only, read-only, no business data, no ignore_permissions).
- Visibility is UX assistance only — backend/page authorization unchanged.

## Frozen contracts this shell must never break
- `[data-ec-notification-bell="1"]` — the shell EMITS this marker on its bell
  node; `notification_center.js` owns all bell behavior (capture-phase click,
  badge mount, MutationObserver adoption). Never rename, wrap, or handle it.
- Logout = `fetch('/api/method/logout') → /login-page` (pm_app contract).
- User card → `/app/user`.
- Approval deep links `?id=&tab=` — the shell does no routing and never
  touches location/query/hash.
- z-index ≤ 900 (NC pop is 1000, toasts 1100).

## Tests
```
python3 -m unittest ecentric_workspace.shell.tests.test_nav_registry \
                    ecentric_workspace.shell.tests.test_pilot_optin
node ecentric_workspace/shell/tests/ec_shell_check.js
```
(bench DB test that also covers the hub page: `ecentric_workspace.approval_center.tests.test_approvals_page`)

## Deployment runbook (per step: what it's for)
1. **Backup/rollback prep** (page sync): fresh read-only snapshot
   `MSOSOPOREC/phase8/snapshot_pages.ps1` (+ `snapshot_live_state.ps1`).
2. **Pull/merge** (shared assets + hooks): merge `feat/erp-shell-v1` → main →
   Frappe Cloud deploy of the target commit.
3. **Asset build** (shared assets): FC deploy runs `bench build` — required
   (new `ec_shell.bundle.js/.css` must be compiled + content-hashed).
4. **Restart** (hooks/web include): FC deploy restarts automatically — required
   for the new `web_include_css` / extended `web_include_js` to take effect.
   **`bench migrate`: NOT required** (no schema, no patches.txt entry).
5. **Page sync** (pilot Web Pages; SM session, one POST each, explicit
   confirmation per A33):
   - `/api/method/ecentric_workspace.approval_center.hub_page_sync.sync_approvals_page`
   - `…approval_center.leave.page_sync.sync_leave_page`
   - `…approval_center.hr_activity.page_sync.sync_hr_activity_page`
   - `…approval_center.dashboard.page_sync.sync_dashboard_page`
6. **Cache clear** (page sync): `frappe.website.doctype.web_page…` route cache —
   use the existing force_clear_cache step from the proven deploy scripts.
7. **Smoke tests** (prod): the 4 routes render; correct active item; bell badge
   + dropdown on all 4 (new capability there); `?id=&tab=` deep link on leave;
   back/forward; `/home`, `/pm`, `/alerts`, one non-pilot approval page
   (`/approvals/ai-topup`) unchanged; no console errors.
8. **Kill-switch verify**: set `ec_shell_disabled: 1` → reload pilot page →
   fallback nav shows, page + NC still work → unset.
9. **NC verify**: `erp-inspection/verify_global_notification_center.ps1`.
10. **Rollback**: see below.

## Rollback
- **Operational (instant):** `ec_shell_disabled: 1` in site config. Pages stay
  usable via fallback nav; NC unaffected; approval logic unaffected.
- **Page-level:** re-run each pilot page's sync method from the pre-1B commit
  (`git checkout <pre-1B-sha> -- ecentric_workspace/approval_center/frontend/<f>.html`
  in a scratch clone → run sync). Restores the embedded sidebar exactly.
- **Code:** revert the single Phase 1B commit → FC deploy (build+restart) →
  re-sync the 4 pilot pages → clear cache. No migrate-down; approval business
  logic untouched by construction.
