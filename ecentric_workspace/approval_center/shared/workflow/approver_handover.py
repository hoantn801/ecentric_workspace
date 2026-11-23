# Copyright (c) 2026, eCentric and contributors
"""Chuyen nguoi duyet DANG CHO khi nguoi duyet nghi viec / bi khoa (Dot 0 HR, 23/11/2026).

Truoc day: dong duyet chot luc nop phieu, nen khi nguoi duyet nghi viec (job 00:30 khoa tai
khoan) phieu nam im o mot tai khoan khong ai dang nhap. Duong duy nhat la quan tri "duyet thay".

Nay, ba cua vao cung mot luat (`handle_row`):
  1. doc_events User.on_update: tai khoan bi khoa (enabled 1 -> 0) -> chuyen ngay;
  2. job 00:45 (sau job khoa 00:30): quet moi dong Pending tren phieu dang mo cua nguoi da bi
     khoa / Employee "Left" - luoi an toan khi hook bi bo qua (db.set_value...);
  3. System Manager chuyen tay (`reassign_approver`, POST, bat buoc ly do).

Luat chon nguoi thay (khong ten nguoi, khong ten role nao viet cung):
  * cap con nguoi khac du dieu kien (cung nhom voi Each Group) -> chi bo nguoi cu;
  * dong kieu "Role: X" -> nhung nguoi KHAC dang giu role X;
  * dong khac (quan ly truc tiep, User, Reference ...) -> quan ly cua nguoi cu (reports_to);
  * van khong co -> nguoi du phong (fallback_user) cau hinh o cap do;
  * khong ai -> GIU NGUYEN, ghi Error Log de quan tri chuyen tay (khong de cap rong).
Nguoi thay khong bao gio la nguoi gui / doi tuong (chan tu duyet - engine kiem lai).
Moi thay doi ghi EC Approval Action "Reassigned" (xem transitions.reassign_pending_approver).
"""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.workflow import transitions as engine

_APPROVER = "EC Approval Request Approver"
_OPEN = ("Pending", "Information Required")
SYSTEM_ACTOR = "Administrator"


def _active(u):
    return engine._is_active_system_user(u)


def _role_holders(role):
    users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"},
                           pluck="parent", distinct=True) or []
    return [u for u in sorted(set(users)) if _active(u)]


def _config_fallbacks(request_level):
    """fallback_user cua cac dong Approver o cap cau hinh ma cap tren phieu sinh ra tu do."""
    try:
        src = frappe.db.get_value("EC Approval Request Level", request_level, "source_process_level")
        if not src:
            return []
        lvl = frappe.get_doc("EC Approval Level", src)
    except Exception:
        return []
    out = []
    for p in (lvl.participants or []):
        fb = p.get("fallback_user")
        if p.participant_purpose == "Approver" and fb and fb not in out and _active(fb):
            out.append(fb)
    return out


def candidates_for(row, old_user):
    """Danh sach nguoi thay cho mot dong (chua loai nguoi gui / doi tuong - engine loai)."""
    role = engine.role_of(row.get("source"))
    if role:
        c = [u for u in _role_holders(role) if u != old_user]
        if c:
            return c
    mgr = engine._manager_user_of_employee(old_user)
    if mgr and mgr != old_user and _active(mgr):
        return [mgr]
    return [u for u in _config_fallbacks(row.get("request_level")) if u != old_user]


def _others_still_cover(row, level_rows, mode, minimum):
    """Cap van du nguoi neu bo `row`? (khong can nguoi thay)."""
    others = [x for x in level_rows
              if x.name != row.name and x.status == "Pending" and _active(x.approver)
              and engine.row_still_eligible(x.source, x.approver)]
    if mode == engine.EACH_GROUP:
        mine = row.get("participant_group")
        if any(x.participant_group == mine and x.status == "Approved" for x in level_rows):
            return True
        return any(x.participant_group == mine for x in others)
    if mode == "Minimum Count":
        approved = sum(1 for x in level_rows if x.status == "Approved")
        return approved + len(others) >= int(minimum or 0) > 0
    return bool(others)


