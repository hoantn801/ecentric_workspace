# Copyright (c) 2026, eCentric and contributors
"""Nap SLA cho 65 buoc duyet/xu ly. Chu so huu dien ngay 16/09/2026.

Truoc dot nay: 57/60 buoc duyet KHONG co han - chi AI Topup co. Nghia la neu bat
do luong len, gan het moi buoc se roi vao cot "chua cau hinh han" va bang diem
khong noi duoc gi.

DOT NAY DOI HANH VI TREN BAN SONG, khac han p001. Cu the:

  * cap duyet duoc kich hoat TU GIO TRO DI se co `due_at`. Cap dang mo tu truoc
    KHONG bi gan han hoi to - `_activate_level` chi tinh han luc kich hoat. Nen
    thay doi ngam dan theo phieu moi, khong ap mot luc len ca ton dong.
  * Action Center se bat dau xep cac phieu do vao nhom "qua han / can lam ngay /
    sap den han" thay vi "khong co han". Day la thay doi NHIN THAY DUOC, va la
    muc dich - nhung phai noi truoc.
  * KHONG co email hay thong bao moi nao phat sinh tu SLA. `_activate_level` chi
    ghi `due_at`; thong bao cho nguoi duyet van la thong bao cu, khong doi.

Patch FAIL-SAFE: moi dong mot diem luu rieng, ket qua ghi vao Error Log, luon
ket thuc xanh. Mot bang cau hinh thieu vai dong khong dang chan ca ban deploy
cua 28 form dang chay.

NHUNG "deploy xanh" KHONG co nghia la "cau hinh dung". Patch nay co the ghi
nhan da chay trong khi 65/65 dong deu hong, va Frappe se khong bao gio chay lai
no. Vi vay dot nay kem theo hai duong doc lap, dung sau moi lan deploy:

    ecentric_workspace.sla.controllers.api.verify_approval_sla    (chi doc)
    ecentric_workspace.sla.controllers.api.reimport_approval_sla  (nap lai)

Ca hai chay lai duoc bao nhieu lan cung duoc. Lan cap nhat SLA sau nay chi can
sua tep JSON roi goi `reimport_approval_sla` - khong phai viet patch moi.
"""
import frappe

from ecentric_workspace.sla.application import policy_import


def execute():
    try:
        report = policy_import.apply()
    except Exception:
        frappe.log_error(title="p002 import approval sla - that bai hoan toan",
                         message=frappe.get_traceback())
        return

    frappe.log_error(
        title="p002 import approval sla",
        message="\n".join(
            ["TOM TAT: " + (policy_import.summarize(report) or "(khong co gi doi)"), ""]
            + ["%s (%d):\n  %s" % (k, len(v), "\n  ".join(str(x) for x in v))
               for k, v in sorted(report.items()) if v]))
