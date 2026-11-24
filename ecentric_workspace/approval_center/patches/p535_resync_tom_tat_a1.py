# Copyright (c) 2026, eCentric and contributors
"""p535_resync_tom_tat_a1 (24/11/2026, Hoan chot "Tom tat A1 ok"): sync lai 32 trang form phe duyet tu nguon
repo (A65). Khoi "Tom tat" cuoi form doi sang phuong an A1 "Luoi can bang": dai so chinh 1 hang (so tien o mep
phai), moi nhom la luoi o can bang (5 -> 3+2), luong duyet 1 dong, thanh duoi gom "con thieu" (bam nhay toi o)
+ hang nut cua trang (Gui o goc phai). Trang chi khai cau hinh; khung + kieu dung chung:
public/js|css/ec_summary.bundle.* (web_include). Chi hien thi - khong doi gui/luu/validate.

Moi trang mot khoi try; trang nao lech live (khoa chong troi tu choi) -> ghi Error Log, trang khac van
chay. KHONG nem loi, KHONG xoa du lieu, KHONG goi ra ngoai."""
import frappe

FEATURES = (
    "adhoc_approval",
    "affiliate_bonus",
    "ai_topup",
    "asset_damage_loss",
    "asset_request",
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
    frappe.log_error(title="p535 tom tat A1", message="\n".join(ket))
