# Approval Center — Backlog Inventory & Wave Rollout Plan

> Report-first planning for the remaining approval forms after **AI Topup v1** (published, reference impl).
> Standards: `approval_rollout_template_v1.md`, `approval_form_intake_template.md`, `approval_rollout_checklist.md`.
> Source of the 19 names: `approval_center/seed/approval_types_seed.json` (seeded by patch `p002`). **The 19
> approval NAMES are real (from the repo). Their business RULES/fields/levels are NOT in the repo** and must
> be supplied by the business owner via the intake template before coding each form.

---

## TASK 1 — Inventory (from the seeded catalogue)

All 19 rows exist as `EC Approval Type` catalogue entries with the fixed B1 defaults: `card_status = Coming
Soon`, `process_status = Discovery`, `route = ""` (empty), `visibility_mode = All Internal Users`,
`legacy_source = MS Teams`. **Only `AI_TOPUP` has been built** (route, business DocType, process, page,
published). For the other 18: catalog card exists, **no** business DocType, **no** process, **no** frontend
page.

| # | Approval name | Code | Category | Route | Status | Card | Biz DocType | Process | Page | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | AI Topup | AI_TOPUP | IT & Data | /approvals/ai-topup | **Live/Published** | yes | yes | AI_TOPUP-V1 | yes | Reference implementation |
| 2 | Payment Request | PAYMENT_REQUEST | Finance & Budget | — | Coming Soon | yes | no | no | no | Amount + proof |
| 3 | Annual Budget Setting | ANNUAL_BUDGET | Finance & Budget | — | Coming Soon | yes | no | no | no | Likely budget line items |
| 4 | Monthly Budget Setting | MONTHLY_BUDGET | Finance & Budget | — | Coming Soon | yes | no | no | no | Likely budget line items |
| 5 | Resignation Requests | RESIGNATION | HR | — | Coming Soon | yes | no | no | no | HR, possible Employee update |
| 6 | Special Bonus | SPECIAL_BONUS | HR | — | Coming Soon | yes | no | no | no | Amount approval |
| 7 | Hiring Request | HIRING_REQUEST | HR | — | Coming Soon | yes | no | no | no | May create requisition/opening |
| 8 | HR Activity | HR_ACTIVITY | HR | — | Coming Soon | yes | no | no | no | Possibly budgeted activity |
| 9 | Promotion Request | PROMOTION_REQUEST | HR | — | Coming Soon | yes | no | no | no | Possible Employee grade update |
| 10 | Employee Referral | EMPLOYEE_REFERRAL | HR | — | Coming Soon | yes | no | no | no | Possible referral bonus |
| 11 | Employee Lateral Move | LATERAL_MOVE | HR | — | Coming Soon | yes | no | no | no | Possible Employee dept/position update |
| 12 | Data Request | DATA_REQUEST | IT & Data | — | Coming Soon | yes | no | no | no | IT sibling of AI Topup |
| 13 | Daily Target Setting | DAILY_TARGET | Operations & Performance | — | Coming Soon | yes | no | no | no | Targets per period |
| 14 | Daily Target Setting — Project Level | DAILY_TARGET_PROJECT | Operations & Performance | — | Coming Soon | yes | no | no | no | Likely per-project child rows |
| 15 | Purchase Request | PURCHASE_REQUEST | Procurement & Asset | — | Coming Soon | yes | no | no | no | Item lines, may create PO |
| 16 | Asset Request | ASSET_REQUEST | Procurement & Asset | — | Coming Soon | yes | no | no | no | Links/creates Asset master |
| 17 | Asset Damage or Loss | ASSET_DAMAGE_LOSS | Procurement & Asset | — | Coming Soon | yes | no | no | no | Evidence + Asset status update |
| 18 | Outside Work | OUTSIDE_WORK | Attendance & Workplace | — | Coming Soon | yes | no | no | no | Simple attendance approval |
| 19 | Document Request | DOCUMENT_REQUEST | Administration | — | Coming Soon | yes | no | no | no | Request doc; admin issues |

**Completeness:** the 19 **names** are complete (repo). The **business specifications are incomplete** — no
fields/levels/approvers/rules for the 18 unbuilt forms exist in code. **Business owner must provide the
per-form specs (via `approval_form_intake_template.md`) before coding.**

## TASK 2 — Pattern classification (INFERRED — confirm at intake)

Patterns: **A** simple approval · **B** amount approval · **C** approval + fulfillment · **D** approval +
master-data update · **E** complex/special (child tables / integration / high permission).
Effort: **S** 0.5–1d · **M** 1–2d · **L** 2–4d · **XL** separate design phase.
> Every classification below is **inferred from the name** and marked pending intake — do not treat as the
> business rule. New net engine work is only expected for D/E; A/B reuse the current engine as-is.

