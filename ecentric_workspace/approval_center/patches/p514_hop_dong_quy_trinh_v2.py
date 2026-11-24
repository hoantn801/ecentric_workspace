# Copyright (c) 2026, eCentric and contributors
"""24/11/2026 (PO chot cau D ban giao chat Ky so): dung CONTRACT_REVIEW-V2 (Draft) roi doi V1 -> Retired /
V2 -> Active. V2 = V1 + cap "HR & C&B Review" (Role EC CnB + HR) cho hop dong lao dong (Nhan su -> CEO).

  * Chep nguoi duyet / SLA L1-L3 + CEO tu process DANG Active (khong ghi cung email).
  * Chi doi khi V2 qua validate (role co nguoi...). Khong qua -> V2 o Draft, V1 giu Active, ly do o Error
    Log; System Manager chay lai activate_contract_review_v2 sau. Service tim cap theo TEN nen chay dung
    voi ca V1 lan V2.
  * Phieu dang chay giu snapshot V1 (engine) - khong vo. Khong xoa V1.
Chay lai: V2 da Active -> bo qua. Khong nem loi (migrate)."""
import frappe

_M = "ecentric_workspace.approval_center.features.contract_review.infrastructure.setup_v2"


def execute():
    if not frappe.db.exists("DocType", "EC Approval Process"):
        return
    ket = []
    try:
        mod = frappe.get_module(_M)
        r1 = mod.setup_contract_review_v2(dry_run=0, apply=1) or {}
        ket.append("setup: %s errors=%s warnings=%s notes=%s" % (r1.get("result"), r1.get("errors"),
                                                                 r1.get("warnings"), r1.get("notes")))
        if r1.get("result") != "BLOCKED":
            r2 = mod.activate_contract_review_v2(dry_run=0, apply=1) or {}
            ket.append("activate: %s retire=%s blockers=%s" % (r2.get("result"), r2.get("retire"),
                                                               r2.get("blockers")))
    except Exception:
        frappe.db.rollback()
        ket.append("LOI\n%s" % frappe.get_traceback())
    frappe.log_error(title="p514 hop dong quy trinh V2", message="\n".join(ket))
