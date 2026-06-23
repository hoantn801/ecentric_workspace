\# PM v2 — G4.3 Terminal Task Operational Lock + Safe Notifications Navigation



\## Status



\* Implemented: COMPLETE

\* Committed: COMPLETE

\* Pushed: COMPLETE

\* Backend deployed: COMPLETE

\* Frontend deployed: COMPLETE

\* Production verified: COMPLETE



\## Commit



`d54d753` — `PM v2 G4.3: lock terminal task operations and preserve PM navigation`



\## Scope



G4.3 hardened terminal task behavior and PM notification navigation.



\### Terminal operational lock



For tasks in `Done` or `Cancelled`, or with terminal status:



\* Block starting a new timer

\* Block resuming a paused timer

\* Block manual timesheet logging

\* Block assigning the task

\* Keep pause available for an existing running timer

\* Keep stop available so an existing timer can be flushed and saved

\* Preserve read-only worktime history

\* Reopen remains the governed path before further operational actions



\### Checklist regression protection



`checklist.set\_item` was refactored to use the shared terminal-state helper while preserving the exact G4.2 error message and behavior.



\### Notifications navigation



\* PM sidebar Notifications opens the global Notification Log in a new tab

\* PM topbar bell opens the global Notification Log in a new tab

\* The current `/pm` SPA view, active navigation, and breadcrumb remain unchanged



\## Files changed



\* `ecentric\_workspace/pm/permissions.py`

\* `ecentric\_workspace/pm/api/checklist.py`

\* `ecentric\_workspace/pm/api/timer.py`

\* `ecentric\_workspace/pm/api/timesheet.py`

\* `ecentric\_workspace/pm/api/tasks.py`

\* `ecentric\_workspace/pm/frontend/pm\_app.html`



No schema change.

No migration patch.

No workflow change.



\## Production verification



Production smoke test result: \*\*13/13 PASS\*\*



Verified:



\* Done modal hides Start Work, Log manually, and Assign

\* Cancelled modal hides Start Work, Log manually, and Assign

\* Active task keeps Start Work, Log manually, and Assign

\* Done checklist remains locked with badge `Đã hoàn thành`

\* Notifications sidebar opens a new tab and keeps `/pm` unchanged

\* Topbar bell opens a new tab

\* Terminal `timesheet.log` is blocked

\* Terminal `tasks.assign` is blocked

\* Terminal `timer.start` is blocked

\* Terminal `timer.resume` is blocked

\* Active pause/resume works

\* Terminal stop flushes the existing timer successfully

\* G4.2 checklist terminal message remains unchanged



No G4.2 regression was found.



\## Controlled test artifacts



\### Task



`TASK-2026-00030`



Final subject:



`\[PM TEST - CLOSED] Design homepage`



Final state:



\* `workflow\_state`: Cancelled

\* `status`: Overdue

\* `docstatus`: 0



This task must not be reused for future testing.



\### Timesheet



`TS-2026-00028`



\* Draft

\* 0h

\* Created by the controlled G4.3 timer lifecycle test

\* Retained as a test artifact

\* Not hard-deleted



\## Final conclusion



G4.3 is complete and production verified.



No code changes were made after smoke testing.



\## Pending outside G4.3



PM Member UAT remains pending and requires a real PM Member session. No impersonation or fabricated credentials were used.



