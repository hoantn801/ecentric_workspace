# Copyright (c) 2026, eCentric and contributors
"""p499_resync_dau_trang_form_phe_duyet (23/11/2026, Hoan chot phuong an C): sync lai 33 trang form phe
duyet tu nguon repo (A65). Dau trang moi la THANH CONG CU DINH: icon mau nhom + ten Viet / dong phu Anh +
nut doi loai phieu (Da ghim / Ban hay dung) + hang tab + sao ghim + "?" huong dan. Luong duyet (stepper)
giu nguyen ben duoi. Kieu + hanh vi dung chung: public/css|js/ec_form_header.bundle.* (web_include).

Moi trang mot khoi try; trang nao lech live (khoa chong troi tu choi) -> ghi Error Log, trang khac van
chay. KHONG nem loi, KHONG xoa du lieu, KHONG goi ra ngoai."""
import frappe

FEATURES = (
    "adhoc_approval",
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
    "employee_review",
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


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    ket = []
    for f in FEATURES:
        mod = "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync" % f
        try:
            res = frappe.get_module(mod).sync() or {}
            act = res.get("action") if isinstance(res, dict) else res
            ket.append("%s: %s" % (f, act))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            ket.append("%s LOI\n%s" % (f, frappe.get_traceback()))
    frappe.log_error(title="p499 dau trang form phe duyet", message="\n".join(ket))
