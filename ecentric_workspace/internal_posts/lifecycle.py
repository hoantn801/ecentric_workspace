# Copyright (c) 2026, eCentric and contributors
"""Vong doi mot bai Tin noi bo - controller EC Internal Post goi vao day.

Trang viet bai (/tin-noi-bo/viet-bai) va form /app CUNG di qua day, nen quy tac chi co mot ban:
  validate   : chuan hoa + kiem (domain.validate), sinh slug, ghi published_on lan dau dang,
               tat "dua len popup" khi bai theo phong ban (popup hien cho moi nguoi).
  after_save : lan DAU bai o trang thai da dang -> xep job bao tin (chuong + popup) sau commit;
               go bai (bo dang) -> rut thong bao popup cua bai.
  on_trash   : rut thong bao popup.
"""
import frappe
from frappe import _

from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts import domain as D
from ecentric_workspace.internal_posts import repository as R


def _was(doc, field):
    before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
    return before.get(field) if before else None


def validate(doc):
    doc.title = (doc.title or "").strip()
    doc.summary = (doc.summary or "").strip()
    depts = [r.department for r in (doc.get("departments") or []) if r.department]
    # bo dong trung phong (chon 2 lan)
    if len(depts) != len(set(depts)):
        keep, rows = set(), []
        for r in doc.departments:
            if r.department and r.department not in keep:
                keep.add(r.department)
                rows.append(r)
        doc.departments = rows
        depts = [r.department for r in rows]
    if not D.popup_allowed(len(depts)):
        doc.push_to_home = 0
    if doc.cover_kind not in (C.COVER_KIND_COLOR, C.COVER_KIND_IMAGE):
        doc.cover_kind = C.COVER_KIND_COLOR
    if doc.cover_kind == C.COVER_KIND_COLOR and not doc.cover_color:
        cat = R.category(doc.category) or {}
        doc.cover_color = cat.get("color") or C.COVER_COLOR_DEFAULT
    # Ngay bai LEN: bai hen gio vua duoc job dang -> ngay da hen (job tre qua nua dem van dung luat
    # luc HR hen); bai dang hen -> ngay hen; con lai -> hom nay.
    was_sched = _was(doc, "publish_at") if doc.published and not _was(doc, "published") else None
    start_at = doc.publish_at or was_sched
    ref_day = min(R.today(), D.as_date(start_at)) if was_sched else R.today()
    if doc.published:
        doc.publish_at = None                       # da dang thi khong con hen
    if not doc.notify_bell:
        doc.notify_teams = 0                        # Teams di kem chuong
    if not doc.require_ack:
        doc.ack_deadline = None
    # bai HEN GIO kiem nhu bai dang (chuyen muc bat buoc, han...) - toi gio job dang thang.
    going_live = bool(doc.published or doc.publish_at)
    post = {
        "title": doc.title, "category": doc.category, "scope": "dept" if depts else "all",
        "expires_on": doc.expires_on, "published": going_live, "_was_published": _was(doc, "published"),
        "cover_color": doc.cover_color, "cover_kind": doc.cover_kind, "cover_image": doc.cover_image,
        "publish_at": start_at, "require_ack": doc.require_ack, "ack_deadline": doc.ack_deadline,
    }
    errs = D.validate(post, ref_day, R.category_exists, len(depts))
    if going_live:
        errs += D.check_dates(post, ref_day)
    if len(doc.get("attachments") or []) > C.MAX_ATTACHMENTS:
        errs.append(_("Tối đa {0} tệp đính kèm.").format(C.MAX_ATTACHMENTS))
    errs += _foreign_files(doc)
    if errs:
        frappe.throw("<br>".join(errs), title=_("Bài chưa lưu được"))
    _set_slug(doc)
    if doc.published and not doc.published_on:
        doc.published_on = R.now()


def _foreign_files(doc):
    """Anh bia / tep dinh kem phai la File DA GAN VAO CHINH BAI NAY (ca khi luu tu /app, REST).
    Khong co chot nay: dan duong dan tep private cua ho so khac -> moi nguoi doc bai tai duoc."""
    errs = []
    if doc.cover_kind == C.COVER_KIND_IMAGE and doc.cover_image:
        f = R.file_info(doc.cover_image, doc.name)
        if not f or f.get("is_private"):
            errs.append(_("Ảnh bìa phải là ảnh tải lên (hoặc AI tạo) cho chính bài này."))
    for row in doc.get("attachments") or []:
        f = R.file_info(row.file_url, doc.name)
        if not f or not f.get("is_private"):
            errs.append(_("Tệp đính kèm phải tải lên cho chính bài này: {0}").format(row.file_name or row.file_url))
    return errs


def _set_slug(doc):
    """Slug sinh tu tieu de; sau khi bai DA DANG thi giu nguyen (link da gui di khong duoc gay)."""
    wanted = doc.slug or doc.title
    # Da tung dang (co published_on) thi giu link: chuong / popup cu da tro toi no.
    if doc.slug and _was(doc, "published_on") and _was(doc, "slug") == doc.slug:
        return
    doc.slug = D.unique_slug(wanted, lambda s: R.slug_taken(s, exclude=doc.name))


def after_save(doc):
    was_pub = bool(_was(doc, "published"))
    has_depts = any(r.department for r in (doc.get("departments") or []))
    popup_on = bool(doc.push_to_home) and not has_depts
    # Bai DANG HIEN ma tat popup / thu hep pham vi -> rut popup ngay (popup hien cho MOI nguoi).
    if was_pub and doc.published and not popup_on:
        _withdraw(doc.name)
    # Lan dau dang, dang LAI sau khi go, hoac bai dang hien co popup (bat moi / doi tieu de, han):
    # job tu xet - chuong chi gui MOT lan (notified_on), popup cap nhat cho dung bai.
    if doc.published and ((not was_pub and (doc.notify_bell or popup_on)) or (not doc.notified_on and doc.notify_bell)
                          or popup_on):
        frappe.enqueue("ecentric_workspace.internal_posts.notify.run", post=doc.name,
                       queue="short", timeout=600, enqueue_after_commit=True,
                       job_id="ec_internal_post_notify::" + doc.name, deduplicate=True)
    if was_pub and not doc.published:
        _withdraw(doc.name)


def on_trash(doc):
    _withdraw(doc.name)


def _withdraw(name):
    try:
        from ecentric_workspace.home_today import announce_service
        announce_service.withdraw_source(C.POST_DT, name)
    except Exception:
        R.log_error("internal_posts.withdraw_popup")
