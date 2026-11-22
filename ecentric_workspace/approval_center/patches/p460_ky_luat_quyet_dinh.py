# Copyright (c) 2026, eCentric and contributors
"""p460_ky_luat_quyet_dinh (23/11/2026, Dot 3 HR - Ky luat): seed EC Approval Type
DISCIPLINE_DECISION (the "Coming Soon" - phieu TU TAO tu ho so ky luat, route /ky-luat/quyet-dinh,
rieng tu neu engine da co truong `private`), dung + kich hoat process DISCIPLINE_DECISION-V1
(1 cap, role ky tu EC Discipline Settings). Khong co Web Page: trang la www/ky_luat (A65).
Moi buoc mot khoi try; ket qua ghi Error Log. Chay lai: type co roi / process Active -> bo qua.
Khong nem loi, khong goi ra ngoai."""
import frappe

CODE = "DISCIPLINE_DECISION"
ROUTE = "/ky-luat/quyet-dinh"
ROW = {"approval_code": CODE, "approval_title": "Quyết định kỷ luật", "category": "ADMINISTRATION",
       "card_status": "Coming Soon", "process_status": "Building", "visibility_mode": "All Internal Users",
       "description": "Tự tạo khi HR trình CEO từ hồ sơ kỷ luật (/ky-luat). Không tạo tay.",
       "sort_order": 40}
_F = "ecentric_workspace.approval_center.features.discipline_decision.infrastructure."


def execute():
    ket = []
    try:
        if frappe.db.exists("EC Approval Type", CODE):
            ket.append("type da co")
        else:
            doc = frappe.new_doc("EC Approval Type")
            doc.update(ROW)
            doc.route = ROUTE
            if frappe.get_meta("EC Approval Type").has_field("private"):
                doc.set("private", 1)
            doc.insert(ignore_permissions=True)
            ket.append("da tao type %s" % CODE)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("type LOI\n" + frappe.get_traceback())
    try:
        r1 = frappe.get_module(_F + "setup").setup_discipline_decision_v1(dry_run=0, apply=1) or {}
        ket.append("setup: %s %s" % (r1.get("result"), r1.get("errors") or ""))
        r2 = frappe.get_module(_F + "activation").activate_discipline_decision(dry_run=0, apply=1, commit=1) or {}
        ket.append("activate: %s blockers=%s" % (r2.get("result") or r2.get("mode"), r2.get("blockers")))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("process LOI\n" + frappe.get_traceback())
    frappe.log_error(title="p460 ky luat quyet dinh", message="\n".join(ket))
