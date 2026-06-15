from . import __version__ as app_version

app_name = "ecentric_workspace"
app_title = "eCentric Workspace"
app_publisher = "eCentric"
app_description = "Employee portal + approval workflow"
app_email = "it@ecentric.vn"
app_license = "MIT"

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
    },
}

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