| # | Approval | Pattern (inferred) | Effort | Fulfillment | Amount/ccy | Attach/proof | Dup prevention | Special perm | Likely DocTypes |
|---|---|---|---|---|---|---|---|---|---|
| 18 | Outside Work | A | S | no | no | maybe | no | no | 1 biz |
| 19 | Document Request | A (maybe C) | S–M | maybe (admin issues) | no | maybe | no | no | 1 biz |
| 12 | Data Request | A (maybe C) | S–M | maybe (data delivered) | no | maybe | no | no | 1 biz |
| 5 | Resignation Requests | A (maybe D) | M | no | no | maybe | no | HR-sensitive | 1 biz (+ Employee update?) |
| 8 | HR Activity | A/B | S–M | no | maybe | maybe | no | no | 1 biz |
| 10 | Employee Referral | A/B | S–M | no | maybe (bonus) | maybe | possible (dup referral) | no | 1 biz |
| 2 | Payment Request | **E (SCTS integration)** | **XL** | yes (signed file) | yes | yes | maybe | finance + signer | 1 biz + signing/callback |
| 6 | Special Bonus | B | M | no | yes | maybe | no | HR/finance | 1 biz |
| 9 | Promotion Request | A/D | M | no | maybe | maybe | no | HR-sensitive | 1 biz (+ Employee update?) |
| 11 | Employee Lateral Move | A/D | M | no | no | maybe | no | HR-sensitive | 1 biz (+ Employee update?) |
| 16 | Asset Request | D | M–L | maybe | maybe | maybe | yes (asset) | no | 1 biz + Asset master |
| 17 | Asset Damage or Loss | C/D | M–L | yes (evidence) | maybe (loss value) | yes | no | no | 1 biz (+ Asset status) |
| 13 | Daily Target Setting | A/E | M | no | numeric targets | no | no | manager scope | 1 biz (maybe child) |
| 7 | Hiring Request | E | L–XL | maybe | maybe (budget) | maybe | no | HR | 1 biz + child + master? |
| 14 | Daily Target — Project Level | E | L | no | numeric | no | no | project scope | 1 biz + child rows |
| 15 | Purchase Request | E | L–XL | maybe | yes | yes | maybe | procurement | 1 biz + item child (+ PO?) |
| 4 | Monthly Budget Setting | E | L–XL | no | yes | no | no | finance | 1 biz + budget-line child |
| 3 | Annual Budget Setting | E | XL | no | yes | no | no | finance | 1 biz + budget-line child |

## TASK 3 — Fastest-safe wave plan

### Wave 1 — simple approvals only, minimize new engine work (4 forms)
**Included:** Outside Work (A/S) · Document Request (A/S–M) · Data Request (A/S–M) · **HR Activity (A/S–M)**.
*(Employee Referral is the alternate 4th if HR Activity's intake turns out to involve budgeted amounts; pick
whichever intake is simplest.)*
> **Payment Request moved OUT of Wave 1** — the business clarification makes it a Pattern E / SCTS
> digital-signing integration (see the note under Task 4 and Wave 3). It is **no longer** a simple amount form.
**Why these first:** all fit **Pattern A** (simple approval), which the current engine + AI Topup patterns
already fully support — **no new engine changes**, no child tables, no external integration, no master-data
mutation, no amount/finance sensitivity, clear approvers, lowest operational risk. Outside Work de-risks the
scaffolding end-to-end with the least surface; Document Request and Data Request keep v1 as **simple approval**
(defer any "issuance / data-delivery as fulfillment" unless intake says it is mandatory).
**Shared implementation pattern:** copy the AI Topup template structure — one business DocType, `api/<slug>.py`
(read + write endpoints), `<slug>.main_section.html` following Template v1, a `p00x_create_<slug>_page` patch,
tests; card stays inactive until UAT.
**Estimated risk:** **Low** — no amount/finance, no integration, no master mutation in Wave 1.
**Dependencies:** business intake for each of the 4 (fields, level design, approvers). No engine dependency.

### Wave 2 — medium forms, introduce the master-update (Pattern D) pattern
Special Bonus (B/M) · HR Activity (A-B/S–M) · Employee Referral (A-B/S–M) · Resignation Requests (A-D/M) ·
Promotion Request (A-D/M) · Employee Lateral Move (A-D/M) · Asset Request (D/M–L) · Asset Damage or Loss
(C-D/M–L). These add the **completion-updates-master** pattern (Employee/Asset), which needs one reusable
"master upsert with duplicate guard" utility (AI Topup already has the reference in `_upsert_account`).
Effort mostly **M**, a few **L**.

