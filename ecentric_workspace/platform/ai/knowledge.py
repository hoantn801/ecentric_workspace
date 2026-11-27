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
# QC 27/11 (BAO_CAO.md): regex cu bi lach bang NFD / ky tu an / khong dau / tieng Anh khac / tu
# long. Gio: (1) CHUAN HOA truoc khi xet (norm), (2) tu vung rong hon, (3) xet ca dang "dinh
# lien" (l.ư.ơ.n.g), (4) loc LICH SU va (5) loc CAU TRA LOI + DU LIEU co so tien (leaks/scrub).
# Regex KHONG BAO GIO du - lop (5) va viec khong nguon nao doc luong/PnL moi la chot that.
import unicodedata

#: Chu Cyrillic / Hy Lap trong giong chu Latin -> Latin (go "sаlary" voi a Cyrillic).
_CONFUSABLE = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ѕ": "s",
    "ј": "j", "һ": "h", "ԁ": "d", "ɡ": "g", "ո": "n", "ᴨ": "n", "ν": "v", "ο": "o", "α": "a",
    "ρ": "p", "ι": "i", "κ": "k", "τ": "t", "υ": "u", "ε": "e", "ǀ": "l", "ⅼ": "l"})


def norm(text):
    """PURE. Chuan hoa truoc khi xet vung cam: NFKC (gop dau to hop, chu fullwidth -> thuong),
    bo ky tu an / dieu khien (zero-width, bidi, soft hyphen), chu giong Latin -> Latin, gop
    khoang trang, chu thuong. GIU dau tieng Viet ("lương" != "lượng")."""
    t = unicodedata.normalize("NFKC", str(text or ""))
    t = "".join(" " if ch in "\n\r\t" else ch for ch in t
                if ch in "\n\r\t" or unicodedata.category(ch) not in ("Cf", "Cc"))
    t = unicodedata.normalize("NFC", t).lower().translate(_CONFUSABLE)
    return re.sub(r"\s+", " ", t).strip()


def _squeeze(text):
    """PURE. Bo moi thu khong phai chu/so - bat 'l.ư.ơ.n.g', 'd o a n h t h u'."""
    return re.sub(r"[\W_]+", "", text)


#: Xet tren van ban DA norm() nhung CON DAU. Tu co dau khop chu co dau; cum khong dau (ASCII)
#: chi khop khi nguoi dung GO khong dau - nen "luong" (go khong dau) bi chan con "luồng",
#: "lượng", "chất lượng" thi khong.
_SALARY = re.compile(
    r"(lương|thu nhập|tiền thưởng|mức thưởng|lĩnh thưởng|lãnh thưởng|"
    r"thưởng (tết|cuối năm|kpi|quý|năm|tháng|nóng|dự án|hiệu quả|doanh số|lễ|bao nhiêu)|"
    r"tháng (lương )?(thứ )?13|phụ cấp|trợ cấp|đãi ngộ|thuế tncn|thuế thu nhập|"
    r"mức đóng (bhxh|bảo hiểm)|tiền về tài khoản|"
    r"(nhận|lãnh|lĩnh|kiếm|được trả|trả)( được| về)? (bao nhiêu|mấy)"
    r"( tiền| triệu| củ| một tháng| mỗi tháng| tháng này|/tháng|$)|"
    r"bao nhiêu (tiền )?(một|mỗi|1|/) ?tháng|"
    # tieng Anh
    r"salar(y|ies)|payroll|pay ?slips?|pay ?checks?|\bwages?\b|compensation|remuneration|"
    r"\bctc\b|\bbonus(es)?\b|\bincentives?\b|\ballowances?\b|\bincome\b|"
    r"\bearnings?\b|\bgross\b|\bnet (pay|income|luong|lương)\b|\b(get|gets|got|is|are) paid\b|"
    r"\bpay (rise|raise|grade|band|scale)\b|\boffer (amount|package)\b|\bpackage (của|cua|of)\b|"
    r"13th month|"
    # go khong dau / telex / viet tat
    r"\bluong\b(?! (duyet|phe duyet|xu ly|cong viec|di|chay|quy trinh|du lieu|data|thong tin|"
    r"tin|viec|lam viec|nghiep vu|ky|don|chinh|phu|live|stream))"
    r"|luwowng|lu7o7ng|\bthu nhap\b|\btien thuong\b|\bmuc thuong\b|"
    r"\bthuong (tet|cuoi nam|kpi|quy|nong|du an|hieu qua|doanh so|thang 13|bao nhieu)\b|"
    r"\bthang (luong )?(thu )?13\b|\bphu cap\b|\btro cap\b|\bdai ngo\b|\bthue tncn\b|"
    r"\blcb\b|\blg (thang|tháng|thg|co ban|cơ bản|bao nhieu|bao nhiêu|net|gross)\b|"
    r"\blg (cua|của) (anh|chi|chị|sep|sếp|em|ban|bạn|co|cô|chu|chú|moi|mọi|ceo|nv|nhan|nhân|"
    r"toi|tôi|minh|mình)\b(?! (bao hanh|bảo hành|hong|hỏng|bi|bị))|"
    r"\b(muc|mức|bang|bảng|phieu|phiếu|tang|tăng|tinh|tính) lg\b)", re.I)
