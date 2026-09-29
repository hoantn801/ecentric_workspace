# Copyright (c) 2026, eCentric and contributors
"""Job 00:30 hang ngay: nhan vien da qua ngay lam viec cuoi -> status Left + khoa tai khoan.
Idempotent (chi lay nguoi con Active), try/except tung nguoi, log bat dau / ket thuc.
Tat khan cap: site_config `ec_offboarding_lock_disabled: 1`. Logic o service.py."""
import frappe

from ecentric_workspace.hr.offboarding import service

KILL_CONF = "ec_offboarding_lock_disabled"


def run(today=None):
    if frappe.conf.get(KILL_CONF):
        return {"skipped": "disabled"}
    rows = service.due_employees(today)
    results = []
    for row in rows:
        try:
            results.append((row, service.lock_one(row)))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Nghi viec: khong khoa duoc %s" % row.name,
                             message=frappe.get_traceback())
            results.append((row, ("error", row.name)))
    try:
        service.notify_summary(results)
        frappe.db.commit()
    except Exception:
        frappe.log_error(title="Nghi viec: thong bao tong loi", message=frappe.get_traceback())
    out = {"due": len(rows), "results": [(r.name, k) for r, (k, _n) in results]}
    if rows:
        frappe.log_error(title="lock_left_employees_job: %d nguoi" % len(rows), message=str(out))
    return out
