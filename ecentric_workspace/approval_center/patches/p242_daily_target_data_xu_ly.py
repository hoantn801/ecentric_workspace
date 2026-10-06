# Copyright (c) 2026, eCentric and contributors
"""Daily Target: buoc "Data xu ly" sau khi duyet (01/10/2026, Hoan).

1. Tao Role `EC Data Team` (rong - KHONG tu gan ai: Hoan gan linh.vuong + hoan.tran trong Desk).
2. Them dong Fulfiller = Role EC Data Team vao CA HAI process DAILY_TARGET_PROJECT-V1 va
   DAILY_TARGET_CONSOLIDATED-V1 (dang Active: sua truc tiep qua doc.save()).
3. Resync trang /approvals/daily-target (tab "Toi xu ly", the "Team Data xu ly", stepper).
Idempotent; moi phan mot try; ket qua ghi Error Log. Khong nem loi. Phieu da duyet TRUOC ban nay
khong tu vao hang doi."""
import frappe

ROLE = "EC Data Team"
PROCESSES = ("DAILY_TARGET_PROJECT-V1", "DAILY_TARGET_CONSOLIDATED-V1")
PAGE = "ecentric_workspace.approval_center.features.daily_target.infrastructure.page_sync"


def execute():
    ket = []
    try:
        if frappe.db.exists("Role", ROLE):
            ket.append("Role %s da co" % ROLE)
        else:
            r = frappe.new_doc("Role")
            r.role_name = ROLE
            r.desk_access = 0
            r.insert(ignore_permissions=True)
            ket.append("Da tao Role %s (chua gan cho ai)" % ROLE)
        for code in PROCESSES:
            if not frappe.db.exists("EC Approval Process", code):
                ket.append("khong co %s" % code)
                continue
            proc = frappe.get_doc("EC Approval Process", code)
            if any(p.participant_purpose == "Fulfiller" and p.role == ROLE for p in (proc.participants or [])):
                ket.append("%s da co Fulfiller" % code)
                continue
            proc.append("participants", {"participant_purpose": "Fulfiller", "source_type": "Role",
                                         "role": ROLE, "sort_order": len(proc.participants or [])})
            proc.save(ignore_permissions=True)
            ket.append("Da them Fulfiller %s vao %s" % (ROLE, code))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("LOI\n" + frappe.get_traceback())
    try:
        res = frappe.get_module(PAGE).sync() or {}
        ket.append("page: %s" % res.get("action"))
    except Exception:
        ket.append("page LOI\n" + frappe.get_traceback())
    frappe.log_error(title="p242 daily target data xu ly", message="\n".join(ket))
