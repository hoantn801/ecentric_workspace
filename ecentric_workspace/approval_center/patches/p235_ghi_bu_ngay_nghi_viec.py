# Copyright (c) 2026, eCentric and contributors
"""Ghi bu ngay nghi viec vao ho so cho cac Don nghi viec DA DUYET truoc ban 29/09 (Hoan chot:
"co nhe ghi bu nhe"). Dung dung ham cua luong moi (hr.offboarding.service.mark_resignation) -
chi ghi resignation_letter_date + relieving_date, KHONG doi status, KHONG khoa tai khoan: viec
khoa do job 00:30 lam (nguoi da qua ngay cuoi se bi khoa ngay dem dau tien sau deploy).
Bo qua don co ho so da co relieving_date (khong ghi de ngay HR da sua tay). Khong tao Clearance
cho don cu. Idempotent; moi don mot try; ket qua ghi Error Log. Khong nem loi."""
import frappe

DT = "EC Resignation Request"
#: Danh sach DICH DANH (kiem live 29/09): 4 don that. EC-RESN-2026-00001 la phieu TEST cua
#: hoan.tran (ngay cuoi 2029-01-01) - KHONG ghi, de khong gan ngay nghi viec that len ho so.
TARGETS = ("EC-RESN-2026-00002", "EC-RESN-2026-00003", "EC-RESN-2026-00004",
           "EC-RESN-2026-00005")


def execute():
    from ecentric_workspace.hr.offboarding import service as offboarding
    ket = []
    rows = frappe.get_all(DT, filters={"name": ["in", list(TARGETS)], "approval_request": ["is", "set"]},
                          fields=["name", "approval_request", "employee_email", "last_working_day",
                                  "submitted_at", "creation"], order_by="creation asc",
                          limit_page_length=0)
    for r in rows:
        try:
            st = frappe.db.get_value("EC Approval Request", r.approval_request, "approval_status")
            if st != "Approved":
                continue
            emp = offboarding.employee_of(r.employee_email)
            if emp and frappe.db.get_value("Employee", emp, "relieving_date"):
                ket.append("%s: ho so da co relieving_date - giu nguyen" % r.name)
                continue
            ket.append("%s: %s" % (r.name, offboarding.mark_resignation(
                r.employee_email, letter_date=r.submitted_at or r.creation,
                relieving_date=r.last_working_day, source=r.name)))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            ket.append("%s: LOI\n%s" % (r.name, frappe.get_traceback()))
    frappe.log_error(title="p235 ghi bu ngay nghi viec", message="\n".join(ket) or "khong co don nao")
