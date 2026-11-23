# Copyright (c) 2026, eCentric and contributors
"""Khoi "Tai lieu & ky so" dung chung len form Hop dong (PR-E 23/11/2026, THIETKE_ky_so_hop_dong
muc 2h).

Hai trang, cung mot tep nguon platform/esign/ui/document_signing_section.html:
  * /approvals/contract-review: page_sync GHEP THEM khoi (truoc day chi co main_section). Khoi tu
    gan vao `#ctr-esign-slot` ma trang da dat san + nghe `ctr:detail-rendered`. Che do hop dong:
    an be mat tai tep + nut Go (tep do cac o tep cua Hop dong quan ly), giu o "Bo chung tu",
    danh sach tai lieu, drawer dat o ky, tinh trang ky. Loai chung tu chua co ho so ky -> khoi an.
  * /approvals/payment-request: khoi doi cach chon chung tu (target()) - trang DNTT khong co slot
    nen VAN goi `payment_request_name` nhu cu. Hanh vi khong doi; resync de live = nguon.
Landmark = dieu PHAI CO tren ban song sau khi ghi.
"""
import frappe

from ecentric_workspace.approval_center.features.contract_review.infrastructure import \
    page_sync as ctr_sync
from ecentric_workspace.approval_center.features.payment_request.infrastructure import \
    page_sync as pr_sync

_PAGES = (
    ("approvals/contract-review", ctr_sync, ('id="ec-docsign"', "function target(",
                                             "ctr:detail-rendered", ".ec-docsign.ecd-ctr .ecd-up")),
    ("approvals/payment-request", pr_sync, ('id="ec-docsign"', "function target(")),
)


def execute():
    for route, mod, landmarks in _PAGES:
        res = mod.sync()
        action = (res or {}).get("action")
        # Chi ghi Error Log khi CO VAN DE (tu choi ghi / thieu dau moc) - QC 23/11.
        if action == "refused":
            frappe.log_error("p432: %s TU CHOI GHI (live lech) - trang KHONG duoc cap nhat. "
                             "Doi chieu SUPERSEDES_SHA256." % route, "p432 REFUSED")
            continue
        html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
        thieu = [m for m in landmarks if m not in html]
        if thieu:
            frappe.log_error("p432: %s thieu dau moc %s" % (route, thieu), "p432 KHONG toi noi")
