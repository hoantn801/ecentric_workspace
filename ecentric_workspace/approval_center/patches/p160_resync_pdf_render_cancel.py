# Copyright (c) 2026, eCentric and contributors
"""Drawer dat vi tri ky: MOT luot ve mot luc tren cung canvas (do that tren prod 08/09).

pdf.js nem "Cannot use the same canvas during multiple render() operations" khi luot ve thu
hai bat dau luc luot dau chua xong. `hydrateBoxes()` treo o `.promise.then(...)` cua luot ve,
nen luot bi nem KHONG BAO GIO ve o ky: nguoi dung thay tai lieu nhung KHONG thay o chu ky nao,
khong loi, khong bao gi - va o ky la thu duy nhat de lam viec trong drawer. Tai lap 08/09
10:44 tren EC-PAYR-2026-00046: dong drawer roi mo lai trong ~1 giay (bam chuyen trang nhanh
cung the) -> 0 o ky, console co ngoai le, man hinh im lang.

Nay: (1) MOI luot ve dung mot CANVAS MOI (thay the nut trong DOM, giu id + style) - khong con
trang thai cu nao de ket, ke ca khi mot luot cu bi ro ri o dau do; (2) giu RenderTask, huy luot
cu truoc khi bat dau luot moi; huy la chuyen binh thuong nen
nuot rieng no, con loi ve THAT thi hien ra o dong loi cua drawer. Kem chot phien: luot ve cua
tai lieu/trang CU khong duoc dung o cua tai lieu/trang MOI.
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync

_LANDMARKS = ("DRW.task.cancel()", "RenderingCancelled", "Không vẽ được trang tài liệu",
              'cv.id = "ecdCanvas"')


def execute():
    res = page_sync.sync()
    frappe.log_error("p160 payment_request sync=%s" % (res or {}).get("action"), "p160 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                               "main_section_html") or ""
    missing = [m for m in _LANDMARKS if m not in html]
    if missing:
        raise Exception("p160: trang approvals/payment-request thieu %s sau sync (action=%s)"
                        % (missing, (res or {}).get("action")))
