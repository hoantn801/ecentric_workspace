# Copyright (c) 2026, eCentric and contributors
"""Chuyen 7 cap duyet HR tu "gan cung tuan.ly" sang role `EC CnB` (Any One) - 25/09/2026, Hoan.

VI SAO. huong.pham (team CnB) khong bao gio nhan phieu Promotion/Special Bonus vi cap CnB chi
co mot dong User = tuan.ly. Ca bay luong HR deu vay. Hoan chot: dung luon role `EC CnB`, mot
nguoi duyet la qua cap; Resignation giu nguyen (tuan.ly chi la nguoi DU PHONG khi nhan vien khong
co quan ly - engine chi nhan du phong la mot user).

PHAM VI - dung bay cap, dinh danh bang (process, level_no, level_name):
    PROMOTION_REQUEST-V1   L2 CnB Review         SPECIAL_BONUS-V1       L2 CnB Review
    HIRING_REQUEST-V1      L2 HR Review          LATERAL_MOVE-V1        L3 HR Review
    HR_ACTIVITY-V1         L1 HR Manager Review  EMPLOYEE_INFO_UPDATE-V1 L1 HR Review
    EMPLOYEE_REFERRAL-V1   L1 Careers Review
Setup cua bay luong nay (features/*/infrastructure/setup.py) doi cung luc sang
`role:EC CnB` nen moi truong moi dung len se giong production.

PHIEU DANG CHAY KHONG BI ANH HUONG: nguoi duyet duoc chot thanh dong Approver luc NOP. Luc viet
patch chi co EC-APR-2026-00378 (Promotion) dang chay, va da qua cap CnB.

AN TOAN:
  * Chi doi mot cap khi dong Approver cua no DUNG la mot dong User tuan.ly (nhu snapshot
    24/09). Khac di (ai do da sua tay) -> bo qua cap do, ghi ly do - khong de len thay doi cua nguoi.
  * Da la Role `EC CnB` -> bo qua (idempotent).
  * Role khong ton tai hoac khong co ai dang bat -> KHONG doi cap nao: doi xong ma role rong thi
    moi phieu nop moi se bi chan "khong resolve duoc nguoi duyet".
  * Chi thay dong participant_purpose = Approver; dong CC/khac giu nguyen. Luu qua doc.save()
    de validate_participants chay va Version ghi vet ai doi gi.
  * KHONG BAO GIO nem loi: patch chay trong migrate (p116). Moi cap mot khoi rieng.
"""
import frappe

from ecentric_workspace.approval_center.shared.workflow.participants import CNB_ROLE, active_role_users

CU = "tuan.ly@ecentric.vn"
CAP = (
    ("PROMOTION_REQUEST-V1", 2, "CnB Review"),
    ("SPECIAL_BONUS-V1", 2, "CnB Review"),
    ("HIRING_REQUEST-V1", 2, "HR Review"),
    ("LATERAL_MOVE-V1", 3, "HR Review"),
    ("HR_ACTIVITY-V1", 1, "HR Manager Review"),
    ("EMPLOYEE_INFO_UPDATE-V1", 1, "HR Review"),
    ("EMPLOYEE_REFERRAL-V1", 1, "Careers Review"),
)


def _mot_cap(proc, no, ten):
    names = frappe.get_all("EC Approval Level", filters={"approval_process": proc, "level_no": no},
                           pluck="name")
    if len(names) != 1:
        return "bo qua: %d dong EC Approval Level" % len(names)
    lvl = frappe.get_doc("EC Approval Level", names[0])
    if lvl.level_name != ten:
        return "bo qua: ten cap la %r, khong phai %r" % (lvl.level_name, ten)
    duyet = [p for p in lvl.participants if p.participant_purpose == "Approver"]
    if len(duyet) == 1 and duyet[0].source_type == "Role" and duyet[0].role == CNB_ROLE:
        return "da la Role %s" % CNB_ROLE
    if not (len(duyet) == 1 and duyet[0].source_type == "User" and duyet[0].user == CU):
        return "bo qua: cau hinh da khac snapshot (%s)" % ", ".join(
            "%s/%s" % (p.source_type, p.user or p.role or "") for p in duyet)
    giu = [p for p in lvl.participants if p.participant_purpose != "Approver"]
    lvl.set("participants", giu)
    lvl.append("participants", {"participant_purpose": "Approver", "source_type": "Role",
                                "role": CNB_ROLE, "sort_order": 0})
    lvl.save(ignore_permissions=True)
    return "DA DOI: User %s -> Role %s (%s)" % (CU, CNB_ROLE, lvl.approval_mode)


def execute():
    ket = []
    try:
        ai = active_role_users(CNB_ROLE) if frappe.db.exists("Role", CNB_ROLE) else []
    except Exception:
        ai = []
    if not ai:
        ket.append("DUNG: Role %s khong ton tai hoac khong co ai dang bat - khong doi cap nao." % CNB_ROLE)
    else:
        ket.append("Role %s dang co: %s" % (CNB_ROLE, ", ".join(ai)))
        for proc, no, ten in CAP:
            try:
                ket.append("%s L%d: %s" % (proc, no, _mot_cap(proc, no, ten)))
                frappe.db.commit()
            except Exception:
                frappe.db.rollback()
                frappe.log_error(title="p208 %s L%d FAILED" % (proc, no), message=frappe.get_traceback())
                ket.append("%s L%d: LOI - xem Error Log" % (proc, no))
    frappe.log_error(title="p208 cap CnB -> role", message="\n".join(ket))
