# Copyright (c) 2026, eCentric and contributors
"""Thong bao cua module Ky luat: chuong ERP + Teams qua notification_center (ton trong gio yen
lang 21h-9h va cai dat cua tung nguoi), them email khi thu tuc bat buoc (thong bao hop ky luat,
quyet dinh) - email vao Email Queue (gui nen), khong goi ra ngoai trong giao dich.

Nuot loi tung nguoi nhan: thong bao hong khong duoc lam hong thao tac nghiep vu - nhung ghi
Error Log de HR biet ma bao tay."""
import frappe

EVENT_ACTION = "task_assigned"


def _abs(url):
    if not url:
        return None
    if url.startswith("http"):
        return url
    return frappe.utils.get_url() + url


def send(users, subject, doctype, name, message="", url=None, email=False, severity=None):
    from ecentric_workspace.notification_center import events as ncev
    stamp = frappe.utils.now_datetime().strftime("%Y%m%d%H%M%S%f")
    sent = []
    for u in dict.fromkeys(u for u in users or () if u and u not in ("Guest", "Administrator")):
        try:
            ncev.publish_notification_event(
                EVENT_ACTION, u, subject, message=message or "", severity=severity,
                action_url=_abs(url), reference_doctype=doctype, reference_name=name,
                dedupe_key="|".join(("ky_luat", doctype or "", name or "", u, stamp)))
            sent.append(u)
        except Exception:
            frappe.log_error(title="ky_luat notify %s" % u, message=frappe.get_traceback())
    if email and sent:
        try:
            body = "<p>%s</p>%s" % (frappe.utils.escape_html(subject),
                                    ("<p>%s</p>" % frappe.utils.escape_html(message)) if message else "")
            if url:
                body += '<p><a href="%s">Mở trên ERP</a></p>' % _abs(url)
            frappe.sendmail(recipients=sent, subject=subject, message=body,
                            reference_doctype=doctype, reference_name=name, delayed=True)
        except Exception:
            frappe.log_error(title="ky_luat email %s" % name, message=frappe.get_traceback())
