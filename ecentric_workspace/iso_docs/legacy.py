# Copyright (c) 2026, eCentric and contributors
"""Nhap tai lieu CU tu SharePoint (DMS) - mot lan, Ban ISO chay (PO Hoan yeu cau 05/10/2026).

Tai lieu cu da duoc duyet ngoai ERP (ky giay, MS Teams Approval), nen KHONG di lai luong duyet:
tao ban ghi, ghi lich su phien ban theo bang "Lich su thay doi" cua file Word (phien ban moi nhat
= Hieu luc, cac ban truoc = Het hieu luc, chi co tep neu con giu file), roi dat thang trang thai
"Ban hanh". Moi dong lich su ghi nguon "Nhap file cu" + ten nguoi lap / kiem tra / phe duyet theo
file. Trang /tai-lieu gan nhan "Ban cu" cho tai lieu nay toi khi Ban ISO soan lai.

Khong bao gio ghi de: ma da co ma khong phai tai lieu nhap cu -> tu choi; da nhap du phien ban ->
bo qua (chay lai an toan). Khong tao thong bao trang chu.
"""
import json

from ecentric_workspace.iso_docs import constants as C
from ecentric_workspace.iso_docs import domain as D
from ecentric_workspace.iso_docs.errors import DocError, Forbidden

SOURCE = "Nhập file cũ"
TYPES = tuple(n for _p, n in C.DOC_TYPES)
FILE_MAX = 24 * 1024 * 1024


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.iso_docs import repository
    return repository


def _date(s):
    import datetime as dt
    if not s:
        return None
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        raise DocError("Ngày không hợp lệ: %s" % s)


def check(data, departments):
    """-> [loi] cho mot tai lieu cu."""
    e = []
    code = (data.get("code") or "").strip().upper()
    ce = D.code_error(code, data.get("type"))
    if ce:
        e.append(ce)
    if data.get("type") not in TYPES:
        e.append("Loại tài liệu không hợp lệ: %r." % data.get("type"))
    if data.get("dept") not in departments:
        e.append("Phòng ban không có trên ERP: %r." % data.get("dept"))
    if not (data.get("name") or "").strip():
        e.append("Thiếu tên tài liệu.")
    revs = data.get("revisions") or []
    if not revs:
        e.append("Thiếu phiên bản.")
    prev = None
    for r in revs:
        v = r.get("version") or ""
        if not D.parse_version(v):
            e.append("Phiên bản không hợp lệ: %r." % v)
        elif prev and not D.version_gt(v, prev):
            e.append("Phiên bản phải tăng dần: %s sau %s." % (v, prev))
        prev = v
        try:
            _date(r.get("from"))
            _date(r.get("to"))
        except DocError as x:
            e.append(str(x))
    if revs and not revs[-1].get("from"):
        e.append("Phiên bản hiện hành thiếu ngày hiệu lực.")
    return e


def import_one(user, data, repo=None):
    """Nhap MOT tai lieu cu. data: {code, name, type, dept, company_wide, purpose, signers, mermaid,
    steps_json, revisions: [{version, from, to, summary, changed_sections, by, pdf, docx}],
    forms: [{name, file}]} - pdf / docx / file la {name, content} da giai ma.
    -> {code, created, skipped, versions}."""
    repo = _repo(repo)
    if not repo.is_manager(user):
        raise Forbidden("Chỉ Ban ISO nhập được tài liệu cũ.")
    errs = check(data, repo.departments())
    if errs:
        raise DocError("; ".join(errs))
    code = data["code"].strip().upper()
    revs = data["revisions"]
    if repo.exists(code):
        doc = repo.get_doc(code)
        if doc.get("ec_source") != SOURCE:
            raise DocError("Mã %s đã có trên ERP (không phải tài liệu nhập cũ): không ghi đè." % code)
        have = {r.get("version") for r in doc.get("ec_revisions") or []}
        if all(r["version"] in have for r in revs):
            return {"code": code, "created": False, "skipped": True, "versions": sorted(have)}
        raise DocError("%s đã nhập một phần (%s): kiểm tra tay trước khi nhập lại." % (code, ", ".join(sorted(have))))

    repo.insert_doc({
        "quality_procedure_name": data["name"].strip()[:140], "ec_doc_code": code,
        "ec_doc_type": data["type"], "ec_department": data["dept"],
        "ec_company_wide": 1 if data.get("company_wide", 1) else 0, "ec_notify_home": 0,
        "ec_source": SOURCE, "ec_review_months": C.REVIEW_MONTHS_DEFAULT,
        "scope_departments": [] if data.get("company_wide", 1) else list(data.get("scope") or []),
    })
    steps = {}
    if data.get("steps_json"):
        try:
            steps = json.loads(data["steps_json"])
        except ValueError:
            steps = {}
    forms = []
    for f in data.get("forms") or []:
        blob = f.get("file")
        if blob:
            forms.append({"ma": "", "ten": f.get("name") or blob["name"],
                          "url": repo.save_file(code, blob["name"], blob["content"])})
    if forms or data.get("purpose"):
        steps.setdefault("tom_tat", {})
        if data.get("purpose"):
            steps["tom_tat"]["muc_dich"] = data["purpose"].strip()
        steps["bieu_mau"] = list(steps.get("bieu_mau") or []) + forms
    steps_raw = json.dumps(steps, ensure_ascii=False, indent=1) if steps else ""
    rows = []
    last = len(revs) - 1
    for i, r in enumerate(revs):
        row = {"version": r["version"], "change_kind": C.KIND_MAJOR if r["version"].endswith(".0") else C.KIND_MINOR,
               "status": C.REV_EFFECTIVE if i == last else C.REV_EXPIRED,
               "effective_from": _date(r.get("from")), "effective_to": None if i == last else _date(r.get("to")),
               "summary": (r.get("summary") or "").strip() or "Bản chuyển từ SharePoint",
               "changed_sections": r.get("changed_sections") or "", "source": SOURCE, "approved_on": _date(r.get("from"))}
        if r.get("by"):
            row["summary"] += " · Biên soạn: %s" % r["by"].strip()
        if i == last and data.get("signers"):
            row["summary"] += " · Duyệt ngoài ERP (%s)" % data["signers"].strip()
        for kind in ("pdf", "docx"):
            if r.get(kind):
                row[kind] = repo.save_file(code, r[kind]["name"], r[kind]["content"])
        if i == last:
            row["mermaid"] = (data.get("mermaid") or "").strip()
            row["steps_json"] = steps_raw
        rows.append(row)
    eff = rows[-1]["effective_from"]
    repo.update_draft(code, {
        "ec_revisions": rows, "ec_current_version": rows[-1]["version"], "ec_effective_from": eff,
        "ec_next_review": D.add_months(eff, C.REVIEW_MONTHS_DEFAULT), "ec_mermaid": rows[-1]["mermaid"],
        "ec_steps_json": steps_raw, "ec_change_summary": "",
    })
    repo.force_published(code, "Nhập từ SharePoint (bản cũ, đã duyệt ngoài ERP) - %d phiên bản." % len(rows))
    return {"code": code, "created": True, "skipped": False, "versions": [r["version"] for r in rows]}