### Wave 3 — complex / integration (separate design gates)
**Payment Request + SCTS digital signing (E / XL)** · Purchase Request (L–XL) · Annual Budget Setting (XL) ·
Monthly Budget Setting (L–XL) · Daily Target Setting (M) · Daily Target — Project Level (L) · Hiring Request
(L–XL). Child tables / item lines / budget lines / possible document generation (PO, job opening) and — for
Payment Request — an **external SCTS digital-signing integration**. Each needs its own **report-first design
gate** before coding.

**Payment Request — do NOT build as a simple duplicate form.** Today users submit the payment document in
**SCTS** for digital signing **and** again in the approval workflow (double work). The target is a single ERP
submission: create in ERP → Approval Center internal approval → ERP prepares/sends the signing package to
SCTS → SCTS signs → ERP receives the signed status/file → the Payment Request completes with audit +
attachments. A separate **Payment Request + SCTS design gate** must cover: the current SCTS flow; signing
package requirements; document templates; signer roles; file handoff; the signed-file callback (or a manual
upload fallback); the audit trail; error/retry handling; and whether ERP can integrate directly with the SCTS
API. Building it as a plain amount-approval that still forces a separate SCTS submission is explicitly out of
scope.

## TASK 4 — Recommended Approval Form #2

**Recommendation: `Outside Work` (OUTSIDE_WORK).**
- **Why next:** the lowest-risk, fastest full end-to-end cycle (Pattern A, effort **S**) — no amount, no
  fulfillment, no master mutation, a single obvious approver (Direct Manager). It validates that Template v1
  drops onto the shared engine cleanly and produces a repeatable scaffold, before we take on the amount
  pattern. (Payment Request is **no longer** a near-term candidate — it is now a Wave 3 / Pattern E form
  gated on the SCTS digital-signing integration design; see Wave 3.)
- **Expected route:** `/approvals/outside-work`
- **Expected business DocType:** `EC Outside Work Request`
- **Expected process code:** `OUTSIDE_WORK-V1`
- **Expected approval levels (to confirm):** L1 Direct Manager (`Requester Manager`, Any One) — possibly L2
  HR/Department Manager. No fulfillment.
- **Data still needed from business owner (blockers before coding):**
  1. Exact fields: date/time range, location/destination, purpose/reason, transport?, cost/amount? (if any → becomes Pattern B).
  2. Approval levels + approvers: Direct Manager only, or + HR/Department Manager? approval mode per level?
  3. Attachment required? (e.g. supporting doc)
  4. Any duplicate/overlap rule (same person, overlapping dates)?
  5. Cancel/withdraw rules and who can.
  6. My Requests / Need Approval list columns.
  7. Does completion update any master (attendance record)? If yes → Pattern D, re-scope.
- **Blocker:** the intake for Outside Work is **not in the repo** → cannot code until the business owner
  completes `approval_form_intake_template.md` for it.

## TASK 6 — Risks & speed-up (no quick hacks)

**Reuse from AI Topup (safe, high-leverage):** the shared engine (levels/modes/participants/SLA/snapshot),
the API shape (`get_bootstrap`/`list_*`/`get_detail`/`save_draft`/`submit`/`approve`/`reject`/
`request_information`/`resubmit`/`admin_approve_current_level`), the page structure (tabs/stepper/timeline/
namespaced modal/delegated actions/friendly errors), the amount+currency+tax-basis pattern, the ToDo
lifecycle, DocShare suppression, and the fulfillment scaffolding (for C forms).

**Do NOT copy blindly:** AI Topup business fields (ai_tool/account/plan/subscription), the Existing-Account
picker, and the AI-Account upsert — these are AI-Topup-specific. Extract the *pattern*, not the fields.

**Avoid over-engineering:** don't build per-form escalation, don't add child tables unless the intake requires
them, don't centralize the shell/nav mid-rollout, and don't create speculative abstractions before 3–4 forms
reveal the real shared shape.

**Safe shared utilities to create now (small, additive):** (a) a `master upsert with duplicate guard` helper
(generalize `_upsert_account`) for Wave 2; (b) a shared frontend error-map + namespaced-modal + delegated-
action + stepper snippet set copied verbatim per page for now (formal component library deferred). Keep these
additive and covered by tests.

**Deferred until after 19 forms (locked):** ERP Website Shell/Menu v1, Versioned Web Page Sync, shared
frontend component library, shared data-driven page renderer, consolidated dashboard, notification/escalation
framework — **unless one becomes a hard blocker**, in which case raise it as a separate design gate.

## Blockers summary

- **Business specifications for all 18 unbuilt forms are missing from the repo.** Names are known; fields,
  levels, approvers, and rules are not. Each form is blocked on its completed intake.
- No engine/code blocker for Wave 1 (all Pattern A — fully supported by the current engine today).
