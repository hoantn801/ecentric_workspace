# Copyright (c) 2026, eCentric and contributors
"""Approval Engine -- canonical visibility / actionability service.

ONE definition of "who may view a governed request", shared by every consumer
so the permission rule is never duplicated:
  - the approval-center form APIs (``api/*.py`` ``_can_view``);
  - the Action Center feed (``action_center.feed._engine_link_state``), which
    normalizes engine-linked business documents and must gate the canonical
    Approval Center URL on the SAME rule (never a second, divergent definition).

The rule is the union previously encoded inline in the per-form ``_can_view`` /
``_is_fulfiller`` helpers: System Manager, the requester, any approver on the
request, the fulfillment owner, or an eligible fulfiller (a configured Fulfiller
on an Active process of the request's approval type, or a user holding an Open
ToDo on the business DocType).
"""
import frappe

#: request statuses that are still open/actionable (mirrors service.OPEN_STATUSES).
OPEN_STATUSES = ("Pending", "Information Required")


def is_system_manager(user=None):
    return "System Manager" in frappe.get_roles(user or frappe.session.user)


def _is_configured_fulfiller(user, approval_type):
    """A configured Fulfiller participant on an Active process of approval_type."""
    if not approval_type:
        return False
    procs = frappe.get_all(
        "EC Approval Process",
        filters={"approval_type": approval_type, "status": "Active"},
        pluck="name") or []
    for p in procs:
        if frappe.db.exists("EC Approval Participant",
                            {"parent": p, "parenttype": "EC Approval Process",
                             "participant_purpose": "Fulfiller", "user": user}):
            return True
    return False


def is_eligible_fulfiller(user, approval_type=None, business_doctype=None,
                          business_name=None):
    """System Manager, Fulfiller duoc cau hinh cua `approval_type`, hoac nguoi dang giu mot
    viec mo TREN CHINH PHIEU NAY.

    DUONG TODO PHAI GAN VOI MOT PHIEU CU THE (siet 01/09).
    ----------------------------------------------------------------------------------
    Truoc day dieu kien chi la "co mot ToDo mo tren LOAI phieu nay" - khong hoi la phieu
    nao. Hau qua: mot truong bo phan dang co DUNG MOT phieu cua nhan vien minh cho duyet
    thi trong ca khoang thoi gian do doc duoc MOI De nghi thanh toan cua toan cong ty:
    so tien, nguoi nhan, so tai khoan ngan hang cua phong khac. Chi can mot viec bat ky
    la mo ca loai.

    Hoan chot 01/09: khong chap nhan. Nhung phai siet DUNG CHO - hai duong con lai giu
    nguyen:
      * System Manager: nguyen ven;
      * Fulfiller duoc CAU HINH trong quy trinh (Ke toan...): nguyen ven theo LOAI, vi ho
        that su xu ly moi phieu loai do - do la vai tro, khong phai lo hong.
    Chi rieng duong "dang giu viec" moi bi buoc vao dung phieu.

    `business_name=None` giu nguyen hanh vi cu MOT CACH CO Y: mot so cho hoi cau "nguoi
    nay co the la nguoi xu ly loai phieu nay khong" khi chua co phieu cu the trong tay
    (vi du dung de quyet dinh co hien menu/bao cao hay khong). Nhung cho DOC MOT PHIEU thi
    luon truyen ten phieu vao - xem can_view_request.
    """
    if is_system_manager(user):
        return True
    if _is_configured_fulfiller(user, approval_type):
        return True
    if business_doctype:
        todo = {"reference_type": business_doctype, "allocated_to": user, "status": "Open"}
        if business_name:
            todo["reference_name"] = business_name
        if frappe.db.exists("ToDo", todo):
            return True
    return False


def is_eligible_fulfiller_without_todo(user=None, approval_type=None, fulfillment_owner=None):
    """Fulfillment ENTITLEMENT, decoupled from any ToDo (Phase 1b.3.1 hotfix).

    True for the fulfillment owner, a System Manager, or a configured Fulfiller
    participant on an Active process of ``approval_type``. Deliberately EXCLUDES
    the 'any Open ToDo on the DocType' path so that -- when the Action Center feed
    pairs this with the separate record-scoped Open-ToDo gate -- the SAME ToDo row
    can never establish BOTH permission (entitlement) and action existence. The
    existing ``is_eligible_fulfiller`` / ``can_fulfill`` keep their ToDo-inclusive
    behavior for the form APIs (not migrated in this hotfix)."""
    user = user or frappe.session.user
    if fulfillment_owner and fulfillment_owner == user:
        return True
    if is_system_manager(user):
        return True
    return _is_configured_fulfiller(user, approval_type)


def can_view_request(request_name, user=None, business_doctype=None,
                     requested_by=None, fulfillment_owner=None, approval_type=None,
                     business_name=None):
    """THE canonical Approval Engine visibility check.

    A user may view a governed request if they are a System Manager, the
    requester, any approver on the request, the fulfillment owner, or an
    eligible fulfiller. Inputs are primitives (already-loaded business fields +
    the linked request name) so BOTH the form APIs and the Action Center feed
    can call it without re-deriving anything.
    """
    user = user or frappe.session.user
    if is_system_manager(user):
        return True
    if requested_by and requested_by == user:
        return True
    if request_name and frappe.db.exists(
            "EC Approval Request Approver",
            {"approval_request": request_name, "approver": user}):
        return True
    if fulfillment_owner and fulfillment_owner == user:
        return True
    # Truyen ten phieu xuong: doc MOT phieu thi duong "dang giu viec" phai la viec TREN
    # CHINH PHIEU DO, khong phai mot viec bat ky cung loai.
    return is_eligible_fulfiller(user, approval_type, business_doctype, business_name)


def can_fulfill(user=None, business_doctype=None, fulfillment_owner=None, approval_type=None):
    """Canonical FULFILLMENT-action permission (Phase 1b.3.1). Distinct from
    can_view_request: only the fulfillment owner or an eligible fulfiller may act
    on a fulfillment stage -- a requester/approver who can merely VIEW the request
    must NOT receive the fulfillment action. Mirrors the form APIs'
    claim_fulfillment (_is_fulfiller) / complete_fulfillment (owner or SM) gates.
    """
    user = user or frappe.session.user
    if fulfillment_owner and fulfillment_owner == user:
        return True
    return is_eligible_fulfiller(user, approval_type, business_doctype)


def is_actionable(request_name, current_level, user=None, approval_status=None):
    """Canonical actionability check: the user is a Pending approver on the
    request's CURRENT level and the request is still open. Mirrors the approval
    APIs' ``_pending_row``."""
    if approval_status is not None and approval_status not in OPEN_STATUSES:
        return False
    if not request_name or not current_level:
        return False
    return bool(frappe.db.exists(
        "EC Approval Request Approver",
        {"approval_request": request_name, "level_no": current_level,
         "approver": user or frappe.session.user, "status": "Pending"}))


