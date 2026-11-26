# Copyright (c) 2026, eCentric and contributors
"""PO duyet 26/11/2026: du an dang mo (Open) ma ec_department trong -> dien phong ban cua nguoi tao
(Employee.department; khong co thi cua quan ly ec_manager). Du an khong phong ban chi nguoi tao / quan ly /
thanh vien xem duoc (vi.le khong mo duoc PROJ-0054 cua team). Bo qua du an cua Administrator.
Ghi Comment Info tren tung du an. Tu bat loi, khong chan deploy."""
import frappe

SYSTEM = ("Administrator", "Guest", "")


def _dept(user):
    if not user or user in SYSTEM:
        return None
    return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "department")


def execute():
    done = 0
    for p in frappe.get_all("Project", filters={"status": "Open"},
                            fields=["name", "owner", "ec_manager", "ec_department"], limit_page_length=0):
        if p.get("ec_department") or (p.get("owner") or "") in SYSTEM:
            continue
        try:
            d = _dept(p.get("owner")) or _dept(p.get("ec_manager"))
            if not d:
                continue
            frappe.db.set_value("Project", p["name"], "ec_department", d)
            frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "Project",
                            "reference_name": p["name"],
                            "content": "Tự điền phòng ban %s (PO duyệt 26/11/2026): dự án để trống phòng ban nên đồng nghiệp cùng team không xem được." % d
                            }).insert(ignore_permissions=True)
            done += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p559_pm_dien_phong_ban_du_an " + str(p.get("name")))
    frappe.logger("approval_center").info("p559_pm_dien_phong_ban_du_an: dien phong ban %s du an" % done)
