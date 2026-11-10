# Copyright (c) 2026, eCentric and contributors
"""Kien thuc ERP cho AI hoi dap (eC Mate + o chat trang chu) - Hoan 10/11/2026:
"AI hieu toan bo thong tin tren ERP, theo phan quyen nhan su; hoi luong nguoi khac thi khong
duoc tra loi".

HAI LUAT, KHONG NOI LONG:
  1. MOI NGUON doc DUNG cai nguoi hoi tu mo duoc tren trang cua module do - goi lai ham ma
     chinh trang do dung, chay duoi quyen nguoi dang dang nhap (khao sat = hub cua /khao-sat,
     tin noi bo = list_page cua /tin-noi-bo, tai lieu = thu vien /tai-lieu, phieu = phieu
     CUA MINH + phieu dang cho MINH duyet, cong viec = task giao cho MINH, phep = phep CUA
     MINH). Khong co nguon nao doc bang `frappe.get_all` vo quyen tren du lieu nguoi khac.
  2. LUONG / THU NHAP: khong co nguon nao cham toi (Salary Slip, Salary Structure, phu cap...).
     Cau hoi ve luong -> tra loi co dinh, KHONG goi AI (salary_question), chi chi duong toi
     trang phieu luong cua chinh nguoi do.

Chon nguon theo tu khoa trong cau (pick_sources, PURE) - chi lay cai can, it token, it lo.
Moi nguon hong -> bo nguon do (ghi Error Log), cac nguon khac van chay.
"""
import re
import unicodedata

SURVEY, NEWS, DOCS, TASKS, APPROVALS, LEAVE, DATA, WEEKLY = (
    "survey", "news", "docs", "tasks", "approvals", "leave", "data", "weekly")
#: Khong khop tu khoa nao -> nhin tong quan nhe (viec cua toi + phieu + khao sat dang mo).
DEFAULT_SOURCES = (WEEKLY, TASKS, APPROVALS, SURVEY)
MAX_ITEMS = 15
SALARY_ROUTE = "/ec-hr/salary"

#: Tu khoa da BO DAU, chu thuong (xem fold()).
KEYWORDS = {
    SURVEY: ("khao sat", "survey", "vong quay", "quay so", "phieu khao"),
    NEWS: ("tin noi bo", "tin tuc", "thong bao", "bai viet", "ban tin", "tin moi"),
    DOCS: ("tai lieu", "quy trinh", "quy dinh", "iso", "chinh sach", "bieu mau", "huong dan",
           "noi quy", "so tay"),
    TASKS: ("cong viec", "task", "viec cua", "deadline", "han chot", "du an", "viec can lam",
            "viec dang lam"),
    APPROVALS: ("phieu", "phe duyet", "cho duyet", "duyet", "de nghi", "trang thai yeu cau",
                "yeu cau cua"),
    LEAVE: ("ngay phep", "phep con", "con bao nhieu ngay", "so ngay nghi", "quy phep",
            "phep nam", "nghi phep con"),
    DATA: ("yeu cau du lieu", "trung tam du lieu", "crawl", "data hub"),
    WEEKLY: ("bao cao tuan", "weekly", "bao cao", "tien do", "mood", "tam trang", "blocker",
             "phong minh", "team", "diem ai", "ai score"),
}
#: Nguon chac chan la TRA CUU (khong phai tao phieu) - router cua eC Mate dung de khong hoi
#: nham "AI Topup hay System Request?" khi nguoi dung chi hoi ve khao sat / tai lieu.
LOOKUP_ONLY = (SURVEY, NEWS, DOCS, LEAVE, TASKS)

_SALARY = re.compile(
    r"(lương|thu nhập|salary|payroll|payslip|"
    r"\b(bang|phieu|muc|tien|quy|he so)\s+luong\b|\bluong\s+(cua|thang|co ban|net|gross)\b|"
    r"\bthu nhap\b)", re.I)


