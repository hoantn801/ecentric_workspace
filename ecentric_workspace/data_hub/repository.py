# Copyright (c) 2026, eCentric and contributors
"""Trung tam Du lieu - NOI DUY NHAT doc/ghi DB. Khong co quy tac nghiep vu o day.

QUYEN: moi DocType cua module chi System Manager co quyen Desk (khong co duong /app, /api/resource
nao cho nhan vien ghi). Moi doc / ghi di qua service / ops_service, va service da kiem quyen TRUOC
khi goi vao day - nen ham o day dung ignore_permissions.
"""
from contextlib import contextmanager

import frappe

from ecentric_workspace.data_hub import constants as C

TICKET_FIELDS = [
    "name", "kind", "title", "request_type", "description", "requester", "requester_department",
    "data_used", "reference_link", "proposed_priority", "urgent_reason", "priority", "priority_confirmed_by",
    "status", "assignee", "start_date", "due_date", "original_due_date", "intake_due_date", "sla_days",
    "rule_version", "due_change_count", "accepted_at", "accepted_by", "done_at", "closed_at", "acceptance",
    "reject_count", "paused_since", "paused_seconds", "paused_days", "pm_task", "output_link",
    "cancel_reason", "legacy_ref", "platforms", "channels", "method", "availability_rows",
    "reminded_review_on", "creation", "modified",
]
LIST_FIELDS = [
    "name", "kind", "title", "request_type", "requester", "requester_department", "proposed_priority",
    "priority", "status", "assignee", "start_date", "due_date", "original_due_date", "intake_due_date",
    "sla_days", "due_change_count", "done_at", "closed_at", "acceptance", "pm_task", "creation", "modified",
    "paused_since", "urgent_reason",
]


def _memo(key, fn):
    """Nho trong MOT request."""
    store = getattr(frappe.local, "ec_data_hub_memo", None)
    if store is None:
        store = {}
        try:
            frappe.local.ec_data_hub_memo = store
        except Exception:
            return fn()
    if key not in store:
        store[key] = fn()
    return store[key]


@contextmanager
def as_system():
    """Ghi duoi SYSTEM_USER roi tra lai DUNG phien cu (cung cach voi feedback.repository.as_system:
    frappe.set_user() doi ca session.sid / session.data / form_dict cua request)."""
    local = frappe.local
    saved = dict(local.session)
    saved_form = getattr(local, "form_dict", None)
    try:
        frappe.set_user(C.SYSTEM_USER)
        yield
    finally:
        local.session.clear()
        local.session.update(saved)
        if saved_form is not None:
            local.form_dict = saved_form
        local.role_permissions = {}
        local.user_perms = None
        local.new_doc_templates = {}
        local.jenv = None


# ------------------------------------------------------------------ nguoi dung -----------
def roles(user):
    return _memo("roles:" + (user or ""), lambda: set(frappe.get_roles(user)))


def is_admin(user):
    return bool(user) and user != "Guest" and C.ADMIN_ROLE in roles(user)


def employee(user):
    """Ho so Employee dang Active -> {name, department} hoac None."""
    if not user or user == "Guest":
        return None
    return _memo("emp:" + user, lambda: _employee(user))


def _employee(user):
    rows = frappe.get_all("Employee", filters={"user_id": user, "status": "Active"},
                          fields=["name", "department"], limit=1)
    return {"name": rows[0].name, "department": rows[0].department} if rows else None


def full_names(users):
    users = [u for u in set(users or ()) if u]
    if not users:
        return {}
    return {r.name: r.full_name or r.name
            for r in frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"],
                                    limit_page_length=0)}


def enabled_users(users):
    users = [u for u in set(users or ()) if u]
    if not users:
        return set()
    return set(frappe.get_all("User", filters={"name": ["in", users], "enabled": 1}, pluck="name",
                              limit_page_length=0))


def users_with_role(role):
    """Tai khoan dang bat co role nay (bo Administrator / Guest)."""
    def load():
        users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent",
                               limit_page_length=0)
        users = [u for u in set(users) if u not in ("Administrator", "Guest")]
        return sorted(enabled_users(users))
    return _memo("role_users:" + role, load)


def people(q, limit=10):
    """Nhan vien Active co tai khoan, ten / email khop q (o @ten trong tin nhan)."""
    q = (q or "").strip()
    filters = {"status": "Active", "user_id": ["is", "set"]}
    or_filters = None
    if q:
        like = "%" + q.replace("%", "") + "%"
        or_filters = {"employee_name": ["like", like], "user_id": ["like", like]}
    rows = frappe.get_all("Employee", filters=filters, or_filters=or_filters,
                          fields=["user_id", "employee_name", "department"], order_by="employee_name asc",
                          limit_page_length=limit)
    return [{"user": r.user_id, "name": r.employee_name or r.user_id, "dept": r.department or ""} for r in rows]


