# Copyright (c) 2026, eCentric and contributors
"""p561_resync_gan_phieu_nguoi_lap (26/11/2026): sync lai 32 trang form phe duyet tu nguon repo (A65).

1. Gan phieu duyet cho NGUOI LAP phieu (truoc do 0 EC Approval Link tren site: trang chi ve khoi o panel nguoi
   duyet). Chi tiet phieu NHAP: panel hanh dong noi EcAddFile.buttonHTML(cap) (chip + nut theo capability
   server). Form tao moi / sua nhap / sua de gui lai: the Tom tat A1 nhan khoi EcApprovalLinks.formHTML - form
   moi bam nut -> saveDraft(false, done) cua trang (o lai form) -> get_detail -> hop chon phieu.
   Asset: public/js/ec_approval_links.bundle.js + ec_summary.bundle.js (web_include).
2. Contract Review: Bang tinh chi tiet - dong Thuc nhan co nen mo bo goc, cot thong so ben phai thanh card.

Moi trang mot khoi try; trang nao lech live (khoa chong troi tu choi) -> ghi Error Log, trang khac van chay.
KHONG nem loi, KHONG xoa du lieu, KHONG goi ra ngoai."""
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
    frappe.log_error(title="p561 gan phieu nguoi lap", message="\n".join(ket))