#: "luong" go khong dau ngay sau cac tu nay la "lượng" (chat luong, so luong...) - khong chan.
_LUONG_BENIGN = re.compile(
    r"\b(chat|so|khoi|san|nang|luu|tru|uoc|dinh|thoi|dung|hang|can|trong|tai|phan|dai|tieu|hoa|"
    r"thuong|luc|do|ham|dinh|tuong|doi|tinh)\s+luong\b")
#: Hoa hong cua NHAN SU (KAM, sales...) la thu nhap -> chan. Hoa hong KOC / affiliate / doi tac la
#: nghiep vu hang ngay (DNTT hoa hong KOC) -> KHONG chan. Xet tren van ban da bo dau.
_COMMISSION = re.compile(
    r"\b(hoa hong|commissions?)\b (cua |cho |of |for |tien )?(kam|nhan vien|nv|sales|anh|chi|em|sep|"
    r"minh|toi|tui|ban|nguoi|team|phong|bo phan|leader|staff|employee)\b")
#: Dang dinh lien (sau _squeeze), CON DAU: 'l.ư.ơ.n.g' -> 'lương'.
_SALARY_SQ = re.compile(r"(lương|thunhập|salary|payroll|tiềnthưởng)")

#: PnL / doanh thu / loi nhuan / chi phi cong ty - tren van ban DA norm() + BO DAU.
_ORG = r"(cong ty|cty|company|ecentric|toan|tong|phong|bo phan|team|brand|khach|nam nay|" \
       r"thang|quy|q[1-4])"
_PNL = re.compile(
    r"(\bp\W{0,3}n\W{0,3}l\b|\bp\W{0,3}(&|and|va|/|-)\W{0,3}l\b|doanh thu|doanh so|loi nhuan|"
    r"\b(gmv|nmv)\b|"
    r"bien loi|lai gop|lai rong|ebit(da)?\b|gross profit|net profit|\brevenues?\b|\bprofits?\b|"
    r"profitab|\bmargins?\b(?! (css|top|left|right|bottom|trang|le|slide|cua (slide|trang|anh)))|"
    r"\bturnover\b|\btop ?line\b|\bbottom ?line\b|\bcash ?flow\b|dong tien|cong no|thu chi|"
    r"tong thu\b|tong chi\b|tong chi phi|bao cao tai chinh|ket qua kinh doanh|income statement|"
    r"balance sheet|financial (statement|report|result)|"
    r"chi phi luong|chi phi nhan su|quy luong|"
    r"chi phi [^.?!]{0,30}\b(cong ty|cty|phong|bo phan|ecentric|team|toan)\b|"
    r"\b(ngan sach|budget) [^.?!]{0,20}\b(cong ty|cty|phong|bo phan|ecentric|team|toan)\b|"
    r"\b(gmv|nmv|sales|net sales|tien|so tien)\b[^.?!]{0,25}\b(cong ty|cty|company|ecentric|"
    r"toan cong|tong cong) ?(thu)?|"
    r"\b(cong ty|cty|company|ecentric)\b[^.?!]{0,25}\b(gmv|nmv|sales|thu (duoc|ve|cua)|"
    r"(loi|lai|lo|kiem|thu) (duoc )?(bao nhieu|may))|"
    r"phi dich vu[^.?!]{0,30}\b(thu|bao nhieu)\b|\bservice fee\b|"
    r"\b(ln|loi nhuan) (truoc|sau) thue\b|\b(tien|khoan) (loi|lai|lo)\b)", re.I)
#: Cum de nham khi bo dau ("lo lại" != "lỗ lãi") - xet tren van ban CON DAU / go khong dau.
_PNL_ACC = re.compile(r"(lãi lỗ|lỗ lãi|lời lãi|lời lỗ|\b(lai lo|lo lai|loi lai)\b)")
_PNL_SQ = re.compile(r"(doanhthu|doanhso|loinhuan|revenue|grossprofit|netprofit|gmv|nmv)")
#: Cau tao phieu co the nhac "doanh thu" (xuat hoa don doanh thu...) - eC Mate khong chan.
_CREATE = ("tao phieu", "tao de nghi", "lap de nghi", "lam de nghi", "tao dntt", "tao dnmh",
           "lap phieu", "len phieu", "xuat hoa don", "tam ung", "hoan ung", "dien giup",
           "dien ho", "tao yeu cau", "tao booking")
