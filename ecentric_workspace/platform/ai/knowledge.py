# Copyright (c) 2026, eCentric and contributors
"""Kien thuc ERP cho AI hoi dap (eC Mate + o chat trang chu).

Hoan 10/11/2026: "AI hieu toan bo thong tin tren ERP, theo phan quyen nhan su; hoi luong nguoi
khac thi khong duoc tra loi".
Hoan 27/11/2026: "AI chua bao quat duoc ERP ... mo cho no tra loi duoc toan bo - tuyet doi theo
phan quyen; khong tra loi luong; han che cau hoi ngoai ERP (tu van cong viec thi duoc); strictly
nghiem cam dong toi PnL / luong / phan khong thuoc quyen nguoi do".

BA LUAT, KHONG NOI LONG:
  1. MOI NGUON (knowledge_sources.py) doc DUNG cai nguoi hoi tu mo duoc tren trang cua module
     do, chay duoi quyen nguoi dang dang nhap.
  2. LUONG / THU NHAP / THUONG va PnL / DOANH THU / LOI NHUAN: tra loi CO DINH, KHONG goi AI,
     KHONG doc gi (guard). Khong nguon nao cham cac du lieu do.
  3. Cau ngoai cong viec: loi dan (chat.RULES) bat AI tu choi lich su - xem chat.py.

Chon nguon theo tu khoa (pick_sources, PURE). LUON kem 4 nguon gon (ban do ERP, huong dan,
loai phieu tao duoc, viec cua toi) de AI tra loi duoc "lam X o dau / the nao". Moi nguon hong
-> bo nguon do (ghi Error Log), cac nguon khac van chay.
"""
import re

from ecentric_workspace.platform.ai import knowledge_sources as S

fold = S.fold

(SURVEY, NEWS, DOCS, TASKS, APPROVALS, LEAVE, DATA, WEEKLY, MAP, GUIDES, GUIDE_TEXT, CATALOG,
 MYWORK, ASSETS, SLA, TRAINING, SOCIAL, FEEDBACK, TODAY, ATTENDANCE, DIRECTORY, REPORTS) = (
    "survey", "news", "docs", "tasks", "approvals", "leave", "data", "weekly", "map", "guides",
    "guide_text", "catalog", "mywork", "assets", "sla", "training", "social", "feedback", "today",
    "attendance", "directory", "reports")
#: Luon co (gon, re): tra loi duoc "o dau / lam the nao / phieu gi / toi con viec gi".
ALWAYS = (MYWORK, CATALOG, GUIDES, MAP)
#: Khong khop tu khoa nao -> them tong quan nhe.
DEFAULT_SOURCES = (WEEKLY, TASKS, APPROVALS, SURVEY, TODAY)
MAX_ITEMS = 15
WIDTH = 300
#: Nguon dai hon mac dinh: (so dong toi da, do dai dong).
CAPS = {MAP: (80, 220), CATALOG: (60, 260), GUIDES: (40, 260), GUIDE_TEXT: (2, S.GUIDE_TEXT_CHARS),
        DOCS: (60, 260), DIRECTORY: (320, 160), MYWORK: (21, 260), TRAINING: (20, 200),
        ATTENDANCE: (35, 160)}
SALARY_ROUTE = "/ec-hr/salary"

#: Tu khoa da BO DAU, chu thuong (xem fold()).
KEYWORDS = {
    SURVEY: ("khao sat", "survey", "vong quay", "phieu khao"),
    NEWS: ("tin noi bo", "tin tuc", "bai viet", "ban tin", "tin moi", "thong bao"),
    DOCS: ("tai lieu", "quy trinh", "quy dinh", "iso", "chinh sach", "bieu mau", "noi quy",
           "so tay", "quy che"),
    TASKS: ("cong viec", "task", "viec cua", "deadline", "han chot", "du an", "viec can lam",
            "viec dang lam"),
    APPROVALS: ("phieu", "phe duyet", "cho duyet", "duyet", "de nghi", "trang thai yeu cau",
                "yeu cau cua"),
    LEAVE: ("ngay phep", "phep con", "con bao nhieu ngay", "so ngay nghi", "quy phep",
            "phep nam", "nghi phep", "don nghi"),
    DATA: ("yeu cau du lieu", "trung tam du lieu", "crawl", "data hub"),
    WEEKLY: ("bao cao tuan", "weekly", "tien do", "mood", "tam trang", "blocker",
             "phong minh", "team", "diem ai", "ai score"),
    ASSETS: ("tai san", "thiet bi", "laptop", "may tinh", "man hinh", "ban quyen", "license",
             "cap phat", "thu hoi", "kiem ke", "sua chua", "ban giao"),
    SLA: ("sla", "dung han", "tre han", "qua han", "dung hen"),
    TRAINING: ("dao tao", "bai hoc", "khoa hoc", "quiz", "training", "ve quay", "quay so"),
    SOCIAL: ("bang tin", "bai dang", "cau lac bo", "clb", "newsfeed", "su kien"),
    FEEDBACK: ("gop y", "phan anh", "feedback"),
    TODAY: ("sinh nhat", "nhan vien moi", "ban moi", "ky niem", "ngay le", "nghi le", "nghi tet",
            "lich nghi", "thong bao", "hom nay co gi", "su kien"),
    ATTENDANCE: ("cham cong", "di muon", "ve som", "check in", "checkin", "ngay cong",
                 "cong thang", "quen cham", "khuon mat", "vang mat"),
    DIRECTORY: ("ai la", "la ai", "truong phong", "truong bo phan", "quan ly cua", "sep",
                "lien he", "email cua", "phu trach", "danh ba", "phong ban", "thuoc phong",
                "chuc danh", "leader", "line manager", "bao cao cho", "nguoi nao", "ai lo"),
    REPORTS: ("bao cao nao", "dashboard", "report", "trung tam bao cao", "so lieu"),
}
#: Nguon chac chan la TRA CUU (khong phai tao phieu) - router cua eC Mate dung de khong hoi
#: nham "AI Topup hay System Request?" khi nguoi dung chi hoi. KHONG dua ASSETS / DIRECTORY /
#: ATTENDANCE vao: "cap phat laptop", "booking ... nguoi phu trach Y" la tao phieu that.
LOOKUP_ONLY = (SURVEY, NEWS, DOCS, LEAVE, TASKS, SLA, TRAINING)

