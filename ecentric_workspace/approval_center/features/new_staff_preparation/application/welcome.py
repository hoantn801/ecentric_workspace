# Copyright (c) 2026, eCentric and contributors
"""Chao mung nhan vien moi NGAY ONBOARD (28/09/2026, Hoan chot gio).

  * 08:30 tro di: popup tren trang chu ERP cho moi nguoi (public/js/ec_welcome_popup.js goi
    `welcome_today`); moi nguoi thay MOT lan / nhan vien moi (nho o trinh duyet).
    CHUA BAT: A65 §6 cam module chen DOM vao trang chu - popup cho khe widget trang chu.
  * 10:00: thiep "Chao mung thanh vien moi" len Teams qua MOT Workflow webhook do HR tao
    trong group chat chung (site_config `ec_onboard_welcome_webhook_url`) - thay flow Power
    Automate cu. Moi phieu gui MOT lan (danh dau welcome_teams_sent_at).

Du lieu lay tu New Staff Preparation: ten, vi tri, bo phan, loi gioi thieu HR dien truoc.
KHONG co gi ve luong. Phieu da Huy / Tu choi thi khong chao.

Kill switch: site_config `ec_onboard_welcome_disabled` = 1 (tat ca popup lan Teams)."""
import datetime

import frappe
from frappe.utils import now_datetime, nowdate

BUSINESS_DT = "EC New Staff Preparation"
WEBHOOK_CONF = "ec_onboard_welcome_webhook_url"
KILL_CONF = "ec_onboard_welcome_disabled"
POPUP_FROM = datetime.time(8, 30)
_CHET = ("Rejected", "Cancelled")
TIMEOUT = 15


def _disabled():
    return bool(frappe.conf.get(KILL_CONF))


def today_rows(day=None):
    """Phieu co ngay onboard = hom nay, da gui, chua Huy/Tu choi."""
    day = day or nowdate()
    rows = frappe.get_all(BUSINESS_DT, filters={"onboard_date": day},
                          fields=["name", "candidate_name", "position", "department",
                                  "welcome_intro", "approval_request", "welcome_teams_sent_at"],
                          order_by="creation asc", limit_page_length=0)
    out = []
    for r in rows:
        if not r.approval_request:
            continue
        st = frappe.db.get_value("EC Approval Request", r.approval_request, "approval_status")
        if st in _CHET:
            continue
        out.append(r)
    return out


def payload(r):
    dept = r.department and (frappe.db.get_value("Department", r.department, "department_name")
                             or r.department)
    return {"name": r.name, "candidate_name": (r.candidate_name or "").strip(),
            "position": r.position or "", "department": dept or "",
            "welcome_intro": (r.welcome_intro or "").strip()}


def welcome_today():
    """Cho popup trang chu (whitelist o controllers/api.py). Nguoi da dang nhap; tu 08:30."""
    if frappe.session.user == "Guest" or _disabled():
        return {"rows": []}
    if now_datetime().time() < POPUP_FROM:
        return {"rows": []}
    return {"rows": [payload(r) for r in today_rows()]}


def build_card(p):
    """Adaptive Card cho Workflow webhook ("Post card in a chat or channel")."""
    ten = (p["candidate_name"] or "").upper()
    body = [
        {"type": "TextBlock", "text": "\U0001F31F Chào mừng thành viên mới \U0001F31F",
         "weight": "Bolder", "size": "Large", "wrap": True},
        {"type": "TextBlock", "wrap": True,
         "text": "Mọi người ơi, hôm nay **eCentric** chính thức chào đón thành viên mới:"},
        {"type": "FactSet", "facts": [
            {"title": "Tên:", "value": ten},
            {"title": "Vị trí:", "value": p.get("position") or "—"},
            {"title": "Bộ phận:", "value": p.get("department") or "—"}]},
    ]
    if p.get("welcome_intro"):
        body += [
            {"type": "TextBlock", "text": "Đôi lời giới thiệu từ chính chủ:", "weight": "Bolder",
             "wrap": True, "spacing": "Medium"},
            {"type": "Container", "style": "emphasis", "items": [
                {"type": "TextBlock", "text": p["welcome_intro"], "wrap": True, "isSubtle": True}]},
        ]
    body += [
        {"type": "TextBlock", "wrap": True, "spacing": "Medium",
         "text": "Cả nhà cùng **say hi** và hỗ trợ nhân viên mới trong thời gian đầu làm quen nhé!"},
        {"type": "TextBlock", "wrap": True, "weight": "Bolder",
         "text": "Welcome on board, %s! \U0001F680 \U0001F499" % ten},
    ]
    card = {"type": "AdaptiveCard", "version": "1.4",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "body": body}
    return {"type": "message", "attachments": [
        {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}]}


def _post(url, data):
    import requests
    r = requests.post(url, json=data, timeout=TIMEOUT)
    return r.status_code, (r.text or "")[:300]


def send_welcome_teams():
    """Scheduler 10:00, chay lai 10:15 / 10:30 / 10:45 (hooks.py). Idempotent: phieu da gui
    thi bo qua, nen lan sau chi gui lai phieu lan truoc loi (Teams / mang chap chon).
    Moi phieu mot try/except."""
    if _disabled():
        return {"skipped": "disabled"}
    rows = [r for r in today_rows() if not r.welcome_teams_sent_at]
    if not rows:
        return {"sent": 0}
    url = (frappe.conf.get(WEBHOOK_CONF) or "").strip()
    if not url:
        frappe.log_error(title="Onboard welcome: chua cau hinh webhook",
                         message="Co %d nhan vien onboard hom nay (%s) nhung site_config chua co %s."
                                 % (len(rows), ", ".join(r.name for r in rows), WEBHOOK_CONF))
        return {"sent": 0, "skipped": "no_webhook"}
    sent = 0
    for r in rows:
        try:
            code, text = _post(url, build_card(payload(r)))
            ok = 200 <= int(code) < 300
            frappe.db.set_value(BUSINESS_DT, r.name, {
                "welcome_teams_sent_at": now_datetime() if ok else None,
                "welcome_teams_result": ("OK %s" % code) if ok else ("HTTP %s %s" % (code, text)),
            }, update_modified=False)
            if ok:
                sent += 1
            else:
                frappe.log_error(title="Onboard welcome Teams %s: HTTP %s" % (r.name, code),
                                 message=text)
        except Exception:
            frappe.log_error(title="Onboard welcome Teams %s" % r.name, message=frappe.get_traceback())
            frappe.db.set_value(BUSINESS_DT, r.name, "welcome_teams_result",
                                "LOI - xem Error Log", update_modified=False)
        frappe.db.commit()
    return {"sent": sent, "total": len(rows)}
