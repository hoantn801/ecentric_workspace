# Approval Form Intake Template

> Fill one copy per new approval form **before** any code. It captures everything an implementer needs to
> build the form against `approval_rollout_template_v1.md`. Copy this file to
> `docs/intake/<slug>_intake.md` and complete it. Nothing gets built until this is signed off by the business
> owner.

- Form slug (route): `_______` (e.g. `ai-topup`)
- Intake author / date: `_______`
- Business owner sign-off: `[ ] pending  [ ] approved`  by `_______` on `_______`

---

## 1. Basic information

- Approval name (display): `_______`
- Business owner: `_______`
- Department(s): `_______`
- Urgency / priority: `[ ] high  [ ] medium  [ ] low`
- Route: `/approvals/<slug>`  (slug: `_______`)
- Approval type code: `_______`  (e.g. `AI_TOPUP`)
- Process version code: `_______`  (e.g. `<TYPE>-V1`)
- Catalog card title: `_______`
- Catalog card description: `_______`
- Card icon / category: `_______`

## 2. Requester

- Who can submit (roles/all employees): `_______`
- Required role/department to submit: `_______`
- Does a department restriction apply? `[ ] yes  [ ] no`  detail: `_______`
- Requester must have a Direct Manager (`Employee.reports_to`)? `[ ] yes  [ ] no`
  (Required if any level uses `Requester Manager`.)

## 3. Business data

- Business DocType name: `_______`
- Core fields (name | type | required | notes):
  - `_______`
- Master data links (field -> master DocType): `_______`
- Child tables (name | rows represent | key fields): `_______`
- Attachments required? `[ ] yes  [ ] no`  which: `_______`
- Amount involved? `[ ] yes  [ ] no`  currency field + default: `_______`
- VAT / tax / fee basis relevant? `[ ] yes  [ ] no`  (Included/Excluded/Not Applicable/Unknown)
- Duplicate rule (unique key + behavior when it already exists): `_______`
  (e.g. block with a friendly message, or link the existing record.)

## 4. Approval flow

- Levels in order (level_no | name | approvers | mode | SLA):
  1. `_______`
  2. `_______`
  3. `_______`
- Approval mode per level: `Any One` / `All Required` / `Minimum Count` / `Specific User` /
  `Requester Manager` / `Department Manager` / `Role-based`
- SLA policy per level (hours, business-hours?): `_______`
- Can an approver adjust amount/business data? `[ ] yes  [ ] no`  which level + which field: `_______`
- Comment rules: reject reason required (always); request-info comment required (always);
  amount-change comment required when approved != requested? `[ ] yes  [ ] no`
- Request Information allowed? `[ ] yes  [ ] no`  from which levels: `_______`
- Restart-on-material-change on resubmit? `[ ] same level (default)  [ ] restart`  (only if the business rule
  already exists; do not invent restart.)

## 5. Fulfillment

- Is a fulfillment step needed? `[ ] yes  [ ] no`
- Fulfiller users/roles: `_______`
- Required proof/evidence at completion: `_______`
- Data created after completion (new DocType record?): `_______`
- Master data updated after completion (which master, which fields): `_______`
- Duplicate guard on the created/updated master: `_______`

## 6. Edge cases

- Cancel: who can cancel, in which states: `_______`
- Reject: terminal? reason required (yes): `_______`
- Resubmit: returns to same level (default) / other: `_______`
- Duplicate: expected behavior (block / link): `_______`
- Expired / stale request handling: `_______`
- Permission exceptions (SM override, delegated approver, etc.): `_______`

## 7. Reports / listing

- My Requests columns: `_______`
- Need Approval columns: `_______`
- Fulfillment queue columns (if applicable): `_______`
- Dashboard metrics (optional): `_______`

## 8. UAT test cases

- Happy path (submit -> all levels approve -> complete): `_______`
- Rejection (with reason, terminal): `_______`
- Request Information -> edit/resubmit -> returns to correct level: `_______`
- Permission test (non-current approver blocked backend-side): `_______`
- Duplicate / validation test (friendly message, no raw DB error): `_______`
- Fulfillment test (proof required, master create/update, no duplicate): `_______`
- Display/hydration test (hard refresh, no raw internal values, clean errors): `_______`
