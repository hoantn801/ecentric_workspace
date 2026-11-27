# Copyright (c) 2026, eCentric and contributors
"""Nguon du lieu ERP cho AI hoi dap - moi ham (user) -> [dong van ban].

LUAT CHUNG (Hoan 10/11 + 27/11/2026 "AI bao quat toan bo ERP, tuyet doi theo phan quyen"):
  * Moi nguon goi lai CHINH ham ma trang cua module do dung, chay duoi frappe.session.user =
    nguoi hoi -> AI thay dung cai nguoi do mo duoc tren trang, khong hon.
  * Doc truc tiep DocType chi khi (a) loc cung theo CHINH nguoi hoi (Attendance, Task, phieu
    cua minh) hoac (b) qua frappe.get_list (co kiem quyen) voi danh sach cot CO DINH.
  * KHONG nguon nao cham luong / thu nhap / PnL / doanh thu / chi phi / so tai khoan / giay to
    (test_chat.ChonNguon.test_khong_nguon_nao_doc_luong quet ma nguon tung ham).
  * Chi chon cot can hien; khong dua nguyen dict cua trang vao loi dan (tranh lot cot nhay cam
    nhu gia tri tai san khi nguoi hoi la quan ly tai san).

Phan dau file la helper PURE (test khong can frappe).
"""
import html as _html
import io
import os
import re
import unicodedata

GUIDE_TEXT_CHARS = 5000
GUIDE_PICK = 2
GUIDE_MIN_SCORE = 2
#: Muc menu khong dua vao ban do ERP cho AI (Hoan 27/11: cam dong toi PnL).
MAP_HIDE = ("pnl",)
#: Mot dong mo ta them cho cac trang hay bi hoi "lam X o dau" (route -> mo ta).
MAP_NOTES = {
    "/approvals": "tao moi loai phieu/de nghi (thanh toan, mua hang, tam ung, tai san, booking...)",
    "/approvals/all-requests": "xem phieu toi da gui / cho toi duyet / toi theo doi",
    "/viec-cua-toi": "moi viec dang cho ban: phieu can duyet, task, bao cao tuan",
    "/pm": "du an, task, lich, giao viec, dat phong hop",
    "/ec-hr/attendance": "cham cong, giai trinh cong",
    "/ec-hr/leave": "xin nghi phep, so ngay phep con",
    "/ec-hr/salary": "phieu luong cua CHINH ban",
    "/ec-hr/phan-bo-cong-viec": "chot cong thang, nop ty trong brand",
    "/sla": "diem dung han (SLA) cua ban",
    "/weekly-update": "nop / xem bao cao tuan",
    "/khao-sat": "khao sat noi bo dang mo",
    "/tai-lieu": "quy trinh, quy dinh, bieu mau ISO",
    "/huong-dan": "bai huong dan dung ERP",
    "/tai-san/cua-toi": "tai san, thiet bi, ban quyen dang giao cho ban",
    "/gop-y": "gui gop y cho cong ty (co the an danh)",
    "/dao-tao": "bai hoc tuan, quiz, ve quay so",
    "/du-lieu": "gui yeu cau du lieu cho team Data",
    "/bang-tin": "bang tin noi bo, cau lac bo, su kien",
    "/tin-noi-bo": "tin tuc, thong bao cua HR/Admin",
    "/chat": "chat noi bo",
    "/kalodata": "xep hang dung chung tai khoan Kalodata",
}
_STOP = set((
    "cac cho cua the nao lam sao khi voi mot nhung duoc trong tren erp nay kia toi minh ban "
    "can muon xin hoi giup phai khong gi dau thi hay va hoac tai sao bao nhieu quy trinh "
    "huong dan nhan vien nguoi viec cong").split())