def fold(text):
    """PURE. Chu thuong, bo dau tieng Viet (d/D -> d) - de khop tu khoa du go co dau hay khong."""
    t = unicodedata.normalize("NFD", str(text or "").lower())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return t.replace("đ", "d")


def salary_question(message):
    """PURE. Cau nay hoi ve luong / thu nhap? (cua ai cung vay - AI khong tra loi)."""
    return bool(_SALARY.search(str(message or "")))


SALARY_REPLY = ("Mình không tra cứu hay trả lời về lương, thu nhập của bất kỳ ai. "
                "Phiếu lương của bạn xem ở trang Nhân sự › Phiếu lương (%s)." % SALARY_ROUTE)


def pick_sources(message):
    """PURE. -> danh sach nguon theo thu tu KEYWORDS; khong khop gi -> DEFAULT_SOURCES."""
    t = " %s " % fold(message)
    hit = [src for src, words in KEYWORDS.items()
           if any(re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(w), t) for w in words)]
    return hit or list(DEFAULT_SOURCES)


def is_lookup(message):
    """PURE. Cau nhac toi khao sat / tin / tai lieu / phep con lai / viec cua minh -> tra cuu."""
    t = " %s " % fold(message)
    return any(re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(w), t)
               for src in LOOKUP_ONLY for w in KEYWORDS[src])


def _short(text, cap=160):
    t = " ".join(str(text or "").split())
    return t if len(t) <= cap else t[:cap - 1] + "…"


def render(sections):
    """PURE. [(tieu de, [dong])] -> khoi van ban cho loi dan. Bo khoi rong."""
    out = []
    for title, lines in sections:
        if not lines:
            continue
        out += ["", "=== %s ===" % title] + ["- " + _short(l, 300) for l in lines[:MAX_ITEMS]]
    return "\n".join(out)


# ------------------------------------------------------------------ nguon (impure) --
# Moi ham: (user) -> [dong]. Chay duoi frappe.session.user = nguoi hoi.

def _survey(user):
    from ecentric_workspace.surveys.controllers import api
    data = (api.hub() or {}).get("data") or {}
    lines = []
    for c in data.get("open") or []:
        lines.append("CHO BAN LAM: %s%s - %s cau hoi%s - mo tai /khao-sat" % (
            c.get("title"), (" (han %s)" % c["close_at"]) if c.get("close_at") else "",
            c.get("questions") or "?", (" - " + _short(c["description"], 120)) if c.get("description") else ""))
    for c in data.get("done") or []:
        lines.append("BAN DA NOP: %s - luc %s%s" % (
            c.get("title"), c.get("submitted_at") or "?",
            (" - qua: " + c["prize_label"]) if c.get("prize_label") else ""))
    return lines


def _news(user):
    from ecentric_workspace.internal_posts import service
    ctx = service.list_page(user) or {}
    cards = []
    for sec in ctx.get("sections") or []:
        cards += sec.get("cards") or []
    if ctx.get("pin"):
        cards.insert(0, ctx["pin"])
    seen, lines = set(), []
    for c in cards:
        if c.get("name") in seen or c.get("draft"):
            continue
        seen.add(c.get("name"))
        lines.append("%s [%s, %s]%s - %s" % (
            c.get("title"), (c.get("category") or {}).get("name") or "", c.get("date_label") or "",
            (": " + _short(c["summary"], 140)) if c.get("summary") else "", c.get("url") or "/tin-noi-bo"))
    return lines


def _docs(user):
    from ecentric_workspace.iso_docs import library
    ctx = library.library_page(user) or {}
    lines = []
    for sec in ctx.get("sections") or []:
        for c in sec.get("cards") or []:
            lines.append("%s %s (%s, %s%s)%s - /tai-lieu/%s" % (
                c.get("code"), c.get("name"), c.get("type") or "tai lieu", c.get("dept") or "",
                (", ban " + c["version"]) if c.get("version") else "",
                (": dung khi " + _short(c["use"], 100)) if c.get("use") else "", c.get("code")))
    return lines[:60]


