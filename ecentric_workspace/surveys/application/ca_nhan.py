# Copyright (c) 2026, eCentric and contributors
"""Khao sat CA NHAN (giao cho tung nguoi) - ha tang + job moc thu viec / thuc tap.

Hoan chot 22-23/11/2026 (HR Dot 2). Truoc day module chi co khao sat theo CHIEN DICH (doi tuong
= phong ban / ca cong ty). Quy trinh nhan su can giao mot khao sat cho MOT nguoi vao MOT ngay
(thu viec D7/D30/D45, thuc tap D30/D60/D75, khao sat nghi viec), co han, nhac, va chi mot
nhom nguoi duoc xem ket qua.

Thiet ke (dung lai EC Survey / Participant / Response, them EC Survey Assignment):
  * moi loai khao sat = mot EC Survey "mau" (`survey_kind` = ca nhan, `ma_mau` on dinh);
  * moi lan giao = mot EC Survey Assignment (nguoi, han, ngu canh, nguoi xem, `dedupe_key`);
  * NGUOI TRA LOI lam bai tren trang /khao-sat/lam nhu moi khao sat khac - access.eligible_set
    doc lan giao dang mo, khong doc bang doi tuong;
  * DA NOP hay chua: doc EC Survey Participant (mot nguon su that, khong chep trang thai);
  * NHAC: job 09:00 ngay lam viec, MOT lan, truoc han 1 ngay lam viec, ghi `reminded_at`;
  * XEM KET QUA: domain/ca_nhan.quyen_xem - HR / C&B (role trong viewer_roles) xem du, LM cua
    nguoi tra loi xem phan "LM xem duoc" (cau trong lm_hidden_items bi an).

API ON DINH CHO MODULE KHAC (Agent C - khao sat nghi viec goi qua frappe.get_attr):
    giao_khao_sat(user, ma_mau, han_ngay_lv, ngu_canh, nguoi_xem_role) -> dict
Khong bao gio nem loi nghiep vu ra ngoai: thieu mau / user khong hop le -> {"ok": False, "ly_do"}
+ Error Log, de luong goi (duyet don nghi viec) khong hong vi mot khao sat phu.
"""
import json

from ecentric_workspace.hr.hop_dong import domain as hd
from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.application import access, export_format
from ecentric_workspace.surveys.domain import ca_nhan as rule
from ecentric_workspace.surveys.domain import moc as moc_rule
from ecentric_workspace.surveys.domain import schema
from ecentric_workspace.surveys.domain.errors import SurveyNotFound, SurveyPermissionError
from ecentric_workspace.surveys.infrastructure import repository as default_repo


def _hr_repo():
    from ecentric_workspace.hr.hop_dong import repository
    return repository


# --------------------------------------------------------------------------- giao --

def giao_khao_sat(user, ma_mau, han_ngay_lv=None, ngu_canh=None, nguoi_xem_role=None,
                  repo=default_repo):
    """Giao khao sat mau `ma_mau` cho `user`, han `han_ngay_lv` ngay lam viec tu hom nay.

    ngu_canh      : dict (vd {"khoa": "<don nghi viec>", ...}); "khoa" (neu co) la khoa chong trung.
    nguoi_xem_role: role duoc xem ket qua ("HR" / "HR,EC CnB,LM" / list); "LM" = quan ly truc tiep
                    hien tai cua nguoi tra loi. None -> role quan ly cua mau.
    Tra ve {"ok": bool, "assignment": ten, "duplicate": bool, "due_date": "YYYY-MM-DD", "ly_do"}.
    Idempotent: cung (user, ma_mau, ngu_canh) goi lai -> tra lan giao cu, khong bao lai."""
    try:
        return _giao(user, ma_mau, han_ngay_lv, ngu_canh, nguoi_xem_role, repo)
    except Exception:
        repo.log_error("surveys.ca_nhan.giao_khao_sat %s %s" % (user, ma_mau))
        return {"ok": False, "ly_do": "loi_he_thong"}