_TAG = re.compile(r"<[^>]+>")
#: Bo ca khoi: ma, hinh, va VO MENU shell (aside/nav) nhung san trong trang huong dan.
_BLOCK = re.compile(r"<(script|style|svg|noscript|template|aside|nav|button)\b.*?</\1\s*>", re.I | re.S)
_BREAK = re.compile(r"<\s*(br|/p|/li|/h[1-6]|/div|/tr|/section|/article|/summary|/dt|/dd)\b[^>]*>", re.I)
_BULLET = re.compile(r"<\s*li\b[^>]*>", re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.S)


def fold(text):
    """PURE. Chu thuong, bo dau tieng Viet - khop tu khoa du go co dau hay khong."""
    t = unicodedata.normalize("NFD", str(text or "").lower())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return t.replace("đ", "d")


def short(text, cap=160):
    t = " ".join(str(text or "").split())
    return t if len(t) <= cap else t[:cap - 1] + "…"


def name_of(x):
    """PURE. Ten nguoi tu dict {name|full_name|label} hoac chuoi."""
    if isinstance(x, dict):
        return x.get("full_name") or x.get("name") or x.get("label") or ""
    return str(x or "")


def html_text(html, cap=GUIDE_TEXT_CHARS):
    """PURE. HTML trang huong dan -> van ban thuan (bo script/style/svg, giu xuong dong, '- ' cho
    muc danh sach), cat o `cap` ky tu."""
    t = _COMMENT.sub(" ", str(html or ""))
    t = _BLOCK.sub(" ", t)
    t = _BULLET.sub("\n- ", t)
    t = _BREAK.sub("\n", t)
    t = _html.unescape(_TAG.sub(" ", t))
    lines = [" ".join(l.split()) for l in t.split("\n")]
    out = "\n".join(l for l in lines if re.search(r"\w", l))   # bo dong chi co mui ten / gach
    return out if len(out) <= cap else out[:cap - 1] + "…"


def _words(text):
    return [w for w in re.findall(r"[a-z0-9]+", fold(text)) if len(w) >= 2]


def _score(text, mset, mbi, weight):
    w = _words(text)
    uni = {x for x in w if x not in _STOP and len(x) >= 3} & mset
    bi = {b for b in zip(w, w[1:]) if not (b[0] in _STOP and b[1] in _STOP)} & mbi
    return weight * (2 * len(bi) + len(uni))


def match_guides(message, guides, pick=GUIDE_PICK, min_score=GUIDE_MIN_SCORE):
    """PURE. Bai huong dan sat cau hoi nhat. Diem = (2 x cap tu lien trung + tu don trung, bo tu
    chung chung) - trung o TIEU DE tinh gap doi tom tat. Hoa diem -> bai tieu de ngan hon (cu the
    hon) truoc. -> [slug] toi da `pick`, diem >= min_score."""
    mw = _words(message)
    mset, mbi = set(mw), set(zip(mw, mw[1:]))
    scored = []
    for g in guides or []:
        head = "%s %s" % (g.get("title") or "", g.get("short") or "")
        score = _score(head, mset, mbi, 2) + _score(g.get("summary"), mset, mbi, 1)
        if score >= min_score:
            scored.append((-score, len(_words(g.get("title"))), g.get("slug") or ""))
    scored.sort()
    top = -scored[0][0] if scored else 0
    # Bai thu hai chi kem khi cung sat (>= nua diem bai dau) - tranh nhoi bai lac de vao loi dan.
    return [slug for sc, _n, slug in scored[:pick] if slug and -sc * 2 >= top]


def map_lines(items):
    """PURE. Muc menu shell (nav.compose_all) -> dong 'Nhom › Ten - /route: mo ta'. An PnL."""
    out = []
    for it in items or []:
        route, label = it.get("route") or "", it.get("label") or ""
        if any(h in fold(route + " " + label) for h in MAP_HIDE):
            continue
        kids = [c.get("label") for c in it.get("children") or [] if c.get("label")]
        note = MAP_NOTES.get(route.split("?")[0], "")
        out.append("%s%s - %s%s%s" % (
            (it["group"] + " › ") if it.get("group") else "", label, route,
            (": " + note) if note else "", (" (gom: " + ", ".join(kids) + ")") if kids else ""))
    return out


