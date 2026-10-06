# Copyright (c) 2026, eCentric and contributors
"""Nut "Nhac nguoi xu ly" tren cac form phe duyet (01/10/2026, Hoan).

Nguoi gui phieu bam -> bao ERP + Teams cho DUNG nguoi dang giu phieu (khong nhac nguoi chua
toi luot / da xong), 15 phut mot lan / phieu. Logic: shared/requests/remind.py; UI dung chung:
public/js/ec_remind.bundle.js (hooks.py web_include_js). Moi trang chi them 2 dong goi bundle.

Ban nay chi RESYNC cac trang (khong doi du lieu). Landmark = dieu PHAI CO tren ban song sau
sync. Trang bi tu choi (lech khoa) -> ghi Error Log, khong nem loi."""
import frappe

_FEATURES = (
    "affiliate_bonus",
    "ai_topup",
    "asset_damage_loss",
    "asset_request",
    "booking_request",
    "budget_setting",
    "clearance_request",
    "compensation_leave",
    "contract_review",
    "daily_target",
    "data_request",
    "document_request",
    "employee_info_update",
    "employee_referral",
    "hiring_request",
    "hr_activity",
    "late_early_out",
    "lateral_move",
    "leave",
    "livestream_sample",
    "livestream_supplies",
    "new_staff_preparation",
    "offer_request",
    "outside_work",
    "payment_request",
    "promotion",
    "purchase_request",
    "resignation",
    "service_referral",
    "special_bonus",
    "system_request",
)
_LANDMARKS = ("EcRemind.buttonHTML(cap)", 'a==="remind"')


def execute():
    thieu, hong = [], []
    for feature in _FEATURES:
        try:
            mod = frappe.get_module(
                "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync" % feature)
            res = mod.sync() or {}
            if res.get("action") == "refused":
                hong.append(feature + " (refused)")
                continue
            html = frappe.db.get_value("Web Page", {"route": mod.ROUTE}, "main_section_html") or ""
            for m in _LANDMARKS:
                if m not in html:
                    thieu.append("%s: %s" % (feature, m))
        except Exception:
            hong.append(feature)
            frappe.log_error(frappe.get_traceback(), "p243 resync %s" % feature)
    frappe.log_error(title="p243 nut nhac nguoi xu ly",
                     message="hong: %s\nthieu landmark: %s\nok: %d/%d" % (
                         hong, thieu, len(_FEATURES) - len(hong), len(_FEATURES)))
