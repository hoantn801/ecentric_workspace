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
        "filters": [["name", "in", ["Project-ec_department", "Project-ec_manager"]]],
    },
]