# ------------------------------------------------------------------ nguon (impure) --
# Moi ham (user) -> [dong]. frappe import TRONG ham (test nap file khong can frappe).

def survey(user):
    from ecentric_workspace.surveys.controllers import api
    data = (api.hub() or {}).get("data") or {}
    lines = []
    for c in data.get("open") or []:
        lines.append("CHO BAN LAM: %s%s - %s cau hoi%s - mo tai /khao-sat" % (
            c.get("title"), (" (han %s)" % c["close_at"]) if c.get("close_at") else "",
            c.get("questions") or "?", (" - " + short(c["description"], 120)) if c.get("description") else ""))
    for c in data.get("done") or []:
        lines.append("BAN DA NOP: %s - luc %s%s" % (
            c.get("title"), c.get("submitted_at") or "?",
            (" - qua: " + c["prize_label"]) if c.get("prize_label") else ""))
    return lines


def news(user):
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
            (": " + short(c["summary"], 140)) if c.get("summary") else "", c.get("url") or "/tin-noi-bo"))
    return lines


def docs(user):
    from ecentric_workspace.iso_docs import library
    ctx = library.library_page(user) or {}
    lines = []
    for sec in ctx.get("sections") or []:
        for c in sec.get("cards") or []:
            lines.append("%s %s (%s, %s%s)%s - /tai-lieu/%s" % (
                c.get("code"), c.get("name"), c.get("type") or "tai lieu", c.get("dept") or "",
                (", ban " + c["version"]) if c.get("version") else "",
                (": dung khi " + short(c["use"], 100)) if c.get("use") else "", c.get("code")))
    return lines


def tasks(user):
    import frappe
    rows = frappe.get_all("Task", filters={"_assign": ["like", '%%"%s"%%' % user],
                                           "status": ["not in", ["Completed", "Cancelled", "Template"]]},
                          fields=["name", "subject", "status", "exp_end_date", "project", "priority"],
                          order_by="exp_end_date asc", limit_page_length=20)
    return ["%s [%s%s%s] - /pm" % (r.subject, r.status or "", (", han %s" % r.exp_end_date) if r.exp_end_date else "",
                                   (", du an " + r.project) if r.project else "") for r in rows]


def approvals(user):
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
        # list_my_pending tra {"rows": [...], "count": n} (cung ham trang "Cho toi duyet" dung) -
        # 27/11 tren site: doc nhu danh sach -> KeyError, nguon "cho ban duyet" luon trong.
        pend = quick_approve.list_my_pending(user) or {}
        rows = pend.get("rows") if isinstance(pend, dict) else pend
        for p in (rows or [])[:10]:
            lines.append("CHO BAN DUYET: %s - %s (nguoi gui %s, cap %s) - %s" % (
                p.get("type_label") or p.get("approval_type"), p.get("title") or p.get("reference_name"),
                p.get("requester_name") or p.get("requested_by") or "", p.get("level_name") or "",
                p.get("detail_url") or "/approvals"))
    except Exception:
        frappe.log_error(title="ai_knowledge approvals pending")
    return lines


def leave(user):
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
    for r in frappe.get_all("Leave Application", filters={"employee": emp},
                            fields=["leave_type", "from_date", "to_date", "total_leave_days", "status"],
                            order_by="from_date desc", limit_page_length=5):
        lines.append("DON NGHI CUA BAN: %s %s -> %s (%s ngay) - %s" % (
            r.leave_type, r.from_date, r.to_date, r.total_leave_days, r.status))
    return lines


def data(user):
    from ecentric_workspace.data_hub import service
    rows = service.list_rows(user) or []
    mine = [r for r in rows if r.get("mine")]
    return ["%s %s [%s%s, nguoi gui %s, phu trach %s] - /du-lieu" % (
        r.get("code"), r.get("title"), r.get("status_label") or r.get("status") or "",
        (", han %s" % r["due"]) if r.get("due") else "", r.get("requester_name") or "",
        r.get("assignee_name") or "-") for r in mine[:10]]


