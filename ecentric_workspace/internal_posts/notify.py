# Copyright (c) 2026, eCentric and contributors
"""Job nen: bao tin khi mot bai duoc dang (lifecycle.after_save xep job SAU commit).

Hai kenh, PO chot 01/10/2026:
  * Chuong ERP: MOT thong bao cho moi nguoi trong pham vi bai, gui MOT lan cho ca doi bai
    (notified_on). Sua bai / dang lai sau khi go KHONG gui lan hai. Di qua
    notification_center.events.publish_notification_event voi event "announcement"
    (Teams = False khoa cung trong ROUTING_MATRIX; web push bat). Dedupe theo bai + nguoi:
    job chay lai (retry, hai worker) khong de ra thong bao trung.
    v6 (03/10): HR tich "Gui kem tin nhan Teams" -> event "announcement_urgent" (co san,
    teams = True): moi nguoi them MOT tin Teams. Bai bat buoc xac nhan: tieu de chuong ghi ro.
    Bai hen gio: job nay chay khi schedule.publish_due dang bai (khong phai luc HR bam hen).
  * Popup trang chu: home_today.announce_service (dung chung) - chi bai toan cong ty.

Idempotent: chay lai bao nhieu lan cung ra mot ket qua. Loi tung nguoi khong giet ca dot.
Link trong thong bao tro /tin-noi-bo/<slug> - KHONG BAO GIO /app (nguoi dung portal khong mo
duoc Desk, xem QC gate test_no_desk_urls).
"""
import frappe

from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts import domain as D
from ecentric_workspace.internal_posts import repository as R
from ecentric_workspace.internal_posts import service


def run(post):
    frappe.logger("internal_posts").info("notify start %s" % post)
    if not R.post_exists(post):
        return {"skipped": "missing"}
    doc = R.get_post(post)
    if not doc.published:
        return {"skipped": "unpublished"}
    depts = [r.department for r in doc.departments if r.department]
    url = "%s/%s" % (C.ROUTE, doc.slug)
    out = {"bell_sent": 0, "bell_failed": 0, "popup": None}

    if doc.notify_bell and not doc.notified_on:
        from ecentric_workspace.notification_center.events import publish_notification_event
        title = doc.title
        message = doc.summary or ""
        if doc.require_ack:
            title = "Cần xác nhận đã đọc: %s" % doc.title
            dl = D.date_label(doc.ack_deadline)
            message = ("Hạn xác nhận %s. " % dl if dl else "") + message
        # v6: "Gui kem tin nhan Teams" -> event co san announcement_urgent (teams = True).
        event = C.NOTIFY_EVENT_TEAMS if doc.notify_teams else C.NOTIFY_EVENT
        out["teams"] = bool(doc.notify_teams)
        for user in service.audience(R, depts):
            if user == doc.owner:
                continue
            try:
                publish_notification_event(
                    event, user, title, message, action_url=url,
                    reference_doctype=C.POST_DT, reference_name=doc.name,
                    actor=doc.owner, from_user=doc.owner,
                    dedupe_key="internal_post|%s|%s" % (doc.name, user))
                out["bell_sent"] += 1
            except Exception:
                out["bell_failed"] += 1
                R.log_error("internal_posts.notify.bell")

    if doc.push_to_home and D.popup_allowed(len(depts)):
        from ecentric_workspace.home_today import announce_service
        cat = D.category_view(R.category(doc.category))
        start, end = D.popup_window(R.today(), doc.expires_on)
        image = doc.cover_image if doc.cover_kind == C.COVER_KIND_IMAGE else ""
        out["popup"] = announce_service.publish_from_source(
            C.POST_DT, doc.name, "", doc.title, category=cat.get("home_category"),
            summary=doc.summary or D.plain_text(doc.content, 220), link=url,
            link_label=C.POPUP_LINK_LABEL, image=image, start_date=start, end_date=end,
            image_link=bool(doc.popup_image_link))
        if out["popup"] and doc.home_announcement != out["popup"]:
            R.set_post_fields(doc.name, {"home_announcement": out["popup"]})

    if not doc.notified_on:
        R.set_post_fields(doc.name, {"notified_on": R.now()})
    R.commit()
    frappe.logger("internal_posts").info("notify done %s %s" % (post, out))
    return out
