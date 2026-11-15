# Copyright (c) 2026, eCentric and contributors
"""Doi chu "SCTS" -> "CMC" tren giao dien ky so (15/11/2026: chuyen nha cung cap SCTS -> CMC
signx.cmc.vn, xem BAOCAO_chuyen_CMC_15_11.md).

Hai trang:
  * /approvals (hub): nut "Ket noi SCTS" -> "Ket noi CMC" + hop thoai ket noi.
  * /approvals/payment-request (page_sync ghep main + panel nguoi de nghi + khoi Tai lieu & ky
    so): chu SCTS trong panel ket noi cua nguoi de nghi, khoi tai lieu, bang cu.
CHI doi chu hien thi. Khong doi API, id, class, luong. Landmark = dieu PHAI CO tren ban song.
"""
import frappe

from ecentric_workspace.approval_center.features.payment_request.infrastructure import \
    page_sync as pr_sync
from ecentric_workspace.approval_center.ui.hub import page_sync as hub_sync

_PAGES = (
    ("approvals", hub_sync, ('aria-expanded="false">Kết nối CMC</button>',)),
    ("approvals/payment-request", pr_sync, ("Kết nối tài khoản ký số CMC",
                                            "chỉ lưu trên ERP, không gửi CMC")),
)


def execute():
    for route, mod, landmarks in _PAGES:
        res = mod.sync()
        action = (res or {}).get("action")
        frappe.log_error("p381 %s sync=%s" % (route, action), "p381 resync")
        if action == "refused":
            frappe.log_error("p381: %s TU CHOI GHI (live lech) - trang KHONG duoc cap nhat. "
                             "Doi chieu SUPERSEDES_SHA256." % route, "p381 REFUSED")
            continue
        html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
        thieu = [m for m in landmarks if m not in html]
        if thieu:
            frappe.log_error("p381: %s thieu dau moc %s" % (route, thieu), "p381 KHONG toi noi")