_BUCKET_LABEL = {"overdue": "QUA HAN", "act_now": "LAM NGAY", "upcoming": "SAP TOI", "undated": "KHONG HAN"}


def mywork(user):
    """Viec cua toi (/viec-cua-toi) - cung bo phan loai voi trang chu + bang 'Viec cua ban'."""
    from ecentric_workspace.action_center import feed
    res = feed.build_feed(user, limit=20) or {}
    c = res.get("counts") or {}
    lines = ["Tong %s viec dang mo: %s" % (res.get("total", 0), ", ".join(
        "%s %s" % (_BUCKET_LABEL.get(k, k), v) for k, v in c.items() if v))] if res.get("total") else []
    for it in res.get("items") or []:
        lines.append("[%s] %s: %s%s%s - %s" % (
            _BUCKET_LABEL.get(it.get("bucket"), it.get("bucket") or ""), it.get("source_label") or "",
            it.get("title") or "", (" - " + short(it["subtitle"], 80)) if it.get("subtitle") else "",
            (" (han %s)" % str(it["due_at"])[:16]) if it.get("due_at") else "", it.get("action_url") or "/viec-cua-toi"))
    return lines


def guides(user):
    from ecentric_workspace.guides import registry
    return ["%s: %s - %s" % (g.get("title"), short(g.get("summary"), 160), g.get("route"))
            for g in registry.listed()]


def guide_text(slug):
    """Noi dung that cua mot bai huong dan (file main_section.html cua app) -> van ban thuan."""
    from ecentric_workspace import guides as pkg
    path = os.path.join(os.path.dirname(pkg.__file__), "pages", str(slug).replace("-", "_"),
                        "main_section.html")
    if not re.match(r"^[a-z0-9-]+\Z", str(slug)) or not os.path.isfile(path):
        return ""
    with io.open(path, encoding="utf-8") as fh:
        return html_text(fh.read())


def guide_index():
    from ecentric_workspace.guides import registry
    return registry.listed()


def catalog(user):
    """Cac loai phieu NGUOI NAY tao duoc (trang Phe duyet cua ho) + bai huong dan neu co."""
    from ecentric_workspace.approval_center.shared import catalog_api
    from ecentric_workspace.guides import registry
    lines = []
    for c in catalog_api.list_catalog().get("types") or []:
        if c.get("card_status") != "Active" or not c.get("route"):
            continue
        g = registry.guide_for_approval_type(c.get("approval_code"))
        lines.append("%s (%s)%s - /%s%s" % (
            c.get("approval_title") or c.get("approval_code"), c.get("approval_code") or "",
            (": " + short(c["description"], 140)) if c.get("description") else "",
            str(c["route"]).lstrip("/"), (" | huong dan: " + g["route"]) if g and g.get("route") else ""))
    return lines


def erp_map(user):
    import frappe
    from ecentric_workspace.shell import nav
    return map_lines(nav.compose_all(roles=set(frappe.get_roles(user))))


def assets(user):
    """Tai san cua toi - CHI ten/the/trang thai; khong lay gia tri/khau hao (cot rieng quan ly)."""
    from ecentric_workspace.tai_san.controllers import api
    d = (api.my_assets() or {}).get("data") or {}
    lines = ["%s %s (%s, %s, tinh trang %s)%s - /tai-san/cua-toi" % (
        a.get("tag") or "", a.get("asset_name") or a.get("model_name") or "", a.get("category") or "",
        a.get("status_label") or "", a.get("condition") or "",
        " - CHO BAN XAC NHAN DA NHAN" if a.get("pending_ack") else "") for a in d.get("assets") or []]
    for l in d.get("licenses") or []:
        lines.append("BAN QUYEN: %s (%s%s) - /tai-san/cua-toi" % (
            l.get("license_name") or l.get("license") or "", l.get("vendor") or "",
            (", het han " + str(l["expiry_date"])) if l.get("expiry_date") else ""))
    return lines


