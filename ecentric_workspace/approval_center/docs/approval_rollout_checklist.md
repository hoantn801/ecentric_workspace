# Approval Rollout Checklist / Tracker

> One row per approval form. Track **Schema / Backend / Frontend / Tests / Deployed / UAT / Published as
> separate states** (a form can be Frontend-done but not Deployed, or Deployed but not Published). Update this
> file in the same PR that advances a form's state. Git is the source of truth.
>
> The 19 names come from `approval_center/seed/approval_types_seed.json` (patch `p002`). Business RULES for the
> 18 unbuilt forms are NOT yet in the repo — each is blocked on a completed `approval_form_intake_template.md`.
> See `approval_backlog_wave_plan.md` for pattern classification and the wave plan.

Legend: `-` = not started · `WIP` = in progress · `OK` = done · `n/a` = not applicable.
UAT: `not started` / `in UAT` / `passed` / `blocked`. Wave from the backlog plan.

---

## Rollout tracker

| # | Approval | Code | Route | Wave | Fulfillment | Schema | Backend | Frontend | Tests | Deployed | UAT | Published | Notes / blockers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | AI Topup | AI_TOPUP | /approvals/ai-topup | 0 | yes | OK | OK | OK | OK | OK | passed | **OK** | Reference implementation (Live) |
| 2 | Outside Work | OUTSIDE_WORK | /approvals/outside-work | 1 | no | - | - | - | - | - | not started | - | Recommended Form #2; needs intake |
| 3 | Payment Request | PAYMENT_REQUEST | /approvals/payment-request | 3 | maybe | - | - | - | - | - | not started | - | **Pattern E — SCTS digital-signing integration; separate design gate (no double SCTS submit)** |
| 4 | Document Request | DOCUMENT_REQUEST | /approvals/document-request | 1 | maybe | - | - | - | - | - | not started | - | Keep simple in v1 |
| 5 | Data Request | DATA_REQUEST | /approvals/data-request | 1 | maybe | - | - | - | - | - | not started | - | Keep simple in v1 |
| 6 | Special Bonus | SPECIAL_BONUS | /approvals/special-bonus | 2 | no | - | - | - | - | - | not started | - | Pattern B |
| 7 | HR Activity | HR_ACTIVITY | /approvals/hr-activity | 1 | no | - | - | - | - | - | not started | - | Wave 1 (4th); Pattern A pending intake |
| 8 | Employee Referral | EMPLOYEE_REFERRAL | /approvals/employee-referral | 2 | no | - | - | - | - | - | not started | - | Alternate Wave 1 (4th) if simpler than HR Activity |
| 9 | Resignation Requests | RESIGNATION | /approvals/resignation | 2 | no | - | - | - | - | - | not started | - | Possible Employee update (D) |
| 10 | Promotion Request | PROMOTION_REQUEST | /approvals/promotion-request | 2 | no | - | - | - | - | - | not started | - | Possible Employee update (D) |
| 11 | Employee Lateral Move | LATERAL_MOVE | /approvals/lateral-move | 2 | no | - | - | - | - | - | not started | - | Possible Employee update (D) |
| 12 | Asset Request | ASSET_REQUEST | /approvals/asset-request | 2 | maybe | - | - | - | - | - | not started | - | Asset master (D) |
| 13 | Asset Damage or Loss | ASSET_DAMAGE_LOSS | /approvals/asset-damage-loss | 2 | yes | - | - | - | - | - | not started | - | Evidence + Asset status |
| 14 | Daily Target Setting | DAILY_TARGET | /approvals/daily-target | 3 | no | - | - | - | - | - | not started | - | May need child rows |
| 15 | Daily Target — Project Level | DAILY_TARGET_PROJECT | /approvals/daily-target-project | 3 | no | - | - | - | - | - | not started | - | Per-project child rows |
| 16 | Hiring Request | HIRING_REQUEST | /approvals/hiring-request | 3 | maybe | - | - | - | - | - | not started | - | Design gate (E) |
| 17 | Purchase Request | PURCHASE_REQUEST | /approvals/purchase-request | 3 | maybe | - | - | - | - | - | not started | - | Item lines / PO (E) |
| 18 | Monthly Budget Setting | MONTHLY_BUDGET | /approvals/monthly-budget | 3 | no | - | - | - | - | - | not started | - | Budget-line child (E) |
| 19 | Annual Budget Setting | ANNUAL_BUDGET | /approvals/annual-budget | 3 | no | - | - | - | - | - | not started | - | Budget-line child (XL) |

> **Routes above are proposed slugs** (not yet created — every unbuilt row has `route = ""` in the catalogue).
> Only **AI Topup** is Live/Published. Nothing else may be marked Published until it truly passes UAT and its
> card is activated. `Fulfillment` is *inferred, pending intake*.

## Per-form column meaning

- **Schema** — DocTypes (+ controllers, `__init__/.json/.py`) created and migrate-clean.
- **Backend** — process configured; `api/<slug>.py` read+write endpoints; services; validation.
- **Frontend** — page follows `approval_rollout_template_v1.md` (tabs, stepper, modal, error handling).
- **Tests** — jsdom + `bench run-tests` backend suite green.
- **Deployed** — migrated + page-synced on the site.
- **UAT** — card hidden, tested via direct route; sign-off recorded.
- **Published** — catalog card activated (`publish_..._after_uat`) after UAT passed; release note updated.

## Batch-level deferred debt (all forms)

See `approval_rollout_template_v1.md` section 13 and `approval_backlog_wave_plan.md`. Do not start any of these
during the 19-form rollout unless one becomes a hard blocker: ERP Website Shell/Menu v1, centralized
navigation, Versioned Web Page Sync, shared component library, shared page renderer, consolidated dashboard,
notification/escalation framework.
