# Copyright (c) 2026, eCentric and contributors
"""Gop y cong ty - NOI DUY NHAT doc/ghi DB. Khong co quy tac nghiep vu o day.

QUYEN: moi DocType cua module chi System Manager doc duoc (khong co duong /app, /api/resource
nao cho nhan vien hay nguoi xu ly). Moi doc / ghi di qua service, va service da kiem "nguoi nay
la nguoi gui / nguoi xu ly" TRUOC khi goi vao day - nen ham o day dung ignore_permissions.

AN DANH (PO chot 04/10): Frappe tu ghi owner / modified_by = nguoi dang dang nhap vao MOI ban
ghi (ca bang con, ca File). Ghi thay nguoi gui an danh thi xong viec PHAI goi scrub_owner()
de doi ca hai cot ve SYSTEM_USER trong cung giao dich. DocType de read_only nen Frappe khong
phat realtime list_update (goi do mang ten nguoi dang dang nhap) cho ai dang mo danh sach.
"""
from contextlib import contextmanager

import frappe

from ecentric_workspace.feedback import constants as C

FEEDBACK_FIELDS = ["name", "title", "topic", "kind", "status", "is_anonymous", "submitter", "submitter_department",
                   "body", "viewed_at", "viewed_by", "due_at", "responded_at", "first_response_at", "closed_at",
                   "reopen_count", "reminded_soon_at", "reminded_overdue_at", "last_activity_at", "duplicate_of",
                   "is_spam", "is_public", "public_title", "public_answer", "public_on", "vote_count",
                   "home_announcement", "notify_pending", "pending_event", "creation"]
LIST_FIELDS = ["name", "title", "topic", "kind", "status", "is_anonymous", "submitter", "due_at", "responded_at",
               "first_response_at", "closed_at", "reopen_count", "is_public", "vote_count", "creation",
               "last_activity_at", "viewed_at", "viewed_by", "is_spam"]
#: Bang chung: CHI truong cong khai - noi dung goc / nguoi gui khong bao gio roi khoi DB qua day.
BOARD_FIELDS = ["name", "topic", "status", "public_title", "public_answer", "public_on", "vote_count", "creation"]


def _memo(key, fn):
    """Nho trong MOT request."""
    store = getattr(frappe.local, "ec_feedback_memo", None)
    if store is None:
        store = {}
        try:
            frappe.local.ec_feedback_memo = store
        except Exception:
            return fn()
    if key not in store:
        store[key] = fn()
    return store[key]


@contextmanager
def as_system():
    """Ghi THAY nguoi gui duoi ten SYSTEM_USER roi tra lai phien cu.

    Vi sao khong chi scrub_owner sau khi ghi: luc insert, Frappe phat realtime (list_update cua File,
    ...) mang `frappe.session.user` cho MOI phien dang mo - ai nghe websocket se thay "File vua tao boi
    X" dung luc mot gop y an danh xuat hien. Ghi duoi SYSTEM_USER thi khong co ten nao de phat.

    frappe.set_user() doi ca session.sid / session.data / form_dict cua request; khoi phuc DUNG
    doi tuong cu (local.session chinh la session_obj.data, cuoi request Frappe luu lai no)."""
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


# ------------------------------------------------------------------ nguoi dung ---
def roles(user):
    return set(frappe.get_roles(user))


def is_admin(user):
    if not user or user == "Guest":
        return False
    return _memo("admin:" + user, lambda: C.ADMIN_ROLE in roles(user))


def employee(user):
    """Ho so Employee dang Active cua nguoi nay -> {name, department} hoac None."""
    if not user or user == "Guest":
        return None
    return _memo("emp:" + user, lambda: _employee(user))


def _employee(user):
    rows = frappe.get_all("Employee", filters={"user_id": user, "status": "Active"},
                          fields=["name", "department"], limit=1)
    return {"name": rows[0].name, "department": rows[0].department} if rows else None


def handlers():
    """Nguoi xu ly = moi nhan vien Active co tai khoan thuoc phong HANDLER_DEPARTMENT (ca phong con)."""
    return _memo("handlers", _handlers)


