# Copyright (c) 2026, eCentric and contributors
"""Cho DUY NHAT cua module SLA co `@frappe.whitelist()`.

Moi ham: doc tham so -> goi service -> boc phong bi -> tra ve. Khong `frappe.db`,
khong nhanh nghiep vu. Tham so tu HTTP luon la chuoi, nen ep kieu tuong minh -
`only_failed=0` nhan duoc "0" se la truthy neu khong ep, va bo loc se im lang
lam nguoc lai y nguoi dung.
"""
import frappe
from frappe import _

from ecentric_workspace.sla import permissions
from ecentric_workspace.sla.application import obligation_service, scoreboard_service
from ecentric_workspace.sla.constants import (
    ADJ_EXCLUDE, ADJ_EXTEND_DUE, ADJ_MARK_MET, ADJ_MARK_MISSED, ADJ_RESTORE,
    ALL_ADJUSTMENTS, DT_ADJUSTMENT, DT_OBLIGATION, STATUS_MET, STATUS_MISSED,
    STATUS_OPEN,
)


def _ok(data, message=""):
    return {"success": True, "message": message, "data": data}


def _fail(message):
    return {"success": False, "message": message, "data": None}


@frappe.whitelist()
def my_board(period=None):
    """Bang diem cua chinh nguoi dang dang nhap."""
    try:
        return _ok(scoreboard_service.person_board(frappe.session.user, period))
    except frappe.PermissionError as e:
        return _fail(str(e))


@frappe.whitelist()
def person_board(user, period=None):
    try:
        return _ok(scoreboard_service.person_board(user, period))
    except frappe.PermissionError as e:
        return _fail(str(e))


@frappe.whitelist()
def person_items(user=None, period=None, group_key=None, only_failed=0):
    user = user or frappe.session.user
    try:
        return _ok(scoreboard_service.person_items(
            user, period, group_key, int(only_failed or 0)))
    except frappe.PermissionError as e:
        return _fail(str(e))


@frappe.whitelist()
def department_board(department=None, period=None):
    return _ok(scoreboard_service.department_board(department, period))


@frappe.whitelist()
def scope():
    """UI can biet nguoi nay duoc thay den dau TRUOC khi ve tab, de khong ve mot
    tab phong ban rong roi de nguoi ta tuong he thong hong."""
    s, depts = permissions.get_scope()
    return _ok({"scope": s, "departments": depts,
                "can_adjust": permissions.can_adjust(),
                "period": scoreboard_service.current_period()})


@frappe.whitelist()
def adjust(obligation, action, reason, new_due_at=None,
           source_doctype=None, source_name=None):
    """Sua diem mot dau viec - luon de lai dau vet."""
    if not permissions.can_adjust():
        return _fail(_("Chi HR Manager hoac System Manager duoc dieu chinh diem SLA."))
    if action not in ALL_ADJUSTMENTS:
        return _fail(_("Hanh dong khong hop le."))
    # Kiem tra TRUOC khi cham vao du lieu. Neu de ban ghi nhat ky validate sau,
    # thi mot lan goi thieu ly do se: doi xong diem -> nhat ky nem loi -> API
    # bao that bai -> nhung diem DA doi va khong co dau vet nao. Mot diem doi ma
    # khong ai ky ten la thu ca he thong nay duoc dung de ngan.
    if not (reason or "").strip():
        return _fail(_("Phai ghi ly do dieu chinh."))
    if action == ADJ_EXTEND_DUE and not new_due_at:
        return _fail(_("Hanh dong gia han can han moi."))
    try:
        return _ok(_apply_adjustment(obligation, action, reason, new_due_at,
                                     source_doctype, source_name))
    except Exception as e:
        frappe.log_error(title="sla.adjust", message=frappe.get_traceback())
        return _fail(str(e))


def _apply_adjustment(obligation, action, reason, new_due_at,
                      source_doctype, source_name):
    """Ghi NHAT KY TRUOC, doi diem SAU.

    Thu tu nay la co y. Nhat ky la thu co the tu choi (ly do rong, ban ghi bat
    bien); diem la thu khong the lay lai neu doi roi ma nhat ky hong. Ghi nhat
    ky truoc nghia la: khong bao gio co mot diem doi ma khong co dong giai thich
    di kem - cung lam la co mot dong nhat ky thua neu buoc sau hong, va mot dong
    thua thi doi chieu duoc, con mot diem doi lang le thi khong.
    """
    prev = frappe.db.get_value(DT_OBLIGATION, obligation, "status")
    if not prev:
        frappe.throw(_("Khong tim thay nghia vu."))
    log = frappe.get_doc({
        "doctype": DT_ADJUSTMENT, "obligation": obligation, "action": action,
        "reason": reason, "new_due_at": new_due_at, "previous_status": prev,
        "resulting_status": prev, "source_doctype": source_doctype,
        "source_name": source_name,
    })
    log.insert(ignore_permissions=True)
    if action == ADJ_EXCLUDE:
        obligation_service.exclude_obligation(obligation, reason)
    elif action == ADJ_MARK_MET:
        frappe.db.set_value(DT_OBLIGATION, obligation,
                            {"status": STATUS_MET, "late_seconds": 0, "is_breached": 0},
                            update_modified=False)
    elif action == ADJ_MARK_MISSED:
        frappe.db.set_value(DT_OBLIGATION, obligation,
                            {"status": STATUS_MISSED, "is_breached": 0},
                            update_modified=False)
    elif action == ADJ_RESTORE:
        frappe.db.set_value(DT_OBLIGATION, obligation,
                            {"status": STATUS_OPEN, "closed_at": None,
                             "excluded_reason": None, "late_seconds": 0},
                            update_modified=False)
    elif action == ADJ_EXTEND_DUE:
        frappe.db.set_value(DT_OBLIGATION, obligation, {"due_at": new_due_at},
                            update_modified=False)
    after = frappe.db.get_value(DT_OBLIGATION, obligation, "status")
    # `resulting_status` la o duy nhat cua ban ghi nhat ky duoc phep ghi sau khi
    # tao - ban ghi la bat bien voi nguoi dung, khong bat bien voi buoc dong so
    # cua chinh no. Ghi thang qua db de khong dung phai `validate` chan sua.
    frappe.db.set_value(DT_ADJUSTMENT, log.name, {"resulting_status": after},
                        update_modified=False)
    frappe.db.set_value(DT_OBLIGATION, obligation, {"adjusted": 1}, update_modified=False)
    return {"obligation": obligation, "from": prev, "to": after}
