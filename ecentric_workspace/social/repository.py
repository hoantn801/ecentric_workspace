# Copyright (c) 2026, eCentric and contributors
"""Bang tin - NOI DUY NHAT doc / ghi DB. Khong co quy tac nghiep vu o day.

Moi DocType cua module chi System Manager (+ HR Manager doc) co quyen: nhan vien KHONG doc
thang bang nao. Service kiem "ai thay bai nao" (domain.can_see) roi moi goi xuong day, nen doc o
day dung get_all (giong feedback/). Ghi la ghi cua HE THONG sau khi service da kiem quyen.

Dung lai (khong viet ban thu hai): nguoi xem / cay phong ban / ten / phong cua nguoi dung, bang cam
xuc EC Home Reaction, bang binh luan EC Post Comment - qua internal_posts.repository.
"""
import io

import frappe

from ecentric_workspace.internal_posts import repository as IR
from ecentric_workspace.social import constants as C

POST_FIELDS = ["name", "kind", "author", "club", "dept_only", "department", "body", "kudos_to", "kudos_value",
               "event_title", "event_start", "event_place", "moment_key", "hidden", "hidden_by", "hidden_on",
               "hidden_reason", "report_count", "edited_on", "creation", "owner"]
CLUB_FIELDS = ["name", "club_name", "slug", "emoji", "color", "category", "description", "status", "lead",
               "proposed_by", "decided_by", "decided_on", "decision_note", "creation"]

# ------------------------------------------------------------------ dung lai ---------
viewer = IR.viewer
dept_tree = IR.dept_tree
full_names = IR.full_names
user_departments = IR.user_departments
reactions = IR.reactions
find_reaction = IR.find_reaction
add_reaction = IR.add_reaction
remove_reaction = IR.remove_reaction
is_duplicate = IR.is_duplicate
log_error = IR.log_error


def now():
    return frappe.utils.now_datetime()


def today():
    return frappe.utils.getdate()


def is_moderator(user):
    if not user or user == "Guest":
        return False
    return IR._memo("soc_mod:" + user, lambda: bool(set(frappe.get_roles(user)) & set(C.MODERATOR_ROLES)))


def hr_managers():
    """Nguoi nhan chuong "co bai bi bao cao": tai khoan dang bat co role HR Manager."""
    rows = frappe.get_all("Has Role", filters={"role": "HR Manager", "parenttype": "User"}, pluck="parent",
                          limit_page_length=0)
    if not rows:
        return []
    return frappe.get_all("User", filters={"name": ["in", list(set(rows))], "enabled": 1,
                                           "user_type": "System User"}, pluck="name")


def people():
    """Nhan vien Active co tai khoan - cho o chon nguoi (khen / gan ten)."""
    rows = frappe.get_all("Employee", filters={"status": "Active", "user_id": ["is", "set"]},
                          fields=["user_id", "employee_name", "department"], order_by="employee_name asc",
                          limit_page_length=0)
    depts = {r.name: (r.department_name or r.name)
             for r in frappe.get_all("Department", fields=["name", "department_name"], limit_page_length=0)}
    seen, out = set(), []
    for r in rows:
        if r.user_id in seen or r.user_id in ("Guest", "Administrator"):
            continue
        seen.add(r.user_id)
        out.append({"user": r.user_id, "name": r.employee_name or r.user_id, "dept": depts.get(r.department) or ""})
    return out


def employee_user(emp):
    return frappe.db.get_value("Employee", emp, "user_id") if emp else None


# ------------------------------------------------------------------ bai --------------
def feed_rows(before=None, limit=60, kinds=None, author=None, mine=None, clubs=None, department=None,
              upcoming_after=None):
    """Bai moi nhat truoc `before`. KHONG loc an / phong ban (service loc theo nguoi xem)."""
    filters = [[C.POST_DT, "kind", "!=", C.KIND_MOMENT]]
    if before:
        filters.append([C.POST_DT, "creation", "<", before])
    if kinds:
        filters.append([C.POST_DT, "kind", "in", list(kinds)])
    if author:
        filters.append([C.POST_DT, "author", "=", author])
    if clubs is not None:
        filters.append([C.POST_DT, "club", "in", list(clubs) or ["-"]])
    if department:
        filters.append([C.POST_DT, "department", "=", department])
    if upcoming_after:
        filters.append([C.POST_DT, "event_start", ">=", upcoming_after])
    or_filters = None
    if mine:
        filters = [f for f in filters if f[1] != "author"]
        or_filters = [[C.POST_DT, "author", "=", mine], [C.POST_DT, "kudos_to", "=", mine]]
    return [dict(r) for r in frappe.get_all(C.POST_DT, filters=filters, or_filters=or_filters, fields=POST_FIELDS,
                                            order_by="creation desc", limit_page_length=limit)]


