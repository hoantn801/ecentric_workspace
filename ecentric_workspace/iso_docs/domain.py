# Copyright (c) 2026, eCentric and contributors
"""Thu vien tai lieu ISO - quy tac THUAN (khong frappe, khong DB). Test chay khong can bench.

Moi ham nhan / tra kieu don gian (str, date, dict, list) de service ghep voi repo.
"""
import datetime as _dt
import re
import unicodedata

from ecentric_workspace.iso_docs import constants as C

_CODE_RE = re.compile(C.CODE_RE)
_VER_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})$")


# --------------------------------------------------------------------------- ten trang thai
def norm_state(s):
    """So trang thai KHONG phan biet dau / hoa thuong. Site da co san Workflow State "Nhap" va
    "Cho Truong bo phan" (luong duyet khac); collation MariaDB coi "Nháp" = "Nhap" nen Workflow
    "Tai lieu ISO" dung lai ten cu va doc luu "Nhap". So bang == se truot (phat hien 05/10)."""
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return " ".join("".join(c for c in s if unicodedata.category(c) != "Mn").casefold().split())


def is_state(value, state):
    return norm_state(value) == norm_state(state)


# --------------------------------------------------------------------------- phien ban X.Y
def parse_version(v):
    """"2.1" -> (2, 1); sai dang / rong -> None."""
    m = _VER_RE.match((v or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def fmt_version(t):
    return "%d.%d" % t


def next_version(current, kind):
    """Phien ban tiep theo. Chua co phien ban nao -> 1.0. Lon -> (X+1).0. Nho -> X.(Y+1)."""
    cur = parse_version(current)
    if not cur:
        return "1.0"
    if kind == C.KIND_MINOR:
        return fmt_version((cur[0], cur[1] + 1))
    return fmt_version((cur[0] + 1, 0))


def version_gt(a, b):
    pa, pb = parse_version(a), parse_version(b)
    if pa is None:
        return False
    return pb is None or pa > pb


# --------------------------------------------------------------------------- ma tai lieu
def code_error(code, doc_type=None):
    """None neu ma hop le. Dang <Loai>-<Phong>-<STT>, bieu mau them -<STT>: BM-QT-TCKT-03-01 cung
    duoc vi ma bieu mau = BM + ma tai lieu goc."""
    code = (code or "").strip()
    if not code:
        return "Thiếu mã tài liệu."
    if code.startswith("BM-") and _CODE_RE.match(code[3:]) and re.search(r"-\d{2}-\d{2}$", code):
        return None
    if not _CODE_RE.match(code):
        return "Mã %s không đúng dạng <Loại>-<Phòng>-<STT>, ví dụ QT-TCKT-03." % code
    want = dict((name, prefix) for prefix, name in C.DOC_TYPES).get(doc_type or "")
    if want and want != "TL" and code.split("-")[0] != want:
        return "Mã %s không khớp loại %s (mã phải bắt đầu bằng %s-)." % (code, doc_type, want)
    return None


# --------------------------------------------------------------------------- kiem tra tai lieu
def validate(d):
    """d: dict cac truong ec_* cua tai lieu. -> danh sach loi (rong = hop le).

    Luat thong bao trang chu (spec 04/10, muc 5): chi tai lieu TOAN CONG TY moi duoc tich."""
    errs = []
    e = code_error(d.get("ec_doc_code"), d.get("ec_doc_type"))
    if e:
        errs.append(e)
    company_wide = bool(d.get("ec_company_wide"))
    if not company_wide and not d.get("scope_departments"):
        errs.append("Tài liệu không áp dụng toàn công ty thì phải chọn phòng ban được đọc.")
    if d.get("ec_notify_home") and not company_wide:
        errs.append("Chỉ tài liệu áp dụng toàn công ty mới được thông báo lên trang chủ.")
    if d.get("ec_change_kind") and d.get("ec_change_kind") not in C.KINDS:
        errs.append("Kiểu sửa phải là Lớn hoặc Nhỏ.")
    dv = (d.get("ec_draft_version") or "").strip()
    if dv:
        if not parse_version(dv):
            errs.append("Phiên bản %s không đúng dạng X.Y, ví dụ 2.0." % dv)
        elif d.get("ec_current_version") and not version_gt(dv, d.get("ec_current_version")):
            errs.append("Phiên bản đang soạn %s phải lớn hơn phiên bản hiệu lực %s."
                        % (dv, d.get("ec_current_version")))
    months = d.get("ec_review_months")
    if months not in (None, "") and (int(months) < 1 or int(months) > 60):
        errs.append("Chu kỳ rà soát phải từ 1 đến 60 tháng.")
    return errs


def draft_kind(current_version, change_kind):
    """Tai lieu moi (chua co phien ban) luon la ban hanh LON (co quyet dinh TGD)."""
    if not current_version:
        return C.KIND_MAJOR
    return change_kind if change_kind in C.KINDS else C.KIND_MAJOR


# --------------------------------------------------------------------------- chuyen trang thai
def transition_kind(before, after):
    """Loai su kien khi trang thai workflow doi before -> after (None neu khong doi)."""
    b, a = norm_state(before), norm_state(after)
    n = norm_state
    if b == a:
        return None
    if a == n(C.S_PUBLISHED) and b in (n(C.S_ISO), n(C.S_CEO)):
        return "publish"
    if a == n(C.S_PUBLISHED) and b == n(C.S_WITHDRAW):
        return "keep"                     # TGD khong dong y thu hoi
    if a == n(C.S_EXPIRED):
        return "withdraw"
    if b == n(C.S_PUBLISHED) and a == n(C.S_DRAFT):
        return "new_draft"
    if b == n(C.S_ISO) and a == n(C.S_CEO):
        return "iso_review"
    return "move"


def add_days(d, n):
    return d + _dt.timedelta(days=n)


def add_months(d, months):
    m = d.month - 1 + int(months)
    y, m = d.year + m // 12, m % 12 + 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return _dt.date(y, m, min(d.day, last))


def publish_plan(revisions, current_version, draft_version, change_kind, today, approver,
                 reviewer=None, effective_from=None, review_months=None, extra=None):
    """Ke hoach ban hanh MOT phien ban - khong ghi gi, service ap dung.

    revisions: [{version, status, ...}] lich su hien co.
    -> {"version", "already": bool, "close": [(index, {..})], "row": {..} | None, "doc": {..}}
    Idempotent theo phien ban: phien ban da co trong lich su -> already=True, khong them dong.
    Phien ban dang hieu luc cu -> Het hieu luc, hieu luc den = ngay truoc ngay hieu luc moi.
    """
    kind = draft_kind(current_version, change_kind)
    version = (draft_version or "").strip() or next_version(current_version, kind)
    eff = effective_from or today
    months = int(review_months or C.REVIEW_MONTHS_DEFAULT)
    doc = {"ec_current_version": version, "ec_effective_from": eff, "ec_approver": approver,
           "ec_next_review": add_months(eff, months),
           "ec_draft_version": "", "ec_change_kind": "", "ec_change_summary": "",
           "ec_draft_pdf": "", "ec_draft_docx": ""}
    if any((r.get("version") or "") == version for r in revisions or ()):
        return {"version": version, "already": True, "close": [], "row": None, "doc": {}}
    close = []
    for i, r in enumerate(revisions or ()):
        if r.get("status") == C.REV_EFFECTIVE:
            to = add_days(eff, -1)
            close.append((i, {"status": C.REV_EXPIRED, "effective_to": to}))
    row = {"version": version, "change_kind": kind, "status": C.REV_EFFECTIVE,
           "effective_from": eff, "effective_to": None, "approver": approver,
           "reviewer": reviewer or approver, "approved_on": today}
    row.update(extra or {})
    return {"version": version, "already": False, "close": close, "row": row, "doc": doc}


def withdraw_plan(revisions, today):
    """Thu hoi ca tai lieu: dong dang hieu luc -> Da thu hoi, hieu luc den = hom nay."""
    return [(i, {"status": C.REV_WITHDRAWN, "effective_to": today})
            for i, r in enumerate(revisions or ()) if r.get("status") == C.REV_EFFECTIVE]


# --------------------------------------------------------------------------- thong bao trang chu
def should_announce(notify_home, company_wide):
    return bool(notify_home) and bool(company_wide)


def announcement_payload(code, title, version, effective_from, summary=""):
    """Tham so cho home_today.announce_service.publish_from_source (spec 04/10, muc 2).
    display "Anh + noi dung" la mac dinh cua service."""
    return {
        "title": "Ban hành: %s %s (v%s)" % (code, (title or "").strip(), version),
        "category": C.HOME_CATEGORY,
        "summary": (summary or "").strip(),
        "start_date": effective_from,
        "end_date": add_days(effective_from, C.HOME_DAYS - 1),
        "link": C.HOME_LINK_PREFIX + code,
        "link_label": C.HOME_LINK_LABEL,
    }


# --------------------------------------------------------------------------- quyen
def in_scope(selected, viewer_lft):
    """selected: [(lft, rgt)] phong duoc doc; phong cha bao gom phong con (nested set)."""
    if viewer_lft is None:
        return False
    return any(lo is not None and lo <= viewer_lft <= hi for lo, hi in selected or ())


def can_read(doc, user, is_manager, viewer, selected):
    """doc: dict (ec_current_version, ec_doc_state, ec_company_wide, ec_drafter, ec_dept_head).
    viewer: {"lft": ...} ho so Employee Active cua nguoi xem, None neu khong co.

    Ban ISO / TGD / SM: moi tai lieu. Nguoi soan + truong BP cua tai lieu: luon thay.
    Nhan vien (co ho so Employee Active): tai lieu DA CO phien ban hieu luc, chua het hieu luc,
    va toan cong ty hoac trong pham vi phong ban (phong cha gom phong con)."""
    if is_manager:
        return True
    if user and user in (doc.get("ec_drafter"), doc.get("ec_dept_head")):
        return True
    if not viewer:
        return False
    if not doc.get("ec_current_version") or is_state(doc.get("ec_doc_state"), C.S_EXPIRED):
        return False
    if doc.get("ec_company_wide"):
        return True
    return in_scope(selected, viewer.get("lft"))


def can_write(doc, user, is_manager):
    """Ghi (luu form / chuyen buoc). Nguoi soan sua khi Nhap; truong BP khi cho minh duyet.
    Buoc nao role nao bam duoc thi Workflow tu quyet; day chi chan ghi ngoai luong."""
    if is_manager:
        return True
    state = doc.get("ec_doc_state") or C.S_DRAFT
    if is_state(state, C.S_DRAFT) and user and user == doc.get("ec_drafter"):
        return True
    if is_state(state, C.S_HEAD) and user and user == doc.get("ec_dept_head"):
        return True
    return False


# --------------------------------------------------------------------------- thong bao duyet
#: trang thai cho -> ai bam buoc tiep (khoa: trang thai da chuan hoa)
_WAITING = {"head": C.S_HEAD, "iso": C.S_ISO, "ceo": C.S_CEO, "withdraw": C.S_WITHDRAW}


def notify_plan(before, after, doc, actor, iso_users=(), ceo_users=(), note=""):
    """Chuyen buoc before -> after cua tai lieu doc (dict) do actor bam -> danh sach thong bao
    [{to, event, title, message, url}]. THUAN, khong goi DB.

    - Vao buoc cho (truong BP / Ban ISO / TGD / thu hoi): bao nguoi bam duoc buoc tiep.
      Truong BP trong (phong chua co) -> Ban ISO, giong dieu kien NO_HEAD cua workflow.
    - Bi tra ve Nhap tu mot buoc cho: bao nguoi soan, kem y kien.
    - Ban hanh: bao nguoi soan.
    Khong bao chinh nguoi bam; moi nguoi mot lan."""
    if before is None or norm_state(before) == norm_state(after):
        return []
    code = doc.get("ec_doc_code") or doc.get("name") or ""
    name = doc.get("quality_procedure_name") or ""
    head = "%s %s" % (code, name)
    ver = doc.get("ec_draft_version") or ""
    ver_txt = ("bản " + ver) if ver else ("bản đầu" if not doc.get("ec_current_version") else "bản mới")
    out = []
    waiting_urls = "/tai-lieu/quan-ly?loc=cho-toi&ma=" + code
    if is_state(after, C.S_HEAD):
        to = [doc.get("ec_dept_head")] if doc.get("ec_dept_head") else list(iso_users)
        out = [(u, "approval_required", "Tài liệu chờ bạn duyệt: " + head,
                "%s · trưởng bộ phận xem trước khi chuyển Ban ISO" % ver_txt, waiting_urls) for u in to]
    elif is_state(after, C.S_ISO):
        out = [(u, "approval_required", "Tài liệu chờ Ban ISO: " + head,
                "%s · trưởng bộ phận đã đồng ý" % ver_txt, waiting_urls) for u in iso_users]
    elif is_state(after, C.S_CEO):
        out = [(u, "approval_required", "Tài liệu chờ Tổng giám đốc duyệt: " + head,
                "%s · Ban ISO đã xem" % ver_txt, waiting_urls) for u in ceo_users]
    elif is_state(after, C.S_WITHDRAW):
        out = [(u, "approval_required", "Đề nghị thu hồi tài liệu: " + head,
                "Ban ISO đề nghị thu hồi bản đang hiệu lực", waiting_urls) for u in ceo_users]
    elif is_state(after, C.S_DRAFT) and any(is_state(before, s) for s in _WAITING.values()):
        msg = "Ý kiến: " + note if note else "Xem ý kiến trong lịch sử duyệt"
        out = [(doc.get("ec_drafter"), "approval_required", "Tài liệu bị trả lại: " + head,
                msg[:300], "/tai-lieu/soan?ma=" + code)]
    elif is_state(after, C.S_PUBLISHED) and any(is_state(before, s) for s in (C.S_ISO, C.S_CEO)):
        out = [(doc.get("ec_drafter"), "mention", "Tài liệu đã ban hành: " + head,
                "Bản %s có hiệu lực, nhân viên đã đọc được" % (doc.get("ec_current_version") or ver),
                "/tai-lieu/" + code)]
    seen, res = set(), []
    for to, ev, title, msg, url in out:
        if not to or to == actor or to in seen or to in ("Guest", "Administrator"):
            continue
        seen.add(to)
        res.append({"to": to, "event": ev, "title": title[:140], "message": msg, "url": url})
    return res
