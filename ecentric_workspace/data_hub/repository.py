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
        return legacy_file_content(code, url)   # dot 3: tep cua phieu Data Request cu (khong chep)
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


# ====================================================================== DOT 3 (09/11/2026) ===
# Noi them cuoi file (dot 2 sua song song): quy tac co phien ban + duyet, chuyen phieu Data Request cu.

def _forget(*prefixes):
    """Bo nho tam trong request (settings / rule_set) sau khi ghi."""
    store = getattr(frappe.local, "ec_data_hub_memo", None)
    if not store:
        return
    for k in list(store):
        if any(k.startswith(p) for p in prefixes):
            store.pop(k, None)


# ------------------------------------------------------------------ quy tac (rules_service) --
RULE_FIELDS = ["name", "version_no", "status", "effective_from", "supersedes", "proposed_by", "reason",
               "submitted_at", "decided_by", "decided_at", "decision_note", "mult_urgent", "mult_high",
               "mult_normal", "mult_low", "creation", "modified"]


def lock_rules():
    """Khoa ghi quy tac: SELECT ... FOR UPDATE tren cac dong cua Settings (Single) - moi thao tac
    sua / gui / duyet / rut lai deu di qua day nen chay noi tiep."""
    frappe.db.sql("select field from `tabSingles` where doctype = %s for update", (C.SETTINGS_DT,))
    _forget("settings", "rule_set:")


def _items(names):
    out = {}
    if not names:
        return out
    for r in frappe.get_all(C.RULE_ITEM_DT, filters={"parent": ["in", list(names)], "parenttype": C.RULE_DT},
                            fields=["parent", "rule_key", "label", "days", "note"], order_by="idx asc",
                            limit_page_length=0):
        out.setdefault(r.parent, []).append({"rule_key": r.rule_key, "label": r.label, "days": r.days,
                                             "note": r.note})
    return out


def rule_doc(name):
    """Mot bo quy tac (dict + items). Nho trong request (khoa "rule_set:doc:" - moi lan ghi quy tac
    va lock_rules deu xoa) - trang Dieu phoi goi cho tung yeu cau con giu ban quy tac cu."""
    if not name:
        return None

    def load():
        rows = frappe.get_all(C.RULE_DT, filters={"name": name}, fields=RULE_FIELDS, limit=1)
        if not rows:
            return None
        d = dict(rows[0])
        d["items"] = _items([name]).get(name, [])
        return d
    got = _memo("rule_set:doc:" + name, load)
    return dict(got, items=[dict(i) for i in got["items"]]) if got else None


def rule_versions(statuses=None, limit=30):
    """Cac bo quy tac moi nhat truoc (kem items) - lich su + ban nhap / cho duyet dang mo."""
    filters = {"status": ["in", list(statuses)]} if statuses else {}
    rows = [dict(r) for r in frappe.get_all(C.RULE_DT, filters=filters, fields=RULE_FIELDS,
                                            order_by="version_no desc", limit_page_length=limit)]
    items = _items([r["name"] for r in rows])
    for r in rows:
        r["items"] = items.get(r["name"], [])
    return rows


def next_rule_version():
    row = frappe.db.sql("select max(version_no) from `tabEC Data SLA Rule Set`")
    return int((row and row[0][0]) or 0) + 1


def insert_rule(values):
    doc = frappe.get_doc(dict(values, doctype=C.RULE_DT))
    doc.insert(ignore_permissions=True)
    _forget("rule_set:")
    return doc.name


def update_rule(name, values):
    """Qua doc.save() (Version / track_changes ghi lai moi lan sua). items -> thay ca bang con."""
    doc = frappe.get_doc(C.RULE_DT, name)
    values = dict(values)
    items = values.pop("items", None)
    doc.update(values)
    if items is not None:
        doc.set("items", [])
        for it in items:
            doc.append("items", it)
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    _forget("rule_set:")


def set_settings(values):
    s = frappe.get_single(C.SETTINGS_DT)
    s.update(values)
    s.flags.ignore_permissions = True
    s.save(ignore_permissions=True)
    _forget("settings", "rule_set:")


def notify_ref(event, recipient, title, message, url, ref_doctype, ref_name, dedupe_key, actor=None):
    from ecentric_workspace.notification_center.events import publish_notification_event
    return publish_notification_event(event, recipient, title, message, action_url=url,
                                      reference_doctype=ref_doctype, reference_name=ref_name,
                                      actor=actor or C.SYSTEM_USER, from_user=actor or C.SYSTEM_USER,
                                      dedupe_key=dedupe_key)


# ------------------------------------------------------------------ phieu Data Request cu ----
LEGACY_FIELDS = ["name", "request_title", "requested_by", "department", "detailed_description", "request_type",
                 "urgency", "importance", "expected_resolution_date", "request_attachment", "submitted_at",
                 "completed_at", "approval_request", "fulfillment_status", "assigned_fulfiller", "fulfillment_owner",
                 "fulfillment_due_at", "fulfillment_summary", "output_link", "output_attachment", "completed_by",
                 "creation"]


def find_by_legacy(ref):
    if not ref:
        return None
    return frappe.db.get_value(C.TICKET_DT, {"legacy_ref": ref}, "name")


def legacy_ready():
    return bool(frappe.db.exists("DocType", C.LEGACY_DT))


