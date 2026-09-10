# Copyright (c) 2026, eCentric and contributors
"""Cap BO QUA hien ten nguoi duyet thay vi lap lai chu "Bo qua" - 26 form (10/09, Hoan chot).

Sau khi luat bo-cap-trung-nguoi len production, EC-HIRE-2026-00005 hien dung nhung xau: duoi
"Direct Manager Review" chu "Bo qua" hien HAI lan. Nhan trang thai lay tu `_STEP_LBL` da la
"Bo qua", roi `meta` cung duoc gan dung chu do - hai cho khac nhau in mot cau.

Gio `meta` hien TEN NGUOI nhu moi cap khac (cap dang chay von hien email nguoi duyet), doc ra
la "Bo qua" / "lam.nguyen@ecentric.vn" - biet ngay ai duoc bo, va khong bao gio sai du sau
nay co them ly do bo khac.

Pham vi: 26 form. CHUA `payment_request` theo yeu cau cua Hoan vi form do co ky so.
Da kiem lai cho chac: CHI payment_request thuc su goi `esign.api` (2 loi goi). `resignation`
KHONG co ky so - 46 chu "esign" dem duoc trong file do deu la khuc giua cua chu "resignation",
mot phep dem chuoi con khong dat ranh gioi tu.

Doan stepper nay lap o ca 27 form nen phai sua ca nhom - vá mot trang de lai 26 trang y het
la dieu CLAUDE.md muc "one-off page-level fixes" bao tranh.

Landmark = dieu PHAI BIEN MAT: trang nao con `meta="Bo qua"` la chua nhan ban moi.
"""
import frappe

_FEATURES = (
    "affiliate_bonus",
    "ai_topup",
    "asset_damage_loss",
    "asset_request",
    "budget_setting",
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
    "outside_work",
    "promotion",
    "purchase_request",
    "resignation",
    "service_referral",
    "special_bonus",
    "system_request",
)


def execute():
    missing = []
    for feature in _FEATURES:
        mod = frappe.get_module(
            "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync" % feature)
        res = mod.sync()
        html = frappe.db.get_value("Web Page", {"route": mod.ROUTE}, "main_section_html") or ""
        if 'meta="B\u1ecf qua"' in html:
            missing.append("%s (action=%s)" % (mod.ROUTE, (res or {}).get("action")))
    frappe.log_error("p172 resync %d form, con lech: %s" % (len(_FEATURES), missing or 0),
                     "p172 resync")
    if missing:
        raise Exception("p172: cac trang sau van lap chu 'Bo qua': " + " | ".join(missing))
