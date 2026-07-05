# Approval Rollout Template v1

> Standard for building the remaining Approval Center forms **fast and consistently**, using AI Topup v1 as
> the reference implementation. Read this before starting form #2.
>
> Reference implementation: **AI Topup v1** — route `/approvals/ai-topup`, type `AI_TOPUP`, process `AI_TOPUP-V1`.
> Reference code: `approval_center/engine/*` (shared engine), `approval_center/ai_topup/*` (business layer),
> `approval_center/api/ai_topup.py` (API), `approval_center/frontend/ai_topup.main_section.html` (page).

---

## 1. Purpose

This template exists so the remaining approval forms roll out quickly **without** each one becoming a
separate custom mini-app. Every new approval reuses the same shared Approval Engine, the same API shape, the
same page structure, and the same UX/error rules that AI Topup v1 already proved in UAT. Speed comes from
**copying the pattern, not the business fields**, and from not re-deriving decisions that are already made.

The long-term ERP standards still apply (maintainability, scalability, permission-awareness, auditability,
reusable services, clean data model, clear module boundaries). This template is how we keep those standards
while moving fast.

## 2. Current decision (locked)

- **ERP Website Shell/Menu v1 is deferred** until after the 19 forms are done. Each approval page keeps
  embedding the current `.ec-sidebar`/topbar shell for now.
- **Versioned Web Page Sync is deferred** until after the 19 forms. Frontend page changes still require a
  manual page sync (see section 11).
- Each approval **may still be its own Web Page route** (`/approvals/<slug>`) for now.
- **But every approval page must follow the structure and behavior in this document.** No freestyle approval
  pages, no bespoke UX, no per-form invention of stepper/timeline/error patterns.

## 3. Standard approval page structure

Single Web Page (`<slug>.main_section.html`) mounted under `#ec-<slug>-root`, reusing the shell + tokens.
Required, in this order/behaviour:

- **Header** — title, subtitle, breadcrumb, and a status badge in Detail.
- **Tabs** (chips): `Tao yeu cau`, `Yeu cau cua toi`, `Can toi duyet`, and `Cho Operation xu ly` *(only if the
  form has a fulfillment step)*. Tabs shown are capability-gated from the bootstrap payload.
- **Create Request** — sectioned form (requester context read-only, business fields, summary), Draft +
  Submit. Primary action is submit (validate then save then submit then detail); `Luu nhap` is secondary.
- **Draft state** — request exists but not submitted; Detail shows a **preview stepper** (see section 7) and
  a clear action panel (submit / continue editing / cancel).
- **My Requests** — paginated, filterable list scoped to the requester; a business-facing step label
  (`Buoc X/N - <level>`), never raw `Level N`.
- **Need My Approval** (`Can toi duyet`) — actionable current-level rows + a history section.
- **Fulfillment / Operation queue** — *if applicable* — unclaimed / mine / (SM) others, claim + complete.
- **Detail state** — consolidated read view: header + **runtime stepper** + business sections + attachments +
  fulfillment + action panel + timeline.
- **Stepper** — see section 7 (draft preview vs runtime; resubmit/edit shows runtime + info banner).
- **Timeline** — see section 9.
- **Action modal** — namespaced dialog (see section 7) for approve / request-info / reject / cancel / admin
  override.
- **Information Required / Resubmit mode** — editable form **with the runtime stepper + info banner shown
  above it** (never a blank create form).
- **Completed read-only display** — evidence, amounts, and outcome shown read-only; completed fields locked.

## 4. Standard approval process model

All process metadata lives in the **shared engine catalog + process DocTypes** — never re-modelled per form.

- **Approval type code** — `EC Approval Type.approval_code` (e.g. `AI_TOPUP`). One per business approval.
- **Process version code** — `EC Approval Process.process_code` (e.g. `AI_TOPUP-V1`). A new version = a new
  record; `active_process_key` (DB-unique) guarantees at most one **Active** process per type.
- **Active process rule** — exactly one Active process per type; go-live via the split
  `enable_..._uat` then `publish_..._after_uat` tooling (System-Manager-only). Card stays inactive during UAT.
- **Level sequence** — `EC Approval Level.level_no` (unique per process), fully dynamic (add L4/L5 by config,
  never by code).
- **Approval mode** per level — `Any One`, `All Required`, `Minimum Count` (implemented). Participant
  `source_type`: `User`, `Role`, `Requester Manager`, `Department Manager` (all supported via
  `resolve_participants`, fail-closed to an active System User). "Specific User" = `source_type: User`.
- **Fulfiller level** — optional; process-level participants with `participant_purpose: Fulfiller`.
- **SLA policy** — optional `EC Approval SLA Policy` per level (business-hours calculator + Holiday List).
- **Escalation** — **placeholder / not implemented** in v1. Do not invent per-form escalation; it is a
  deferred framework item (section 13).

