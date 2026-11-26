# Copyright (c) 2026, eCentric and contributors
"""GAN PHIEU DUYET vao o dinh kem (Dot 0 quy trinh nhan su, Hoan chot 22/11/2026).

Dung mot phieu da duyet (vd Phe duyet dot xuat cua CEO) lam CHUNG TU cho mot phieu khac thay vi
anh chup. Chi luu LIEN KET (`EC Approval Link`: phieu chu <-> EC Approval Request duoc gan),
khong chep noi dung.

Ai gan / go duoc: NGUOI DANG GIU phieu chu - nguoi gui khi phieu con nhap hoac "Can bo sung";
nguoi duyet dang Pending o cap hien tai / chu viec xu ly (CUNG luat `add_file.holder_stage`).
Go: nguoi da gan (hoac System Manager) khi phieu chu con sua duoc.

Phieu gan la RIENG TU (privacy.is_private_type):
  * nguoi gan PHAI la nguoi gui phieu do (hoac System Manager);
  * BAT BUOC chon ro co cho nguoi duyet phieu chu doc hay khong (khong co mac dinh ngam);
  * cho doc -> moi nguoi duyet / nguoi xu ly / nguoi gui cua phieu chu duoc XEM noi dung va TAI
    TEP cua DUNG phieu do: dong `EC Approval Link Grant` (permissions.can_view_request doc no) +
    DocShare doc tren chung tu nghiep vu cua phieu gan (cong tep cua Frappe doc DocShare). Moi
    lan ho mo phieu do -> EC Approval Access Log (privacy.note_access). Go gan -> thu hoi ca hai
    (chi xoa DocShare DO GRANT TAO RA).
  * khong cho doc -> chip chi hien ma + "Phieu rieng tu" + trang thai.

Chip (nhan an toan, MOT ham `_label` cho moi duong ra): ma phieu, tieu de (an voi phieu rieng tu
nguoi xem khong duoc mo), trang thai song, "da gan vao N phieu khac" (chi dem), canh bao do khi
phieu gan bi Tu choi / Huy. Gui phieu chu khi co phieu gan bi Tu choi / Huy ma chua ghi ly do ->
chan (`assert_host_submittable`).
Moi lan gan / go / ghi ly do -> EC Approval Action tren phieu chu (neu da gui) va tren phieu gan.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

LINK_DT = "EC Approval Link"
GRANT_DT = "EC Approval Link Grant"
_REQ = "EC Approval Request"
MAX_LINKS = 20
BAD_STATUSES = ("Rejected", "Cancelled")
_STATUS_VI = {"Pending": "Đang phê duyệt", "Information Required": "Cần bổ sung",
              "Approved": "Đã duyệt", "Rejected": "Bị từ chối", "Cancelled": "Đã hủy"}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _engine():
    from ecentric_workspace.approval_center.shared.workflow import transitions
    return transitions


def _privacy():
    from ecentric_workspace.approval_center.shared.workflow import privacy
    return privacy


def _is_sm(user):
    return "System Manager" in frappe.get_roles(user)


def _definition_for(host_doctype):
    from ecentric_workspace.approval_center.shared.registry import get_definition_for_doctype
    try:
        return get_definition_for_doctype(host_doctype)
    except KeyError:
        frappe.throw(_("Loại phiếu {0} không hỗ trợ gắn phiếu duyệt.").format(host_doctype))


def _host(host_doctype, host_name):
    from ecentric_workspace.approval_center.shared.requests import capabilities
    definition = _definition_for(host_doctype)
    doc = frappe.get_doc(definition.business_doctype, host_name)
    req = capabilities.approval_request_for(definition, host_name)
    return definition, doc, req


def _req_row(name):
    return frappe.db.get_value(_REQ, name, ["name", "approval_type", "approval_status",
                                            "requested_by", "reference_doctype",
                                            "reference_name"], as_dict=True)


def can_view_target(user, row):
    """Luat xem chuan cua engine cho phieu GAN (kem duong grant cua chinh tinh nang nay)."""
    from ecentric_workspace.approval_center.shared.workflow.permissions import can_view_request
    if not row:
        return False
    meta = frappe.get_meta(row.reference_doctype)
    owner = (frappe.db.get_value(row.reference_doctype, row.reference_name, "fulfillment_owner")
             if meta.has_field("fulfillment_owner") else None)
    return bool(can_view_request(row.name, user, business_doctype=row.reference_doctype,
                                 requested_by=row.requested_by, fulfillment_owner=owner,
                                 approval_type=row.approval_type,
                                 business_name=row.reference_name))


def can_edit_links(user, business, request):
    """Nguoi DANG GIU phieu chu (xem docstring module)."""
    if not user or user == "Guest":
        return False
    requester = getattr(business, "requested_by", None) or business.get("requested_by")
    if request is None:
        return requester == user
    if request.get("approval_status") == "Information Required":
        return requester == user
    from ecentric_workspace.approval_center.shared.requests import add_file
    return bool(add_file.holder_stage(user, business, request))


def _host_viewer_ok(user, definition, business, request):
    from ecentric_workspace.approval_center.shared.requests import capabilities
    return capabilities.can_view(user, business, request)


def _active_links(host_doctype, host_name):
    return frappe.get_all(LINK_DT, filters={"host_doctype": host_doctype, "host_name": host_name,
                                            "active": 1},
                          fields=["name", "target_request", "share_to_host_approvers",
                                  "added_by", "added_at", "override_reason", "host_request"],
                          order_by="creation asc") or []


def _used_elsewhere(target_request, host_doctype, host_name):
    rows = frappe.get_all(LINK_DT, filters={"target_request": target_request, "active": 1},
                          fields=["host_doctype", "host_name"]) or []
    return len({(r.host_doctype, r.host_name) for r in rows
                if (r.host_doctype, r.host_name) != (host_doctype, host_name)})


def _label(row, viewer, link=None, host=None):
    """NHAN AN TOAN cho mot phieu gan - duong DUY NHAT dua thong tin phieu gan ra ngoai."""
    priv = _privacy().is_private_type(row.approval_type)
    can_open = can_view_target(viewer, row)
    title = None
    if can_open or not priv:
        title = _engine().request_label(row.reference_doctype, row.reference_name,
                                        row.approval_type)
    route = frappe.db.get_value("EC Approval Type", row.approval_type, "route") if can_open else None
    out = {
        "request": row.name,
        "code": row.reference_name,
        "type_title": frappe.db.get_value("EC Approval Type", row.approval_type,
                                          "approval_title") or row.approval_type,
        "title": title,
        "status": row.approval_status,
        "status_label": _STATUS_VI.get(row.approval_status, row.approval_status),
        "private": bool(priv),
        "can_open": bool(can_open),
        "detail_url": ("/" + route.lstrip("/") + "?id=" + row.reference_name) if route else None,
        "bad": row.approval_status in BAD_STATUSES,
    }
    if link is not None:
        out.update({
            "link": link.name,
            "shared": bool(link.share_to_host_approvers),
            "added_by": link.added_by,
            "override_reason": link.override_reason or "",
            "can_unlink": False,
        })
    if host is not None:
        out["used_elsewhere"] = _used_elsewhere(row.name, host[0], host[1])
    return out


def links_for_host(host_doctype, host_name, viewer=None, can_edit=False):
    """Chip cua mot phieu chu cho `viewer` (nguoi goi da duoc kiem quyen xem phieu chu)."""
    viewer = viewer or frappe.session.user
    out = []
    for link in _active_links(host_doctype, host_name):
        row = _req_row(link.target_request)
        if not row:
            continue
        lab = _label(row, viewer, link, host=(host_doctype, host_name))
        lab["can_unlink"] = bool(can_edit and (link.added_by == viewer or _is_sm(viewer)))
        out.append(lab)
    return out


def capability(user, business, request):
    """Khoi cho capabilities.derive: chip + co gan duoc khong. Loi -> rong (khong lam vo trang)."""
    try:
        can = can_edit_links(user, business, request)
        chips = links_for_host(business.doctype, business.name, user, can_edit=can)
        return {"approval_links": chips, "can_link_approval": bool(can),
                "approval_link_host": {"doctype": business.doctype, "name": business.name}}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "approval_links.capability")
        return {"approval_links": [], "can_link_approval": False, "approval_link_host": None}


# --------------------------------------------------------------------------- #
# audit
# --------------------------------------------------------------------------- #
def _audit(host_request, target_request, action, host_comment, target_comment, actor):
    eng = _engine()
    if host_request:
        eng.log_action(host_request, action, actor, comment=host_comment)
    if target_request:
        eng.log_action(target_request, action, actor, comment=target_comment)


def _who(user):
    return frappe.db.get_value("User", user, "full_name") or user


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def search(host_doctype, host_name, q=None, box=None, limit=20):
    """Phieu `user` duoc xem (CUNG luat tab "Tat ca" - scope_predicate, phieu rieng tu chi khi o
    trong luong), tru chinh phieu chu. box: mine | received | None."""
    from ecentric_workspace.approval_center.reporting import scope as _scope
    from ecentric_workspace.approval_center.reporting import queries as _q
    user = frappe.session.user
    definition, doc, req = _host(host_doctype, host_name)
    if not can_edit_links(user, doc, req):
        frappe.throw(_("Chỉ người đang giữ phiếu mới gắn được phiếu duyệt."), frappe.PermissionError)
    filters = {}
    if box == "mine":
        filters.update({"box": "sent", "_me": user})
    elif box == "received":
        filters.update({"box": "received", "_me": user})
    scope = _scope.resolve_scope(user)
    rows = _q.fetch_requests_page(scope, filters, 0, int(limit or 20) + 1,
                                  search=(q or "").strip() or None) or []
    have = {l.target_request for l in _active_links(host_doctype, host_name)}
    out = []
    for r in rows:
        if req and r.get("name") == req.name:
            continue
        row = _req_row(r.get("name"))
        if not row or row.reference_doctype == host_doctype and row.reference_name == host_name:
            continue
        lab = _label(row, user, host=(host_doctype, host_name))
        lab["already_linked"] = row.name in have
        lab["needs_share_choice"] = lab["private"]
        lab["can_attach"] = (not lab["private"]) or row.requested_by == user or _is_sm(user)
        out.append(lab)
        if len(out) >= int(limit or 20):
            break
    return {"rows": out}


def _parse_share(share):
    if share in (None, ""):
        return None
    s = str(share).strip().lower()
    if s in ("1", "true", "yes", "co"):
        return 1
    if s in ("0", "false", "no", "khong"):
        return 0
    return None


def link(host_doctype, host_name, target_request, share=None):
    user = frappe.session.user
    definition, doc, req = _host(host_doctype, host_name)
    if req:
        frappe.db.get_value(_REQ, req.name, "name", for_update=True)
    if not can_edit_links(user, doc, req):
        frappe.throw(_("Chỉ người đang giữ phiếu (người gửi khi nháp / cần bổ sung, người duyệt "
                       "ở bước hiện tại) mới gắn được phiếu duyệt."), frappe.PermissionError)
    row = _req_row(target_request)
    if not row or not can_view_target(user, row):
        # Mot cau chung: khong lo phieu do co ton tai hay khong.
        frappe.throw(_("Không tìm thấy phiếu duyệt hoặc bạn không có quyền xem."),
                     frappe.PermissionError)
    if (req and row.name == req.name) or (row.reference_doctype == host_doctype
                                          and row.reference_name == host_name):
        frappe.throw(_("Không gắn được chính phiếu này."))
    priv = _privacy().is_private_type(row.approval_type)
    share_v = _parse_share(share)
    if priv:
        if row.requested_by != user and not _is_sm(user):
            frappe.throw(_("Phiếu riêng tư chỉ người gửi phiếu đó mới gắn được."),
                         frappe.PermissionError)
        if share_v is None:
            frappe.throw(_("Phiếu {0} là phiếu riêng tư: chọn rõ có cho người duyệt phiếu này "
                           "đọc nội dung hay không.").format(row.reference_name))
    else:
        share_v = 0
    links = _active_links(host_doctype, host_name)
    for l in links:
        if l.target_request == row.name:
            return {"link": l.name, "duplicate": True,
                    "chips": links_for_host(host_doctype, host_name, user, True)}
    if len(links) >= MAX_LINKS:
        frappe.throw(_("Mỗi phiếu gắn tối đa {0} phiếu duyệt.").format(MAX_LINKS))
    new = frappe.get_doc({
        "doctype": LINK_DT, "host_doctype": host_doctype, "host_name": host_name,
        "host_request": req.name if req else None, "target_request": row.name,
        "share_to_host_approvers": share_v, "active": 1, "added_by": user,
        "added_at": now_datetime()}).insert(ignore_permissions=True)
    note = ""
    if priv:
        note = _(" (phiếu riêng tư, {0})").format(
            _("cho người duyệt phiếu này xem + tải tệp") if share_v else _("chỉ hiện mã + trạng thái"))
    _audit(req.name if req else None, row.name, "Approval Linked",
           _("{0} gắn phiếu duyệt {1}{2}").format(_who(user), row.reference_name, note),
           _("Được gắn làm chứng từ cho một phiếu khác{0}").format(
               _(" - người duyệt phiếu đó được xem") if share_v else ""), user)
    if share_v and req:
        sync_grants(new)
    return {"link": new.name, "duplicate": False,
            "chips": links_for_host(host_doctype, host_name, user, True)}


def unlink(link_name):
    user = frappe.session.user
    l = frappe.get_doc(LINK_DT, link_name)
    if not l.active:
        frappe.throw(_("Liên kết này đã được gỡ."))
    definition, doc, req = _host(l.host_doctype, l.host_name)
    if not (can_edit_links(user, doc, req) and (l.added_by == user or _is_sm(user))):
        frappe.throw(_("Chỉ người đã gắn (khi phiếu còn sửa được) mới gỡ được."),
                     frappe.PermissionError)
    frappe.db.set_value(LINK_DT, l.name, {"active": 0, "removed_by": user,
                                         "removed_at": now_datetime()})
    revoke_grants(l.name)
    code = frappe.db.get_value(_REQ, l.target_request, "reference_name") or l.target_request
    _audit(req.name if req else None, l.target_request, "Approval Unlinked",
           _("{0} gỡ phiếu duyệt {1}").format(_who(user), code),
           _("Đã gỡ khỏi phiếu khác - quyền xem đi kèm (nếu có) đã thu hồi"), user)
    return {"chips": links_for_host(l.host_doctype, l.host_name, user, True)}


def set_override_reason(link_name, reason):
    user = frappe.session.user
    reason = (reason or "").strip()
    if not reason:
        frappe.throw(_("Vui lòng nhập lý do."))
    l = frappe.get_doc(LINK_DT, link_name)
    definition, doc, req = _host(l.host_doctype, l.host_name)
    if not l.active or not can_edit_links(user, doc, req):
        frappe.throw(_("Chỉ người đang giữ phiếu mới ghi được lý do."), frappe.PermissionError)
    frappe.db.set_value(LINK_DT, l.name, "override_reason", reason[:1000])
    if req:
        code = frappe.db.get_value(_REQ, l.target_request, "reference_name") or l.target_request
        _engine().log_action(req.name, "Commented", user,
                             comment=_("Vẫn dùng phiếu {0} (bị từ chối/huỷ). Lý do: {1}")
                             .format(code, reason[:500]))
    return {"chips": links_for_host(l.host_doctype, l.host_name, user, True)}


def assert_host_submittable(host_doctype, host_name):
    """Gui / gui lai phieu chu: phieu gan bi Tu choi / Huy ma chua ghi ly do -> chan."""
    bad = []
    try:
        links = _active_links(host_doctype, host_name)
    except Exception:
        return
    for l in links:
        st = frappe.db.get_value(_REQ, l.target_request, ["approval_status", "reference_name"],
                                 as_dict=True) or {}
        if st.get("approval_status") in BAD_STATUSES and not (l.override_reason or "").strip():
            bad.append(st.get("reference_name") or l.target_request)
    if bad:
        # 26/11/2026: cau mo dau "Vui long ..." CO CHU Y - bo loc loi cua ~31 trang form (mapErr /
        # resubmitErr) chi giu nguyen thong diep server khi khop "Vui long|bat buoc|..."; cau cu bi thay
        # bang "Khong the gui lai yeu cau..." nen nguoi gui khong biet phai lam gi.
        frappe.throw(_("Vui lòng xử lý phiếu gắn kèm {0} trước khi gửi: phiếu đó đã bị từ chối / huỷ. "
                       "Ghi lý do vẫn dùng ở chip phiếu (người duyệt sẽ thấy) hoặc gỡ phiếu đó.")
                     .format(", ".join(bad)))


# --------------------------------------------------------------------------- #
# quyen doc phieu rieng tu duoc gan
# --------------------------------------------------------------------------- #
def _host_readers(host_request):
    """Nguoi duyet (moi cap, moi trang thai) + nguoi xu ly cau hinh + nguoi gui cua phieu chu."""
    from ecentric_workspace.approval_center.shared.workflow import permissions as _perm
    r = frappe.db.get_value(_REQ, host_request, ["requested_by", "approval_type"], as_dict=True)
    if not r:
        return []
    users = list(frappe.get_all("EC Approval Request Approver",
                                filters={"approval_request": host_request},
                                pluck="approver") or [])
    try:
        users += _perm.configured_fulfiller_users(r.approval_type)
    except Exception:
        pass
    users.append(r.requested_by)
    return [u for u in dict.fromkeys(users) if u and u not in ("Guest", "Administrator")]


def _share_exists(doctype, name, user):
    return frappe.db.get_value("DocShare", {"share_doctype": doctype, "share_name": name,
                                            "user": user}, "name")


def sync_grants(link_doc):
    """Cap quyen doc phieu gan (rieng tu, co cho doc) cho nguoi doc phieu chu con thieu."""
    if not (link_doc.active and link_doc.share_to_host_approvers and link_doc.host_request):
        return []
    row = _req_row(link_doc.target_request)
    if not row or not _privacy().is_private_type(row.approval_type):
        return []
    have = set(frappe.get_all(GRANT_DT, filters={"approval_link": link_doc.name, "active": 1},
                              pluck="user") or [])
    added = []
    for u in _host_readers(link_doc.host_request):
        if u in have:
            continue
        existed = bool(_share_exists(row.reference_doctype, row.reference_name, u))
        if not existed:
            _engine()._engine_grant_read(row.reference_doctype, row.reference_name, u)
        frappe.get_doc({"doctype": GRANT_DT, "approval_link": link_doc.name,
                        "target_request": row.name, "user": u,
                        "created_share": 0 if existed else 1, "active": 1,
                        "granted_at": now_datetime()}).insert(ignore_permissions=True)
        added.append(u)
    return added


def revoke_grants(link_name):
    """Thu hoi moi grant cua mot lien ket. Chi xoa DocShare do grant tao ra, va chi khi khong con
    grant song nao khac cho cung nguoi + cung phieu (khi do chuyen co `created_share` sang no)."""
    rows = frappe.get_all(GRANT_DT, filters={"approval_link": link_name, "active": 1},
                          fields=["name", "user", "target_request", "created_share"]) or []
    for g in rows:
        frappe.db.set_value(GRANT_DT, g.name, {"active": 0, "revoked_at": now_datetime()})
        if not g.created_share:
            continue
        other = frappe.get_all(GRANT_DT, filters={"target_request": g.target_request,
                                                  "user": g.user, "active": 1},
                               pluck="name", limit_page_length=1)
        if other:
            frappe.db.set_value(GRANT_DT, other[0], "created_share", 1)
            continue
        row = _req_row(g.target_request)
        if not row:
            continue
        sh = _share_exists(row.reference_doctype, row.reference_name, g.user)
        if sh:
            frappe.delete_doc("DocShare", sh, ignore_permissions=True, force=True)
    return len(rows)


def on_host_snapshot(req):
    """Engine goi sau build_snapshot / chuyen nguoi duyet: gan host_request, cap quyen con thieu.
    Khong bao gio nem."""
    try:
        for l in frappe.get_all(LINK_DT, filters={"host_doctype": req.reference_doctype,
                                                  "host_name": req.reference_name, "active": 1},
                                pluck="name") or []:
            doc = frappe.get_doc(LINK_DT, l)
            if not doc.host_request:
                frappe.db.set_value(LINK_DT, doc.name, "host_request", req.name)
                doc.host_request = req.name
            sync_grants(doc)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "approval_links.on_host_snapshot")
