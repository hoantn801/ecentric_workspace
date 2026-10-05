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


# =========================================================================== trang /tai-lieu
LIST_FIELDS = ["name", "quality_procedure_name", "ec_doc_code", "ec_doc_type", "ec_department",
               "ec_doc_state", "ec_current_version", "ec_effective_from", "ec_next_review",
               "ec_draft_version", "ec_change_kind", "ec_change_summary", "ec_drafter", "ec_dept_head",
               "ec_company_wide", "ec_parent_doc", "modified"]
REV_FIELDS = ["parent", "idx", "version", "change_kind", "status", "effective_from", "effective_to",
              "summary", "approver", "pdf", "docx", "steps_json", "source"]


def list_docs():
    """Moi tai lieu NGUOI NAY doc duoc - frappe.get_list ap permission_query_conditions."""
    return frappe.get_list(C.QP, fields=LIST_FIELDS, order_by="ec_doc_code asc", limit_page_length=0)


def revisions(names, effective_only=False):
    if not names:
        return []
    filters = {"parent": ["in", list(names)], "parenttype": C.QP}
    if effective_only:
        filters["status"] = C.REV_EFFECTIVE
    return frappe.get_list(C.REVISION_DT, parent_doctype=C.QP, filters=filters, fields=REV_FIELDS,
                           order_by="idx asc", limit_page_length=0)


def exists(code):
    return bool(code) and bool(frappe.db.exists(C.QP, code))


def get_doc(code):
    """Tai lieu + kiem quyen doc. Khong co -> None; khong duoc doc -> frappe.PermissionError."""
    if not exists(code):
        return None
    doc = frappe.get_doc(C.QP, code)
    if not frappe.has_permission(C.QP, "read", doc=doc):
        raise frappe.PermissionError
    return doc


def transitions(doc):
    """Cac buoc NGUOI DANG DANG NHAP bam duoc o trang thai hien tai (role + dieu kien Workflow)."""
    from frappe.model.workflow import get_transitions
    try:
        return [{"action": t.action, "next_state": t.next_state} for t in get_transitions(doc)]
    except Exception:
        return []


def apply_action(doc, action):
    from frappe.model.workflow import apply_workflow
    return apply_workflow(doc.as_dict(), action)


def add_comment(doc_name, text):
    frappe.get_doc(C.QP, doc_name).add_comment("Comment", text)


def mark_seen(code, user, version):
    try:
        from ecentric_workspace.platform import read_receipt
        read_receipt.mark_seen(C.QP, code, user, version or "")
    except Exception:
        frappe.log_error(title="iso_docs.mark_seen")


def full_names(users):
    users = [u for u in set(users or ()) if u]
    if not users:
        return {}
    rows = frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"])
    return {r.name: r.full_name or r.name for r in rows}


def departments():
    return frappe.get_all("Department", filters={"is_group": 0}, pluck="name", order_by="lft asc",
                          limit_page_length=0)


def save_file(doc_name, filename, content):
    """Tep rieng tu dinh vao tai lieu: ai doc duoc tai lieu thi tai duoc tep (File.has_permission)."""
    f = frappe.get_doc({"doctype": "File", "file_name": filename, "attached_to_doctype": C.QP,
                        "attached_to_name": doc_name, "is_private": 1, "content": content})
    f.save()
    return f.file_url


def insert_doc(fields):
    scope = fields.pop("scope_departments", [])
    doc = frappe.get_doc(dict(fields, doctype=C.QP))
    doc.set("ec_scope_departments", [{"department": d} for d in scope])
    doc.insert()
    return doc


def update_draft(code, fields):
    doc = frappe.get_doc(C.QP, code)
    scope = fields.pop("scope_departments", None)
    revisions = fields.pop("ec_revisions", None)
    doc.update(fields)
    if revisions is not None:
        doc.set("ec_revisions", revisions)
    if scope is not None:
        doc.set("ec_scope_departments", [{"department": d} for d in scope])
    doc.save()
    return doc


def force_published(code, note):
    """CHI cho nhap tai lieu cu (legacy.import_one): dat thang trang thai "Ban hanh" - tai lieu da
    duyet ngoai ERP, khong di lai Workflow. Ghi Comment de con dau vet."""
    frappe.db.set_value(C.QP, code, C.STATE_FIELD, C.S_PUBLISHED, update_modified=False)
    add_comment(code, note)
