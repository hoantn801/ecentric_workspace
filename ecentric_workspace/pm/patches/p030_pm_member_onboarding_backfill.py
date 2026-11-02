"""p030 - grant PM Member to active employees onboarded after p023 (02/11/2026).

From now on pm.onboarding.on_employee_update grants it on every Employee save (Active + user),
so this is the LAST backfill. Idempotent; logs, never raises."""

import frappe


def execute():
    try:
        from ecentric_workspace.pm import onboarding
        granted = onboarding.backfill_active_employees()
        print("[p030] PM Member granted to %d users: %s" % (len(granted), ", ".join(granted)))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p030 PM Member onboarding backfill")
