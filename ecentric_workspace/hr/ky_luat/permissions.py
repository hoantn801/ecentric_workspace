# Copyright (c) 2026, eCentric and contributors
"""Quyen doc DocType cua module Ky luat - MOT luat (application/access.py) cho moi duong doc:

  * permission_query_conditions -> danh sach / bao cao / /api/resource: HR/CEO thay het; nguoi
    khac chi dong lien quan (minh / team / minh gui / minh du hop) - loc lai tung dong o has_permission.
  * has_permission -> mo mot ban ghi, TAI TEP RIENG TU dinh kem (File.has_permission di theo ban ghi).

has_permission chi duoc TU CHOI (Frappe khong cap them ngoai role); ptype ghi tra True de
quyen role tu quyet (DocType chi cap ghi cho System Manager - moi thao tac di qua service)."""
import frappe

from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.application import access as A
from ecentric_workspace.hr.ky_luat.application import views
from ecentric_workspace.hr.ky_luat.infrastructure.repository import Repository

_READ = ("read", "select", "print", "email", "export", "report")


def _ctx(user):
    return views.make_ctx(Repository(), user or frappe.session.user)


def _cond(doctype, ctx):
    if ctx.sees_all:
        return ""
    t = "`tab%s`" % doctype
    esc = frappe.db.escape
    me = ["%s.employee_user = %s" % (t, esc(ctx.user))]
    if ctx.employee:
        me.append("%s.employee = %s" % (t, esc(ctx.employee)))
    parts = []
    if ctx.team:
        parts.append("%s.employee in (%s)" % (t, ", ".join(esc(e) for e in sorted(ctx.team))))
    if doctype == C.NOTICE:
        parts += me + ["%s.issued_by = %s" % (t, esc(ctx.user))]
    else:
        visible = "%s.status in (%s)" % (t, ", ".join(esc(s) for s in C.CASE_VISIBLE_TO_EMPLOYEE))
        parts.append("((%s) and %s)" % (" or ".join(me), visible))
        parts.append("(%s.union_rep_user = %s and %s)" % (t, esc(ctx.user), visible))
        parts.append("%s.proposed_by = %s" % (t, esc(ctx.user)))
    return "(" + " or ".join(parts) + ")"


def notice_query(user=None, doctype=None):
    return _cond(C.NOTICE, _ctx(user))


def case_query(user=None, doctype=None):
    return _cond(C.CASE, _ctx(user))


def _get(doc):
    return doc.get if hasattr(doc, "get") else (lambda k: getattr(doc, k, None))


def notice_has_permission(doc, ptype=None, user=None, debug=False):
    if ptype and ptype not in _READ:
        return True
    g = _get(doc)
    return A.can_view_notice(_ctx(user), {k: g(k) for k in ("employee", "employee_user", "issued_by")})


def case_has_permission(doc, ptype=None, user=None, debug=False):
    if ptype and ptype not in _READ:
        return True
    g = _get(doc)
    return A.can_view_case(_ctx(user), {k: g(k) for k in ("employee", "employee_user", "proposed_by",
                                                         "union_rep_user", "status")})