Snapshot rule: at submit, the engine **freezes** the level/approver config into `EC Approval Request Level` /
`EC Approval Request Approver`. Later config edits never alter in-flight requests.

## 5. Standard DocType design pattern

Choose the minimum that fits the business:

| Need | Use |
|---|---|
| Simple request | one **business DocType** only |
| Repeating line items | business DocType **+ child table(s)** |
| References existing master | **Link** to the master DocType (do not copy its data) |
| Produces a document on completion | create the target doc in the completion **service** |
| Updates master on completion | upsert the master in the completion **service** (guard duplicates) |

**Standard fields every business DocType should carry:**
`request_title` (Data, required at submit, auto-suggested), `requested_by`/`employee`/`department`/`company`
(submission snapshot; department locked after submit), `approval_type`, `approval_request`
(Link -> `EC Approval Request`, read-only pointer), a `*_status` **business** status only if it differs from
the approval status, `amount` + `currency` (separate fields) + a tax/fee basis Select where money is involved,
`request_attachment`, `purpose`/`requester_note`, fulfillment fields where applicable
(`fulfillment_status`, owner, `actual_*` evidence, `payment_proof`, `invoice_*`), and `material_signature`
(for resubmit material-change detection).

**Ownership rules (do not violate):**
- **Approval STATE + audit live in the Approval Engine** (`EC Approval Request` / `Request Level` /
  `Request Approver` / `EC Approval Action`). The business DocType has **no** `approval_status`/`current_stage`.
- **Business data lives in the business DocType.**
- Do **not** duplicate approval-status logic in the business layer or the frontend.
- One concept = one canonical DocType + one canonical field name.
- Fieldnames must not shadow `Document`/`Meta` members (e.g. `process`, `validate`, `submit`); every DocType
  folder needs `__init__.py` + `.json` + `.py` (class = name minus spaces) or migrate fails.

## 6. Standard API contract

One `approval_center/api/<slug>.py` module, all `@frappe.whitelist`, server-side scoped. Mirror AI Topup:

**Read**
- `get_bootstrap()` — user/employee context, `manager_resolvable`, available tabs, `form_options`.
- `get_form_options()` — link/select option lists.
- `list_my_requests(filters, start, page_length)` — scoped `requested_by`, capped page size, +step-label data.
- `list_need_my_approval(section)` (a.k.a. `list_my_approvals`) — actionable current-level rows / history.
- `list_fulfillment_queue(section)` — *if applicable*, eligibility-gated.
- `get_detail(name)` (a.k.a. `get_request_detail`) — **one consolidated payload**: `business`, `approval`,
  `levels`, `approvers`, `fulfillment`, `attachments`, `timeline`, `process_preview` (draft only),
  `capabilities`.
- dashboard/summary — *optional*.

**Write**
- `save_draft(name, payload)` — allowlisted editable fields only; controller validates.
- `submit_request(name)` — thin wrapper over the engine submit service.
- `approve(name, comment, approved_amount?)` — routes amount adjustments to the finance service.
- `reject(name, comment)` — mandatory reason.
- `request_information(name, comment)` — mandatory comment.
- `resubmit(name, payload)` — save then material-signature-aware resubmit.
- `claim_fulfillment(name)` / `complete_fulfillment(name, payload)` — *if applicable*.
- `admin_approve_current_level(name, reason)` — SM-only override for UAT/support (no impersonation).

**Rules**
- **Backend is the boundary.** Whitelisted APIs use `frappe.get_all`/`get_doc` **after** explicit scope/role
  checks; capability flags in the payload are advisory — every write re-validates.
- Frontend **never** bypasses permission/status validation.
- **No raw DB/system errors to users.** Wrap: friendly Vietnamese for known cases, generic Vietnamese for
  unknown/500; raw error to `console` only.
- Suppress Frappe share/assignment popups centrally (see section 8).

## 7. Standard frontend behavior

- **No raw Frappe msgprint/share popup** — suppressed at the engine `assign`/`close_todos` helpers.
- **No raw DB keys/errors** — friendly VN via a `mapErr`-style mapper; generic message for SQL/IntegrityError.
- **Delegated, namespaced action dispatch** — one delegated `click` listener (capture phase) on a stable
  root, dispatching `[data-act]`/`[data-action]`; action buttons carry `type="button"`. Never rely on
  per-element `onclick` that dies on re-render.
- **Namespaced modal** — dialog class `ec-<slug>-modal` / overlay `ec-<slug>-overlay` with `display:flex`,
  never generic `.modal`/`.overlay` (collides with Frappe/Bootstrap and gets hidden). `role="dialog"`,
  `aria-modal`, Escape to close, focus in/restore.
- **Stepper** — after submit, use **runtime** levels (`EC Approval Request Level`/`Approver`); Draft/create
  use `process_preview`; **resubmit/edit must show the runtime stepper + Information Required banner** above
  the editable form. One continuous base + progress line (not per-step connectors).
