# Copyright (c) 2026, eCentric and contributors
"""Tin noi bo - NOI DUY NHAT doc/ghi DB. Khong co quy tac nghiep vu o day.

QUYEN: danh sach bai doc bang frappe.get_list (CO kiem quyen theo phien - permission query
cua permissions.py loc nhap / het han / ngoai pham vi). Mot bai le doc bang get_doc roi
has_permission("read") - di qua has_permission cua permissions.py. Khong ham doc bai nao
dung ignore_permissions. Cac bang phu (phong ban, cay Department, Employee de dem nguoi
trong pham vi) doc bang get_all vi chi dung de TINH, khong tra du lieu nhay cam ra ngoai.
"""
import re

import frappe

from ecentric_workspace.internal_posts import constants as C

POST_LIST_FIELDS = ["name", "title", "slug", "category", "summary", "published", "published_on",
                    "pinned", "expires_on", "cover_kind", "cover_color", "cover_icon", "cover_image",
                    "creation", "modified", "owner", "author_label", "publish_at", "require_ack", "ack_deadline",
                    "notify_bell", "notify_teams", "push_to_home", "allow_comments"]

_STRIP_RE = re.compile(r"<(style|link|script|iframe|object|embed)\b[^>]*>.*?</\1\s*>"
                       r"|<(style|link|script|iframe|object|embed|meta)\b[^>]*/?>", re.I | re.S)


# ------------------------------------------------------------------ nguoi dung ---
def roles(user):
    return set(frappe.get_roles(user))


def is_editor(user):
    if not user or user == "Guest":
        return False
    return _memo("editor:" + user, lambda: bool(roles(user) & set(C.EDITOR_ROLES)))


def _memo(key, fn):
    """Nho trong MOT request (has_permission bi goi nhieu lan / trang)."""
    store = getattr(frappe.local, "ec_internal_posts_memo", None)
    if store is None:
        store = {}
        try:
            frappe.local.ec_internal_posts_memo = store
        except Exception:
            return fn()
    if key not in store:
        store[key] = fn()
    return store[key]


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


def dept_tree():
    """{ten phong: (lft, rgt, ten hien thi, is_group, disabled)} - TOAN BO cay Department.

    Quyen doc dung ca phong da tat (nguoi con nam trong do van phai doc duoc bai cua phong);
    o chon phong tren trang viet bai tu loc phong da tat."""
    return _memo("dept_tree", _dept_tree)


def _dept_tree():
    has_dis = _has_field("Department", "disabled")
    fields = ["name", "lft", "rgt", "department_name", "is_group"] + (["disabled"] if has_dis else [])
    return {r.name: (r.lft, r.rgt, r.department_name or r.name, int(r.is_group or 0),
                     int(r.get("disabled") or 0))
            for r in frappe.get_all("Department", fields=fields, order_by="lft asc", limit_page_length=0)}


def _has_field(dt, field):
    try:
        return frappe.get_meta(dt).has_field(field)
    except Exception:
        return False


def active_employees():
    """[{user, lft}] moi nhan vien Active co tai khoan - de dem "bai toi N nguoi"."""
    rows = frappe.get_all("Employee", filters={"status": "Active", "user_id": ["is", "set"]},
                          fields=["user_id", "department"], limit_page_length=0)
    lfts = {r.name: r.lft for r in frappe.get_all("Department", fields=["name", "lft"], limit_page_length=0)}
    seen, out = set(), []
    for r in rows:
        if r.user_id and r.user_id not in seen and r.user_id != "Guest":
            seen.add(r.user_id)
            out.append({"user": r.user_id, "lft": lfts.get(r.department)})
    return out


