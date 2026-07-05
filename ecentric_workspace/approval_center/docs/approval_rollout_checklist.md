# Approval Rollout Checklist / Tracker

> One row per approval form. Track **implemented / deployed / tested / published as separate states** (a form
> can be Frontend-done but not Deployed, or Deployed but not Published). Update this file in the same PR that
> advances a form's state. Git is the source of truth.

Legend: `-` = not started · `WIP` = in progress · `OK` = done · `n/a` = not applicable.
UAT status: `not started` / `in UAT` / `passed` / `blocked`.

---

## Rollout tracker

| # | Approval name | Route | Business owner | Process code | Business DocType | Fulfillment needed | Schema done | Backend done | Frontend done | Tests done | UAT status | Published | Notes / blockers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | AI Topup | /approvals/ai-topup | (Ops) | AI_TOPUP-V1 | EC AI Topup Request | yes | OK | OK | OK | OK | passed | OK | Reference implementation |
| 2 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | Start with intake template |
| 3 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 4 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 5 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 6 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 7 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 8 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 9 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 10 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 11 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 12 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 13 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 14 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 15 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 16 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 17 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 18 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |
| 19 | (TBD) | /approvals/_____ | _____ | _____-V1 | _____ | _____ | - | - | - | - | not started | - | |

> The 19 approval names are the ones catalogued during B1 (seeded "Coming Soon" on `/approvals`). Fill each
> row from that catalogue as work starts; do not invent names here. Rows 2-19 are placeholders.

## Per-form column meaning

- **Schema done** — DocTypes (+ controllers, `__init__/.json/.py`) created and migrate-clean.
- **Backend done** — process configured; `api/<slug>.py` read+write endpoints; services; validation.
- **Frontend done** — page follows `approval_rollout_template_v1.md` (tabs, stepper, modal, error handling).
- **Tests done** — jsdom + `bench run-tests` backend suite green.
- **UAT status** — card hidden, tested via direct route; sign-off recorded.
- **Published** — catalog card activated (`publish_..._after_uat`) only after UAT passed; release note updated.

## Batch-level deferred debt (all forms)

See `approval_rollout_template_v1.md` section 13. Do not start any of these during the 19-form rollout:
ERP Website Shell/Menu v1, centralized navigation, Versioned Web Page Sync, shared component library, shared
page renderer, consolidated dashboard, notification/escalation framework.
