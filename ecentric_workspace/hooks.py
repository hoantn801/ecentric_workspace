from . import __version__ as app_version

app_name = "ecentric_workspace"
app_title = "eCentric Workspace"
app_publisher = "eCentric"
app_description = "Employee portal + approval workflow"
app_email = "it@ecentric.vn"
app_license = "MIT"

# Global asset includes (website context only)
# --------------------------------------------
# Notification Center is an app-owned, ERP-wide foundation. It must run on EVERY
# custom eCentric Workspace page that renders the shared shell (the website/portal
# context: /home, /overview, /approval, /tasks, /weekly-update, Team Pulse, Alert
# Center, HR/Resource pages, and any future custom page), not just the homepage.
#
# `web_include_js` loads a CONTENT-HASHED bundle (notification_center.bundle.js ->
# /assets/.../dist/js/notification_center.bundle.<hash>.js) so deploys bust the
# immutable /assets cache uniformly. It injects this asset into
# every website-rendered page exactly once. This is deliberately NOT `app_include_js`
# (that would load into Frappe Desk /app/* and bind to Desk's native bell, which we
# must never do). The asset itself bails out on /app/* and on pages with no eCentric
# bell, and is single-install guarded so the homepage (which also still carries the
# legacy per-page loader) never double-installs.
web_include_js = ["notification_center.bundle.js"]

# Document Events
# ---------------
# Hook on doctype methods - approval side effects, validation, etc.

# doc_events = {
#     "Vendor Code Request": {
#         "on_update": "ecentric_workspace.hooks_handlers.vrq_on_update"
#     }
# }

# WR1A weekly obligation lifecycle (local-only until deployed).
doc_events = {
    "Weekly Team Update": {
        "on_update": "ecentric_workspace.weekly_report.events.on_weekly_update",
    },
    "ToDo": {
        "validate": "ecentric_workspace.weekly_report.events.validate_weekly_report_todo",
    },
    "Task": {
        # G4.10: enforce PM transition rules on EVERY save path (API + generic apply_workflow).
        "before_save": "ecentric_workspace.pm.api.tasks.pm_task_transition_guard",
    },
    "PM Task Label": {
        # G4.9: block hard-delete of an in-use label on EVERY delete path (incl. Administrator).
        "on_trash": "ecentric_workspace.pm.api.labels.pm_label_before_delete",
    },
    "PM Assignment Request": {
        # G5.0 B2: service-only mutation guard (rejects generic insert/update, incl. Administrator;
        # enforces append-only events) + hard-delete guard for decided audit history.
        "before_save": "ecentric_workspace.pm.api.assignment.pm_assignment_request_guard",
        "on_trash": "ecentric_workspace.pm.api.assignment.pm_assignment_request_before_delete",
    },
}

# Scheduled Tasks
# ---------------
# scheduler_events = {
#     "cron": {
#         "*/15 * * * *": [
#             "ecentric_workspace.tasks.sync_sharepoint_attendance"
#         ]
#     }
# }

# PM v2 recurring tasks: daily generation of due PM Recurrence rules.
# WR1A weekly obligations: daily idempotent generator (see
# ecentric_workspace.weekly_report.scheduler).
scheduler_events = {
    "daily": [
        "ecentric_workspace.pm.api.recurrence.run_due",
        "ecentric_workspace.pm.api.notifications.pm_overdue_scan",
        # Notification Delivery v1: new producers (distinct jobs, not duplicates).
        "ecentric_workspace.pm.api.notifications.pm_due_soon_scan",
        "ecentric_workspace.weekly_report.scheduler.wr_due_overdue_scan",
        "ecentric_workspace.weekly_report.scheduler.generate_weekly_obligations",
    ],
    # Alert Center Phase E (decision D2-E): both jobs are dry-run-safe and
    # kill-switchable via site_config `ec_alerts_scheduler_disabled: 1`.
    "hourly": [
        "ecentric_workspace.alerts.tasks.expire_automation_pauses",
    ],
    "cron": {
        "*/10 * * * *": [
            "ecentric_workspace.alerts.tasks.process_action_queue_job",
            # Hotfix B (2026-06-13): durable failed-order retry. LIGHTWEIGHT cron
            # = enqueue dispatcher only. Dispatcher finds brands with due items
            # and enqueues <=1 per-brand worker (Redis brand lock); the worker
            # atomically claims + re-pulls each item. Nothing is claimed in the
            # cron/dispatcher (no item stuck Processing while only queued).
            # Same kill switch ec_alerts_scheduler_disabled / ec_alerts_pull_disabled.
            "ecentric_workspace.alerts.tasks.dispatch_order_retries",
        ],
        # Narrow Omisell pull scheduler (approved 2026-06-10): quadruple-gated
        # in tasks.scheduled_omisell_pull - runs nothing until site_config
        # ec_alerts_scheduled_pull_brands lists at least one brand.
        "*/15 * * * *": [
            "ecentric_workspace.alerts.tasks.scheduled_omisell_pull",
        ],
        # Notification Delivery v1: bounded Teams retry sweep. Idempotent -- only picks
        # up EC Notification Delivery Log rows (channel=teams, status=Failed) whose
        # next_retry_at is due and attempt_count < MAX_ATTEMPTS.
        "*/5 * * * *": [
            "ecentric_workspace.notification_center.providers.teams.process_teams_retries",
            # esign S2A (2026-07-11): polling reconciler - AUTHORITATIVE status path
            # (Phase 1 works with polling only; callback is a later acceleration
            # signal). Kill-switched via site_config ec_esign_scheduler_disabled
            # (fail-safe: config read error => disabled). Inert until an esign
            # profile is enabled + gates opened.
            "ecentric_workspace.approval_center.esign.tasks.poll_pending",
        ],
    },
}

# esign S2A: stale monitor + orphan-file scan share the same kill switch and are
# inert without enabled profiles.
scheduler_events["hourly"].append(
    "ecentric_workspace.approval_center.esign.tasks.sweep_stale")
scheduler_events["daily"].append(
    "ecentric_workspace.approval_center.esign.tasks.orphan_file_scan")

# Permissions
# -----------
# PM v2 uses SERVICE-LAYER permission (ecentric_workspace.pm.api.*), NOT global
# permission_query_conditions, to avoid affecting other modules (GBS / Approval /
# Project dropdowns / reports). Revisit global hooks after UAT (PM1-T03 revised).
# permission_query_conditions = {}

# Override standard whitelisted methods
# -------------------------------------
# override_whitelisted_methods = {}

# Fixtures
# --------
# PM v2 custom fields owned by this app (PM1-T01). Filtered so only these two
# Custom Fields are exported/synced -- never every Custom Field on the site.
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["name", "in", [
            "Project-ec_department", "Project-ec_manager",
            # PM v2 Batch G1 checklist foundation (created by p005_pm_checklist):
            "PM Recurrence-checklist_template", "Task-pm_checklist",
            # Alert Center Phase B (ALERT_CENTER/01_PHASE_B_PLAN.md, decision D1):
            # daily KAM owner for marketplace alerts - NOT the approval manager.
            "Brand Approver-kam_owner",
        ]]],
    },
    {
        "dt": "Role",
        "filters": [["name", "in", ["PM Manager", "PM Member"]]],
    },
]
