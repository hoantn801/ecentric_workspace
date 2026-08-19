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
web_include_js = ["notification_center.bundle.js", "ec_shell.bundle.js", "ec_datepicker.bundle.js"]

# ERP Shell v1 (Phase 1B pilot). Both assets are loaded site-wide via the same
# proven content-hashed-bundle mechanism as the Notification Center, but
# ec_shell.js is a hard NO-OP unless the page opts in with a
# `data-ec-shell="1"` marker node (Phase 1B: only the 4 approval pilot pages).
# Kill switch: site_config `ec_shell_disabled: 1` (fail-closed for the shell
# only; never affects Notification Center or any business logic).
web_include_css = ["ec_shell.bundle.css", "ec_datepicker.bundle.css"]

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
        # AC-1a: close assignment ToDos when a Task enters a terminal state
        # (keeps the shared Action feed / tabToDo hygienic).
        "on_update": "ecentric_workspace.pm.api.todo_lifecycle.pm_task_close_todos_on_terminal",
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
            "ecentric_workspace.platform.esign.tasks.poll_pending",
        ],
    },
}

# esign S2A: stale monitor + orphan-file scan share the same kill switch and are
# inert without enabled profiles.
scheduler_events["hourly"].append(
    "ecentric_workspace.platform.esign.tasks.sweep_stale")
scheduler_events["daily"].append(
    "ecentric_workspace.platform.esign.tasks.orphan_file_scan")
# esign S2B-C1: bounded retry (*/30) of signed-PDF retrieval for terminal-completed
# packages whose signed bundle is not yet complete. Safe GET/download only; never resends
# AddDocument/bulk-process. Same kill switch (ec_esign_scheduler_disabled) + per-provider
# integration gate (exits with zero SCTS calls while OFF).
scheduler_events["cron"].setdefault("*/30 * * * *", []).append(
    "ecentric_workspace.platform.esign.tasks.retrieve_signed_bundles")

# PM time-blocking: remind users to confirm elapsed unconfirmed hours TWICE a day
# (site timezone Asia/Ho_Chi_Minh = Vietnam): 09:00 + 18:00.
scheduler_events["cron"].setdefault("0 9 * * *", []).append(
    "ecentric_workspace.pm.api.schedule.nudge_unconfirmed")
scheduler_events["cron"].setdefault("0 18 * * *", []).append(
    "ecentric_workspace.pm.api.schedule.nudge_unconfirmed")

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
# Custom Fields owned by this app. Filtered so only these Custom Fields are
# exported/synced -- never every Custom Field on the site.
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["name", "in", [
            "Project-ec_department", "Project-ec_manager",
            # Phase 1b.3.1b: fulfillment-action marker on ToDo (p044) -- scopes the
            # fulfillment ToDo lifecycle so unrelated ToDos are never touched.
            "ToDo-ec_fulfillment",
            # PM v2 Batch G1 checklist foundation (created by p005_pm_checklist):
            "PM Recurrence-checklist_template", "Task-pm_checklist",
            # Brand consolidation (2026-07-28): native Brand is the single brand
            # master after Brand Approver was retired. ALL 16 ec_* Custom Fields on
            # Brand are app-owned and MUST ship as fixtures -- a bench built from
            # this app alone would otherwise get a Brand with no ec_status /
            # ec_kam_owner, and alerts.permissions.get_allowed_brands would fall
            # back to an EMPTY scope (every KAM sees zero brands, silently).
            # ec_kam_owner = daily KAM for marketplace alerts (Alert Center
            # decision D1) - NOT the approval manager.
            "Brand-ec_legacy_key",
            "Brand-ec_sect", "Brand-ec_brand_code", "Brand-ec_brand_name",
            "Brand-ec_status", "Brand-ec_parent_client", "Brand-ec_cb1",
            "Brand-ec_kam_owner", "Brand-ec_manager_email",
            "Brand-ec_leader_email", "Brand-ec_finance_email",
            "Brand-ec_sect2", "Brand-ec_approval_recipe", "Brand-ec_gbs_recipe",
            "Brand-ec_cb2", "Brand-ec_boxme_customer",
            # C4b B7 (2026-08-03): buoc "Gui lai / Can sua" cho MSO / Sales Order /
            # Purchase Order. ec_revision_reason giu ly do nguoi duyet yeu cau sua,
            # ec_revision_count dem so lan. CHUNG KHONG PHAI TRANG THAI -- trang thai
            # duy nhat van la workflow_state cua Frappe Workflow. Nhan "Can sua" tren
            # trang /approval duoc suy ra tu (workflow_state == "Draft" VA
            # ec_revision_reason con noi dung), nen khong co cho nao luu trang thai
            # song song. Thieu 2 field nay thi ec_*_before_save se chan moi buoc
            # Pending -> Draft (bat buoc co ly do >= 10 ky tu) => phai ship cung nhau.
            "MSO-ec_revision_reason", "MSO-ec_revision_count",
            "Sales Order-ec_revision_reason", "Sales Order-ec_revision_count",
            "Purchase Order-ec_revision_reason", "Purchase Order-ec_revision_count",
        ]]],
    },
    {
        "dt": "Role",
        "filters": [["name", "in", ["PM Manager", "PM Member"]]],
    },
]