def _giao(user, ma_mau, han_ngay_lv, ngu_canh, nguoi_xem_role, repo):
    if isinstance(ngu_canh, str):
        try:
            ngu_canh = json.loads(ngu_canh) if ngu_canh.strip() else {}
        except ValueError:
            ngu_canh = {"ghi_chu": ngu_canh}
    ngu_canh = ngu_canh if isinstance(ngu_canh, dict) else {}
    if not repo.user_exists(user):
        return {"ok": False, "ly_do": "user_khong_hop_le"}
    survey = repo.survey_by_ma_mau(ma_mau)
    if not survey:
        repo.log_error("surveys.ca_nhan: chua co mau khao sat %s" % ma_mau)
        return {"ok": False, "ly_do": "chua_co_mau"}
    if survey.get("status") != C.STATUS_OPEN:
        repo.log_error("surveys.ca_nhan: mau %s dang %s (can Open)" % (ma_mau, survey.get("status")))
        return {"ok": False, "ly_do": "mau_chua_mo"}
    key = rule.khoa_giao(user, ma_mau, ngu_canh)
    old = repo.assignment_by_key(key)
    if old:
        return {"ok": True, "assignment": old["name"], "duplicate": True,
                "due_date": str(old.get("due_date") or "")}
    viewers = rule.chuan_hoa_nguoi_xem(nguoi_xem_role) or tuple(access.manager_roles_of(survey))
    hom_nay = repo.today()
    try:
        n = int(han_ngay_lv) if han_ngay_lv not in (None, "") else C.HAN_NGAY_LV_MAC_DINH
    except (TypeError, ValueError):
        n = C.HAN_NGAY_LV_MAC_DINH
    due = hd.cong_ngay_lam_viec(hom_nay, max(n, 1), repo.ngay_le())
    emp = repo.employee_of_user(user) or {}
    name = repo.insert_assignment({
        "survey": survey["name"], "ma_mau": ma_mau, "user": user, "employee": emp.get("name"),
        "status": C.ASSIGN_OPEN, "assigned_on": hom_nay, "due_date": due,
        "viewer_roles": "\n".join(viewers),
        "ngu_canh": json.dumps(ngu_canh, ensure_ascii=False, sort_keys=True, default=str),
        "dedupe_key": key})
    repo.notify(user, "Bạn có khảo sát cần làm: %s" % (survey.get("title") or ma_mau),
                "Hạn %s. Câu trả lời chỉ những người được phép mới xem." % _vn(due),
                "/" + C.ROUTE_FILL + "?s=" + survey["name"], survey["name"],
                "survey|assign|%s" % name)
    return {"ok": True, "assignment": name, "duplicate": False, "due_date": str(due)}


def huy_giao(assignment, ly_do, repo=default_repo):
    """Huy mot lan giao chua nop (vd NV nghi viec). Da nop thi giu nguyen."""
    a = repo.get_assignment(assignment)
    if not a or a.get("status") != C.ASSIGN_OPEN:
        return False
    if repo.get_participant(a["survey"], a["user"]):
        return False
    repo.set_assignment(assignment, {"status": C.ASSIGN_CANCELLED,
                                     "cancelled_reason": (ly_do or "")[:500]})
    return True


def _vn(d):
    d = hd.as_date(d)
    return "%02d/%02d/%04d" % (d.day, d.month, d.year) if d else "—"


# --------------------------------------------------------------------- job moc --

def giao_khao_sat_moc_job(hom_nay=None, repo=default_repo, hr=None):
    """Job 09:00 ngay lam viec: giao khao sat moc thu viec / thuc tap. Tra ve so lan giao moi.

    Idempotent (khoa = dong hop dong + so moc). Chi giao moc DANG MO (domain/moc.moc_can_giao),
    nen job tat vai ngay khong ban ca ba khao sat mot luc. NV khong con Probation / Intern (len
    chinh thuc som, nghi viec) -> khong giao moc con lai."""
    if repo.site_flag(C.FLAG_MOC_DISABLED):
        return 0
    hr = hr or _hr_repo()
    hom_nay = hd.as_date(hom_nay) or repo.today()
    ngay_le = repo.ngay_le()
    if not hd.la_ngay_lam_viec(hom_nay, ngay_le):
        return 0
    emps = [e for e in hr.nhan_vien_dang_lam() if e.get("user_id")]
    rows_by = hr.hop_dong_cua([e["name"] for e in emps])
    da_giao = 0
    for e in emps:
        try:
            if (e.get("employment_type") or "") not in (hd.ET_PROBATION, hd.ET_INTERN, ""):
                continue
            row = hd.dong_hien_hanh(rows_by.get(e["name"]) or [], hom_nay)
            if not row or row.get("loai_hop_dong") not in moc_rule.MOC:
                continue
            den = hd.as_date(row.get("den_ngay"))
            if den and den < hom_nay:
                continue
            ngay_nhap = hd.ngay_tao_nhap(hd.loai_danh_gia(row), den, ngay_le) if den else None
            m = moc_rule.moc_can_giao(
                moc_rule.cac_moc(row["loai_hop_dong"], row.get("tu_ngay"), ngay_nhap, ngay_le),
                hom_nay, ngay_nhap)
            if not m:
                continue
            res = giao_khao_sat(e["user_id"], m[1], C.HAN_NGAY_LV_MAC_DINH, {
                "khoa": "%s|moc%s" % (row.get("name"), m[0]), "loai": row["loai_hop_dong"],
                "moc": m[0], "ngay_moc": str(m[2]), "employee": e["name"],
                "dong_hop_dong": row.get("name"), "tu_ngay": str(row.get("tu_ngay") or ""),
                "den_ngay": str(den or "")}, C.VIEWERS_MOC, repo=repo)
            if res.get("ok") and not res.get("duplicate"):
                da_giao += 1
        except Exception:
            repo.log_error("surveys.ca_nhan.giao_khao_sat_moc_job %s" % e.get("name"))
    return da_giao