#: ...nhung co dau hieu HOI so lieu thi van chan (QC: "tao de nghi ... cho minh biet doanh thu").
_ASKING = re.compile(r"(\?|bao nhieu|\bmay\b|cho (minh|toi|em|anh|chi|tui)? ?(biet|xem|hoi)|"
                     r"la gi|the nao|ra sao|tinh hinh|so lieu|thong ke|tong hop|liet ke|"
                     r"\bbao cao\b|tom tat|so sanh|\bhow\b|\bwhat\b|\btell\b|\bshow\b)")

SALARY_REPLY = ("Mình không tra cứu hay trả lời về lương, thu nhập, thưởng của bất kỳ ai. "
                "Phiếu lương của bạn xem ở trang Nhân sự › Phiếu lương (%s); quy trình xét "
                "tăng lương / thăng chức xem ở Hướng dẫn sử dụng (/huong-dan)." % SALARY_ROUTE)
PNL_REPLY = ("Mình không trả lời về PnL, doanh thu, lợi nhuận hay chi phí của công ty. Nếu bạn "
             "được cấp quyền, số liệu nằm ở trang Doanh thu (PnL); cần quyền thì bạn liên hệ "
             "quản lý trực tiếp nhé.")
LEAK_REPLY = ("Mình không cung cấp số liệu về lương, thu nhập, thưởng hay PnL / doanh thu / lợi "
              "nhuận / chi phí. Bạn xem ở trang tương ứng theo quyền của mình nhé.")
HIDDEN = "[đã ẩn: số liệu lương / tài chính]"


def salary_question(message):
    """PURE. Cau nay hoi ve luong / thu nhap / thuong? (cua ai cung vay - AI khong tra loi)."""
    t = norm(message)
    if _SALARY_SQ.search(_squeeze(t)):
        return True
    if _COMMISSION.search(fold(t)):
        return True
    # "so luong", "chat luong" go khong dau: bo cac cap do truoc khi xet chu "luong" tran.
    return bool(_SALARY.search(_LUONG_BENIGN.sub(" ", t)))


def pnl_question(message):
    """PURE. Cau nay dong toi PnL / doanh thu / loi nhuan / chi phi cong ty?"""
    t = norm(message)
    f = fold(t)
    return bool(_PNL.search(f) or _PNL_ACC.search(t) or _PNL_SQ.search(_squeeze(f)))


def creating(message):
    """PURE. Cau la LENH TAO phieu (co dong tu tao) va KHONG kem cau hoi so lieu."""
    f = fold(norm(message))
    return any(w in f for w in _CREATE) and not _ASKING.search(f)


#: Hoi TU VAN / KHAI NIEM / QUY TRINH (Hoan 27/11: "tu van thi ok co the noi") - vd "KPI doanh
#: thu la gi", "viet email xin tang luong", "tam ung luong lam the nao", "quy trinh thang chuc
#: dieu chinh luong". Xet tren van ban DA norm() + bo dau.
_ADVICE = re.compile(
    r"(la gi|nghia la|khai niem|dinh nghia|cach tinh|cong thuc|the nao|lam sao|ra sao|quy trinh|"
    r"thu tuc|huong dan|cac buoc|viet (giup |ho |mot |1 )?(email|mail|thu|don|tin nhan)|soan|"
    r"\bmau (email|mail|thu|don)|tu van|goi y|meo|ky nang|dam phan|nen (lam|noi|chuan bi)|"
    r"chuan bi gi|kinh nghiem|\bhow to\b|\bwhat is\b|\bexplain\b)")
#: ...nhung co dau hieu hoi SO LIEU THAT / NGUOI CU THE / TO CHUC CU THE -> van chan.
_SPECIFIC = re.compile(
    r"(bao nhieu|\bmay (trieu|tien|cu|phan tram|%)|\d|"
    r"\b(cua|of) (anh|chi|em|ban|sep|ceo|co|chu|ong|ba|bac|thay|nguoi|nhan vien|nv|moi nguoi|"
    r"phong(?! van)|team|bo phan|cong ty|cty|ecentric|brand|khach|minh|toi|tui|tao)\b|"
    r"\b(anh|chi|sep|ceo|giam doc|truong phong|leader|dong nghiep|moi nguoi|ai)\b|"
    r"\b(cong ty|cty|ecentric|phong(?! van)|team|bo phan|brand|khach hang|vinasoy)\b|"
    r"\b(thang|nam|quy|tuan|ky) (nay|truoc|sau|toi|roi|vua roi)\b|hom nay|hien tai|"
    r"so lieu|bang luong|phieu luong|danh sach|tong (cong|so)|cho (minh|toi|em|tui)? ?(xem|biet))")


