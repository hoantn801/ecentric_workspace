# Copyright (c) 2026, eCentric and contributors
"""23/11/2026 - sua 3 diem phat hien khi kiem sau deploy quy trinh nhan su (Hoan chot):

  1. Role "HR" chua ton tai -> setup V2 Offer / Nghi viec da bo "role:HR" khoi cap CnB/HR.
     Hoan chot 22/11: luc.nguyen cap role HR. Tao Role HR (desk_access=0, chi la nhan nhom duyet),
     cap cho luc.nguyen neu user ton tai + dang bat, roi THEM mot dong participant Role HR vao cap
     CnB/HR cua OFFER_REQUEST-V2 va RESIGNATION-V2 (Any One - them nguoi, khong bot ai).
     Phieu dang chay giu snapshot cu (engine); phieu gui moi moi co luc.nguyen.
  2. p450 publish the Danh gia nhan su loi "route must start with '/'" -> chay lai publish sau khi
     activation.py da sua route.
  3. The "Phan bo ty trong brand" (BRAND_WEIGHT) dang "Sap ra mat", route thieu "/" -> tro the sang
     /ec-hr/phan-bo-cong-viec va bat the (Hoan 23/11: "link no vao cho phan bo ty trong").

Moi buoc mot khoi try, ket qua ghi Error Log "p490 ...". Khong goi ra ngoai, khong enqueue, khong
gui thong bao, khong xoa gi. Chay lai an toan (kiem truoc khi them)."""
import frappe

ROLE_HR = "HR"
HR_USER = "luc.nguyen@ecentric.vn"
CNB_LEVELS = (("OFFER_REQUEST-V2", 2), ("RESIGNATION-V2", 2))
BRAND_TYPE = "BRAND_WEIGHT"
BRAND_ROUTE = "/ec-hr/phan-bo-cong-viec"


def _role_hr(ket):
    if not frappe.db.exists("Role", ROLE_HR):
        frappe.get_doc({"doctype": "Role", "role_name": ROLE_HR, "desk_access": 0}).insert(
            ignore_permissions=True)
        ket.append("role HR: created")
    else:
        ket.append("role HR: da co")
    if not frappe.db.get_value("User", HR_USER, "enabled"):
        ket.append("user %s: khong ton tai / da tat -> khong cap" % HR_USER)
        return
    if frappe.db.exists("Has Role", {"parent": HR_USER, "parenttype": "User", "role": ROLE_HR}):
        ket.append("user %s: da co role HR" % HR_USER)
        return
    # Chen dong Has Role truc tiep (khong User.save): tranh hook / Server Script tren User goi ra
    # ngoai trong luc migrate (bai hoc p425 20/11). Xoa cache quyen cua user sau khi them.
    frappe.get_doc({"doctype": "Has Role", "parent": HR_USER, "parenttype": "User",
                    "parentfield": "roles", "role": ROLE_HR}).insert(ignore_permissions=True)
    frappe.clear_cache(user=HR_USER)
    ket.append("user %s: cap role HR" % HR_USER)


def _them_role_vao_cap(ket):
    for proc, level_no in CNB_LEVELS:
        lv = frappe.db.get_value("EC Approval Level", {"approval_process": proc, "level_no": level_no}, "name")
        if not lv:
            ket.append("%s L%s: khong thay cap -> bo qua" % (proc, level_no))
            continue
        doc = frappe.get_doc("EC Approval Level", lv)
        if any(p.source_type == "Role" and p.role == ROLE_HR for p in doc.participants or []):
            ket.append("%s L%s (%s): da co role HR" % (proc, level_no, doc.level_name))
            continue
        n = max([p.sort_order or 0 for p in doc.participants or []] or [0]) + 1
        doc.append("participants", {"participant_purpose": "Approver", "source_type": "Role",
                                    "role": ROLE_HR, "sort_order": n})
        doc.save(ignore_permissions=True)
        ket.append("%s L%s (%s): them role HR" % (proc, level_no, doc.level_name))


def _publish_danh_gia(ket):
    if frappe.db.get_value("EC Approval Type", "EMPLOYEE_REVIEW", "card_status") == "Active":
        ket.append("EMPLOYEE_REVIEW: the da Active")
        return
    from ecentric_workspace.approval_center.features.employee_review.infrastructure import activation as act
    r = act.publish_employee_review(dry_run=0, apply=1, commit=1) or {}
    ket.append("EMPLOYEE_REVIEW publish: %s blockers=%s" % (r.get("result"), r.get("blockers")))


def _the_phan_bo(ket):
    if not frappe.db.exists("EC Approval Type", BRAND_TYPE):
        ket.append("BRAND_WEIGHT: khong co type -> bo qua")
        return
    cur = frappe.db.get_value("EC Approval Type", BRAND_TYPE, ["card_status", "process_status", "route"],
                              as_dict=True)
    frappe.db.set_value("EC Approval Type", BRAND_TYPE,
                        {"route": BRAND_ROUTE, "card_status": "Active", "process_status": "Live"})
    ket.append("BRAND_WEIGHT: %s/%s/%s -> Active/Live/%s" % (cur.card_status, cur.process_status,
                                                              cur.route, BRAND_ROUTE))


def execute():
    if not frappe.db.exists("DocType", "EC Approval Type"):
        return
    ket = []
    for buoc in (_role_hr, _them_role_vao_cap, _publish_danh_gia, _the_phan_bo):
        try:
            buoc(ket)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            ket.append("%s LOI\n%s" % (buoc.__name__, frappe.get_traceback()))
    frappe.log_error(title="p490 HR sua sau deploy", message="\n".join(ket))
