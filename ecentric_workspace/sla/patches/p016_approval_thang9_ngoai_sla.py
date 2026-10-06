# Copyright (c) 2026, eCentric and contributors
"""Phan hoi phe duyet thang 9/2026: van do, KHONG tinh vao %SLA.

Chu so huu chot 30/09: nhom Phe duyet thang 9 chua tinh diem, tu 01/10 tinh lai
binh thuong. `counts_toward_sla` duoc chup tren TUNG dong luc mo (xem
scoring.aggregate), nen doi hang so khong du - phai ha co cua nhung dong da mo
trong ky 2026-09. Dong mo moi trong ky nay da duoc `open_obligation` ha san
(GROUP_OFF_PERIODS).

KHONG xoa, KHONG doi trang thai: dong van hien tren /sla voi nhan "ngoai %SLA".
Chay lai khong sao.
"""
import frappe

TITLE = "p016 phe duyet thang 9 ngoai %SLA"


def execute():
    try:
        from ecentric_workspace.sla.constants import DT_OBLIGATION, GROUP_OFF_PERIODS
        n = 0
        for group_key, periods in GROUP_OFF_PERIODS.items():
            for period in periods:
                names = frappe.get_all(DT_OBLIGATION, filters={
                    "group_key": group_key, "period_month": period,
                    "counts_toward_sla": 1}, pluck="name", limit_page_length=0)
                for name in names:
                    frappe.db.set_value(DT_OBLIGATION, name, "counts_toward_sla", 0,
                                        update_modified=False)
                n += len(names)
        frappe.log_error(title=TITLE, message="ha co %s dong" % n)
    except Exception:
        frappe.log_error(title=TITLE, message=frappe.get_traceback())
