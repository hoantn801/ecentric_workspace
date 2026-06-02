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

# Scheduled Tasks
# ---------------
# scheduler_events = {
#     "cron": {
#         "*/15 * * * *": [
#             "ecentric_workspace.tasks.sync_sharepoint_attendance"
#         ]
#     }
# }

# Permissions
# -----------
# PM v2 row-level visibility (PM1-T03 activation). Backend-enforced for Project
# and Task. Non-PM users get "" (unchanged) so other modules are NOT affected.
permission_query_conditions = {
    "Project": "ecentric_workspace.pm.permissions.get_permission_query_conditions_for_project",
    "Task": "ecentric_workspace.pm.permissions.get_permission_query_conditions_for_task",
}

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
        "filters": [["name", "in", ["Project-ec_department", "Project-ec_manager"]]],
    },
    {
        "dt": "Role",
        "filters": [["name", "in", ["PM Manager", "PM Member"]]],
    },
]
