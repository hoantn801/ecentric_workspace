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


def is_fulfiller_participant(process_names, user):
    """`user` co phai Fulfiller cua mot trong cac process nay khong - theo dong User HOAC dong
    Role (user mang role do). Truoc 07/09 chi xet dong User, nen Fulfiller cau hinh theo Role
    (Payment Request: ca phong Finance = Role EC Finance) khong bao gio duoc coi la du dieu
    kien: khong thay hang cho, Nhac viec khong xep, chi nhan viec duoc nho ToDo. Cung mot
    ham cho permissions va transitions de hai cho khong lech nhau."""
    names = [n for n in (process_names or []) if n]
    if not names or not user:
        return False
    if frappe.db.exists("EC Approval Participant",
                        {"parent": ["in", names], "parenttype": "EC Approval Process",
                         "participant_purpose": "Fulfiller", "source_type": "User", "user": user}):
        return True
    roles = [r.role for r in frappe.get_all(
        "EC Approval Participant", fields=["role"],
        filters={"parent": ["in", names], "parenttype": "EC Approval Process",
                 "participant_purpose": "Fulfiller", "source_type": "Role",
                 "role": ["is", "set"]})]
    if not roles:
        return False
    return bool(set(roles) & set(frappe.get_roles(user)))


def fulfilled_approval_types(user):
    """LOAI phieu ma `user` la Fulfiller DUOC CAU HINH (dong User hoac dong Role) tren
    mot quy trinh dang Active. Tra list ma loai, da sap xep.

    Vi sao ham nay ton tai. `is_fulfiller_participant` tra loi "co/khong" cho mot tap
    quy trinh; trang bao cao lai can cau nguoc: "nguoi nay xu ly NHUNG LOAI nao" - de
    dua vao dieu kien loc. Hoi tung loai mot thi la 2 truy van x 27 loai cho moi lan mo
    trang. Nen dat o day, canh `is_fulfiller_participant`, dung DUNG bo loc do: hai cau
    hoi ve cung mot su that phai doc cung mot cho, neu khong thi mot ngay nao do chung
    lech nhau va khong ai biet (dung kieu lech 09/09: trang form coi chi Dan la nguoi
    xu ly, trang bao cao thi khong).
    """
    if not user or user == "Guest":
        return []
    procs = frappe.get_all("EC Approval Process", filters={"status": "Active"},
                           fields=["name", "approval_type"]) or []
    type_of = {p["name"]: p.get("approval_type") for p in procs}
    if not type_of:
        return []
    names = list(type_of)
    base = {"parent": ["in", names], "parenttype": "EC Approval Process",
            "participant_purpose": "Fulfiller"}
    hit = set()
    for r in frappe.get_all("EC Approval Participant", fields=["parent"],
                            filters=dict(base, source_type="User", user=user)):
        hit.add(type_of.get(r["parent"]))
    roles = set(frappe.get_roles(user))
    for r in frappe.get_all("EC Approval Participant", fields=["parent", "role"],
                            filters=dict(base, source_type="Role", role=["is", "set"])):
        if r.get("role") in roles:
            hit.add(type_of.get(r["parent"]))
    return sorted(t for t in hit if t)


def _is_configured_fulfiller(user, approval_type):
    """A configured Fulfiller participant (User or Role) on an Active process of approval_type."""
    if not approval_type:
        return False
    procs = frappe.get_all(
        "EC Approval Process",
        filters={"approval_type": approval_type, "status": "Active"},
        pluck="name") or []
    return is_fulfiller_participant(procs, user)


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


def configured_fulfiller_users(approval_type):
    """NHUNG AI la Fulfiller duoc cau hinh cua `approval_type` - da bung dong Role ra
    thanh nguoi that. Tra list email, da sap xep, chi nguoi con hoat dong.

    Vi sao ham nay ton tai. `is_fulfiller_participant` hoi "nguoi nay co phai khong";
    `fulfilled_approval_types` hoi "nguoi nay xu ly loai nao". Cho cap quyen DOC lai can
    cau thu ba: "loai nay do NHUNG AI xu ly" - vi DocShare la theo tung NGUOI, khong nhan
    role. Ca ba cau deu hoi ve mot su that, nen dat canh nhau va dung DUNG mot bo loc.
    Neu khong, mot ngay nao do chung lech nhau va khong ai biet - dung kieu lech 09/09
    (trang form coi chi Dan la nguoi xu ly, trang bao cao thi khong).
    """
    if not approval_type:
        return []
    procs = frappe.get_all(
        "EC Approval Process",
        filters={"approval_type": approval_type, "status": "Active"}, pluck="name") or []
    if not procs:
        return []
    base = {"parent": ["in", procs], "parenttype": "EC Approval Process",
            "participant_purpose": "Fulfiller"}
    # `["is", "set"]` chi la THU HEP o tang DB (do dong phai keo ve), khong phai lop bao
    # dam: hanh vi cua no doi theo phien ban Frappe. Dong `user` bo trong lot qua duoc thi
    # cung bi bo loc `enabled` ben duoi chan (khong co User nao ten rong), nen o day KHONG
    # them mot phep loc thu ba - da thu bo no va khong test nao chet, tuc no la code thua.
    # Dong `role` bo trong thi KHAC: no se khop voi cac dong `Has Role` co role rong, nen
    # phep loc `if r` ben duoi la that su can (da dot bien, test chet ngay).
    users = set(frappe.get_all("EC Approval Participant", pluck="user",
                               filters=dict(base, source_type="User", user=["is", "set"])) or [])
    roles = [r for r in (frappe.get_all("EC Approval Participant", pluck="role",
                                        filters=dict(base, source_type="Role",
                                                     role=["is", "set"])) or []) if r]
    if roles:
        users.update(frappe.get_all("Has Role", pluck="parent",
                                    filters={"role": ["in", roles], "parenttype": "User"}) or [])
    users.discard("Guest")
    users.discard(None)
    if not users:
        return []
    # Nguoi da nghi viec (disabled) khong duoc cap quyen doc ho so tien.
    live = frappe.get_all("User", pluck="name",
                          filters={"name": ["in", list(users)], "enabled": 1}) or []
    return sorted(live)


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


