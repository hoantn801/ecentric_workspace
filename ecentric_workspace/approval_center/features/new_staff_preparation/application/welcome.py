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
                                  "welcome_intro", "approval_request", "welcome_teams_sent_at",
                                  "line_manager", "new_employee", "onboard_date"],
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


def card_payload(r):
    """Them cho THIEP (khong dua ra popup): ten quan ly truc tiep + email cong ty cua nhan vien
    moi (nut "Nhan chao" mo chat Teams 1-1). Thieu du lieu thi bo truong, khong loi."""
    p = payload(r)
    lm = (r.get("line_manager") or "").strip()
    p["line_manager_name"] = (lm and (frappe.db.get_value("User", lm, "full_name") or "")) or ""
    email = ""
    if r.get("new_employee"):
        e = frappe.db.get_value("Employee", r.new_employee, ["company_email", "user_id"], as_dict=True)
        email = e and (e.get("company_email") or e.get("user_id")) or ""
    p["chat_email"] = email if "@" in (email or "") else ""
    p["onboard_date"] = str(r.get("onboard_date") or "")
    return p


_THU = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")


def _ngay(s):
    try:
        d = datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return ""
    return "%s, %02d/%02d/%d" % (_THU[d.weekday()], d.day, d.month, d.year)


def _ten_goi(full):
    """Ten de goi ("Nguyen Vu Duy Phong" -> "Phong")."""
    parts = (full or "").split()
    return parts[-1] if parts else ""


def build_card(p):
    """Adaptive Card cho Workflow webhook ("Send webhook alerts to a chat").

    Giu bo cuc thiep HR van gui (24/11 Hoan gui mau), lam gon + ro hon:
      * dai tieu de mau nhan (Container accent) + thu, ngay onboard;
      * ten giu nguyen hoa thuong nhu HR viet (khong UPPER);
      * them Quan ly truc tiep (neu co);
      * loi gioi thieu: thanh doc ben trai + chu nghieng (RichTextBlock), giu xuong dong;
      * nut "Nhan chao <ten>" mo chat Teams 1-1 (chi khi biet email cong ty).
    KHONG co gi ve luong."""
    ten = (p.get("candidate_name") or "").strip()
    header = [{"type": "TextBlock", "text": "\U0001F31F Chào mừng thành viên mới \U0001F31F",
               "weight": "Bolder", "size": "Large", "wrap": True, "color": "Accent"}]
    ngay = _ngay(p.get("onboard_date"))
    if ngay:
        header.append({"type": "TextBlock", "text": ngay, "isSubtle": True, "spacing": "None",
                       "wrap": True})
    facts = [{"title": "Tên:", "value": ten or "—"},
             {"title": "Vị trí:", "value": p.get("position") or "—"},
             {"title": "Bộ phận:", "value": p.get("department") or "—"}]
    if p.get("line_manager_name"):
        facts.append({"title": "Quản lý:", "value": p["line_manager_name"]})
    body = [
        {"type": "Container", "style": "accent", "bleed": True, "items": header},
        {"type": "TextBlock", "wrap": True, "spacing": "Medium",
         "text": "Mọi người ơi, hôm nay **eCentric** chính thức chào đón thành viên mới:"},
        {"type": "FactSet", "facts": facts},
    ]
    intro = (p.get("welcome_intro") or "").strip()
    if intro:
        doan = [d.strip() for d in intro.replace("\r\n", "\n").split("\n") if d.strip()]
        body += [
            {"type": "TextBlock", "text": "Đôi lời giới thiệu từ chính chủ:", "weight": "Bolder",
             "wrap": True, "spacing": "Medium"},
            {"type": "ColumnSet", "spacing": "Small", "columns": [
                {"type": "Column", "width": "4px", "style": "emphasis", "bleed": False,
                 "items": [{"type": "TextBlock", "text": " "}]},
                {"type": "Column", "width": "stretch", "items": [
                    {"type": "RichTextBlock", "spacing": "Small" if k else "None", "inlines": [
                        {"type": "TextRun", "text": d, "italic": True}]}
                    for k, d in enumerate(doan)]},
            ]},
        ]
    body += [
        {"type": "TextBlock", "wrap": True, "spacing": "Medium",
         "text": "Cả nhà cùng **say hi** và hỗ trợ nhân viên mới trong thời gian đầu làm quen nhé!"},
        {"type": "TextBlock", "wrap": True, "weight": "Bolder",
         "text": "Welcome on board, %s! \U0001F680 \U0001F499" % (ten or "bạn mới")},
    ]
    card = {"type": "AdaptiveCard", "version": "1.4",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "body": body,
            "msteams": {"width": "Full"}}
    if p.get("chat_email"):
        from urllib.parse import quote
        goi = _ten_goi(ten) or ten
        loi = "Chào %s, chào mừng bạn đến với eCentric! \U0001F44B" % goi
        card["actions"] = [{"type": "Action.OpenUrl",
                            "title": "\U0001F44B Nhắn chào %s" % goi,
                            "url": "https://teams.microsoft.com/l/chat/0/0?users=%s&message=%s"
                                   % (quote(p["chat_email"]), quote(loi))}]
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
            code, text = _post(url, build_card(card_payload(r)))
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
