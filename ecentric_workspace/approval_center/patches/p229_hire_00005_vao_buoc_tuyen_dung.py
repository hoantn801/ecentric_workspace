# Copyright (c) 2026, eCentric and contributors
"""Dua EC-HIRE-2026-00005 vao buoc "HR tuyen dung" moi (29/09/2026, Hoan yeu cau).

Phieu nay (Data Analyst Intern) duoc CEO duyet 10/09, TRUOC khi co buoc tuyen dung (p218),
nen `fulfillment_status` van "Not Started": khong vao hang doi cua EC Recruiter, khong co nut
"+ Tao Offer". Patch goi DUNG ham ma phieu duyet moi di qua (`service.on_final_approval`):
Assigned + ToDo cho nguoi giu role EC Recruiter + thong bao. Khong co luat rieng o day.

Chi chay khi phieu con Approved va chua vao buoc tuyen dung - chay lai khong lam gi.
Khong nem loi (migrate); ket qua ghi Error Log."""
import frappe

NAME = "EC-HIRE-2026-00005"
BUSINESS_DT = "EC Hiring Request"
CHUA_VAO = (None, "", "Not Started")


def execute():
    ket = []
    try:
        cur = frappe.db.get_value(BUSINESS_DT, NAME, ["approval_request", "fulfillment_status"],
                                  as_dict=True)
        if not cur:
            ket.append("khong thay %s - bo qua" % NAME)
        elif cur.fulfillment_status not in CHUA_VAO:
            ket.append("%s da o buoc tuyen dung (%s) - bo qua" % (NAME, cur.fulfillment_status))
        elif frappe.db.get_value("EC Approval Request", cur.approval_request,
                                 "approval_status") != "Approved":
            ket.append("%s khong con Approved - bo qua" % NAME)
        else:
            from ecentric_workspace.approval_center.features.hiring_request.application import service
            service.on_final_approval(NAME)
            frappe.db.commit()
            ket.append("%s -> %s" % (NAME, frappe.db.get_value(BUSINESS_DT, NAME, "fulfillment_status")))
    except Exception:
        frappe.db.rollback()
        ket.append("LOI:\n" + frappe.get_traceback())
    frappe.log_error(title="p229 hire 00005 vao buoc tuyen dung", message="\n".join(ket))