def _handlers():
    lr = frappe.db.get_value("Department", C.HANDLER_DEPARTMENT, ["lft", "rgt"])
    if not lr:
        return []
    depts = frappe.get_all("Department", filters={"lft": [">=", lr[0]], "rgt": ["<=", lr[1]]}, pluck="name",
                           limit_page_length=0)
    if not depts:
        return []
    users = frappe.get_all("Employee", filters={"status": "Active", "department": ["in", depts],
                                                "user_id": ["is", "set"]}, pluck="user_id", limit_page_length=0)
    return sorted({u for u in users if u and u != "Guest"})


def full_names(users):
    users = [u for u in set(users or ()) if u]
    if not users:
        return {}
    return {r.name: r.full_name or r.name
            for r in frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"])}


# ------------------------------------------------------------------ chu de -------
def topics(include_disabled=False):
    filters = None if include_disabled else {"enabled": 1}
    return frappe.get_all(C.TOPIC_DT, filters=filters,
                          fields=["name", "topic_name", "color", "icon", "hint", "sort_order", "enabled"],
                          order_by="sort_order asc, topic_name asc", limit_page_length=0)


# ------------------------------------------------------------------ gop y: doc ---
def get(name):
    if not name:
        return None
    rows = frappe.get_all(C.FEEDBACK_DT, filters={"name": name}, fields=FEEDBACK_FIELDS, limit=1)
    if not rows:
        return None
    fb = dict(rows[0])
    fb["attachments"] = [dict(r) for r in frappe.get_all(
        C.FILE_CHILD_DT, filters={"parent": name, "parenttype": C.FEEDBACK_DT},
        fields=["name", "file_url", "file_name", "file_size"], order_by="idx asc", limit_page_length=0)]
    return fb


def exists(name):
    return bool(name) and bool(frappe.db.exists(C.FEEDBACK_DT, name))


def list_rows(filters=None, order_by="creation desc", limit=0, fields=None):
    return [dict(r) for r in frappe.get_all(C.FEEDBACK_DT, filters=filters or {}, fields=fields or LIST_FIELDS,
                                            order_by=order_by, limit_page_length=limit or 0)]


def board_rows():
    return [dict(r) for r in frappe.get_all(C.FEEDBACK_DT, filters={"is_public": 1}, fields=BOARD_FIELDS,
                                            order_by="public_on desc", limit_page_length=0)]


def rows_between(start, end):
    """Gop y TAO trong [start, end) - cho thong ke / ban tin. Spam khong tinh."""
    return list_rows({"creation": ["between", [start, end]], "is_spam": 0}, order_by="creation asc",
                     fields=LIST_FIELDS + ["body"])


def pending_notify():
    """Gop y an danh dang cho chuong gom (job nhac moi gio)."""
    return list_rows({"notify_pending": 1}, fields=LIST_FIELDS + ["pending_event"])


def open_unresponded():
    """Gop y con mo, chua phan hoi trong vong hien tai, co han - cho job nhac."""
    return list_rows({"status": ["in", [C.ST_NEW, C.ST_VIEWING]], "responded_at": ["is", "not set"],
                      "due_at": ["is", "set"]},
                     fields=LIST_FIELDS + ["reminded_soon_at", "reminded_overdue_at"])


# ------------------------------------------------------------------ danh tinh ----
def my_names(user, limit=0):
    """Gop y nguoi nay da gui (ca an danh), moi nhat truoc."""
    return frappe.get_all(C.IDENTITY_DT, filters={"user": user}, pluck="feedback", order_by="creation desc",
                          limit_page_length=limit or 0)


def my_unread(user):
    return {r.feedback: int(r.sender_unread or 0) for r in frappe.get_all(
        C.IDENTITY_DT, filters={"user": user, "sender_unread": [">", 0]}, fields=["feedback", "sender_unread"],
        limit_page_length=0)}


def sender_of(name):
    """Tai khoan nguoi gui - CHI dung de kiem quyen / gui thong bao cho chinh ho, khong tra ra ngoai."""
    return frappe.db.get_value(C.IDENTITY_DT, {"feedback": name}, "user") if name else None


def sent_today(user, day):
    return frappe.db.count(C.IDENTITY_DT, {"user": user, "sent_on": day})


def bump_unread(name):
    frappe.db.sql("update `tabEC Feedback Identity` set sender_unread = ifnull(sender_unread, 0) + 1, "
                  "modified_by = %s where feedback = %s", (C.SYSTEM_USER, name))


def clear_unread(name):
    frappe.db.sql("update `tabEC Feedback Identity` set sender_unread = 0, modified_by = %s "
                  "where feedback = %s and sender_unread > 0", (C.SYSTEM_USER, name))


# ------------------------------------------------------------------ gop y: ghi ---
def insert_feedback(values, user, day, files):
    """Tao gop y + danh tinh + tep. Owner / modified_by cua MOI ban ghi vua tao -> SYSTEM_USER (ca
    gop y co ten: nguoi gui da nam o submitter, khong can them dau vet thu hai; mot luat cho moi gop y
    thi khong ai doan duoc "ban ghi owner = Administrator la an danh")."""
    with as_system():
        return _insert_feedback(values, user, day, files)


def _insert_feedback(values, user, day, files):
    doc = frappe.get_doc(dict(values, doctype=C.FEEDBACK_DT))
    doc.insert(ignore_permissions=True)
    file_names = []
    for f in files or ():
        fd = frappe.get_doc({"doctype": "File", "file_name": f["name"], "content": f["content"], "is_private": 1,
                             "attached_to_doctype": C.FEEDBACK_DT, "attached_to_name": doc.name})
        # Khong dung lai tep trung noi dung da co (Frappe khu trung theo content_hash va lay luon
        # file_url cua tep cu - duong dan do co the gan voi ho so khac cua chinh nguoi gui).
        fd.flags.ignore_existing_file_check = True
        fd.insert(ignore_permissions=True)
        file_names.append(fd.name)
        doc.append("attachments", {"file_url": fd.file_url, "file_name": fd.file_name, "file_size": fd.file_size})
    if files:
        doc.save(ignore_permissions=True)
    ident = frappe.get_doc({"doctype": C.IDENTITY_DT, "feedback": doc.name, "user": user, "sent_on": day,
                            "sender_unread": 0})
    ident.insert(ignore_permissions=True)
    scrub_owner(C.FEEDBACK_DT, [doc.name])
    scrub_owner(C.IDENTITY_DT, [ident.name])
    scrub_owner("File", file_names)
    frappe.db.sql("update `tabEC Feedback File` set owner = %s, modified_by = %s where parent = %s "
                  "and parenttype = %s", (C.SYSTEM_USER, C.SYSTEM_USER, doc.name, C.FEEDBACK_DT))
    return doc.name


def scrub_owner(doctype, names):
    """owner + modified_by -> SYSTEM_USER (khong doi `modified`)."""
    names = [n for n in names or () if n]
    if not names:
        return
    frappe.db.sql("update `tab{0}` set owner = %s, modified_by = %s where name in %s".format(doctype),
                  (C.SYSTEM_USER, C.SYSTEM_USER, tuple(names)))


def set_fields(name, values, by=None):
    """Cap nhat truong cua gop y. by = nguoi xu ly (co ten) hoac None = he thong / nguoi gui an danh."""
    frappe.db.set_value(C.FEEDBACK_DT, name, values, update_modified=False)
    frappe.db.sql("update `tabEC Feedback` set modified = %s, modified_by = %s where name = %s",
                  (now(), by or C.SYSTEM_USER, name))


def insert_message(values, by=None):
    """Mot dong trong luong trao doi. by = None -> owner la SYSTEM_USER (nguoi gui / he thong)."""
    if by:
        doc = frappe.get_doc(dict(values, doctype=C.MESSAGE_DT))
        doc.insert(ignore_permissions=True)
        return doc.name
    with as_system():
        doc = frappe.get_doc(dict(values, doctype=C.MESSAGE_DT))
        doc.insert(ignore_permissions=True)
    scrub_owner(C.MESSAGE_DT, [doc.name])
    return doc.name


def messages(name):
    return [dict(r) for r in frappe.get_all(
        C.MESSAGE_DT, filters={"feedback": name},
        fields=["name", "kind", "author_role", "author", "body", "from_status", "to_status", "from_topic",
                "to_topic", "creation"], order_by="creation asc", limit_page_length=0)]


# ------------------------------------------------------------------ +1 -----------
def my_votes(user, names=None):
    filters = {"user": user}
    if names is not None:
        if not names:
            return set()
        filters["feedback"] = ["in", list(names)]
    return set(frappe.get_all(C.VOTE_DT, filters=filters, pluck="feedback", limit_page_length=0))


def find_vote(name, user):
    return frappe.db.get_value(C.VOTE_DT, {"feedback": name, "user": user}, "name")


def add_vote(name, user):
    doc = frappe.get_doc({"doctype": C.VOTE_DT, "feedback": name, "user": user,
                          "dedupe_key": "%s|%s" % (name, user)})
    doc.insert(ignore_permissions=True)


def remove_vote(vote):
    frappe.delete_doc(C.VOTE_DT, vote, ignore_permissions=True, force=True)


def set_vote_count(name, n):
    """So +1 cache tren gop y - khong doi modified / modified_by (bam +1 khong phai sua gop y)."""
    frappe.db.set_value(C.FEEDBACK_DT, name, "vote_count", int(n), update_modified=False)


def count_votes(name):
    return frappe.db.count(C.VOTE_DT, {"feedback": name})


def is_duplicate(exc):
    return isinstance(exc, (frappe.DuplicateEntryError, frappe.UniqueValidationError))


# ------------------------------------------------------------------ tep ----------
def file_content(name, file_url):
    """-> (ten tep, bytes) cua tep GAN VAO gop y nay, hoac None."""
    rows = frappe.get_all("File", filters={"file_url": file_url, "attached_to_doctype": C.FEEDBACK_DT,
                                           "attached_to_name": name}, pluck="name", limit=1)
    if not rows:
        return None
    f = frappe.get_doc("File", rows[0])
    return f.file_name, f.get_content()


# ------------------------------------------------------------------ lich lam viec --
def calendar():
    """-> (periods_by_wd, holidays, gio lam / ngay) hoac None neu chua cau hinh lich."""
    return _memo("calendar", _calendar)


def _calendar():
    from ecentric_workspace.approval_center.shared.workflow import business_hours as bh
    from ecentric_workspace.approval_center.shared.workflow import holidays as hol
    code = frappe.conf.get(C.CALENDAR_CONF_KEY) or C.CALENDAR_DEFAULT
    if not frappe.db.exists("EC Approval Business Calendar", code):
        return None
    cal = frappe.get_cached_doc("EC Approval Business Calendar", code)
    periods = bh.build_periods(cal.working_periods)
    if not periods:
        return None
    company = frappe.defaults.get_global_default("company")
    hl = hol.resolve_holiday_list(company=company) if company else None
    holidays = hol.holiday_dates(hl) if hl else set()
    per_day = max(sum((_secs(et) - _secs(st)) for st, et in p) for p in periods.values()) / 3600.0
    return periods, holidays, per_day


def _secs(t):
    return t.hour * 3600 + t.minute * 60 + t.second


def business_due(start, hours):
    from ecentric_workspace.approval_center.shared.workflow import business_hours as bh
    cal = calendar()
    return bh.calculate_business_due_at(start, hours, cal[0], cal[1])


def business_seconds(a, b):
    from ecentric_workspace.approval_center.shared.workflow import business_hours as bh
    cal = calendar()
    if not cal:
        return int((b - a).total_seconds()) if a and b and b > a else 0
    return bh.business_seconds_between(a, b, cal[0], cal[1])


# ------------------------------------------------------------------ ban tin ------
def digest(month):
    return frappe.db.get_value(C.DIGEST_DT, month, ["name", "month", "stats", "hot_topics", "generated_on",
                                                     "sent_on", "ai_model"], as_dict=True)


def save_digest(month, values):
    if frappe.db.exists(C.DIGEST_DT, month):
        frappe.db.set_value(C.DIGEST_DT, month, values)
    else:
        frappe.get_doc(dict(values, doctype=C.DIGEST_DT, month=month)).insert(ignore_permissions=True)


def ai_runs_today(user, day):
    """So lan nguoi nay bam "Tom tat ngay" hom nay (nho trong cache, het ngay tu het)."""
    return int(frappe.cache().get_value("ec_feedback_ai:%s:%s" % (user, day)) or 0)


def bump_ai_runs(user, day):
    key = "ec_feedback_ai:%s:%s" % (user, day)
    frappe.cache().set_value(key, ai_runs_today(user, day) + 1, expires_in_sec=86400)


# ------------------------------------------------------------------ khac ---------
def today():
    return frappe.utils.getdate(frappe.utils.nowdate())


def now():
    return frappe.utils.now_datetime()


def commit():
    frappe.db.commit()


def log_error(title):
    frappe.log_error(title=title, message=frappe.get_traceback())


def log_message(title, message):
    with as_system():                   # Error Log mang owner = phien hien hanh (co the la nguoi gui)
        frappe.log_error(title=title, message=str(message)[:2000])


def announce(name, title, summary, link, start, end):
    from ecentric_workspace.home_today import announce_service
    with as_system():
        return announce_service.publish_from_source(C.FEEDBACK_DT, name, "", title, category=C.POPUP_CATEGORY,
                                                    summary=summary, link=link, link_label=C.POPUP_LINK_LABEL,
                                                    start_date=start, end_date=end)


def withdraw(name):
    """Rut popup. Duoi SYSTEM_USER: home_today ghi set_value(update_modified=True) -> modified_by cua
    EC Home Announcement (HR doc duoc) se la nguoi bam "Chua on" = nguoi gui an danh."""
    from ecentric_workspace.home_today import announce_service
    with as_system():
        return announce_service.withdraw_source(C.FEEDBACK_DT, name)


def clean_image(content, ext):
    """Ve lai anh, bo EXIF / XMP / ICC / text chunk (ten may, GPS, ten nguoi chup). -> bytes.
    Anh khong mo duoc -> ValueError (service bao loi cho nguoi gui)."""
    import io
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(content))
        im.load()
    except Exception:
        raise ValueError("anh hong")
    fmt = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "gif": "GIF", "webp": "WEBP"}[ext]
    clean = im.convert("RGB") if fmt == "JPEG" and im.mode not in ("RGB", "L") else im.copy()
    clean.info = {}                     # Pillow doc EXIF / ICC / text / comment tu .info khi luu
    out = io.BytesIO()
    clean.save(out, format=fmt, **({"quality": 90} if fmt == "JPEG" else {}))
    return out.getvalue()


def notify(event, recipient, title, message, url, name, dedupe_key, actor=None):
    """Mot thong bao. actor mac dinh SYSTEM_USER: thong bao "gop y moi" KHONG BAO GIO mang ten nguoi
    gui (from_user cua Notification Log hien tren chuong cua nguoi nhan)."""
    from ecentric_workspace.notification_center.events import publish_notification_event
    who = actor or C.SYSTEM_USER
    return publish_notification_event(event, recipient, title, message, action_url=url,
                                      reference_doctype=C.FEEDBACK_DT if name else None,
                                      reference_name=name or None, actor=who,
                                      from_user=who, dedupe_key=dedupe_key)


def enqueue(method, **kwargs):
    # Duoi SYSTEM_USER: RQ luu ten nguoi xep job vao metadata + log worker.
    with as_system():
        frappe.enqueue(method, queue="short", timeout=600, enqueue_after_commit=True, **kwargs)


def generate_ai(prompt, schema):
    from ecentric_workspace.platform.ai import gateway
    return gateway.generate(prompt, schema=schema, json_mode=True, purpose="feedback_digest")
