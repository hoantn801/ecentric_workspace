# Copyright (c) 2026, eCentric and contributors
"""p500_resync_quy_trinh_a_z (24/11/2026, Hoan: "quy trinh xu li cua tat ca cac form nen show full tu A-Z
thay vi toi khi CEO review xong roi moi co quy trinh tiep theo"): sync lai 33 trang form tu nguon repo
(A65). Stepper moi trang goi EcApprovalUI.withJourney(steps, boot.journey_after): sau cac cap duyet ve
tiep viec xu ly cua phieu (fulfillment / auto) -> Hoan tat -> phieu / viec tiep theo. Du lieu cac buoc
khai o ApprovalDefinition.journey_after (domain/definition.py tung feature).

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
    frappe.log_error(title="p500 quy trinh A-Z", message="\n".join(ket))