# ----------------------------------------------------------------------- nhac --

def nhac_khao_sat_ca_nhan_job(hom_nay=None, repo=default_repo):
    """Job 09:00 ngay lam viec: nhac MOT lan nhung lan giao chua nop, tu 1 ngay lam viec truoc han.

    Ghi `reminded_at` - da co thi khong nhac lai. Nguoi dang nghi hom nay -> de ngay lam viec sau.
    Nguoi khong con la nhan vien Active -> huy lan giao (khong nhac nguoi da nghi)."""
    hom_nay = hd.as_date(hom_nay) or repo.today()
    ngay_le = repo.ngay_le()
    if not hd.la_ngay_lam_viec(hom_nay, ngay_le):
        return 0
    opens = [a for a in repo.open_assignments() if not a.get("reminded_at")]
    done = repo.participants_of_pairs([(a["survey"], a["user"]) for a in opens])
    da_nhac = 0
    for a in opens:
        try:
            if (a["survey"], a["user"]) in done:
                continue
            emp = repo.employee_of_user(a["user"])
            if emp and emp.get("status") not in (None, "", "Active"):
                huy_giao(a["name"], "Nhân viên không còn làm việc", repo=repo)
                continue
            due = hd.as_date(a.get("due_date"))
            if not due or hom_nay < hd.lui_ngay_lam_viec(due, C.NHAC_TRUOC_NGAY_LV, ngay_le):
                continue
            if not repo.nguoi_di_lam([a["user"]], hom_nay):
                continue
            repo.notify(a["user"], "Nhắc: khảo sát cần làm trước %s" % _vn(due),
                        "Bạn chưa trả lời khảo sát được giao. Mất khoảng vài phút.",
                        "/" + C.ROUTE_FILL + "?s=" + a["survey"], a["survey"],
                        "survey|remind1|%s" % a["name"])
            repo.set_assignment(a["name"], {"reminded_at": repo.now()})
            da_nhac += 1
        except Exception:
            repo.log_error("surveys.ca_nhan.nhac %s" % a.get("name"))
    return da_nhac


# ---------------------------------------------------------------- xem ket qua --

def _form(survey):
    raw = survey.get("form_json") or "{}"
    try:
        return schema.normalize(json.loads(raw) if isinstance(raw, str) else raw)
    except Exception:
        return {"v": 1, "items": []}


def _hien_thi(questions, answers):
    out = []
    for q in questions:
        v = (answers or {}).get(q["id"])
        if q["type"] in C.GRID_TYPES:
            cols = {c["id"]: c["label"] for c in q.get("cols") or []}
            parts = []
            for r in q.get("rows") or []:
                x = (v or {}).get(r["id"]) if isinstance(v, dict) else None
                if isinstance(x, list):
                    x = ", ".join(cols.get(c, c) for c in x)
                else:
                    x = cols.get(x, x or "")
                if x:
                    parts.append("%s: %s" % (r["label"], x))
            text = "; ".join(parts)
        else:
            text = export_format.cell(q, v)
        out.append({"id": q["id"], "title": q.get("title") or "", "type": q["type"],
                    "value": "" if text in (None, "") else str(text)})
    return out


