"""PM v2 - backend permission query conditions.

Real logic lands in PM1-T03. These functions will be registered in hooks.py:

    permission_query_conditions = {
        "Task": "ecentric_workspace.pm.permissions.get_permission_query_conditions_for_task",
        "Project": "ecentric_workspace.pm.permissions.get_permission_query_conditions_for_project",
    }

Scoping (planned):
  PM Member  - own + assigned + member-project rows
  PM Manager - rows in their department's / managed projects
  System Manager - all

Status: PM1-T00 scaffold. IMPORTANT: these stubs are intentionally NOT registered
in hooks.py yet, and they return "" (no restriction). Do NOT wire them until
PM1-T03 implements real conditions, otherwise they would be a no-op that grants
broad visibility. No functional change in PM1-T00.
"""

import frappe


def get_permission_query_conditions_for_task(user=None):
    """Stub for PM1-T03. Returns no condition. NOT registered in hooks yet."""
    return ""


def get_permission_query_conditions_for_project(user=None):
    """Stub for PM1-T03. Returns no condition. NOT registered in hooks yet."""
    return ""
