# Copyright (c) 2026, eCentric and contributors
"""Shared validation for EC Approval Participant rows (used by EC Approval
Process and EC Approval Level). No hardcoded users/emails."""
import frappe
from frappe import _

_REQUIRED = {"User": "user", "Role": "role"}
# "Requester Manager" resolves dynamically (Employee.reports_to) -> no static field.
# "Department Manager": 'department' is OPTIONAL - empty means "the requester's own
# department", resolved at submit time (transitions.resolve_participants line ~189).
_OPTIONAL = {"Department Manager": "department"}


def validate_participants(doc, fieldname):
    seen = set()
    for p in (doc.get(fieldname) or []):
        st = p.source_type
        required = _REQUIRED.get(st)
        allowed = {required, _OPTIONAL.get(st)} - {None}
        if required and not p.get(required):
            frappe.throw(_("Participant with source_type '{0}' requires '{1}'.").format(st, required))
        for f in ("user", "role", "department"):
            if f not in allowed and p.get(f):
                frappe.throw(_("Participant source_type '{0}' must not populate '{1}'.").format(st, f))
        if st == "Reference Department Head" and not p.get("department_field"):
            frappe.throw(_("Participant source_type 'Reference Department Head' requires 'department_field'."))
        key = (p.participant_purpose, st, p.get("user"), p.get("role"), p.get("department"))
        if key in seen:
            frappe.throw(_("Duplicate participant within the same parent and purpose."))
        seen.add(key)




# --------------------------------------------------------------------------- #
# Seed args cho setup_*_v1: mot muc la EMAIL (nguoi co dinh) hoac "role:<Ten role>".
#
# Vi sao co lop nay (25/09/2026). Bay luong HR (Promotion, Special Bonus, Hiring, HR Activity,
# Employee Info Update, Employee Referral, Lateral Move) tung GAN CUNG tuan.ly o cap CnB/HR.
# huong.pham (cung team CnB) vi the khong bao gio nhan phieu, va moi lan doi nguoi la phai sua
# cau hinh tung luong. Nay cac cap do resolve theo ROLE (`EC CnB`), nhung setup van nhan danh
# sach email khi can ep nguoi cu the (test tich hop dang dung dung cach do). Mot cach viet cho
# ca hai, dung chung cho moi setup - khong copy vong lap append vao tung file nua.
# --------------------------------------------------------------------------- #
ROLE_PREFIX = "role:"
CNB_ROLE = "EC CnB"


def role_ref(role):
    return ROLE_PREFIX + role


def _split(entry):
    e = (entry or "").strip()
    if e.lower().startswith(ROLE_PREFIX):
        return "Role", e[len(ROLE_PREFIX):].strip()
    return "User", e


def participant_rows(entries):
    """Danh sach seed -> dong EC Approval Participant (chua co purpose/sort_order)."""
    rows = []
    for e in entries or []:
        st, v = _split(e)
        rows.append({"source_type": st, "role" if st == "Role" else "user": v})
    return rows


def active_role_users(role):
    """Nguoi dung THAT SU nhan phieu khi cap resolve theo role nay: enabled System User.
    Cung bo loc voi transitions.resolve_participants, de kiem o day khop voi luc chay."""
    out = []
    for r in frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"},
                            fields=["parent"], distinct=True):
        u = frappe.db.get_value("User", r.parent, ["enabled", "user_type"], as_dict=True)
        if u and u.enabled and u.user_type == "System User" and r.parent not in ("Administrator", "Guest"):
            out.append(r.parent)
    return sorted(set(out))


def validate_seed_entries(label, entries, rep):
    """Thay cho `_validate` rieng cua tung setup: email -> phai la System User dang bat;
    role -> phai ton tai va co it nhat mot nguoi dang bat (khong thi cap nay chan nop phieu)."""
    from ecentric_workspace.approval_center.shared.workflow.user_rules import require_active_system_user
    if not entries:
        rep["errors"].append("No %s users supplied." % label)
    for e in entries or []:
        st, v = _split(e)
        if st == "Role":
            if not frappe.db.exists("Role", v):
                rep["errors"].append("%s: Role %s does not exist." % (label, v))
            elif not active_role_users(v):
                rep["errors"].append("%s: Role %s has no active System User." % (label, v))
            continue
        try:
            require_active_system_user(v, label)
        except Exception as ex:
            rep["errors"].append("%s: %s" % (label, str(ex)))


def check_approver_parts(parts, level_no):
    """Cho validate_*_v1: [(ok, msg)] cho cac dong Approver kieu User/Role cua mot cap."""
    out = []
    users = [p.user for p in parts if p.source_type == "User"]
    roles = [p.role for p in parts if p.source_type == "Role"]
    out.append((bool(users or roles) and len(users) == len(set(users)) and len(roles) == len(set(roles)),
                "L%s approvers, no dup" % level_no))
    for u in users:
        r = frappe.db.get_value("User", u, ["enabled", "user_type"], as_dict=True)
        out.append((bool(r and r.enabled and r.user_type == "System User"),
                    "L%s approver %s active" % (level_no, u)))
    for role in roles:
        out.append((bool(active_role_users(role)), "L%s role %s has active users" % (level_no, role)))
    return out