def handle_row(row_name, old_user, reason, actor=SYSTEM_ACTOR):
    """-> "skipped" | "reassigned" | "manual" | "noop". Khong nem (loi -> Error Log, "manual")."""
    try:
        row = frappe.db.get_value(_APPROVER, row_name,
                                  ["name", "approval_request", "request_level", "level_no",
                                   "approver", "source", "participant_group", "status"],
                                  as_dict=True)
        if not row or row.status != "Pending" or row.approver != old_user:
            return "noop"
        st = frappe.db.get_value("EC Approval Request", row.approval_request, "approval_status")
        if st not in _OPEN:
            return "noop"
        lv = frappe.db.get_value("EC Approval Request Level", row.request_level,
                                 ["approval_mode", "minimum_approvals"], as_dict=True) or {}
        level_rows = frappe.get_all(_APPROVER, filters={"approval_request": row.approval_request,
                                                        "level_no": row.level_no},
                                    fields=["name", "approver", "source", "status",
                                            "participant_group"]) or []
        if _others_still_cover(row, level_rows, lv.get("approval_mode"),
                               lv.get("minimum_approvals")):
            engine.reassign_pending_approver(row_name, [], actor=actor, reason=reason)
            return "skipped"
        cands = candidates_for(row, old_user)
        res = engine.reassign_pending_approver(row_name, cands, actor=actor, reason=reason,
                                               require_target=True) if cands else None
        if res and res.get("added"):
            return "reassigned"
        frappe.log_error(title="Chuyen nguoi duyet: can xu ly tay %s" % row.approval_request,
                         message="Cap %s cua %s chi con %s (%s) va khong tim duoc nguoi thay. "
                                 "System Manager dung reassign_approver hoac duyet thay."
                                 % (row.level_no, row.approval_request, old_user, reason))
        return "manual"
    except Exception:
        frappe.log_error(frappe.get_traceback(), "approver_handover.handle_row %s" % row_name)
        return "manual"


def handle_inactive_user(user, reason):
    """Moi dong Pending cua `user` tren phieu dang mo -> handle_row. Tra dict dem ket qua."""
    out = {}
    if not user:
        return out
    rows = frappe.get_all(_APPROVER, filters={"approver": user, "status": "Pending"},
                          pluck="name") or []
    for n in rows:
        r = handle_row(n, user, reason)
        out[r] = out.get(r, 0) + 1
    return out


# --------------------------------------------------------------------------- #
# Cua vao 1: doc_events User.on_update
# --------------------------------------------------------------------------- #
def on_user_update(doc, method=None):
    """Tai khoan vua bi khoa -> chuyen cac dong duyet dang cho. Nuot moi loi (hook chay trong
    giao dich luu User - loi lot ra se lam hong chinh viec khoa tai khoan)."""
    try:
        before = doc.get_doc_before_save()
        if not before or not before.get("enabled") or doc.get("enabled"):
            return
        handle_inactive_user(doc.name, _("Tài khoản người duyệt đã bị khoá"))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "approver_handover.on_user_update")


# --------------------------------------------------------------------------- #
# Cua vao 2: job hang ngay 00:45
# --------------------------------------------------------------------------- #
def _inactive_pending_approvers():
    rows = frappe.db.sql(
        """SELECT DISTINCT ra.approver AS u
           FROM `tabEC Approval Request Approver` ra
           JOIN `tabEC Approval Request` r ON r.name = ra.approval_request
           WHERE ra.status = 'Pending' AND r.approval_status IN ('Pending', 'Information Required')""",
        as_dict=True) or []
    out = []
    for r in rows:
        u = r.get("u")
        if not u or u in ("Guest", "Administrator"):
            continue
        if not _active(u):
            out.append((u, _("Tài khoản người duyệt đã bị khoá")))
            continue
        emp = frappe.db.get_value("Employee", {"user_id": u}, ["status"], as_dict=True)
        if emp and emp.get("status") == "Left":
            out.append((u, _("Người duyệt đã nghỉ việc")))
    return out


def sweep():
    """Job 00:45. Tat khan cap: site_config `ec_approver_handover_disabled: 1`."""
    if frappe.conf.get("ec_approver_handover_disabled"):
        return {"disabled": True}
    tong = {}
    for user, why in _inactive_pending_approvers():
        for k, v in handle_inactive_user(user, why).items():
            tong[k] = tong.get(k, 0) + v
        frappe.db.commit()
    if tong:
        frappe.logger("approval_center").info("approver_handover.sweep %s" % tong)
    return tong


# --------------------------------------------------------------------------- #
# Cua vao 3: System Manager chuyen tay
# --------------------------------------------------------------------------- #
@frappe.whitelist(methods=["POST"])
def reassign_approver(request_name, old_user, new_user, reason=None):
    """System Manager chuyen dong duyet Pending cua `old_user` (cap hien tai hoac cap sau) sang
    `new_user`. Bat buoc ly do. Nguoi moi khong duoc la nguoi gui / doi tuong."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Chỉ System Manager được chuyển người duyệt."), frappe.PermissionError)
    if not (reason or "").strip():
        frappe.throw(_("Bắt buộc nhập lý do chuyển người duyệt."))
    rows = frappe.get_all(_APPROVER, filters={"approval_request": request_name,
                                              "approver": old_user, "status": "Pending"},
                          fields=["name", "level_no"], order_by="level_no asc") or []
    if not rows:
        frappe.throw(_("{0} không có dòng duyệt đang chờ trên phiếu này.").format(old_user))
    res = engine.reassign_pending_approver(rows[0]["name"], [new_user],
                                           actor=frappe.session.user, reason=reason,
                                           require_target=True)
    if not res.get("added"):
        frappe.throw(_("Không chuyển được sang {0} (người không hoạt động, là người gửi / đối "
                       "tượng của phiếu, hoặc đã có trong bước này).").format(new_user))
    return res
