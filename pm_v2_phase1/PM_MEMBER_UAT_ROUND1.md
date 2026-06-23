# PM Member UAT — Round 1 Handover

**Date:** 2026-06-22 · **Tester session:** `hoan.tran@ecentric.vn` (real non-superuser; NOT Administrator, NOT System Manager) · **Browser:** Edge Hoàn · **Scope under test:** PM v2 incl. G4.3 terminal lock.

## UAT status
- **Functional non-admin UAT: PASS**
- **Restricted-scope UAT: PENDING** (needs a genuinely scope-restricted PM Member)
- **Pilot blocker: NO** — provided initial pilot users are management / full-visibility users.
- **Required before wider rollout: YES** — must test once with a genuinely restricted PM Member.

## User tested
- `hoan.tran@ecentric.vn`: valid non-superuser session. Verified `get_logged_user` ≠ Administrator and no `System Manager` role.

## Cases passed
1. Open `/pm` + in-scope pages (Tổng quan, Việc của tôi, Dự án, Công việc, Timesheet, Recurring) — load OK, no hung spinner, no error.
3. Active task (TASK-2026-00071):
   - open modal — PASS
   - checklist tick/untick — PASS (reversible, restored)
   - Start Work — PASS (user already had a Paused timer on TASK-2026-00003; single-timer guard shown correctly)
   - Log manually — PASS (permission verified, non-mutating probe)
   - Assign — PASS (permission verified, non-mutating probe; no PermissionError)
5. Terminal task (TASK-2026-00075 Done):
   - modal checklist read-only, no Start Work / Log manually / Assign, badge "Đã hoàn thành" — PASS
   - direct API (set_item / timer.start / timesheet.log / tasks.assign) → backend 417 blocked with correct messages — PASS
6. Workflow (block side): out-of-role/invalid action `set_status('Move to To Do')` → 417 "Not a valid Workflow Action" — PASS (blocked).
7. Console errors / API 4xx-5xx / spinners: 0 console errors, page-load APIs all 200, deliberate 417 throws handled, no hung spinners — PASS.

## Cases blocked (could not execute with this user)
2. "Only see permitted project/task" — BLOCKED: `hoan.tran` has full PM visibility (9/9 projects, 107 tasks); nothing to exclude.
4. "Out-of-scope task → PermissionError" — BLOCKED: no out-of-scope task exists for a full-visibility user.
6 (visibility part). "Only see role-appropriate workflow actions" — partially blocked: `get_transitions` returned `[]` for this user; block side verified, but role-scoped visibility differentiation needs a restricted user.

## Configuration (recorded as config, NOT a bug — do not change in this batch)
- `hoan.tran` has full PM data visibility (`can_see_all_pm_data` = true; likely Management department / manager-all).
- `hoan.tran` currently has no available workflow transitions (`get_transitions` = []); system correctly shows none and blocks attempts.
- No roles/permissions changed. No code changed. No new user created.

## No side effects
- No timers / timesheets / assignments created (used non-mutating permission probes + reversible checklist tick→untick).
- Did not touch hoan.tran's real Paused timer on TASK-2026-00003.
- No production data created or deleted.

## Exact requirement for the future restricted-scope session (Round 2)
Provide a real login for a PM Member who is **all** of:
1. has role `PM Member` (and may have `PM Manager` only if testing manager scope separately),
2. **NOT** `System Manager` / not Administrator,
3. **NOT** in the `Management` department (so `can_see_all_pm_data` = false),
4. is a member/owner/assignee of **only a subset** of projects/tasks — so at least one project AND one task exist **outside** their scope.

With that session, Round 2 will verify: case 2 (sees only in-scope), case 4 (out-of-scope task → PermissionError on view/API), and case 6 visibility (only role-appropriate workflow actions shown). Verify identity (`get_logged_user` + roles, confirm not System Manager and not full-visibility) before testing.
