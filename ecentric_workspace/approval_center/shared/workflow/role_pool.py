# Copyright (c) 2026, eCentric and contributors
"""Nhom nguoi duyet resolve theo ROLE: ai con duoc dung trong nhom (25/09/2026).

Hai lo hong cung mot goc - dong nguoi duyet duoc CHOT luc nop phieu, con role thi song:

1. MAT ROLE VAN DUYET DUOC. EC-CTR-2026-00023 nop 24/09 16:58, luc anh Lam con role
   `EC Finance` -> co dong "Role: EC Finance" o cap Finance Team Review. 17:39 Hoan go role.
   25/09 15:49 anh Lam van bam duyet duoc: `approve()` chi hoi "co dong Pending ten ban khong",
   khong hoi "ban con role do khong". Ca cap Any One dong theo.
   -> `transitions.row_still_eligible` + `_actor_pending_row` chan o MOI duong bam
      (duyet / tu choi / yeu cau bo sung) va an nut tren UI;
   -> `on_user_update` (doc_events User): go role la cac dong Pending "Role: X" cua nguoi do
      thanh Skipped ngay, dong ToDo, loai dau viec SLA - de hop thu cua ho sach luon.

2. NGUOI CO GHE RIENG O CAP SAU LAI NAM TRONG NHOM O CAP TRUOC. Chi Phuong la HOF (cap 3,
   dich danh) nhung cung giu `EC Finance` nen nam trong nhom cap 2. Chi bam cap 2 -> luat
   "da duyet cap truoc thi cap sau tu qua" bo luon cap HOF: EC-CTR-2026-00014, 00022, 00026
   thuc chat khong co ai trong nhom Finance xem, va HOF cung khong duyet rieng.
   -> `transitions.drop_own_seat`: luc dung luong, nguoi co ghe DICH DANH (User) o mot cap SAU bi loai
      khoi nhom ROLE o cap truoc. Anh Lam (CEO, cap 4) cung duoc loai theo cung luat.

KHONG BAO GIO lam mot cap mat het nguoi: neu loai xong khong con ai thi GIU NGUYEN va ghi
Error Log - phieu ket vi khong ai duyet te hon phieu co mot nguoi duyet hoi du.
Khong ten nguoi, khong ten role nao duoc viet cung trong file nay.
"""
import frappe

from ecentric_workspace.approval_center.shared.workflow.transitions import (  # noqa: F401
    ROLE_LABEL, drop_own_seat, named_seats_after, role_of, row_still_eligible)

OPEN = ("Pending", "Information Required")


# --------------------------------------------------------------------------- #
# Don cac dong da chot tren phieu dang mo
# --------------------------------------------------------------------------- #
def tidy_open_rows(users=None, actor=None):
    """Chuyen sang Skipped moi dong Pending kieu Role tren phieu DANG MO ma nguoi do mat role
    hoac co ghe dich danh o cap sau. -> [(approval_request, level_no, user, ly_do, ket_qua)].

    Chi dung cac dong Pending; dong da Approved/Rejected la lich su, khong ai sua."""
    from ecentric_workspace.approval_center.shared.workflow import transitions as tr
    actor = actor or frappe.session.user
    filters = {"status": "Pending", "source": ["like", ROLE_LABEL + "%"]}
    if users:
        filters["approver"] = ["in", list(users)]
    rows = frappe.get_all("EC Approval Request Approver", filters=filters,
                          fields=["name", "approval_request", "level_no", "approver", "source"])
    if not rows:
        return []
    reqs = {r.name: r for r in frappe.get_all(
        "EC Approval Request",
        filters={"name": ["in", sorted({r.approval_request for r in rows})],
                 "approval_status": ["in", list(OPEN)]},
        fields=["name", "reference_doctype", "reference_name", "current_level"])}
    roles = {}

    def roles_of(u):
        if u not in roles:
            roles[u] = set(frappe.get_roles(u))
        return roles[u]

    snap = {}

    def rows_of(req_name):
        # Ban chot CUA CHINH PHIEU (khong doc lai cau hinh process: no co the da doi).
        if req_name not in snap:
            snap[req_name] = frappe.get_all(
                "EC Approval Request Approver",
                filters={"approval_request": req_name, "status": ["in", ["Pending", "Approved"]]},
                fields=["name", "level_no", "approver", "source", "status"])
        return snap[req_name]

    def reason(req_name, level_no, user, source):
        role = role_of(source)
        if not role:
            return None
        if role not in roles_of(user):
            return "Khong con giu vai tro %s" % role
        if any(n.level_no > level_no and n.approver == user and not role_of(n.source)
               for n in rows_of(req_name)):
            return "Co ghe rieng o cap sau - khong nam trong nhom %s" % role
        return None

    out = []
    for r in rows:
        req = reqs.get(r.approval_request)
        if not req:
            continue
        why = reason(req.name, r.level_no, r.approver, r.source)
        if not why:
            continue
        frappe.db.get_value("EC Approval Request", req.name, "name", for_update=True)
        con = [x for x in rows_of(req.name)
               if x.level_no == r.level_no and x.status == "Pending" and x.name != r.name
               and not reason(req.name, r.level_no, x.approver, x.source)]
        if not con:
            frappe.log_error(title="role_pool: giu nguyen nguoi duyet cuoi cung",
                             message="%s cap %s: %s (%s) - loai di thi cap khong con ai. "
                                     "Can chuyen nguoi duyet bang tay."
                                     % (req.reference_name, r.level_no, r.approver, why))
            out.append((req.name, r.level_no, r.approver, why, "giu - nguoi cuoi"))
            continue
        frappe.db.set_value("EC Approval Request Approver", r.name,
                            {"status": "Skipped", "comment": why})
        for x in rows_of(req.name):
            if x.name == r.name:
                x.status = "Skipped"
        tr.log_action(req.name, "Skipped", actor, r.level_no, comment=why, related_user=r.approver)
        if r.level_no == req.current_level:
            _clear_todo(tr, req, r.approver)
            tr._sla().on_approver_removed(
                request_doctype=req.reference_doctype, request_name=req.reference_name,
                level_no=r.level_no, user=r.approver, reason=why)
        out.append((req.name, r.level_no, r.approver, why, "Skipped"))
    return out


def _clear_todo(tr, req, user):
    for td in frappe.get_all("ToDo", filters={"reference_type": req.reference_doctype,
                                              "reference_name": req.reference_name,
                                              "allocated_to": user, "status": "Open"},
                             pluck="name"):
        frappe.db.set_value("ToDo", td, "status", "Cancelled", update_modified=False)
    tr._engine_maintain_assign(req.reference_doctype, req.reference_name, user, add=False)


# --------------------------------------------------------------------------- #
# doc_events: User.on_update
# --------------------------------------------------------------------------- #
def on_user_update(doc, method=None):
    """Go role khoi mot nguoi -> don ngay cac dong Pending "Role: <role do>" cua ho.

    Nuot moi loi: hook chay trong giao dich luu User; loi lot ra se lam Hoan khong luu
    duoc viec go role - dung dieu ta dang muon lam."""
    try:
        before = doc.get_doc_before_save()
        if not before:
            return
        had = {r.role for r in (before.get("roles") or [])}
        has = {r.role for r in (doc.get("roles") or [])}
        if not (had - has):
            return
        tidy_open_rows(users=[doc.name])
    except Exception:
        frappe.log_error(title="role_pool.on_user_update", message=frappe.get_traceback())
