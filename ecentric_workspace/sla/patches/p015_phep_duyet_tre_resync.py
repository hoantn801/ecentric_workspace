# Copyright (c) 2026, eCentric and contributors
"""Cham lai ngay cong cua nhung phieu nghi duoc duyet TRE hon cua so 7 ngay.

Chieu 30/09 bon phieu nghi thang 9 duoc duyet cung luc, co phieu nghi 18/09.
Job dem chi quet 7 ngay gan nhat nen ngay 18/09 nam `Open` va hien "Chua lam"
tren /sla (tam.nguyen, anh.luu). Hook `on_leave_application_submit` chan viec
nay tu nay ve sau; patch nay sua nhung ngay DA ket.

Chi dong bo lai nhung ngay NAM TRONG phieu nghi da duyet tu 01/09 - khong quet
lai ca cong ty. Chay lai khong nhan doi gi: `open_obligation` tra ve dong cu,
`_ensure_excluded` bo qua dong da `Excluded`. KHONG xoa ban ghi nao.

FAIL-SAFE: moi loi bi nuot va ghi Error Log.
"""
import frappe

TITLE = "p015 cham lai ngay cong cua phep duyet tre"


def execute():
    try:
        from ecentric_workspace.sla.infrastructure import attendance_source
        rows = frappe.get_all("Leave Application", filters={
            "status": "Approved", "docstatus": 1,
            "to_date": (">=", "2026-09-01"),
            "from_date": ("<=", frappe.utils.nowdate()),
        }, fields=["name", "employee", "from_date", "to_date"], limit_page_length=0)
    except Exception:
        frappe.log_error(title=TITLE, message=frappe.get_traceback())
        return

    loai_tru, hoi_to, loi = [], [], []
    for r in rows:
        try:
            res = attendance_source.sync_leave(r["employee"], r["from_date"], r["to_date"])
        except Exception:
            loi.append(r["name"])
            continue
        if not res:
            continue
        loai_tru.extend(res.get("loai_tru") or [])
        hoi_to.extend(res.get("hoi_to_nghi_phep") or [])
        loi.extend(res.get("loi") or [])

    try:
        frappe.log_error(
            title=TITLE,
            message="phieu=%s loai_tru=%s go_missed=%s loi=%s\n%s" % (
                len(rows), len(loai_tru), len(hoi_to), len(loi),
                "\n".join((loai_tru + hoi_to)[:100])))
    except Exception:
        pass
