# eCentric Workspace

Employee portal and approval workflow custom app for eCentric, built on Frappe Framework.

## Features

- MSO/SO/PO/REC approval workflow (multi-level chain)
- Vendor Code Request workflow
- Budget tracking (MSO -> SO, SO -> PO)
- Brand-based approver mapping
- SharePoint file storage integration (Phase 2)
- Microsoft 365 SSO

## API Endpoints

All under `/api/method/ecentric_workspace.api.<method>`:

- `submit_mso` - Create MSO Request + chain
- `submit_so` - Create Service Request + chain
- `submit_po` - Create Procurement Request + chain
- `submit_rec` - Create Reconciliation Request + chain
- `submit_vendor_request` - Create Vendor Code Request + chain
- `approval_decision` - Approve/reject + side effects
- `get_mso_budget` - Total/used/remaining for MSO
- `get_so_budget` - Total/used/remaining for SO
- `lookup_parents` - GET by type+id
- `get_ticket_detail` - alias of lookup_parents

## Install

```bash
cd ~/frappe-bench
bench get-app https://github.com/<your-org>/ecentric_workspace.git
bench --site <site_name> install-app ecentric_workspace
bench --site <site_name> migrate
bench restart
```

## Local Preview (no bench required)

`approval_center/frontend/*.main_section.html` fragments call the real backend
via `frappe.call`, so they normally only render inside a live site. For a
quick look at layout/CSS/JS changes before pushing, without a full Frappe
bench:

```bash
python tools/dev/local_preview.py [port]   # default 8787
```

Open `http://127.0.0.1:<port>/` for the page list. The server:

- Serves each `*.main_section.html` fragment wrapped in a shell that stubs
  `window.frappe.call` (and `/api/method/upload_file`) with fake data, so
  tabs/buttons/forms wire up and render.
- Also serves the real `ec_shell.js` / `ec_shell.bundle.css` /
  `notification_center.js` (the shared sidebar/topbar chrome every page loads
  via `hooks.py` `web_include_js`/`web_include_css`) so the shell renders
  styled instead of as raw fallback markup.
- Serves the real production **routes** too (`/approvals`, `/approvals/dashboard`,
  `/approvals/outside-work`, `/mso-plan-form`, ...), not just `/page/<file>`, by
  importing each `page_sync.py`/`hub_page_sync.py` under a stub `frappe`
  (`tools/ci/stubs`, same trick `tools/ci/check.py` uses) and calling its real
  `_html()`. That's what makes sidebar links inside the preview actually
  navigate instead of 404ing. A couple of pages don't fit this shape
  (`pm/pages.py`, `legacy_pages/home` — Jinja/guarded) and still 404.
- Reads files from disk on every request — no restart needed after an edit,
  just refresh the browser tab.

Not a substitute for testing on a real bench/site: all API data is fake, and
there's no permission/business-logic checking. Use it for layout, CSS, and
JS-wiring checks only.

For a bench that mirrors production (real DB, real API, real permissions),
run this app inside a Frappe bench (Linux/WSL2) as in Install below.

## License

MIT
