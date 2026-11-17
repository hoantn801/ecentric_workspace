# Copyright (c) 2026, eCentric and contributors
"""De nghi thanh toan: hoi lai khi phieu ghi "dot 1" / "50%" / "dat coc" nhung chon Thanh toan 100%
(17/11/2026, Hoan duyet).

EC-PAYR-2026-00501 / 00508 / 00602 ghi "dot 1" trong ly do nhung gui o che do 100% -> Finance chi xong
khong co nut "Tao de nghi dot 2". Khong phai loi he thong (Version cho thay payment_mode chua tung la
Installment). Them hop hoi truoc khi Gui / Bo sung & gui lai: "Chuyen sang Chia nhieu dot" hoac
"Van gui thanh toan 100%". Chi hoi, khong chan. Patch chi resync trang form. KHONG BAO GIO nem loi.
"""
import frappe

_EXPECT = ("function installmentHint(d)", "data-inst-switch")


def execute():
    try:
        from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync
        res = page_sync.sync() or {}
        if res.get("action") == "refused":
            frappe.log_error("p395: upsert TU CHOI GHI (khoa chong troi) live_sha=%s" % res.get("live_sha"),
                             "p395 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        thieu = [m for m in _EXPECT if m not in html]
        if thieu:
            frappe.log_error("p395: thieu landmark=%s" % (thieu,), "p395 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p395 resync payment request")
