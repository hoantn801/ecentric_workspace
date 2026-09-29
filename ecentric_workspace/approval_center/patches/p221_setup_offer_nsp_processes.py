# Copyright (c) 2026, eCentric and contributors
"""Dung + bat (UAT) hai quy trinh moi - 28/09/2026:
  OFFER_REQUEST-V1           Line manager -> HR & CnB (EC CnB) -> HOF (EC HOF) -> CEO (EC CEO)
  NEW_STAFF_PREPARATION-V1   1 cap "Each Group": Lead HR / HOF / CnB / Operation song song

Goi DUNG ham setup + enable_uat cua tung form (khong co luat rieng o day). UAT = process Active,
the tren Approval Center van an - hai form nay mo tu Hiring / tu tao, khong can the.
Validate khong qua (vd role chua ai giu) thi DE Draft va ghi ro ly do vao Error Log - khong ep.
Chay lai: setup thay process Active thi bo qua ("ALREADY_ACTIVE"). Khong nem loi."""
import frappe

STEPS = (
    ("offer_request", "setup_offer_request_v1", "enable_offer_request_uat"),
    ("new_staff_preparation", "setup_new_staff_preparation_v1", "enable_new_staff_preparation_uat"),
)


def execute():
    ket = []
    for feat, setup_fn, uat_fn in STEPS:
        try:
            setup = frappe.get_module(
                "ecentric_workspace.approval_center.features.%s.infrastructure.setup" % feat)
            act = frappe.get_module(
                "ecentric_workspace.approval_center.features.%s.infrastructure.activation" % feat)
            r1 = getattr(setup, setup_fn)(dry_run=0, apply=1) or {}
            ket.append("%s setup: %s %s" % (feat, r1.get("result"), r1.get("errors") or ""))
            r2 = getattr(act, uat_fn)(dry_run=0, apply=1, commit=1) or {}
            ket.append("%s uat: %s blockers=%s" % (feat, r2.get("result") or r2.get("mode"),
                                                    r2.get("blockers")))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            ket.append("%s: LOI\n%s" % (feat, frappe.get_traceback()))
    frappe.log_error(title="p221 offer/nsp processes", message="\n".join(ket))
