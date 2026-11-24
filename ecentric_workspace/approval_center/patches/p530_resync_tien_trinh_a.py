# Copyright (c) 2026, eCentric and contributors
"""p530_resync_tien_trinh_a (24/11/2026, PO Hoan chot "Tien trinh phe duyet A ok"): sync lai 33 trang form
tu nguon repo (A65). Moi trang chi doi 2-3 cho: buildStepper truyen `det` vao renderStepsHTML -> EcApprovalUI
.stepsHTML(..., {detail: det}) de asset dung chung ve stepper phuong an A + bang "Viec cua ban" (du lieu
get_detail "viewer" + levels[i].mine do server tinh - shared/requests/viewer_task.py); man sua & gui lai
truyen viewer:null (khong ve bang tren chinh form dang sua). CSS: public/css/ec_approval_ui.bundle.css.

Moi trang mot khoi try; trang lech live (khoa chong troi tu choi) -> ghi Error Log, trang khac van chay.
KHONG nem loi, KHONG xoa du lieu, KHONG goi ra ngoai."""
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
    frappe.log_error(title="p530 tien trinh phe duyet A", message="\n".join(ket))
