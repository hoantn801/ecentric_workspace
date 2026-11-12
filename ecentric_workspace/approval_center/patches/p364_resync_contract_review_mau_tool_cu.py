# Copyright (c) 2026, eCentric and contributors
"""12/11/2026: hop dong KOL dung lai 18 mau HDDV/BBNT cua Ke toan (tool Google Sheet cu) + SO
doanh thu chuyen tu hop dong sang DNTT (anh Hoan: "SO se duoc gan vao payment request").

RESYNC hai trang:
  * form 27 /approvals/contract-review: bo o SO, xem truoc ngay thuc hien / ngay ky / so HD,
    loc mau theo loai creator - nen tang - coc, nhan "con thieu" do server dich.
  * /approvals/payment-request: o "SO doanh thu" khi nguon la hop dong KOL/KOC.
Truong moi (EC Contract Template.platform, bo mac dinh 30 cua payment_term_days) di theo migrate
DocType; Custom Field EC Payment Request.ec_sales_order (bo read_only) di theo fixtures.
"""
import frappe

_PAGES = (
    ("approvals/contract-review", "contract_review",
     ("ContractReviewKOL", "kol_verify_signed", "missing_labels", "kol_preview_dates")),
    ("approvals/payment-request", "payment_request", ("search_funding_so", "SO doanh thu")),
)


def execute():
    """Chi RESYNC trang. Lech / loi -> Error Log, KHONG BAO GIO nem (patch nem = migrate dung lai)."""
    if not frappe.db.exists("DocType", "Web Page"):
        return
    for route, feature, marks in _PAGES:
        try:
            mod = frappe.get_module("ecentric_workspace.approval_center.features.%s.infrastructure.page_sync"
                                    % feature)
            res = mod.sync() or {}
            html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
            thieu = [m for m in marks if m not in html]
            frappe.logger("approval_center").info("p364 resync %s: %s (thieu moc: %s)"
                                                  % (route, res.get("action"), thieu or "khong"))
            if res.get("action") == "refused" or thieu:
                frappe.log_error(title="p364 resync %s" % route,
                                 message="action=%r thieu=%r" % (res.get("action"), thieu))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p364 resync %s" % route)
