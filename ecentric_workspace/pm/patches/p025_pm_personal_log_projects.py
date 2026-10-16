"""p025 - PM redesign (16/10/2026): flag the worklog projects as personal logs.

Every Project whose project_name starts with "ERP - " (the 13 worklog projects written by
ops/worklog/pm_worklog.py) gets ec_personal_log = 1, so /pm hides them by default (PO point 8).
Prefix checked in Python (not only SQL LIKE) to match exactly. Idempotent: rows already flagged
are skipped. Runs after p024 (field must exist); logs and returns when it does not.
"""

import frappe

PREFIX = "ERP - "


def execute():
    try:
        frappe.clear_cache(doctype="Project")
        if not frappe.get_meta("Project", cached=False).has_field("ec_personal_log"):
            frappe.log_error("p025: Project.ec_personal_log missing (p024 not applied)",
                             "p025 personal log")
            return
        rows = frappe.get_all("Project", filters={"project_name": ["like", PREFIX + "%"]},
                              fields=["name", "project_name", "ec_personal_log"],
                              limit_page_length=0)
        flagged = []
        for r in rows:
            if not (r.get("project_name") or "").startswith(PREFIX) or r.get("ec_personal_log"):
                continue
            frappe.db.set_value("Project", r["name"], "ec_personal_log", 1, update_modified=False)
            flagged.append(r["name"])
        print("[p025] ec_personal_log=1 on %d project(s): %s" % (len(flagged), ", ".join(flagged)))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p025 personal log")