def advisory(message):
    """PURE. Cau hoi tu van / khai niem / quy trinh CHUNG (khong hoi so lieu that, nguoi hay to
    chuc cu the) -> duoc di tiep toi AI; AI chi giai thich bang kien thuc chung (chat.RULES)."""
    f = fold(norm(message))
    plain = re.sub(r"thang (luong )?(thu )?13|13th month", " ", f)   # khai niem, khong phai so lieu
    return bool(_ADVICE.search(f)) and not _SPECIFIC.search(plain)


SALARY, PNL = "salary", "pnl"


def guard_kind(message, creating_ok=False):
    """PURE. -> (loai, cau tra loi co dinh) khi cau vao vung CAM; (None, None) neu duoc di tiep.

    advisory(): cau tu van chung ve luong / doanh thu duoc di tiep (Hoan 27/11).
    creating_ok=True (eC Mate): cau tao phieu co chu "doanh thu" (xuat hoa don doanh thu...) van
    di tiep de tao NHAP - nhap van theo quyen form, khong lo so lieu nao. Luong thi luon chan.
    khay.intent PHAI kiem lai sau router: cau loai nay chi duoc ra hanh dong `approval`."""
    sal, pnl = salary_question(message), pnl_question(message)
    if not (sal or pnl) or advisory(message):
        return None, None
    if sal:
        return SALARY, SALARY_REPLY
    if creating_ok and creating(message):
        return None, None
    return PNL, PNL_REPLY


def guard(message, creating_ok=False):
    """PURE. -> cau tra loi co dinh neu cau hoi vao vung CAM, nguoc lai None (xem guard_kind)."""
    return guard_kind(message, creating_ok)[1]


#: So TIEN / ti le: 12tr, 12 trieu, 1,2 ty, 15.000.000, 15000000, 30%, 500k, 2000 usd.
_MONEY = re.compile(
    r"(\d[\d.,]*\s?(k|tr|trieu|ty|ti|m|mil|million|b|bn|d|vnd|usd|dong|cu|%)\b|"
    r"\d{1,3}([.,]\d{3})+|\d{6,})", re.I)
#: Hep hon _PNL: phieu "chi phi ... phong X 15.000.000d" la viec thuong ngay, khong an.
_PNL_LEAK = re.compile(
    r"(\bp\W{0,3}n\W{0,3}l\b|doanh thu|doanh so|\b(gmv|nmv)\b|loi nhuan|bien loi|lai gop|lai rong|ebit(da)?\b|"
    r"\brevenues?\b|\bprofits?\b|\bturnover\b|quy luong|chi phi luong|chi phi nhan su|"
    r"ket qua kinh doanh|\b(lai|lo|loi) (duoc )?\d)", re.I)
#: Mot "cau": dau cham / phay nam TRONG so (15.000.000) hay duong dan khong cat cau.
_SENT = re.compile(r"(?:[^.!?;\n•|]|[.!?;](?=\S))+")


def leaks(text):
    """PURE. Doan van co CA tu khoa luong/PnL VA mot so tien / ti le trong cung mot cau?
    Dung cho cau tra loi cua AI (chot cuoi) va du lieu nguoi dung viet dua vao loi dan."""
    for m in _SENT.finditer(str(text or "")):
        s = m.group(0)
        if _MONEY.search(fold(s)) and (salary_question(s) or _PNL_LEAK.search(fold(norm(s)))):
            return True
    return False


def scrub(text):
    """PURE. An CAU co so lieu luong/tai chinh trong mot doan do nguoi dung viet (bao cao tuan,
    bai dang, tieu de phieu) truoc khi dua vao loi dan - AI khong thay thi khong lo duoc."""
    text = str(text or "")
    if not leaks(text):
        return text
    return _SENT.sub(lambda m: (" " + HIDDEN) if leaks(m.group(0)) else m.group(0), text)


def safe_history(turns):
    """PURE. Lich su do CLIENT gui (gia mao duoc): bo moi luot cham vung cam (cau hoi luong/PnL
    cu, cau 'model' bia co so lieu) - de "cua anh ay thi sao?" khong keo lai cau da bi chan."""
    out = []
    for h in turns or []:
        t = h.get("text") or ""
        if guard(t) or leaks(t) or t.strip() in (SALARY_REPLY, PNL_REPLY, LEAK_REPLY):
            continue
        out.append(h)
    return out


def safe_reply(reply):
    """PURE. Chot cuoi tren cau tra loi cua AI: co so lieu luong/PnL -> cau co dinh."""
    return LEAK_REPLY if leaks(reply) else reply


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
        out += ["", "=== %s ===" % title] + ["- " + S.short(scrub(l), width) if "\n" not in l else l
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
