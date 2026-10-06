# Copyright (c) 2026, eCentric and contributors
"""p004: o "Mac dinh du cong" tren ho so nhan vien + bat cho anh Lam (01/10/2026, Hoan duyet).

- tao Custom Field Employee.ec_full_cong (fixture sync chay SAU patch nen tao o day);
- bat co cho lam.nguyen@ecentric.vn;
- huy (Cancelled, KHONG xoa) cac nghia vu SLA cham cong da sinh cho nguoi bat co;
- ghi du cong tu 01/09/2026 toi hom nay (chi ngay lam viec con trong).
Hai nguoi khong dung ERP (bac Tuan, bac Linh) chua co ho so: CnB tao ho so roi tick o nay,
job 06:05 tu ghi du cong tu ngay 1 thang truoc.
FAIL-SAFE: moi buoc nuot loi + Error Log.
"""
import frappe

TITLE = "p004 du cong"
USERS = ("lam.nguyen@ecentric.vn",)


def execute():
    from ecentric_workspace.hr import full_cong
    try:
        full_cong.ensure_field()
        frappe.clear_cache(doctype="Employee")
    except Exception:
        frappe.log_error(title=TITLE + " field", message=frappe.get_traceback())
        return
    out = {"bat_co": [], "huy_sla": 0}
    try:
        for u in USERS:
            emp = frappe.db.get_value("Employee", {"user_id": u, "status": "Active"}, "name")
            if emp:
                frappe.db.set_value("Employee", emp, full_cong.FIELD, 1)
                out["bat_co"].append(emp)
        flagged_users = full_cong.users()
        if flagged_users:
            names = frappe.get_all("EC SLA Obligation", filters={
                "obligation_type": "ATTENDANCE_DAY", "owner_user": ("in", list(flagged_users)),
                "status": ("!=", "Cancelled")}, pluck="name", limit_page_length=0)
            for n in names:
                frappe.db.set_value("EC SLA Obligation", n, {
                    "status": "Cancelled", "is_breached": 0,
                    "excluded_reason": "Mặc định đủ công - không tính SLA chấm công"},
                    update_modified=False)
            out["huy_sla"] = len(names)
        out["ghi_cong"] = full_cong.mark_range("2026-09-01", frappe.utils.nowdate())
    except Exception:
        frappe.log_error(title=TITLE, message=frappe.get_traceback())
    frappe.log_error(title=TITLE, message=str(out))