# ------------------------------------------------------------------ cau hinh -------------
def settings():
    def load():
        s = frappe.get_cached_doc(C.SETTINGS_DT) if frappe.db.exists("DocType", C.SETTINGS_DT) else None
        out = {"data_team_role": C.DEFAULT_DATA_TEAM_ROLE, "rule_approver": "", "pm_project": "",
               "pm_sync_enabled": 1, "active_rule_set": ""}
        if s:
            for k in out:
                v = s.get(k)
                if v not in (None, ""):
                    out[k] = v
        return out
    return _memo("settings", load)


def rule_set(name=None):
    """Bo quy tac (dict + items). name trong -> bo dang ap dung (Settings, khong co thi ban moi nhat
    co trang thai Dang ap dung)."""
    def load():
        n = name or settings().get("active_rule_set")
        if not n or not frappe.db.exists(C.RULE_DT, n):
            rows = frappe.get_all(C.RULE_DT, filters={"status": C.RULE_ACTIVE}, pluck="name",
                                  order_by="version_no desc", limit=1)
            n = rows[0] if rows else None
        if not n:
            return None
        doc = frappe.get_doc(C.RULE_DT, n)
        d = doc.as_dict()
        d["items"] = [dict(i) for i in doc.get("items") or []]
        return d
    return _memo("rule_set:" + (name or ""), load)


def rule_history(limit=20):
    return [dict(r) for r in frappe.get_all(
        C.RULE_DT, fields=["name", "version_no", "status", "effective_from", "proposed_by", "decided_by",
                           "decided_at", "reason"], order_by="version_no desc", limit_page_length=limit)]


def holidays():
    """Ngay le cong ty (Holiday List mac dinh) - helper chung ngay_lam_viec."""
    def load():
        from ecentric_workspace.approval_center.shared.workflow import ngay_lam_viec
        return ngay_lam_viec.ngay_le_cong_ty()
    return _memo("holidays", load)


def is_off_today(user, day=None):
    from ecentric_workspace.approval_center.shared.workflow import ngay_lam_viec
    return ngay_lam_viec.la_ngay_nghi(user, day)


# ------------------------------------------------------------------ yeu cau: doc ----------
def get(code):
    if not code:
        return None
    rows = frappe.get_all(C.TICKET_DT, filters={"name": code}, fields=TICKET_FIELDS, limit=1)
    if not rows:
        return None
    t = dict(rows[0])
    t["followers"] = [dict(r) for r in frappe.get_all(
        C.FOLLOWER_DT, filters={"parent": code, "parenttype": C.TICKET_DT},
        fields=["name", "user", "added_by", "creation"], order_by="idx asc", limit_page_length=0)]
    t["attachments"] = [dict(r) for r in frappe.get_all(
        C.FILE_DT, filters={"parent": code, "parenttype": C.TICKET_DT},
        fields=["name", "file_url", "file_name", "file_size", "message", "uploaded_by", "creation"],
        order_by="idx asc", limit_page_length=0)]
    return t


def lock(code):
    """Khoa dong (SELECT ... FOR UPDATE) roi doc lai - hai nguoi bam "Nhan" cung luc thi nguoi sau
    thay trang thai moi."""
    if not code:
        return None
    frappe.db.sql("select name from `tabEC Data Ticket` where name = %s for update", (code,))
    return get(code)


def list_rows(filters=None, limit=0, fields=None, order_by="creation desc"):
    return [dict(r) for r in frappe.get_all(C.TICKET_DT, filters=filters or {}, fields=fields or LIST_FIELDS,
                                            order_by=order_by, limit_page_length=limit or 0)]


def open_rows():
    return list_rows({"status": ["in", list(C.OPEN)]})


def find_by_pm_task(task):
    if not task:
        return None
    return frappe.db.get_value(C.TICKET_DT, {"pm_task": task}, "name")


def sent_today(user, day):
    return frappe.db.count(C.TICKET_DT, {"requester": user, "creation": [">=", str(day)]})


def follower_map(codes):
    """{ma: [user]} cho danh sach yeu cau."""
    codes = list(codes or ())
    if not codes:
        return {}
    out = {}
    for r in frappe.get_all(C.FOLLOWER_DT, filters={"parent": ["in", codes], "parenttype": C.TICKET_DT},
                            fields=["parent", "user"], limit_page_length=0):
        out.setdefault(r.parent, []).append(r.user)
    return out


# ------------------------------------------------------------------ yeu cau: ghi ----------
def insert_ticket(values, files=None):
    doc = frappe.get_doc(dict(values, doctype=C.TICKET_DT))
    doc.insert(ignore_permissions=True)
    if files:
        add_files(doc.name, files, values.get("requester"))
    return doc.name