def events_between(start, end, limit=50):
    return [dict(r) for r in frappe.get_all(
        C.POST_DT, filters=[[C.POST_DT, "kind", "=", C.KIND_EVENT], [C.POST_DT, "event_start", ">=", start],
                            [C.POST_DT, "event_start", "<", end], [C.POST_DT, "hidden", "=", 0]],
        fields=POST_FIELDS, order_by="event_start asc", limit_page_length=limit)]


def club_events(club, start, limit=20):
    return [dict(r) for r in frappe.get_all(
        C.POST_DT, filters={"kind": C.KIND_EVENT, "club": club, "event_start": [">=", start]},
        fields=POST_FIELDS, order_by="event_start asc", limit_page_length=limit)]


def post(name):
    if not name:
        return None
    row = frappe.db.get_value(C.POST_DT, name, POST_FIELDS, as_dict=True)
    return dict(row) if row else None


def post_exists(name):
    return bool(name) and bool(frappe.db.exists(C.POST_DT, name))


def images_of(names):
    out = {n: [] for n in names or ()}
    if not names:
        return out
    for r in frappe.get_all(C.IMAGE_DT, filters={"parent": ["in", list(names)], "parenttype": C.POST_DT},
                            fields=["parent", "file_url", "file_name", "width", "height", "idx"],
                            order_by="idx asc", limit_page_length=0):
        out.setdefault(r.parent, []).append(dict(r))
    return out


def mentions_of(names):
    out = {n: [] for n in names or ()}
    if not names:
        return out
    for r in frappe.get_all(C.MENTION_DT, filters={"parent": ["in", list(names)], "parenttype": C.POST_DT},
                            fields=["parent", "user"], order_by="idx asc", limit_page_length=0):
        out.setdefault(r.parent, []).append(r.user)
    return out


def posts_since(user, since):
    return frappe.db.count(C.POST_DT, {"author": user, "kind": ["!=", C.KIND_MOMENT], "creation": [">=", since]})


def insert_post(values, mentions=()):
    doc = frappe.get_doc(dict(values, doctype=C.POST_DT))
    for u in mentions or ():
        doc.append("mentions", {"user": u})
    doc.insert(ignore_permissions=True)
    return doc.name


def attach_images(name, images):
    """images: [{name, content, width, height}] (da ve lai, bo EXIF). File private gan vao bai."""
    doc = frappe.get_doc(C.POST_DT, name)
    for im in images:
        fd = frappe.get_doc({"doctype": "File", "file_name": im["name"], "content": im["content"], "is_private": 1,
                             "attached_to_doctype": C.POST_DT, "attached_to_name": name})
        fd.flags.ignore_existing_file_check = True
        fd.insert(ignore_permissions=True)
        doc.append("images", {"file_url": fd.file_url, "file_name": fd.file_name,
                              "width": im.get("width") or 0, "height": im.get("height") or 0})
    doc.save(ignore_permissions=True)


def update_post(name, values):
    frappe.db.set_value(C.POST_DT, name, values, update_modified=True)


def delete_post(name):
    """Xoa bai + tep anh + binh luan / cam xuc / tham gia / bao cao cua bai."""
    for f in frappe.get_all("File", filters={"attached_to_doctype": C.POST_DT, "attached_to_name": name},
                            pluck="name"):
        frappe.delete_doc("File", f, ignore_permissions=True, force=True)
    cmts = frappe.get_all(IR.C.COMMENT_DT, filters={"ref_doctype": C.POST_DT, "post": name}, pluck="name")
    targets = [C.RX_PREFIX + name] + [IR.C.COMMENT_RX_PREFIX + c for c in cmts]
    frappe.db.delete(IR.C.REACTION_DT, {"target": ["in", targets]})
    frappe.db.delete(IR.C.COMMENT_DT, {"ref_doctype": C.POST_DT, "post": name})
    frappe.db.delete(C.RSVP_DT, {"post": name})
    frappe.db.delete(C.REPORT_DT, {"post": name})
    frappe.delete_doc(C.POST_DT, name, ignore_permissions=True, force=True)


def image_content(name, file_url):
    rows = frappe.get_all("File", filters={"file_url": file_url, "attached_to_doctype": C.POST_DT,
                                           "attached_to_name": name}, pluck="name", limit=1)
    if not rows:
        return None
    f = frappe.get_doc("File", rows[0])
    return f.file_name, f.get_content()


