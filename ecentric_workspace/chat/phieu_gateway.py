# Copyright (c) 2026, eCentric and contributors
"""Phieu trong chat - phan noi Frappe / Approval Center / Raven. KHONG sua Raven, KHONG sua
Approval Center: chi doc registry loai phieu + EC Approval Type.route, va nghe 2 su kien.

Ba hook (hooks.py):
  document_link(doctype, docname)        raven_document_link_override: the phieu trong chat mo
                                         /approvals/<route>?id=<ten>, khong mo Desk.
  on_raven_message_before_insert(doc)    doc_events Raven Message: tin co link phieu ERP ->
                                         gan the phieu (Raven tu ve the + tu kiem quyen xem).
  on_delivery_log_after_insert(doc)      doc_events EC Notification Delivery Log: dong "erp" cua
                                         thong bao phe duyet -> xep hang gui tin bot (sau commit).

Moi loi deu bi nuot (ghi logger): luong duyet phieu va luong chat KHONG BAO GIO hong vi lop nay.
"""
import frappe

from ecentric_workspace.chat import constants as C
from ecentric_workspace.chat import phieu as P

_CACHE_KEY = "ec_chat_phieu_routes"
_CACHE_TTL = 600


def _warn(msg):
    try:
        frappe.logger("ec_chat").warning(msg, exc_info=True)
    except Exception:
        pass


def _off(flag):
    try:
        return bool(frappe.conf.get(C.PHIEU_KILL_SWITCH) or (flag and frappe.conf.get(flag)))
    except Exception:
        return True


# ------------------------------------------------------------------ route <-> doctype
def _maps():
    """({route: doctype}, {doctype: route}) cho cac loai phieu co route. Cache 10 phut."""
    cache = frappe.cache()
    hit = cache.get_value(_CACHE_KEY)
    if hit:
        return hit["r2d"], hit["d2r"]
    from ecentric_workspace.approval_center.shared.registry import APPROVAL_DEFINITIONS
    rows = frappe.get_all("EC Approval Type", fields=["name", "route"], limit_page_length=0)
    r2d, d2r = {}, {}
    for row in rows:
        route = P.norm_route(row.get("route"))
        definition = APPROVAL_DEFINITIONS.get(row.get("name"))
        if not route or definition is None:
            continue
        r2d[route] = definition.business_doctype
        d2r[definition.business_doctype] = route
    cache.set_value(_CACHE_KEY, {"r2d": r2d, "d2r": d2r}, expires_in_sec=_CACHE_TTL)
    return r2d, d2r


def erp_path(doctype, docname):
    """/approvals/<route>?id=<ten> cho phieu, None cho doctype khac."""
    if not doctype or not docname:
        return None
    route = _maps()[1].get(doctype)
    if not route:
        return None
    from urllib.parse import quote
    return "%s?id=%s" % (route, quote(str(docname), safe=""))


def document_link(doctype, docname):
    """Hook raven_document_link_override. Tra duong dan TUONG DOI (Raven tu ghep get_url)."""
    try:
        if _off(None):
            return None
        return erp_path(doctype, docname)
    except Exception:
        _warn("document_link skipped")
        return None


# ------------------------------------------------------------------ dan link phieu
def _hosts():
    from urllib.parse import urlsplit
    hosts = {h.lower() for h in C.ERP_HOSTS}
    try:
        h = urlsplit(frappe.utils.get_url()).hostname
        if h:
            hosts.add(h.lower())
    except Exception:
        pass
    return hosts


def on_raven_message_before_insert(doc, method=None):
    try:
        if _off(None) or doc.get("is_bot_message") or doc.get("link_document"):
            return
        if (doc.get("message_type") or "Text") != "Text":
            return
        r2d, _d2r = _maps()
        found = P.find_approval_link(doc.get("text"), _hosts(), set(r2d))
        if not found:
            return
        route, docname = found
        doctype = r2d[route]
        sender = doc.get("owner") or frappe.session.user
        if not frappe.db.exists(doctype, docname):
            return
        # Nguoi gui khong xem duoc phieu -> giu link tran (khong de lo tieu de / so tien).
        if not frappe.has_permission(doctype, "read", doc=docname, user=sender):
            return
        doc.link_doctype = doctype
        doc.link_document = docname
        doc.hide_link_preview = 1          # xem truoc web cua link noi bo chi ra trang dang nhap
    except Exception:
        _warn("raven message phieu link skipped")


# ------------------------------------------------------------------ bot thong bao
def on_delivery_log_after_insert(doc, method=None):
    try:
        if doc.get("channel") != "erp" or doc.get("status") != "Sent":
            return
        if doc.get("event_type") not in C.BOT_EVENT_TYPES or _off(C.BOT_KILL_SWITCH):
            return
        frappe.enqueue("ecentric_workspace.chat.phieu_gateway.send_bot_message",
                       queue="short", enqueue_after_commit=True, delivery_log=doc.name)
    except Exception:
        _warn("enqueue chat bot skipped")


def _is_chat_user(user):
    if not user or user in ("Guest", "Administrator"):
        return False
    if C.RAVEN_ROLE not in (frappe.get_roles(user) or []):
        return False
    return bool(frappe.db.get_value("Raven User", {"user": user, "enabled": 1}, "name"))


def ensure_bot():
    """Raven Bot ten C.BOT_NAME; tao neu chua co (Raven tu tao Raven User loai Bot)."""
    if frappe.db.exists("Raven Bot", C.BOT_NAME):
        return frappe.get_doc("Raven Bot", C.BOT_NAME)
    bot = frappe.get_doc({"doctype": "Raven Bot", "bot_name": C.BOT_NAME,
                          "description": C.BOT_DESCRIPTION, "image": C.BOT_IMAGE})
    bot.insert(ignore_permissions=True)
    return bot


def send_bot_message(delivery_log):
    """Job nen: doc dong Delivery Log, gui tin rieng cho nguoi nhan kem the phieu."""
    try:
        if _off(C.BOT_KILL_SWITCH) or C.RAVEN_APP not in (frappe.get_installed_apps() or []):
            return
        row = frappe.db.get_value(
            "EC Notification Delivery Log", delivery_log,
            ["recipient", "title", "message", "action_url", "reference_doctype",
             "reference_name"], as_dict=True)
        if not row or not _is_chat_user(row.recipient):
            return
        doctype, docname = row.reference_doctype or None, row.reference_name or None
        path = erp_path(doctype, docname)
        url = row.action_url or (frappe.utils.get_url() + path if path else "")
        link = bool(path) and frappe.db.exists(doctype, docname)
        ensure_bot().send_direct_message(
            row.recipient, text=P.bot_html(row.title, row.message, url),
            link_doctype=doctype if link else None, link_document=docname if link else None)
    except Exception:
        frappe.log_error(title="ec_chat bot", message=frappe.get_traceback())