# --------------------------------------------------------------------- guard --
#: Luong / thu nhap / thuong (cua BAT KY AI). Viet CO DAU cho cac tu de nham khi bo dau
#: ("lương" != "luồng", "thưởng" != "thường"); dang khong dau chi khop cum ro nghia.
_SALARY = re.compile(
    r"(lương|thu nhập|salary|payroll|payslip|\bctc\b|tiền thưởng|thưởng tết|thưởng cuối năm|"
    r"thưởng kpi|\bbonus\b|"
    r"\b(bang|phieu|muc|tien|quy|he so)\s+luong\b|\bluong\s+(cua|thang|co ban|net|gross)\b|"
    r"\bthu nhap\b|\btien thuong\b|\bthuong tet\b)", re.I)
#: PnL / doanh thu / loi nhuan / chi phi cong ty - tren van ban DA BO DAU.
_PNL = re.compile(
    r"(\bpnl\b|\bp\s*&\s*l\b|\bp/l\b|doanh thu|loi nhuan|lai lo|\blo lai\b|bien loi|ebitda|"
    r"gross profit|net profit|\brevenue\b|\bprofit\b|\bmargin\b|chi phi luong|chi phi nhan su|"
    r"quy luong|chi phi (van hanh|toan|cua) cong ty|ket qua kinh doanh)", re.I)
#: Cau tao phieu co the nhac "doanh thu" (xuat hoa don doanh thu...) - eC Mate khong chan.
_CREATE = ("tao phieu", "de nghi", "thanh toan", "dntt", "dnmh", "xuat hoa don", "tam ung",
           "hoan ung", "mua hang", "dien giup", "dien ho")

SALARY_REPLY = ("Mình không tra cứu hay trả lời về lương, thu nhập, thưởng của bất kỳ ai. "
                "Phiếu lương của bạn xem ở trang Nhân sự › Phiếu lương (%s); quy trình xét "
                "tăng lương / thăng chức xem ở Hướng dẫn sử dụng (/huong-dan)." % SALARY_ROUTE)
PNL_REPLY = ("Mình không trả lời về PnL, doanh thu, lợi nhuận hay chi phí của công ty. Nếu bạn "
             "được cấp quyền, số liệu nằm ở trang Doanh thu (PnL); cần quyền thì bạn liên hệ "
             "quản lý trực tiếp nhé.")


def salary_question(message):
    """PURE. Cau nay hoi ve luong / thu nhap / thuong? (cua ai cung vay - AI khong tra loi)."""
    return bool(_SALARY.search(str(message or "")))


def pnl_question(message):
    """PURE. Cau nay dong toi PnL / doanh thu / loi nhuan / chi phi cong ty?"""
    return bool(_PNL.search(fold(message)))


def guard(message, creating_ok=False):
    """PURE. -> cau tra loi co dinh neu cau hoi vao vung CAM, nguoc lai None.

    creating_ok=True (eC Mate): cau tao phieu co chu "doanh thu" (xuat hoa don doanh thu...) van
    di tiep de tao NHAP - nhap van theo quyen form, khong lo so lieu nao. Luong thi luon chan."""
    if salary_question(message):
        return SALARY_REPLY
    if pnl_question(message):
        if creating_ok and any(w in fold(message) for w in _CREATE):
            return None
        return PNL_REPLY
    return None