def clean_image(content, ext, max_side):
    """Ve lai anh: xoay theo EXIF, thu nho canh dai <= max_side, bo EXIF / GPS / ICC.
    -> (bytes, ext, width, height). Anh khong mo duoc -> ValueError."""
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(content))
        im.load()
    except Exception:
        raise ValueError("anh hong")
    if getattr(im, "is_animated", False) and ext == "gif":
        return content, ext, im.width, im.height          # GIF dong: giu nguyen (khong co EXIF)
    im = ImageOps.exif_transpose(im) or im
    im.thumbnail((max_side, max_side))
    fmt = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "gif": "PNG", "webp": "WEBP"}[ext]
    out_ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[fmt]
    clean = im.convert("RGB") if fmt == "JPEG" and im.mode not in ("RGB", "L") else im.copy()
    clean.info = {}
    buf = io.BytesIO()
    clean.save(buf, format=fmt, **({"quality": 85} if fmt == "JPEG" else {}))
    return buf.getvalue(), out_ext, clean.width, clean.height


# ------------------------------------------------------------------ khoanh khac ------
def moment_post(key):
    name = frappe.db.get_value(C.POST_DT, {"moment_key": key}, "name")
    return post(name) if name else None


def moment_posts(keys):
    if not keys:
        return {}
    return {r.moment_key: dict(r) for r in frappe.get_all(C.POST_DT, filters={"moment_key": ["in", list(keys)]},
                                                         fields=POST_FIELDS, limit_page_length=0)}


def insert_moment(key, owner_user):
    """Bai "khoanh khac" tao luc nguoi dau tien gui loi chuc. Hai nguoi cung luc -> mot ban ghi
    (moment_key unique), ben thua doc lai ban ghi kia."""
    sp = "soc_moment"
    frappe.db.savepoint(sp)
    try:
        insert_post({"kind": C.KIND_MOMENT, "moment_key": key, "author": owner_user or None})
    except Exception as exc:
        frappe.db.rollback(save_point=sp)
        if not is_duplicate(exc):
            raise
        # Ben kia vua ghi: doc KHOA (for_update) de thay ban ghi moi nhat, khong doc anh chup cu
        # cua giao dich (REPEATABLE READ).
        name = frappe.db.get_value(C.POST_DT, {"moment_key": key}, "name", for_update=True)
        return post(name) if name else None
    return moment_post(key)


# ------------------------------------------------------------------ binh luan --------
def comment_counts(names):
    return IR.comment_counts(names, ref_doctype=C.POST_DT)


def latest_comments(names, per=2):
    """{bai: [binh luan goc moi nhat, dang hien]} - xem truoc tren the bai (cu -> moi)."""
    out = {n: [] for n in names or ()}
    if not names:
        return out
    rows = frappe.db.sql(
        "select name, post, user, content, creation from `tabEC Post Comment` "
        "where ref_doctype = %s and post in %s and ifnull(parent_comment, '') = '' "
        "and ifnull(hidden, 0) = 0 and ifnull(deleted, 0) = 0 order by creation desc limit 500",
        (C.POST_DT, tuple(names)), as_dict=True)
    for r in rows:
        if len(out.setdefault(r.post, [])) < per:
            out[r.post].append(dict(r))
    return {n: list(reversed(v)) for n, v in out.items()}


# ------------------------------------------------------------------ CLB --------------
def clubs(statuses=None):
    filters = {"status": ["in", list(statuses)]} if statuses else {}
    return [dict(r) for r in frappe.get_all(C.CLUB_DT, filters=filters, fields=CLUB_FIELDS,
                                            order_by="club_name asc", limit_page_length=0)]


def club(name):
    row = frappe.db.get_value(C.CLUB_DT, name, CLUB_FIELDS, as_dict=True) if name else None
    return dict(row) if row else None


def club_by_slug(slug):
    name = frappe.db.get_value(C.CLUB_DT, {"slug": slug}, "name") if slug else None
    return club(name) if name else None


def slug_taken(slug):
    return bool(frappe.db.exists(C.CLUB_DT, {"slug": slug}))


def insert_club(values):
    doc = frappe.get_doc(dict(values, doctype=C.CLUB_DT))
    doc.insert(ignore_permissions=True)
    return doc.name


def update_club(name, values):
    frappe.db.set_value(C.CLUB_DT, name, values, update_modified=True)


def open_proposals_of(user):
    return frappe.db.count(C.CLUB_DT, {"proposed_by": user, "status": C.CLUB_PENDING})


