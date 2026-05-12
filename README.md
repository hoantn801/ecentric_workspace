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

## License

MIT