def legacy_requests():
    """Moi phieu EC Data Request (cu truoc) + approval_status / gio ket thuc cua EC Approval Request."""
    rows = [dict(r) for r in frappe.get_all(C.LEGACY_DT, fields=LEGACY_FIELDS, order_by="creation asc",
                                            limit_page_length=0)]
    reqs = [r["approval_request"] for r in rows if r.get("approval_request")]
    status = {}
    if reqs:
        for a in frappe.get_all(C.LEGACY_REQUEST_DT, filters={"name": ["in", reqs]},
                                fields=["name", "approval_status", "completed_at"], limit_page_length=0):
            status[a.name] = a
    for r in rows:
        a = status.get(r.get("approval_request"))
        r["approval_status"] = a.approval_status if a else None
        r["approval_completed_at"] = a.completed_at if a else None
    return rows


def legacy_actions(approval_request):
    return [dict(r) for r in frappe.get_all(
        C.LEGACY_ACTION_DT, filters={"approval_request": approval_request},
        fields=["name", "seq", "actor", "action", "comment", "action_time", "new_status", "level_no", "level_name"],
        order_by="action_time asc, seq asc", limit_page_length=0)]


def legacy_files(ref, urls=()):
    """File da gan vao phieu cu (+ cac o Attach) -> dong cho bang attachments. KHONG chep noi dung:
    dong moi tro dung file_url cu (file_content tai qua phieu cu, xem duoi)."""
    rows = frappe.get_all("File", filters={"attached_to_doctype": C.LEGACY_DT, "attached_to_name": ref,
                                           "is_folder": 0},
                          fields=["file_url", "file_name", "file_size", "owner"], order_by="creation asc",
                          limit_page_length=0)
    out, seen = [], set()
    for f in rows:
        if f.file_url and f.file_url not in seen:
            seen.add(f.file_url)
            out.append({"file_url": f.file_url, "file_name": f.file_name or f.file_url.rsplit("/", 1)[-1],
                        "file_size": int(f.file_size or 0), "uploaded_by": f.owner, "message": ""})
    for url in urls or ():
        if url and url not in seen:
            seen.add(url)
            out.append({"file_url": url, "file_name": url.rsplit("/", 1)[-1], "file_size": 0, "uploaded_by": None,
                        "message": ""})
    return out


def backdate(doctype, name, at):
    """Gio tao goc (gio gui phieu cu / gio cua tung buoc duyet cu) - chi dung khi chuyen phieu cu."""
    if at:
        frappe.db.set_value(doctype, name, {"creation": at, "modified": at}, update_modified=False)


def insert_migrated(values, created_at):
    """Ticket tu phieu cu. ignore_links: nguoi gui / nguoi xu ly cu co the da nghi viec."""
    doc = frappe.get_doc(dict(values, doctype=C.TICKET_DT))
    doc.flags.ignore_links = True
    doc.insert(ignore_permissions=True)
    backdate(C.TICKET_DT, doc.name, created_at)
    return doc.name


def link_files(code, rows):
    doc = _parent(code)
    doc.flags.ignore_links = True
    for r in rows:
        doc.append("attachments", r)
    doc.save(ignore_permissions=True)


def insert_log_at(values, at):
    doc = frappe.get_doc(dict(values, doctype=C.LOG_DT))
    doc.flags.ignore_links = True
    doc.insert(ignore_permissions=True)
    backdate(C.LOG_DT, doc.name, at)
    return doc.name


def savepoint(name):
    frappe.db.savepoint(name)
    return name


def rollback_savepoint(name):
    try:
        frappe.db.rollback(save_point=name)
    except Exception:
        pass


def task_for_legacy(ref):
    """Task /pm da nhac ma phieu cu trong tieu de (go tay truoc khi chuyen) - de gan, khong tao trung."""
    if not ref:
        return None
    rows = frappe.get_all("Task", filters={"subject": ["like", "%" + ref.replace("%", "") + "%"]}, pluck="name",
                          limit=1)
    return rows[0] if rows else None


def legacy_file_content(code, url):
    """Tep cu (dong attachments tro file_url cua phieu cu): chi tra khi File do THUOC phieu cu ma
    ticket nay mang legacy_ref - khong mo duong tai file bat ky qua file_url."""
    ref = frappe.db.get_value(C.TICKET_DT, code, "legacy_ref")
    if not ref or not url:
        return None
    rows = frappe.get_all("File", filters={"file_url": url, "attached_to_doctype": C.LEGACY_DT,
                                           "attached_to_name": ref}, pluck="name", limit=1)
    if not rows:
        attach = frappe.db.get_value(C.LEGACY_DT, ref, ["request_attachment", "output_attachment"]) or ()
        if url not in attach:
            return None
        rows = frappe.get_all("File", filters={"file_url": url}, pluck="name", limit=1)
    if not rows:
        return None
    f = frappe.get_doc("File", rows[0])
    return f.file_name, f.get_content()


# ------------------------------------------------------------------ the Approval Center ------
def approval_type_route(code):
    """Route cua EC Approval Type; None neu khong co loai nay."""
    if not frappe.db.exists("DocType", "EC Approval Type") or not frappe.db.exists("EC Approval Type", code):
        return None
    return frappe.db.get_value("EC Approval Type", code, "route") or ""


def set_approval_type_route(code, route, note):
    frappe.db.set_value("EC Approval Type", code, "route", route)
    try:
        frappe.get_doc("EC Approval Type", code).add_comment("Comment", note)
    except Exception:
        pass
