# Copyright (c) 2026, eCentric and contributors
"""Promotion - sua theo review chat Phan quyen 29/09/2026 (P1):
1. Buoc 1 "Direct Manager Review" cua PROMOTION_REQUEST-V1: doi nguon tu "Requester Manager"
   sang Reference User Field `salary_reviewer` (nguoi dau tien tren chuoi reports_to cua NHAN SU
   DUOC DE XUAT xem duoc luong nguoi do - service tinh luc gui) va mandatory=0 (khong co ai /
   trung nguoi gui thi bo buoc, co audit). Process dang Active: sua truc tiep dong participant cua
   cap 1 qua doc.save() (validate chay) - phieu dang chay giu nguyen ban chup cu.
2. Resync trang /approvals/promotion (hien "An - khong co quyen xem luong").
Idempotent; moi phan mot try; ket qua ghi Error Log. Khong nem loi."""
import frappe

PROCESS = "PROMOTION_REQUEST-V1"
PAGE = "ecentric_workspace.approval_center.features.promotion.infrastructure.page_sync"


def execute():
    ket = []
    try:
        names = frappe.get_all("EC Approval Level", filters={"approval_process": PROCESS, "level_no": 1},
                               pluck="name")
        if not names:
            ket.append("khong co cap 1 cua %s" % PROCESS)
        else:
            lvl = frappe.get_doc("EC Approval Level", names[0])
            parts = [p for p in lvl.participants if p.participant_purpose == "Approver"]
            if len(parts) == 1 and parts[0].source_type == "Reference User Field" \
                    and parts[0].reference_field == "salary_reviewer" and not lvl.mandatory:
                ket.append("cap 1 da dung salary_reviewer")
            else:
                lvl.set("participants", [p for p in lvl.participants if p.participant_purpose != "Approver"])
                lvl.append("participants", {"participant_purpose": "Approver",
                                            "source_type": "Reference User Field",
                                            "reference_field": "salary_reviewer", "sort_order": 0})
                lvl.mandatory = 0
                lvl.save(ignore_permissions=True)
                ket.append("da doi cap 1 sang salary_reviewer, mandatory=0")
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("process LOI\n" + frappe.get_traceback())
    try:
        res = frappe.get_module(PAGE).sync() or {}
        ket.append("page: %s" % res.get("action"))
    except Exception:
        ket.append("page LOI\n" + frappe.get_traceback())
    frappe.log_error(title="p237 promotion an luong buoc 1", message="\n".join(ket))
