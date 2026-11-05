"""p033 - số chỗ ngồi 5 phòng họp (PO 06/11/2026): 5.1 = 8, 1.1 = 8, 1.2 = 6, 1.3 = 4, 5.2 Cabin = 2.

Only fills an EMPTY capacity (an admin may already have typed it in Desk). Idempotent; logs,
never raises."""

import frappe

CAPACITY = {"5.1": 8, "1.1": 8, "1.2": 6, "1.3": 4, "5.2": 2}


def execute():
    try:
        if not frappe.db.exists("DocType", "EC Meeting Room"):
            return
        done = []
        for code, cap in CAPACITY.items():
            if frappe.db.exists("EC Meeting Room", code) and not frappe.db.get_value("EC Meeting Room", code, "capacity"):
                frappe.db.set_value("EC Meeting Room", code, "capacity", cap)
                done.append(code)
        from ecentric_workspace.pm.api import rooms
        rooms.clear_cache()
        print("[p033] capacity set: %s" % (", ".join(done) or "none"))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p033 meeting rooms capacity")
