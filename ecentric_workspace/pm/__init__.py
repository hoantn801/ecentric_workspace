"""PM v2 module (Phase 1).

Long-term ERP-standard Project & Task management built on native Frappe/ERPNext
DocTypes (Project, Task, ToDo, Comment, File, Workflow, Role Permission).

This package holds the PM v2 service layer and permission logic. It replaces the
legacy single mega-endpoint `pm_app_get_app_data` with small, view-specific,
permission-aware services.

Ticket: PM1-T00 (scaffold). Stubs only - NOT wired into hooks.py, NOT deployed
(no migrate). See PM_V2_PHASE1_BUILD_SHEET.md.
"""
