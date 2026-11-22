# Copyright (c) 2026, eCentric and contributors
"""23/11/2026 (HR v2 - Dot 1, Hoan chot): dung V2 (Draft) roi doi V1 -> Retired / V2 -> Active cho
Offer, New Staff Preparation, Clearance, Nghi viec. Moi buoc mot khoi try, ket qua ghi Error Log.

  * Setup chi ghi cau hinh (process / level / participant / SLA policy) - KHONG gui thong bao, KHONG
    enqueue, khong goi ra ngoai.
  * Doi process chi khi V2 qua validate (role co nguoi, SLA policy bat...). Khong qua -> V2 o Draft,
    V1 giu Active, ly do o Error Log; System Manager chay lai activate_*_v2 sau.
  * Nghi viec: CHI ngung V1 khi hang doi "HR xu ly" cu khong con don (Assigned / In Progress).
  * Phieu dang chay giu snapshot cu (engine) - khong vo. Khong xoa V1.
Chay lai: V2 da Active -> bo qua. Khong nem loi (migrate)."""
import frappe

_F = "ecentric_workspace.approval_center.features."
_STEPS = (
    ("OFFER_REQUEST", _F + "offer_request.infrastructure.setup_v2",
     "setup_offer_request_v2", "activate_offer_request_v2"),
    ("NEW_STAFF_PREPARATION", _F + "new_staff_preparation.infrastructure.setup_v2",
     "setup_new_staff_preparation_v2", "activate_new_staff_preparation_v2"),
    ("CLEARANCE_REQUEST", _F + "clearance_request.infrastructure.setup_v2",
     "setup_clearance_request_v2", "activate_clearance_request_v2"),
    ("RESIGNATION", _F + "resignation.infrastructure.setup_v2",
     "setup_resignation_v2", "activate_resignation_v2"),
)


def execute():
    if not frappe.db.exists("DocType", "EC Approval Process"):
        return
    ket = []
    for atype, module, setup_fn, act_fn in _STEPS:
        try:
            mod = frappe.get_module(module)
            r1 = getattr(mod, setup_fn)(dry_run=0, apply=1) or {}
            ket.append("%s setup: %s errors=%s warnings=%s" % (atype, r1.get("result"), r1.get("errors"),
                                                                r1.get("warnings")))
            if r1.get("result") == "BLOCKED":
                continue
            r2 = getattr(mod, act_fn)(dry_run=0, apply=1) or {}
            ket.append("%s activate: %s retire=%s blockers=%s" % (atype, r2.get("result"), r2.get("retire"),
                                                                  r2.get("blockers")))
        except Exception:
            frappe.db.rollback()
            ket.append("%s LOI\n%s" % (atype, frappe.get_traceback()))
    frappe.log_error(title="p440 HR v2 quy trinh", message="\n".join(ket))
