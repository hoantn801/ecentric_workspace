# Copyright (c) 2026, eCentric and contributors
"""Quyen doc EC Internal Post - MOT luat cho moi duong doc (hooks.py).

  * permission_query_conditions -> danh sach (frappe.get_list, /api/resource, tim kiem, bao cao)
  * has_permission              -> mot bai (trang bai, frappe.get_doc, tai tep private dinh kem)

Luat (PO chot 01/10/2026):
  * Nguoi soan (EDITOR_ROLES) thay moi bai, ke ca nhap / het han.
  * Nhan vien (co ho so Employee dang Active gan tai khoan) doc bai DA DANG ma pham vi trong
    (toan cong ty) hoac chua phong ban cua ho - phong cha bao gom phong con. Nguoi ngoai pham
    vi doan dung link van bi chan.
  * Bai het han: rut khoi DANH SACH (query condition) nhung van mo duoc qua link.
  * Guest / khong co ho so Employee Active: khong thay bai nao.

has_permission chi duoc TU CHOI (Frappe: controller khong cap them quyen ngoai role); voi
ptype khac "read" thi tra True de quyen role (HR ghi/xoa) tu quyet.
"""
import frappe

from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts import domain as D
from ecentric_workspace.internal_posts import repository as R

_READ_PTYPES = ("read", "select", "print", "email", "export", "report")


def query_conditions(user=None, doctype=None):
    user = user or frappe.session.user
    if R.is_editor(user):
        return ""
    v = R.viewer(user)
    if not v:
        return "1=0"
    t = "`tab%s`" % C.POST_DT
    today = frappe.db.escape(str(R.today()))
    lft = v.get("lft")
    in_scope = "0"
    if lft is not None:
        in_scope = (
            "exists (select 1 from `tab{child}` pd join `tabDepartment` sel on sel.name = pd.department "
            "where pd.parent = {t}.name and pd.parenttype = {dt} and sel.lft <= {lft} and sel.rgt >= {lft})"
        ).format(child=C.DEPT_CHILD_DT, t=t, dt=frappe.db.escape(C.POST_DT), lft=int(lft))
    no_scope = ("not exists (select 1 from `tab{child}` pd0 where pd0.parent = {t}.name "
                "and pd0.parenttype = {dt})").format(child=C.DEPT_CHILD_DT, t=t, dt=frappe.db.escape(C.POST_DT))
    return ("({t}.published = 1 and ({t}.expires_on is null or {t}.expires_on >= {today}) "
            "and ({no_scope} or {in_scope}))").format(t=t, today=today, no_scope=no_scope, in_scope=in_scope)


def child_query_conditions(user=None, doctype=None):
    """Bang con (phong ban, tep dinh kem) cua bai: chi dong cua bai nguoi nay doc duoc.
    Frappe chi ap hook cua CHINH doctype duoc truy van - khong co ham nay thi
    /api/resource/EC Internal Post File lo ten + duong dan tep cua bai nhap / phong khac."""
    user = user or frappe.session.user
    cond = query_conditions(user)
    if not cond:
        return ""
    if cond == "1=0":
        return "1=0"
    child = doctype or C.FILE_CHILD_DT
    return ("`tab{child}`.parent in (select `tab{dt}`.name from `tab{dt}` where {cond})"
            .format(child=child, dt=C.POST_DT, cond=cond))


def has_permission(doc, ptype=None, user=None, debug=False):
    user = user or frappe.session.user
    if ptype and ptype not in _READ_PTYPES:
        return True
    if R.is_editor(user):
        return True
    v = R.viewer(user)
    if not v:
        return False
    get = doc.get if hasattr(doc, "get") else (lambda k: getattr(doc, k, None))
    depts = [row.get("department") if hasattr(row, "get") else getattr(row, "department", None)
             for row in (get("departments") or [])]
    selected = _selected(depts)
    post = {"published": get("published")}
    return D.readable(post, v.get("lft"), selected, False)


def _selected(depts):
    """Ten phong -> [(lft, rgt)]. Phong da bi xoa khoi cay -> (None, None): khong ai khop, an toan."""
    if not depts:
        return []
    tree = R.dept_tree()
    out = []
    for d in depts:
        lr = tree.get(d)
        out.append((lr[0], lr[1]) if lr else (None, None))
    return out