- **Completed view is read-only.**
- **Hydration must survive a hard refresh** and mode switches (e.g. Existing-Account selection retained).
- Amount + currency shown **separately**; tax/fee basis shown as a Vietnamese label, never the raw internal
  value.

## 8. Standard ToDo lifecycle

Use the engine `assign` / `close_todos` helpers only — **never** mutate `ToDo` / `_assign` from the frontend
or from business code.

- **Submit** -> create ToDo(s) for the current (first) level's approver(s). `assign` is idempotent (skips a
  user who already has an open ToDo).
- **Approve** -> the level completes -> `_activate_level` **closes the prior level's ToDos** then assigns the
  next level. `Any One` marks the other pending approvers **Skipped** (their ToDos close too).
- **Request Information** -> close the level's ToDos (requester task optional/not implemented in v1).
- **Resubmit** -> re-activate the resuming level -> current-level approver ToDo recreated (no duplicates).
- **Complete / Reject / Cancel** -> close all open ToDos. Fulfillment: claim keeps the owner, closes redundant
  fulfiller ToDos; completion closes the owner's ToDo.
- **Invariant:** no duplicate/stale open ToDos for the same user+request.

## 9. Standard timeline / audit behavior

Append-only `EC Approval Action`. Standard actions:
`Submitted`, `Approved`, `Rejected`, `Information Requested`, `Resubmitted`, `Skipped`, `Assigned`/`Started`
(fulfillment), `Completed`, `Cancelled`, and `Approved` with an "Admin override" comment for SM override.

**Rules**
- Never delete or manually edit audit rows.
- Timeline queries must select **only actual `EC Approval Action` columns** (it stores `request_level`, not
  `level_no`/`level_name` - derive labels safely; omit when unavailable). No column that does not exist.
- No frontend-only/fake timeline entries.
- Actor on an admin override is the real System Manager, never the impersonated approver.

## 10. Standard validation checklist

- Required fields present (incl. `request_title`, amount where applicable).
- Valid links (e.g. Existing account resolves to an **active** master; no free text).
- Duplicate prevention (e.g. block creating a master that already exists on the unique key; friendly message).
- Amount and currency are **separate** (no concatenation); mandatory comment when approved amount != requested.
- Attachment/evidence requirements enforced (e.g. payment proof always required; invoice conditional).
- **Current approver only** may act; non-current/non-permitted actions rejected backend-side.
- Invalid status transitions blocked (terminal request not re-actionable; only Information Required resubmits).
- Stale/version conflict handled with a reload message, not a raw error.
- All of the above enforced **backend-side** (permission-safe), even where the frontend hides the control.

## 11. Standard deploy checklist

1. Branch from **latest `main`**; keep scope to `approval_center/` (scope check).
2. Local: frontend jsdom tests, `node --check`, `py_compile`, DocType JSON valid, `git diff --check`.
3. PR / review (Git is the source of truth).
4. `bench update` / pull on the bench host.
5. **`bench --site <SITE> migrate` only if a DocType/schema/JSON changed** (additive columns are safe).
6. **Manual page sync if the frontend Web Page changed** - run the form's page-sync (or the idempotent
   `p00x` create/update patch), because **Frappe does not re-run an already-applied patch** and there is no
   versioned page-asset sync yet.
7. `bench restart` if backend Python changed.
8. Hard refresh (Ctrl+Shift+R).
9. Smoke test the happy path + one rejection.
10. **Do not publish the catalog card before UAT passes** (keep card inactive; test via the direct route).

> Known limitation: the `p007`-style page patch does **not** auto-re-run once applied, so frontend Web
> Page changes require an explicit page sync each deploy until Versioned Web Page Sync exists (section 13).

## 12. Definition of Done (per approval form)

A form is Done only when **all** hold:
DocTypes created (+ controllers) - process configured (levels/approvers/SLA) - catalog card **hidden during
UAT** - direct route works - draft/save/submit works - full approval flow works - request-information +
resubmit works - fulfillment works (if applicable) - ToDo lifecycle correct - timeline correct - permissions
tested (current-approver-only, scope) - all user-facing errors clean (VN, no raw DB) - **UAT passed** -
catalog card **published** - release note updated.

Track these states **separately**: *implemented* != *deployed* != *tested* != *published*.

## 13. Known technical debt - deferred until after the 19 forms

- **ERP Website Shell/Menu v1** - centralize sidebar/menu/header; stop each Web Page embedding its own shell.
- **Centralized route/card visibility.**
- **Versioned Web Page Sync** (or page-asset sync) - remove the manual page-sync step.
- **Shared frontend component library** (stepper, modal, combobox, list) extracted from AI Topup.
- **Shared approval page renderer** - a data-driven page so each form is mostly config + business sections.
- **Consolidated approval dashboard.**
- **Broader notification / escalation framework** (SLA breach reminders, escalation).

Do not implement these during the 19-form rollout; log them here and address after.
