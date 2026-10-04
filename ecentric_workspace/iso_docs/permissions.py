# Copyright (c) 2026, eCentric and contributors
"""Quyen tren Quality Procedure (tai lieu ISO) - MOT luat cho moi duong doc / ghi (hooks.py).

  * permission_query_conditions -> danh sach (/app, /api/resource, bao cao, tim kiem)
  * has_permission              -> mot tai lieu (form, frappe.get_doc, tai tep private dinh kem)

Luat thuan o domain.can_read / domain.can_write. Role Employee duoc read + write tren
Quality Procedure (Custom DocPerm, patch p001) chi de truong BP / nguoi soan bam duoc buoc
cua minh trong Workflow; has_permission thu hep lai. Frappe: controller chi duoc TU CHOI,
khong cap them quyen ngoai role.
"""
import frappe

from ecentric_workspace.iso_docs import constants as C
from ecentric_workspace.iso_docs import domain as D
from ecentric_workspace.iso_docs import repository as R

_READ_PTYPES = ("read", "select", "print", "email", "export", "report")
_WRITE_PTYPES = ("write", "submit", "cancel", "amend")


def query_conditions(user=None, doctype=None):
    user = user or frappe.session.user
    if R.is_manager(user):
        return ""
    t = "`tab%s`" % C.QP
    u = frappe.db.escape(user)
    mine = "({t}.ec_drafter = {u} or {t}.ec_dept_head = {u})".format(t=t, u=u)
    v = R.viewer(user)
    if not v:
        return mine
    lft = v.get("lft")
    in_scope = "0"
    if lft is not None:
        in_scope = (
            "exists (select 1 from `tab{child}` dd join `tabDepartment` sel on sel.name = dd.department "
            "where dd.parent = {t}.name and dd.parenttype = {dt} and sel.lft <= {lft} and sel.rgt >= {lft})"
        ).format(child=C.DEPT_CHILD_DT, t=t, dt=frappe.db.escape(C.QP), lft=int(lft))
    readable = ("(ifnull({t}.ec_current_version, '') != '' and ifnull({t}.ec_doc_state, '') != {exp} "
                "and ({t}.ec_company_wide = 1 or {in_scope}))").format(
        t=t, exp=frappe.db.escape(C.S_EXPIRED), in_scope=in_scope)
    return "({mine} or {readable})".format(mine=mine, readable=readable)


def child_query_conditions(user=None, doctype=None):
    """Bang con (lich su ban hanh, phong ban) chi lo dong cua tai lieu nguoi nay doc duoc."""
    user = user or frappe.session.user
    cond = query_conditions(user)
    if not cond:
        return ""
    child = doctype or C.REVISION_DT
    return ("`tab{child}`.parent in (select `tab{qp}`.name from `tab{qp}` where {cond})"
            ).format(child=child, qp=C.QP, cond=cond)


def _doc_dict(doc):
    return {k: doc.get(k) for k in ("ec_current_version", "ec_doc_state", "ec_company_wide",
                                    "ec_drafter", "ec_dept_head")}


def has_permission(doc, ptype=None, user=None, debug=False):
    user = user or frappe.session.user
    ptype = ptype or "read"
    if R.is_manager(user):
        return True
    if ptype in _READ_PTYPES:
        depts = [r.get("department") for r in (doc.get("ec_scope_departments") or [])]
        return D.can_read(_doc_dict(doc), user, False, R.viewer(user), R.dept_ranges(depts))
    if ptype in _WRITE_PTYPES:
        return D.can_write(_doc_dict(doc), user, False)
    if ptype in ("create", "delete"):
        return False
    return True