def _tasks(user):
    import frappe
    rows = frappe.get_all("Task", filters={"_assign": ["like", '%%"%s"%%' % user],
                                           "status": ["not in", ["Completed", "Cancelled", "Template"]]},
                          fields=["name", "subject", "status", "exp_end_date", "project", "priority"],
                          order_by="exp_end_date asc", limit_page_length=20)
    return ["%s [%s%s%s] - /pm" % (r.subject, r.status or "", (", han %s" % r.exp_end_date) if r.exp_end_date else "",
                                   (", du an " + r.project) if r.project else "") for r in rows]


def _approvals(user):
    import frappe
    lines = []
    mine = frappe.get_all("EC Approval Request", filters={"requested_by": user},
                          fields=["approval_type", "reference_name", "approval_status", "submitted_at",
                                  "current_level"], order_by="modified desc", limit_page_length=10)
    for r in mine:
        lines.append("PHIEU CUA BAN: %s %s - %s (cap %s, gui %s)" % (
            r.approval_type, r.reference_name, r.approval_status or "?", r.current_level or "-",
            str(r.submitted_at or "")[:16]))
    try:
        from ecentric_workspace.approval_center.shared.requests import quick_approve
        for p in (quick_approve.list_my_pending(user) or [])[:10]:
            lines.append("CHO BAN DUYET: %s - %s (nguoi gui %s, cap %s) - %s" % (
                p.get("type_label") or p.get("approval_type"), p.get("title") or p.get("reference_name"),
                p.get("requester_name") or p.get("requested_by") or "", p.get("level_name") or "",
                p.get("detail_url") or "/approvals"))
    except Exception:
        frappe.log_error(title="ai_knowledge approvals pending")
    return lines


def _leave(user):
    import frappe
    emp = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
    if not emp:
        return []
    from hrms.hr.doctype.leave_application.leave_application import get_leave_details
    det = get_leave_details(emp, frappe.utils.nowdate()) or {}
    lines = []
    for lt, a in (det.get("leave_allocation") or {}).items():
        lines.append("PHEP CUA BAN - %s: con %s / tong %s ngay (da nghi %s, cho duyet %s) - /ec-hr/leave" % (
            lt, a.get("remaining_leaves"), a.get("total_leaves"), a.get("leaves_taken"),
            a.get("leaves_pending_approval")))
    return lines


def _data(user):
    from ecentric_workspace.data_hub import service
    rows = service.list_rows(user) or []
    mine = [r for r in rows if r.get("mine")]
    return ["%s %s [%s%s, nguoi gui %s, phu trach %s] - /du-lieu" % (
        r.get("code"), r.get("title"), r.get("status_label") or r.get("status") or "",
        (", han %s" % r["due"]) if r.get("due") else "", r.get("requester_name") or "",
        r.get("assignee_name") or "-") for r in mine[:10]]


SOURCES = {
    SURVEY: ("Khao sat (/khao-sat)", _survey),
    NEWS: ("Tin noi bo moi nhat (/tin-noi-bo)", _news),
    DOCS: ("Thu vien tai lieu ISO dang hieu luc (/tai-lieu)", _docs),
    TASKS: ("Cong viec dang giao cho ban (/pm)", _tasks),
    APPROVALS: ("Phieu phe duyet cua ban va phieu cho ban duyet", _approvals),
    LEAVE: ("Phep cua ban", _leave),
    DATA: ("Yeu cau du lieu (/du-lieu)", _data),
}


def context(user, message):
    """-> (khoi van ban, [nguon da dung]). WEEKLY khong o day - chat.py lo (luat WTU rieng)."""
    import frappe
    picked = pick_sources(message)
    sections, used = [], []
    for src in picked:
        if src not in SOURCES:
            continue
        title, fn = SOURCES[src]
        try:
            lines = fn(user)
        except Exception:
            frappe.log_error(title="ai_knowledge %s" % src)
            continue
        sections.append((title, lines or ["(khong co gi)"]))
        used.append(src)
    return render(sections), picked