def full_names(users):
    users = [u for u in set(users or ()) if u]
    if not users:
        return {}
    return {r.name: r.full_name or r.name
            for r in frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"])}


# ------------------------------------------------------------------ chuyen muc ---
def categories(include_disabled=False):
    filters = None if include_disabled else {"enabled": 1}
    return frappe.get_all(C.CATEGORY_DT, filters=filters,
                          fields=["name", "category_name", "color", "icon", "sort_order", "home_category", "enabled"],
                          order_by="sort_order asc, category_name asc", limit_page_length=0)


def category_exists(name):
    return bool(name) and bool(frappe.db.exists(C.CATEGORY_DT, name))


def category(name):
    if not name:
        return None
    return frappe.db.get_value(C.CATEGORY_DT, name, ["name", "category_name", "color", "icon", "home_category"],
                               as_dict=True)


# ------------------------------------------------------------------ bai ----------
def list_posts(user, filters=None, or_filters=None, limit=0):
    """Danh sach bai NGUOI NAY duoc thay - frappe.get_list chay permission query."""
    return frappe.get_list(C.POST_DT, fields=POST_LIST_FIELDS, filters=filters or {}, or_filters=or_filters,
                           order_by="pinned desc, published_on desc, creation desc",
                           limit_page_length=limit or 0, user=user)


def post_departments(names):
    """{bai: [phong]} cho nhieu bai."""
    out = {n: [] for n in names or ()}
    if not names:
        return out
    for r in frappe.get_all(C.DEPT_CHILD_DT, filters={"parenttype": C.POST_DT, "parent": ["in", list(names)]},
                            fields=["parent", "department"], limit_page_length=0):
        out.setdefault(r.parent, []).append(r.department)
    return out


def name_by_slug(slug):
    return frappe.db.get_value(C.POST_DT, {"slug": slug}, "name") if slug else None


def post_exists(name):
    return bool(name) and bool(frappe.db.exists(C.POST_DT, name))


def set_post_fields(name, values):
    """Truong he thong (notified_on, home_announcement) - khong doi `modified`, khong chay lai hook."""
    frappe.db.set_value(C.POST_DT, name, values, update_modified=False)


def commit():
    frappe.db.commit()


def rollback():
    frappe.db.rollback()


def is_validation_error(exc):
    """Loi nghiep vu (frappe.throw trong validate) - khac loi tam thoi cua DB."""
    transient = tuple(e for e in (getattr(frappe, "QueryDeadlockError", None),
                                  getattr(frappe, "QueryTimeoutError", None)) if e)
    return isinstance(exc, frappe.ValidationError) and not (transient and isinstance(exc, transient))


def get_post(name):
    return frappe.get_doc(C.POST_DT, name)


def can(name_or_doc, ptype, user):
    return bool(frappe.has_permission(C.POST_DT, ptype, doc=name_or_doc, user=user))


def slug_taken(slug, exclude=None):
    filters = {"slug": slug}
    if exclude:
        filters["name"] = ["!=", exclude]
    return bool(frappe.db.exists(C.POST_DT, filters))


def owner_names(owners):
    return full_names(owners)


# ------------------------------------------------------------------ noi dung -----
def safe_html(html, limit=200000):
    """HTML nguoi soan nhap -> an toan de in ra trang cua MOI nguoi.

    always_sanitize: sanitize_html mac dinh tra NGUYEN chuoi neu no parse duoc thanh JSON hoac
    khong co the. Bo them style/script/iframe: allowlist cua Frappe giu <style> - mot bai co the
    doi mau ca trang. Cung cach voi home_today.repository.safe_html."""
    from frappe.utils.html_utils import sanitize_html
    clean = sanitize_html((html or "")[:limit], always_sanitize=True) or ""
    return _STRIP_RE.sub("", clean)


# ------------------------------------------------------------------ cam xuc ------
def reactions(targets):
    if not targets:
        return []
    return frappe.get_all(C.REACTION_DT, filters={"target": ["in", list(targets)]},
                          fields=["target", "kind", "user"], order_by="creation desc",
                          limit_page_length=0)


def find_reaction(target, kind, user):
    return frappe.db.get_value(C.REACTION_DT, {"target": target, "kind": kind, "user": user}, "name")


def add_reaction(target, kind, user, today):
    """Ghi cua HE THONG (bang cam xuc khong cho nhan vien ghi) - nguoi goi da kiem quyen doc bai."""
    frappe.get_doc({"doctype": C.REACTION_DT, "target": target, "kind": kind, "user": user,
                    "reaction_date": today, "dedupe_key": "%s|%s|%s" % (target, kind, user)}
                   ).insert(ignore_permissions=True)


def remove_reaction(name):
    frappe.delete_doc(C.REACTION_DT, name, ignore_permissions=True, force=True)


def is_duplicate(exc):
    return isinstance(exc, (frappe.DuplicateEntryError, frappe.UniqueValidationError))


# ------------------------------------------------------------------ khac ---------
def today():
    return frappe.utils.getdate(frappe.utils.nowdate())


def now():
    return frappe.utils.now_datetime()


def log_error(title):
    frappe.log_error(title=title, message=frappe.get_traceback())


# ------------------------------------------------------------------ luot xem (dung chung) ----
def mark_seen(name, user):
    from ecentric_workspace.platform import read_receipt
    return read_receipt.mark_seen(C.POST_DT, name, user)


def seen_users(name):
    from ecentric_workspace.platform import read_receipt
    return read_receipt.seen_users(C.POST_DT, name)


def seen_by(user, names):
    from ecentric_workspace.platform import read_receipt
    return read_receipt.seen_by(user, C.POST_DT, names)


def seen_users_many(names):
    from ecentric_workspace.platform import read_receipt
    return read_receipt.seen_users_many(C.POST_DT, names)


# ------------------------------------------------------------------ bai huong dan cu ----
def legacy_guides():
    """Bai huong dan cu (guides.registry - trang tinh /huong-dan/<slug>)."""
    from ecentric_workspace.guides import registry
    out = []
    for g in registry.listed():
        out.append(dict(g))
    return out


def popup_published(name):
    return bool(name) and bool(frappe.db.get_value("EC Home Announcement", name, "published"))


def file_sizes(urls):
    if not urls:
        return {}
    return {r.file_url: r.file_size for r in frappe.get_all("File", filters={"file_url": ["in", list(urls)]},
                                                             fields=["file_url", "file_size"], limit_page_length=0)}


# ------------------------------------------------------------------ ghi bai (nguoi soan) ----
def new_post():
    return frappe.new_doc(C.POST_DT)


def save_post(doc):
    """Luu theo phien nguoi soan - CO kiem quyen role (khong ignore_permissions)."""
    if doc.is_new():
        doc.insert()
    else:
        doc.save()
    return doc


def save_post_system(doc):
    """Job hen gio dang (scheduler chay duoi Administrator) - ghi cua HE THONG thay HR da hen."""
    doc.flags.ignore_permissions = True
    doc.save()
    return doc


def due_scheduled(now, limit=50):
    """Bai nhap co gio hen <= bay gio (job moi 5 phut)."""
    return frappe.get_all(C.POST_DT, filters={"published": 0, "publish_at": ["<=", now]},
                          order_by="publish_at asc", pluck="name", limit_page_length=limit)


def delete_post(name):
    """Xoa nhap (nguoi goi da kiem: chua tung dang). Don nhat ky AI + binh luan + tep gan vao bai
    truoc - cac bang do tro toi bai, khong don thi delete_doc bao LinkExistsError."""
    for dt_ in (C.COVER_JOB_DT, C.COMMENT_DT):
        for row in frappe.get_all(dt_, filters={"post": name}, pluck="name", limit_page_length=0):
            frappe.delete_doc(dt_, row, ignore_permissions=True, force=True)
    frappe.delete_doc(C.POST_DT, name)


def file_info(url, post):
    """Tep `url` DA GAN VAO bai `post` (Frappe dung chung file_url cho tep trung noi dung,
    nen phai loc ca attached_to - khong lay "dong File dau tien co url nay")."""
    if not url or not post:
        return None
    rows = frappe.get_all("File", filters={"file_url": url, "attached_to_doctype": C.POST_DT,
                                           "attached_to_name": post},
                          fields=["name", "file_url", "file_name", "file_size", "is_private",
                                  "attached_to_doctype", "attached_to_name"], limit=1)
    return rows[0] if rows else None


# ------------------------------------------------------------------ AI anh bia ----
def cover_jobs_today(post, day):
    return frappe.db.count(C.COVER_JOB_DT, {"post": post, "job_date": day})


def insert_cover_job(post, user, day, source_text=""):
    """Ghi cua HE THONG (nhat ky luot AI) - nguoi goi da kiem role + quyen sua bai."""
    doc = frappe.get_doc({"doctype": C.COVER_JOB_DT, "post": post, "requested_by": user,
                          "job_date": day, "status": "Queued", "images": "[]",
                          "source_text": source_text or ""})
    doc.insert(ignore_permissions=True)
    return doc.name


def enqueue_cover_job(job):
    frappe.enqueue("ecentric_workspace.internal_posts.cover_ai.run_job", job=job, queue="long",
                   timeout=C.AI_COVER_JOB_TIMEOUT, enqueue_after_commit=True)


def cover_job(job):
    if not job:
        return None
    return frappe.db.get_value(C.COVER_JOB_DT, job, ["name", "post", "status", "images", "error", "source_text",
                                                     "filter_note"], as_dict=True)


def set_cover_job(job, values):
    frappe.db.set_value(C.COVER_JOB_DT, job, values, update_modified=True)
    frappe.db.commit()


def old_cover_jobs(keep_days):
    cutoff = frappe.utils.add_days(frappe.utils.nowdate(), -int(keep_days))
    return frappe.get_all(C.COVER_JOB_DT, filters={"job_date": ["<", cutoff], "images": ["not in", ["", "[]"]]},
                          fields=["name", "post", "images"], limit_page_length=500)


def post_cover(post):
    return frappe.db.get_value(C.POST_DT, post, "cover_image") if post else None


def fetch_image(url, max_bytes):
    """Tai anh tu URL tam cua Kie. -> (bytes, mime)."""
    import requests
    r = requests.get(url, timeout=(5, 60), stream=True)
    r.raise_for_status()
    ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if not ctype.startswith("image/"):
        raise ValueError("khong phai anh: %s" % ctype)
    buf = b""
    for chunk in r.iter_content(65536):
        buf += chunk
        if len(buf) > max_bytes:
            raise ValueError("anh qua lon")
    return buf, ctype


def save_image_bytes(buf, post, file_name):
    """Anh -> File CONG KHAI gan vao bai. -> file_url."""
    f = frappe.get_doc({"doctype": "File", "file_name": file_name, "content": buf, "is_private": 0,
                        "attached_to_doctype": C.POST_DT, "attached_to_name": post})
    f.insert(ignore_permissions=True)     # job nen ghi thay HR da bam
    return f.file_url


def save_remote_image(url, post, file_name, max_bytes):
    """Tai anh tu URL tam cua Kie -> File CONG KHAI gan vao bai. -> file_url."""
    buf, _ctype = fetch_image(url, max_bytes)
    return save_image_bytes(buf, post, file_name)


def delete_post_file(url, post):
    names = frappe.get_all("File", filters={"file_url": url, "attached_to_doctype": C.POST_DT,
                                            "attached_to_name": post}, pluck="name")
    for n in names:
        frappe.delete_doc("File", n, ignore_permissions=True, force=True)
    return len(names)


def log_message(title, message):
    frappe.log_error(title=title, message=str(message)[:2000])


# ------------------------------------------------------------------ xac nhan da doc (v6) ----
def mark_ack(name, user):
    from ecentric_workspace.platform import read_receipt
    return read_receipt.mark_ack(C.POST_DT, name, user)


def ack_users(name):
    from ecentric_workspace.platform import read_receipt
    return read_receipt.seen_users(C.POST_DT, name, kind=read_receipt.ACK)


def ack_times(name):
    from ecentric_workspace.platform import read_receipt
    return read_receipt.seen_times(C.POST_DT, name, kind=read_receipt.ACK)


def acked_by(user, names):
    from ecentric_workspace.platform import read_receipt
    return read_receipt.seen_by(user, C.POST_DT, names, kind=read_receipt.ACK)


def ack_users_many(names):
    from ecentric_workspace.platform import read_receipt
    return read_receipt.seen_users_many(C.POST_DT, names, kind=read_receipt.ACK)


def ack_due_posts(dates):
    """Bai dang hien, bat buoc xac nhan, han roi vao mot trong cac ngay `dates` (job 09:00)."""
    if not dates:
        return []
    return frappe.get_all(C.POST_DT, filters={"published": 1, "require_ack": 1, "ack_deadline": ["in", list(dates)]},
                          pluck="name", limit_page_length=0)


def user_departments(users):
    """{user: ten phong ban} (binh luan: 'Lan · Kinh doanh'; Excel xac nhan)."""
    users = [u for u in set(users or ()) if u]
    if not users:
        return {}
    rows = frappe.get_all("Employee", filters={"user_id": ["in", users], "status": "Active"},
                          fields=["user_id", "department"], limit_page_length=0)
    labels = {k: v[2] for k, v in dept_tree().items()}
    return {r.user_id: labels.get(r.department, r.department or "") for r in rows}


def send_bell(event, user, title, message, url, ref_name, dedupe_key, actor=None):
    """Chuong (va Teams neu event cho phep) qua notification_center - MOT duong gui."""
    from ecentric_workspace.notification_center.events import publish_notification_event
    return publish_notification_event(event, user, title, message, action_url=url,
                                      reference_doctype=C.POST_DT, reference_name=ref_name,
                                      actor=actor, from_user=actor, dedupe_key=dedupe_key)


# ------------------------------------------------------------------ binh luan (v6) ----------
COMMENT_FIELDS = ["name", "post", "parent_comment", "user", "content", "hidden", "hidden_by", "hidden_on",
                  "deleted", "edited_on", "creation"]


def comments_of(post):
    """Moi binh luan cua bai (ca an / da xoa - service quyet dinh ai thay gi)."""
    return frappe.get_all(C.COMMENT_DT, filters={"post": post}, fields=COMMENT_FIELDS,
                          order_by="creation asc", limit_page_length=0)


def comment(name):
    if not name:
        return None
    return frappe.db.get_value(C.COMMENT_DT, name, COMMENT_FIELDS, as_dict=True)


def insert_comment(post, user, content, parent=None):
    """Ghi cua HE THONG - nhan vien khong co quyen tren bang; service da kiem quyen doc bai."""
    doc = frappe.get_doc({"doctype": C.COMMENT_DT, "post": post, "user": user, "content": content,
                          "parent_comment": parent or None})
    doc.insert(ignore_permissions=True)
    return doc.name


def update_comment(name, values):
    frappe.db.set_value(C.COMMENT_DT, name, values, update_modified=True)


def comment_count_since(post, user, since):
    return frappe.db.count(C.COMMENT_DT, {"post": post, "user": user, "creation": [">=", since]})


def comment_counts(names):
    """{bai: so binh luan dang hien (khong an, khong xoa)} - bang quan ly."""
    out = {n: 0 for n in names or ()}
    if not names:
        return out
    rows = frappe.db.sql(
        "select c.post, count(*) from `tabEC Post Comment` c "
        "left join `tabEC Post Comment` root on root.name = c.parent_comment "
        "where c.post in %s and ifnull(c.hidden, 0) = 0 and ifnull(c.deleted, 0) = 0 "
        "and ifnull(root.hidden, 0) = 0 group by c.post", (tuple(names),))
    for post, n in rows:
        out[post] = int(n or 0)
    return out


# ------------------------------------------------------------------ AI viet giup (v6) -------
_AIW_KEY = "ec_internal_posts:ai_write:%s:%s"


def ai_write_used(key, day):
    try:
        return int(frappe.cache().get_value(_AIW_KEY % (key, day)) or 0)
    except Exception:
        return 0


def ai_write_add(key, day):
    """Dem luot AI viet (cache 2 ngay - gioi han mem de giu chi phi, khong phai so sach)."""
    k = _AIW_KEY % (key, day)
    try:
        n = int(frappe.cache().get_value(k) or 0) + 1
        frappe.cache().set_value(k, n, expires_in_sec=2 * 86400)
        return n
    except Exception:
        return 0


def ai_generate(prompt, **kw):
    from ecentric_workspace.platform.ai.gateway import generate
    return generate(prompt, **kw)


def ai_available():
    try:
        from ecentric_workspace.platform.ai import config
        return not config.disabled() and bool(config.api_key())
    except Exception:
        return False