# ----------------------------------------------------------------- chon nguon --
def _hits(text, words):
    return any(re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(w), text) for w in words)


def pick_sources(message):
    """PURE. -> nguon theo thu tu KEYWORDS (KHONG gom ALWAYS); khong khop gi -> DEFAULT_SOURCES."""
    t = " %s " % fold(message)
    hit = [src for src, words in KEYWORDS.items() if _hits(t, words)]
    return hit or list(DEFAULT_SOURCES)


def is_lookup(message):
    """PURE. Cau nhac toi khao sat / tin / tai lieu / phep / viec / SLA / dao tao -> tra cuu."""
    t = " %s " % fold(message)
    return any(_hits(t, KEYWORDS[src]) for src in LOOKUP_ONLY)


#: Dau hieu cau hoi ve cach lam / ERP (ngoai KEYWORDS).
_WORK = ("erp", "lam sao", "the nao", "o dau", "trang nao", "huong dan", "cach", "phieu gi",
         "form nao", "mau nao", "thu tuc", "ai duyet")


def about_work(message):
    """PURE. Cau co nhac toi ERP / cong viec (bat ky tu khoa nguon nao, hay hoi cach lam)?"""
    t = " %s " % fold(message)
    return _hits(t, _WORK) or any(_hits(t, words) for words in KEYWORDS.values())


def render(sections):
    """PURE. [(tieu de, [dong], (max, width)?)] -> khoi van ban cho loi dan. Bo khoi rong."""
    out = []
    for sec in sections:
        title, lines = sec[0], sec[1]
        cap, width = sec[2] if len(sec) > 2 else (MAX_ITEMS, WIDTH)
        if not lines:
            continue
        out += ["", "=== %s ===" % title] + ["- " + S.short(l, width) if "\n" not in l else l
                                             for l in lines[:cap]]
    return "\n".join(out)


def _guide_text(message):
    slugs = S.match_guides(message, S.guide_index())
    return ["[Bai %s - /huong-dan/%s]\n%s" % (s, s, S.guide_text(s)) for s in slugs if S.guide_text(s)]


SOURCES = {
    MYWORK: ("Viec dang cho ban (/viec-cua-toi)", S.mywork),
    SURVEY: ("Khao sat (/khao-sat)", S.survey),
    NEWS: ("Tin noi bo moi nhat (/tin-noi-bo)", S.news),
    DOCS: ("Thu vien tai lieu ISO dang hieu luc (/tai-lieu)", S.docs),
    TASKS: ("Cong viec dang giao cho ban (/pm)", S.tasks),
    APPROVALS: ("Phieu phe duyet cua ban va phieu cho ban duyet", S.approvals),
    LEAVE: ("Phep cua ban", S.leave),
    DATA: ("Yeu cau du lieu (/du-lieu)", S.data),
    ASSETS: ("Tai san / ban quyen dang giao cho ban", S.assets),
    SLA: ("Diem SLA cua ban", S.sla),
    TRAINING: ("Dao tao (/dao-tao)", S.training),
    SOCIAL: ("Bang tin (/bang-tin)", S.social),
    FEEDBACK: ("Gop y ban da gui (/gop-y)", S.feedback),
    TODAY: ("Hom nay o eCentric", S.today),
    ATTENDANCE: ("Cham cong cua ban", S.attendance),
    DIRECTORY: ("Danh ba noi bo (ten - chuc danh - phong - email)", S.directory),
    REPORTS: ("Bao cao ban mo duoc (/reports)", S.reports),
    CATALOG: ("Loai phieu ban tao duoc (Phe duyet)", S.catalog),
    GUIDES: ("Bai huong dan su dung (/huong-dan)", S.guides),
    MAP: ("Ban do ERP - trang nao lam gi (trang co the doi quyen rieng)", S.erp_map),
}


def context(user, message):
    """-> (khoi van ban, [nguon da chon]). WEEKLY khong o day - chat.py lo (luat WTU rieng)."""
    import frappe
    picked = pick_sources(message)
    order = [MYWORK] + [s for s in picked if s != MYWORK] + [s for s in ALWAYS if s != MYWORK]
    sections, seen = [], set()
    for src in order:
        if src in seen or src not in SOURCES:
            continue
        seen.add(src)
        title, fn = SOURCES[src]
        try:
            lines = fn(user)
        except Exception:
            frappe.log_error(title="ai_knowledge %s" % src)
            continue
        sections.append((title, lines or ["(khong co gi)"], CAPS.get(src, (MAX_ITEMS, WIDTH))))
    try:
        text = _guide_text(message)
        if text:
            sections.append(("Noi dung bai huong dan sat cau hoi", text, CAPS[GUIDE_TEXT]))
    except Exception:
        frappe.log_error(title="ai_knowledge guide_text")
    return render(sections), picked
