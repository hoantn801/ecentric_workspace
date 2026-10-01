# Copyright (c) 2026, eCentric and contributors
"""O nhap so tien tren cac form phe duyet: dau cham phan cach hang nghin + can phai (01/10/2026,
Hoan). Asset dung chung public/js/ec_money.bundle.js + css (hooks.py); moi trang danh dau
`data-money` va doc gia tri qua EcMoney.val. Kem: Promotion - luong hien tai la GROSS do nguoi
de xuat tu nhap (khong con lay base cua bang luong).

Ban nay chi RESYNC trang. Landmark = dieu PHAI CO tren ban song sau sync. Trang bi tu choi
(lech khoa) -> ghi Error Log, khong nem loi."""
import frappe

_FEATURES = (
    "affiliate_bonus",
    "ai_topup",
    "asset_damage_loss",
    "booking_request",
    "budget_setting",
    "contract_review",
    "hiring_request",
    "hr_activity",
    "promotion",
    "purchase_request",
    "service_referral",
    "special_bonus",
)
_LANDMARK = "data-money"


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
            if _LANDMARK not in html:
                thieu.append(feature)
        except Exception:
            hong.append(feature)
            frappe.log_error(frappe.get_traceback(), "p250 resync %s" % feature)
    frappe.log_error(title="p250 o so tien dau cham",
                     message="hong: %s\nthieu landmark: %s\nok: %d/%d" % (
                         hong, thieu, len(_FEATURES) - len(hong), len(_FEATURES)))