def set_fields(code, values):
    """Cap nhat truong cua yeu cau - qua doc.save() de Frappe kiem Select / Link va ghi Version
    (track_changes) - dau vet thu hai ben canh EC Data Ticket Log."""
    doc = frappe.get_doc(C.TICKET_DT, code)
    doc.update(values)
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)


def _parent(code):
    doc = frappe.get_doc(C.TICKET_DT, code)
    doc.flags.ignore_permissions = True
    return doc


def add_follower(code, user, by):
    """Dong bang con followers - ghi qua doc cha (child row chuan cua Frappe, co Version)."""
    if frappe.db.exists(C.FOLLOWER_DT, {"parent": code, "parenttype": C.TICKET_DT, "user": user}):
        return False
    doc = _parent(code)
    doc.append("followers", {"user": user, "added_by": by})
    doc.save(ignore_permissions=True)
    return True


def remove_follower(code, user):
    doc = _parent(code)
    keep = [r for r in doc.get("followers") or [] if r.user != user]
    if len(keep) != len(doc.get("followers") or []):
        doc.set("followers", keep)
        doc.save(ignore_permissions=True)


def add_files(code, files, by, message=None):
    """Tep private gan vao yeu cau + dong trong bang con attachments. -> [ten dong]."""
    if not files:
        return []
    doc = _parent(code)
    for f in files:
        fd = frappe.get_doc({"doctype": "File", "file_name": f["name"], "content": f["content"], "is_private": 1,
                             "attached_to_doctype": C.TICKET_DT, "attached_to_name": code})
        # Khong dung lai tep trung noi dung cua ho so khac (xem feedback.repository).
        fd.flags.ignore_existing_file_check = True
        fd.insert(ignore_permissions=True)
        doc.append("attachments", {"file_url": fd.file_url, "file_name": fd.file_name, "file_size": fd.file_size,
                                   "message": message or "", "uploaded_by": by})
    doc.save(ignore_permissions=True)
    return [r.name for r in doc.get("attachments")[-len(files):]]


def file_content(code, row_name):
    """-> (ten tep, bytes) cua tep thuoc DUNG yeu cau nay, hoac None."""
    url = frappe.db.get_value(C.FILE_DT, {"name": row_name, "parent": code, "parenttype": C.TICKET_DT},
                              "file_url")
    if not url:
        return None
    rows = frappe.get_all("File", filters={"file_url": url, "attached_to_doctype": C.TICKET_DT,
                                           "attached_to_name": code}, pluck="name", limit=1)
    if not rows:
        return None
    f = frappe.get_doc("File", rows[0])
    return f.file_name, f.get_content()


def insert_log(values):
    doc = frappe.get_doc(dict(values, doctype=C.LOG_DT))
    doc.insert(ignore_permissions=True)
    return doc.name


def logs(code):
    return [dict(r) for r in frappe.get_all(
        C.LOG_DT, filters={"ticket": code},
        fields=["name", "event", "actor", "source", "from_value", "to_value", "note", "creation"],
        order_by="creation desc", limit_page_length=0)]


def insert_message(values):
    doc = frappe.get_doc(dict(values, doctype=C.MSG_DT))
    doc.insert(ignore_permissions=True)
    return doc.name


def messages(code):
    return [dict(r) for r in frappe.get_all(
        C.MSG_DT, filters={"ticket": code}, fields=["name", "author", "body", "mentions", "creation"],
        order_by="creation asc", limit_page_length=0)]


def count_messages(codes):
    codes = list(codes or ())
    if not codes:
        return {}
    rows = frappe.db.sql("select ticket, count(*) from `tabEC Data Ticket Message` where ticket in %s "
                         "group by ticket", (tuple(codes),))
    return {r[0]: int(r[1]) for r in rows}


# ------------------------------------------------------------------ he thong -------------
def today():
    return frappe.utils.getdate(frappe.utils.nowdate())


def now():
    return frappe.utils.now_datetime()


def commit():
    frappe.db.commit()


def log_error(title):
    try:
        frappe.log_error(title=title[:140], message=frappe.get_traceback())
    except Exception:
        pass


def is_duplicate(exc):
    return isinstance(exc, (frappe.DuplicateEntryError, frappe.UniqueValidationError))


def notify(event, recipient, title, message, url, code, dedupe_key, actor=None):
    from ecentric_workspace.notification_center.events import publish_notification_event
    return publish_notification_event(event, recipient, title, message, action_url=url,
                                      reference_doctype=C.TICKET_DT if code else None,
                                      reference_name=code or None, actor=actor or C.SYSTEM_USER,
                                      from_user=actor or C.SYSTEM_USER, dedupe_key=dedupe_key)


def flags():
    return frappe.flags
