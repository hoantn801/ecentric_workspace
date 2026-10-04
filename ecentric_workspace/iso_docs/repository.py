# Copyright (c) 2026, eCentric and contributors
"""Thu vien tai lieu ISO - MOI truy cap DB nam o day (service / permissions goi qua module nay)."""
import frappe

from ecentric_workspace.iso_docs import constants as C


def _memo(key, fn):
    """Nho trong MOT request (has_permission bi goi nhieu lan / trang)."""
    store = getattr(frappe.local, "ec_iso_docs_memo", None)
    if store is None:
        store = frappe.local.ec_iso_docs_memo = {}
    if key not in store:
        store[key] = fn()
    return store[key]


def session_user():
    return frappe.session.user


def today():
    return frappe.utils.getdate(frappe.utils.nowdate())


def roles(user):
    return _memo("roles:" + (user or ""), lambda: set(frappe.get_roles(user)))


def is_manager(user):
    if not user or user == "Guest":
        return False
    return user == "Administrator" or bool(roles(user) & set(C.MANAGER_ROLES))


def dept_head(department):
    """Truong bo phan = Department.manager_email (truong co tren site; khong co -> None)."""
    if not department or not frappe.get_meta("Department").has_field("manager_email"):
        return None
    return frappe.db.get_value("Department", department, "manager_email") or None


def state_before(doc):
    before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
    return before.get(C.STATE_FIELD) if before else None


def viewer(user):
    """Ho so Employee dang Active cua nguoi xem + vi tri phong ban tren cay (lft)."""
    if not user or user == "Guest":
        return None
    return _memo("viewer:" + user, lambda: _viewer(user))


def _viewer(user):
    rows = frappe.get_all("Employee", filters={"user_id": user, "status": "Active"},
                          fields=["name", "department"], limit=1)
    if not rows:
        return None
    dept = rows[0].department
    lft = frappe.db.get_value("Department", dept, "lft") if dept else None
    return {"employee": rows[0].name, "department": dept, "lft": lft}


def dept_ranges(departments):
    out = []
    for d in departments or ():
        r = frappe.db.get_value("Department", d, ["lft", "rgt"])
        out.append((r[0], r[1]) if r else (None, None))
    return out


def publish_announcement(doc_name, version, payload):
    """Qua service DUNG CHUNG cua popup trang chu (idempotent theo phien ban, nuot loi)."""
    from ecentric_workspace.home_today import announce_service
    return announce_service.publish_from_source(C.QP, doc_name, version, **payload)


def link_announcement(doc_name, version, announcement):
    """Ghi ten thong bao vao tai lieu + dong lich su. Loi o day cung khong chan ban hanh."""
    try:
        frappe.db.set_value(C.QP, doc_name, "ec_home_announcement", announcement,
                            update_modified=False)
        frappe.db.set_value(C.REVISION_DT, {"parent": doc_name, "parenttype": C.QP,
                                            "version": version},
                            "home_announcement", announcement, update_modified=False)
    except Exception:
        frappe.log_error(title="iso_docs.link_announcement")


def withdraw_announcements(doc_name):
    try:
        from ecentric_workspace.home_today import announce_service
        return announce_service.withdraw_source(C.QP, doc_name)
    except Exception:
        frappe.log_error(title="iso_docs.withdraw_announcements")
        return 0
