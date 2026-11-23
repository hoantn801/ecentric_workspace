# Copyright (c) 2026, eCentric and contributors
"""23/11/2026: danh dau Don nghi viec DA DUYET ma chua co Clearance (site: 9 don, 0 Clearance).

CHI GHI NOI BO: dat `clearance_error` tren don ("Can tao bu...") de HR thay ngay tren phieu + mot dong
Error Log liet ke cac don kem chan doan. KHONG tao Clearance o day: tao phieu = gui thong bao cho cac
nhom (Teams...), ma patch chay luc site dang deploy (bai hoc 20/11). Tao bu bang endpoint System Manager
`approval_center.features.clearance_request.controllers.api.tao_bu_clearance` (dry-run mac dinh);
don chua qua ngay cuoi se duoc job 09:05 tao bu tu dong. Khong nem loi (migrate)."""
import frappe

_SVC = "ecentric_workspace.approval_center.features.clearance_request.application.service"


def execute():
    if not (frappe.db.exists("DocType", "EC Resignation Request")
            and frappe.db.has_column("EC Resignation Request", "clearance_error")):
        return
    try:
        svc = frappe.get_module(_SVC)
        thieu = svc.danh_sach_thieu_clearance()
        dong = []
        for name in thieu:
            d = svc.chan_doan(name)
            ly_do = "; ".join(d.get("ly_do") or [])
            frappe.db.set_value("EC Resignation Request", name, "clearance_error",
                                ("Cần tạo bù Clearance (đánh dấu 23/11): " + ly_do)[:500],
                                update_modified=False)
            dong.append("%s | %s | ngay cuoi %s | %s" % (name, d.get("employee_email"),
                                                         d.get("last_working_day"), ly_do))
        frappe.db.commit()
        frappe.log_error(title="p441 clearance can tao bu: %d don" % len(thieu),
                         message="\n".join(dong) or "khong co don nao")
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="p441 clearance danh dau LOI", message=frappe.get_traceback())