def _rate(b):
    b = b or {}
    r = b.get("rate")
    return ("%s%%" % r) if isinstance(r, (int, float)) else "chua du mau"   # scoring da tinh theo %


def sla(user):
    from ecentric_workspace.sla.controllers import api
    d = (api.my_board() or {}).get("data") or {}
    if not d:
        return []
    o = d.get("overall") or {}
    lines = ["SLA CUA BAN ky %s: %s dung han (dung %s, tre %s, lo %s, dang mo %s) - /sla" % (
        d.get("period") or "", _rate(o), o.get("ontime", 0), o.get("late", 0), o.get("missed", 0), o.get("open", 0))]
    for g in d.get("groups") or []:
        if g.get("scored") or g.get("open"):
            lines.append("- %s: %s (tre %s, lo %s)%s" % (g.get("label") or g.get("group_key"), _rate(g),
                                                       g.get("late", 0), g.get("missed", 0),
                                                       "" if g.get("counts_toward_sla") else " - khong tinh diem"))
    return lines


def training(user):
    from ecentric_workspace.dao_tao.controllers import api
    d = (api.learn_hub() or {}).get("data") or {}
    if not d:
        return []
    lines = ["Ban da xong %s/%s bai - /dao-tao" % (d.get("done", 0), d.get("total", 0))]
    for c in d.get("week") or []:
        lines.append("BAI TUAN NAY: %s [%s] - %s" % (c.get("title"), c.get("step_label") or "", c.get("url") or "/dao-tao"))
    for c in (d.get("library") or [])[:15]:
        lines.append("%s (%s, %s) [%s] - %s" % (c.get("title"), c.get("topic") or "", c.get("level") or "",
                                              c.get("step_label") or "", c.get("url") or "/dao-tao"))
    t = d.get("tickets") or {}
    if t:
        lines.append("Ve quay so tuan %s: %s / toi da %s" % (t.get("week") or "", t.get("this_week", 0), t.get("cap") or "?"))
    return lines


def social(user):
    from ecentric_workspace.social import feed
    d = feed.page(user) or {}
    lines = []
    for it in (d.get("items") or [])[:12]:
        if it.get("type") == "post":
            lines.append("BAI CUA %s%s (%s): %s - %s" % (
                name_of(it.get("author")), (" o CLB " + name_of(it.get("club"))) if it.get("club") else "",
                it.get("ago") or "", short(it.get("text") or it.get("body"), 160), it.get("url") or "/bang-tin"))
        elif it.get("title"):
            lines.append("%s: %s - %s" % (it.get("type") or "tin", short(it.get("title"), 140), it.get("url") or "/bang-tin"))
    for c in d.get("my_clubs") or []:
        lines.append("CLB CUA BAN: %s" % name_of(c))
    return lines


def feedback(user):
    from ecentric_workspace.feedback import service
    return ["GOP Y CUA BAN: %s [%s, %s, gui %s%s] - /gop-y/%s" % (
        c.get("title"), c.get("status") or "", c.get("topic") or "", c.get("date") or "",
        (", han tra loi " + c["due"]) if c.get("due") else "", c.get("name"))
        for c in service.my_cards(user, limit=10)]