def members(club_name):
    return frappe.get_all(C.MEMBER_DT, filters={"club": club_name}, pluck="user", order_by="creation asc",
                          limit_page_length=0)


def member_counts(names):
    out = {n: 0 for n in names or ()}
    if not names:
        return out
    for club_name, n in frappe.db.sql("select club, count(*) from `tabEC Club Member` where club in %s group by club",
                                      (tuple(names),)):
        out[club_name] = int(n or 0)
    return out


def member_samples(names, per=3):
    out = {n: [] for n in names or ()}
    if not names:
        return out
    for r in frappe.get_all(C.MEMBER_DT, filters={"club": ["in", list(names)]}, fields=["club", "user"],
                            order_by="creation asc", limit_page_length=0):
        if len(out.setdefault(r.club, [])) < per:
            out[r.club].append(r.user)
    return out


def clubs_of(user):
    return frappe.get_all(C.MEMBER_DT, filters={"user": user}, pluck="club", limit_page_length=0)


def find_member(club_name, user):
    return frappe.db.get_value(C.MEMBER_DT, {"club": club_name, "user": user}, "name")


def add_member(club_name, user):
    frappe.get_doc({"doctype": C.MEMBER_DT, "club": club_name, "user": user,
                    "dedupe_key": "%s|%s" % (club_name, user)}).insert(ignore_permissions=True)


def remove_member(name):
    frappe.delete_doc(C.MEMBER_DT, name, ignore_permissions=True, force=True)


# ------------------------------------------------------------------ tham gia su kien --
def rsvps(posts):
    if not posts:
        return []
    return [dict(r) for r in frappe.get_all(C.RSVP_DT, filters={"post": ["in", list(posts)]},
                                            fields=["name", "post", "user", "answer"], order_by="creation asc",
                                            limit_page_length=0)]


def find_rsvp(post_name, user):
    row = frappe.db.get_value(C.RSVP_DT, {"post": post_name, "user": user}, ["name", "answer"], as_dict=True)
    return dict(row) if row else None


def add_rsvp(post_name, user, answer):
    frappe.get_doc({"doctype": C.RSVP_DT, "post": post_name, "user": user, "answer": answer,
                    "dedupe_key": "%s|%s" % (post_name, user)}).insert(ignore_permissions=True)


def set_rsvp(name, answer):
    frappe.db.set_value(C.RSVP_DT, name, "answer", answer, update_modified=True)


def remove_rsvp(name):
    frappe.delete_doc(C.RSVP_DT, name, ignore_permissions=True, force=True)


# ------------------------------------------------------------------ bao cao ----------
def find_report(post_name, user):
    return frappe.db.get_value(C.REPORT_DT, {"post": post_name, "user": user}, "name")


def add_report(post_name, user, reason):
    frappe.get_doc({"doctype": C.REPORT_DT, "post": post_name, "user": user, "reason": reason,
                    "status": C.REPORT_NEW, "dedupe_key": "%s|%s" % (post_name, user)}).insert(ignore_permissions=True)


def count_reports(post_name, status=None):
    f = {"post": post_name}
    if status:
        f["status"] = status
    return frappe.db.count(C.REPORT_DT, f)


def open_reports():
    return [dict(r) for r in frappe.get_all(C.REPORT_DT, filters={"status": C.REPORT_NEW},
                                            fields=["name", "post", "user", "reason", "creation"],
                                            order_by="creation asc", limit_page_length=0)]


def close_reports(post_name, by, action, at):
    frappe.db.sql("update `tabEC Social Report` set status=%s, handled_by=%s, handled_on=%s, action=%s, "
                  "modified=%s, modified_by=%s where post=%s and status=%s",
                  (C.REPORT_DONE, by, at, action, at, by, post_name, C.REPORT_NEW))


def hidden_posts(limit=100):
    return [dict(r) for r in frappe.get_all(C.POST_DT, filters={"hidden": 1}, fields=POST_FIELDS,
                                            order_by="hidden_on desc", limit_page_length=limit)]


# ------------------------------------------------------------------ chuong -----------
def send_bell(user, title, message, url, ref_name, dedupe_key, actor=None):
    from ecentric_workspace.notification_center.events import publish_notification_event
    return publish_notification_event(C.NOTIFY_EVENT, user, title, message, action_url=url,
                                      reference_doctype=C.POST_DT if ref_name else None,
                                      reference_name=ref_name or None, actor=actor, from_user=actor,
                                      dedupe_key=dedupe_key)