def _quyen(ctx, a, reports):
    manager = ctx.user if a["user"] in reports else None
    return rule.quyen_xem(ctx.user, ctx.roles, rule.doc_danh_sach(a.get("viewer_roles")),
                          a["user"], manager, ctx.is_admin)


def _trang_thai(a, part, hom_nay):
    if a.get("status") == C.ASSIGN_CANCELLED:
        return "Đã huỷ"
    if part:
        return "Đã nộp"
    due = hd.as_date(a.get("due_date"))
    return "Quá hạn" if due and due < hom_nay else "Chưa nộp"


def danh_sach_ket_qua(ctx, repo=default_repo, user=None):
    """Lan giao NGUOI XEM duoc phep thay (du hoac phan LM). user: loc theo nguoi tra loi."""
    reports = repo.direct_report_users(ctx.user)
    filters = {"user": user} if user else None
    rows = repo.assignments(filters)
    mine = [(a, _quyen(ctx, a, reports)) for a in rows]
    mine = [(a, q) for a, q in mine if q]
    parts = repo.participants_of_pairs([(a["survey"], a["user"]) for a, _q in mine])
    names = repo.user_names([a["user"] for a, _q in mine])
    titles = {}
    hom_nay = repo.today()
    out = []
    for a, q in mine:
        if a["survey"] not in titles:
            s = repo.get_survey(a["survey"]) or {}
            titles[a["survey"]] = s.get("title") or a.get("ma_mau")
        part = parts.get((a["survey"], a["user"]))
        out.append({"name": a["name"], "ma_mau": a.get("ma_mau"), "title": titles[a["survey"]],
                    "user": a["user"], "user_name": names.get(a["user"], a["user"]),
                    "assigned_on": str(a.get("assigned_on") or ""),
                    "due_date": str(a.get("due_date") or ""),
                    "submitted_at": str((part or {}).get("submitted_at") or "")[:16],
                    "trang_thai": _trang_thai(a, part, hom_nay), "quyen": q})
    return {"rows": out}


def xem_ket_qua(ctx, assignment, repo=default_repo):
    a = repo.get_assignment(assignment)
    if not a:
        raise SurveyNotFound("Không tìm thấy khảo sát được giao.")
    q = _quyen(ctx, a, repo.direct_report_users(ctx.user))
    if not q:
        raise SurveyPermissionError("Bạn không được xem kết quả khảo sát này.")
    return _chi_tiet(repo, a, q)


def _chi_tiet(repo, a, q):
    survey = repo.get_survey(a["survey"]) or {}
    questions = schema.questions(_form(survey))
    part = repo.get_participant(a["survey"], a["user"])
    answers = {}
    if part and part.get("response"):
        resp = repo.get_response(part["response"]) or {}
        answers = resp.get("answers") or {}
    so_an = 0
    if q == rule.LM:
        questions, answers, so_an = rule.an_voi_lm(
            questions, answers, rule.doc_danh_sach(survey.get("lm_hidden_items")))
    names = repo.user_names([a["user"]])
    return {"name": a["name"], "title": survey.get("title") or a.get("ma_mau"),
            "ma_mau": a.get("ma_mau"), "user": a["user"],
            "user_name": names.get(a["user"], a["user"]), "due_date": str(a.get("due_date") or ""),
            "submitted": bool(part), "submitted_at": str((part or {}).get("submitted_at") or "")[:16],
            "quyen": q, "so_cau_an": so_an, "mau_tam": int(survey.get("mau_tam") or 0),
            "answers": _hien_thi(questions, answers) if part else []}


def ket_qua_cho_danh_gia(viewer, roles, respondent_user, repo=default_repo, is_admin=False):
    """Khoi "Khao sat moc" tren phieu Danh gia nhan su: moi lan giao moc thu viec / thuc tap cua
    `respondent_user` ma `viewer` duoc xem - DA AP quyen + an cau "chi HR". Khong co -> []."""
    ctx = access.Ctx(viewer, roles)
    if is_admin:
        ctx.roles.add("System Manager")
    reports = repo.direct_report_users(viewer)
    out = []
    for a in repo.assignments({"user": respondent_user}):
        if not str(a.get("ma_mau") or "").startswith(("KS_THU_VIEC_", "KS_THUC_TAP_")):
            continue
        q = _quyen(ctx, a, reports)
        if q:
            out.append(_chi_tiet(repo, a, q))
    out.sort(key=lambda r: r["ma_mau"] or "")
    return out