def today(user):
    """Popup 'Hom nay o eCentric': sinh nhat, ban moi, ky niem, ngay nghi le, thong bao."""
    from ecentric_workspace.home_today import service
    d = service.today(user) or {}
    lines = []
    bd = d.get("birthdays") or {}
    for p in bd.get("today") or []:
        lines.append("SINH NHAT HOM NAY: %s" % name_of(p))
    for p in bd.get("soon") or []:
        lines.append("SINH NHAT SAP TOI: %s (%s)" % (name_of(p), p.get("date_label") or p.get("day") or ""))
    for p in d.get("onboard") or []:
        lines.append("BAN MOI: %s%s" % (name_of(p), (" - " + p["role"]) if p.get("role") else ""))
    for p in d.get("anniversaries") or []:
        lines.append("KY NIEM: %s - %s nam" % (name_of(p), p.get("years") or "?"))
    for h in d.get("holidays") or []:
        lines.append("NGHI LE: %s %s%s" % (h.get("date_label") or h.get("date") or "", h.get("title") or h.get("name") or "",
                                         (" (%s ngay)" % h["days_off"]) if h.get("days_off") else ""))
    for n in d.get("news") or []:
        lines.append("THONG BAO: %s%s%s" % (n.get("title") or "", (": " + short(n["excerpt"], 140)) if n.get("excerpt") else "",
                                          (" - " + n["url"]) if n.get("url") else ""))
    return lines


def attendance(user):
    """Cham cong CUA CHINH nguoi hoi - thang nay + check-in hom nay."""
    import frappe
    emp = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
    if not emp:
        return []
    today_ = frappe.utils.getdate(frappe.utils.nowdate())
    start = today_.replace(day=1)
    rows = frappe.get_all("Attendance", filters={"employee": emp, "docstatus": 1,
                                                 "attendance_date": ["between", [start, today_]]},
                          fields=["attendance_date", "status", "late_entry", "early_exit", "working_hours"],
                          order_by="attendance_date asc", limit_page_length=40)
    count = {}
    for r in rows:
        count[r.status] = count.get(r.status, 0) + 1
    lines = ["CONG THANG %s CUA BAN: %s; di muon %s, ve som %s - /ec-hr/attendance" % (
        start.strftime("%m/%Y"), ", ".join("%s %s" % (k, v) for k, v in count.items()) or "chua co",
        sum(1 for r in rows if r.late_entry), sum(1 for r in rows if r.early_exit))]
    for r in rows:
        if r.status != "Present" or r.late_entry or r.early_exit:
            lines.append("- %s: %s%s%s" % (r.attendance_date, r.status, " (di muon)" if r.late_entry else "",
                                           " (ve som)" if r.early_exit else ""))
    logs = frappe.get_all("Employee Checkin", filters={"employee": emp, "time": [">=", str(today_)]},
                          fields=["log_type", "time"], order_by="time asc", limit_page_length=10)
    lines.append("CHECK-IN HOM NAY: " + (", ".join("%s %s" % (l.log_type or "", str(l.time)[11:16]) for l in logs)
                                       or "chua co"))
    return lines


def directory(user):
    """Danh ba noi bo QUA frappe.get_list (co kiem quyen) voi cot CO DINH - ten, chuc danh,
    phong, email cong ty, truong phong. Khong co cot nao khac (cot nhay cam o permlevel 1)."""
    import frappe
    lines = []
    try:
        if frappe.get_meta("Department").has_field("manager_email"):
            for d in frappe.get_list("Department", fields=["department_name", "manager_email"],
                                     limit_page_length=100):
                if d.manager_email:
                    lines.append("TRUONG PHONG %s: %s" % (d.department_name, d.manager_email))
    except Exception:
        frappe.log_error(title="ai_knowledge directory department")
    for e in frappe.get_list("Employee", filters={"status": "Active"},
                             fields=["employee_name", "designation", "department", "user_id"],
                             order_by="employee_name asc", limit_page_length=300):
        lines.append("%s - %s - %s - %s" % (e.employee_name, e.designation or "", e.department or "", e.user_id or ""))
    return lines


def reports(user):
    from ecentric_workspace.reporting.api import catalog
    out = []
    for r in catalog.list_reports_catalog().get("reports") or []:
        if not r.get("route") or any(h in fold("%s %s" % (r.get("title"), r.get("route"))) for h in MAP_HIDE):
            continue
        out.append("%s (%s)%s - %s" % (r.get("title"), r.get("category") or "",
                                     (": " + short(r["description"], 120)) if r.get("description") else "", r["route"]))
    return out
