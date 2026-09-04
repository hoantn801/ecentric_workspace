# Copyright (c) 2026, eCentric and contributors
"""Hub /approvals/all-requests: "Duyet & Ky" cho cap ky so, va thong diep loi doc duoc.

04/09, Vinh mo phieu 00053 tren hub va bam "Duyet": engine tu choi "Cap duyet nay yeu cau ky
so. Vui long dung chuc nang 'Duyệt &amp; Ký'" - dung, nhung (1) hub khong co nut do, (2) chu
"&amp;" hien nguyen vi thong diep da HTML-escape roi bi hien nhu van ban.

- capabilities.derive + reporting.service: them `requires_signature` (hoi esign.guard, nho
  ket qua; hong thi False). query_service.detail them `business_doctype`.
- popup: cap ky so -> nut "Duyet & Ky" -> esign.api.approve_and_sign (dung endpoint form
  Payment Request dang dung). Dong danh sach: nut "Duyet & Ky" mo popup.
- extractServerMsg giai ma entity.

Patch moi vi p131 (resync hub gan nhat) da chay. Tu VERIFY landmark.
"""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync

_LANDMARK = 'data-a="approve_sign"'


def execute():
    res = page_sync.sync()
    frappe.log_error("p141 all_requests sync=%s" % (res or {}).get("action"), "p141 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/all-requests"},
                               "main_section_html") or ""
    if _LANDMARK not in html:
        raise Exception("p141: /approvals/all-requests van chua co nut Duyet & Ky sau sync "
                        "(action=%s)" % (res or {}).get("action"))
