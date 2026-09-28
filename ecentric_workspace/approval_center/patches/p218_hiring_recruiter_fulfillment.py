# Copyright (c) 2026, eCentric and contributors
"""Buoc "HR tuyen dung" cho Hiring Request (28/09/2026, Hoan).

1. Tao Role `EC Recruiter` (rong - KHONG tu gan cho ai: gan role la quyet dinh nhan su).
   Hoan gan cho team tuyen dung (luc.nguyen, tran.bui...) trong Desk.
2. Them dong Fulfiller = Role EC Recruiter vao HIRING_REQUEST-V1. Setup khong dung toi
   process dang Active nen patch nay them truc tiep, luu qua doc.save() de validate chay.

Idempotent: role co roi / dong Fulfiller co roi thi bo qua. Khong bao gio nem loi (migrate).
Hiring da duyet TRUOC ban nay khong tu vao hang doi (chi co phieu test tren production)."""
import frappe

ROLE = "EC Recruiter"
PROCESS = "HIRING_REQUEST-V1"


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
        if not frappe.db.exists("EC Approval Process", PROCESS):
            ket.append("Khong co process %s - bo qua buoc Fulfiller" % PROCESS)
        else:
            proc = frappe.get_doc("EC Approval Process", PROCESS)
            co = [p for p in (proc.participants or [])
                  if p.participant_purpose == "Fulfiller" and p.role == ROLE]
            if co:
                ket.append("%s da co Fulfiller %s" % (PROCESS, ROLE))
            else:
                proc.append("participants", {"participant_purpose": "Fulfiller",
                                             "source_type": "Role", "role": ROLE,
                                             "sort_order": len(proc.participants or [])})
                proc.save(ignore_permissions=True)
                ket.append("Da them Fulfiller Role %s vao %s" % (ROLE, PROCESS))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("LOI:\n" + frappe.get_traceback())
    frappe.log_error(title="p218 hiring recruiter", message="\n".join(ket))
