# Copyright (c) 2026, eCentric and contributors
"""Doi "Bao cao cho" (reports_to) -> viec dang cho duyet di theo quan ly moi.

01/10/2026: CnB doi co cau team Service (12 nguoi), nhung khung chot cong van hien team cu
va 12 giai trinh / 1 don nghi van nam cho quan ly cu. Ly do: lead cua dong chot cong va
nguoi duyet giai trinh / don nghi duoc CHUP luc tao, khong tu doi theo ho so.

Hook Employee.on_update: reports_to doi thi
  - dong EC Timesheet Close CHUA chot team (ky dang mo) -> lead_user moi;
  - giai trinh cham cong dang Open (Attendance Request) -> ToDo chuyen sang quan ly moi;
  - don nghi dang cho buoc quan ly (Leave Application nhap, chua toi buoc HR)
    -> leave_approver + ToDo sang quan ly moi.
Viec DA xu ly khong dong toi. Moi loi bi nuot + Error Log: khong bao gio chan luu ho so.
"""
import frappe


def _mgr_user(reports_to):
    if not reports_to:
        return None
    row = frappe.db.get_value("Employee", reports_to, ["user_id", "status"], as_dict=True)
    if not row or row.status != "Active" or not row.user_id:
        return None
    if not frappe.db.get_value("User", row.user_id, "enabled"):
        return None
    return row.user_id


def _move_todos(ref_type, ref_name, new_user):
    for t in frappe.get_all("ToDo", filters={"reference_type": ref_type, "reference_name": ref_name,
                                             "status": "Open"}, fields=["name", "allocated_to"]):
        if t.allocated_to != new_user:
            frappe.db.set_value("ToDo", t.name, "allocated_to", new_user)


def on_employee_update(doc, method=None):
    try:
        if not doc.has_value_changed("reports_to"):
            return
        new_user = _mgr_user(doc.reports_to)
        if new_user and new_user == doc.user_id:
            new_user = None
        for r in frappe.get_all("EC Timesheet Close", filters={
                "employee": doc.name, "status": ("!=", "Closed")}, fields=["name", "lead_user"]):
            if (r.lead_user or None) != new_user:
                frappe.db.set_value("EC Timesheet Close", r.name, "lead_user", new_user,
                                    update_modified=False)
        if not new_user:
            return
        for ar in frappe.get_all("Attendance Request", filters={
                "employee": doc.name, "docstatus": 0, "ec_appeal_status": "Open"}, pluck="name"):
            _move_todos("Attendance Request", ar, new_user)
        for la in frappe.get_all("Leave Application", filters={
                "employee": doc.name, "docstatus": 0, "status": "Open"},
                fields=["name", "leave_approver", "ec_approval_stage"]):
            if (la.ec_approval_stage or "") == "hr":
                continue
            if la.leave_approver != new_user:
                frappe.db.set_value("Leave Application", la.name, "leave_approver", new_user)
            _move_todos("Leave Application", la.name, new_user)
    except Exception:
        frappe.log_error(title="reports_to_sync %s" % getattr(doc, "name", ""),
                         message=frappe.get_traceback())
