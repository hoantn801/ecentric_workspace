# Copyright (c) 2026, eCentric and contributors
"""Trang quan ly /tai-lieu/quan-ly (mockup B rut gon, PO duyet 04/10) + bam buoc duyet + nhap goi.

Ai vao duoc: moi nhan vien, nhung chi thay tai lieu Frappe cho phep (Ban ISO / TGD / SM thay het;
truong BP / nguoi soan thay tai lieu cua minh). "Cho toi duyet" = tai lieu dang o buoc duyet ma
NGUOI NAY co nut bam (Workflow tu tinh theo role + dieu kien). Nhap goi: chi Ban ISO / TGD / SM.
"""
import json

from ecentric_workspace.iso_docs import constants as C
from ecentric_workspace.iso_docs import domain as D
from ecentric_workspace.iso_docs import package as P
from ecentric_workspace.iso_docs import view as V
from ecentric_workspace.iso_docs.errors import DocError, Forbidden, NotFound

FILTERS = ("cho-toi", "ra-soat", "dang-soan", "het-hieu-luc", "tat-ca", "phong")
RETURN_ACTIONS = ("Trả lại",)
DANGER_ACTIONS = ("Trả lại", "Thu hồi", "Đề nghị thu hồi")
FILE_MAX = 20 * 1024 * 1024
TOTAL_MAX = 24 * 1024 * 1024
FORM_EXT = (".docx", ".doc", ".xlsx", ".xls", ".pdf", ".pptx")


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.iso_docs import repository
    return repository


def _tag(r, acts, today):
    """Nhan tren dong (chi khi can chu y) -> (css, chu) hoac None."""
    st = r.get("ec_doc_state")
    draft_v = r.get("ec_draft_version") or (D.next_version(r.get("ec_current_version"), D.draft_kind(
        r.get("ec_current_version"), r.get("ec_change_kind"))))
    if V.is_pending(st) and acts:
        if D.is_state(st, C.S_WITHDRAW):
            return ("bad", "Đề nghị thu hồi, chờ bạn")
        return ("wait", "Bản %s chờ bạn duyệt" % draft_v)
    if V.is_pending(st):
        return ("off", "Bản %s · %s" % (draft_v, V.state_label(st)))
    if D.is_state(st, C.S_EXPIRED):
        return ("off", "Hết hiệu lực")
    if D.is_state(st, C.S_DRAFT):
        return ("off", "Đang soạn bản %s" % draft_v)
    due = V.review_due(r, today)
    if due == "qua-han":
        return ("old", "Quá hạn rà soát")
    if due == "sap-den-han":
        return ("old", "Rà soát trước %s" % V.fdate(r.get("ec_next_review")))
    return None


def manage_page(user, flt="", dept="", q="", open_code="", repo=None):
    repo = _repo(repo)
    today = repo.today()
    is_mgr = repo.is_manager(user)
    rows = repo.list_docs()
    docs = {}
    acts = {}
    for r in rows:
        if V.is_pending(r.get("ec_doc_state")) or r.get("name") == open_code:
            d = repo.get_doc(r["name"])
            docs[r["name"]] = d
            acts[r["name"]] = repo.transitions(d) if d else []
    mine = [r for r in rows if V.is_pending(r.get("ec_doc_state")) and acts.get(r["name"])]
    due = [r for r in rows if V.review_due(r, today)]
    drafting = [r for r in rows if not D.is_state(r.get("ec_doc_state"), C.S_PUBLISHED)
                and not D.is_state(r.get("ec_doc_state"), C.S_EXPIRED)]
    expired = [r for r in rows if D.is_state(r.get("ec_doc_state"), C.S_EXPIRED)]
    live = [r for r in rows if not D.is_state(r.get("ec_doc_state"), C.S_EXPIRED)]
    by_dept = {}
    for r in live:
        by_dept.setdefault(r.get("ec_department") or "", []).append(r)
    if flt not in FILTERS:
        flt = "cho-toi" if mine else "tat-ca"
    if flt == "phong" and dept not in by_dept:
        flt = "tat-ca"
    pick = {"cho-toi": mine, "ra-soat": due, "dang-soan": drafting, "het-hieu-luc": expired,
            "tat-ca": live, "phong": by_dept.get(dept, [])}[flt]
    if q.strip():
        words = D.norm_state(q).split()
        pick = [r for r in rows if all(w in D.norm_state((r.get("ec_doc_code") or "") + " " +
                                                         (r.get("quality_procedure_name") or "")) for w in words)]
    names = [r["name"] for r in pick]
    revs = {}
    for v in repo.revisions(names):
        revs.setdefault(v["parent"], []).append(v)
    people = repo.full_names([r.get("ec_drafter") for r in pick])
    items = []
    for r in pick:
        name = r["name"]
        a = acts.get(name)
        if a is None:
            # chua tinh (tai lieu khong o buoc duyet): chi can khi mo dong -> tinh luon cho dong do
            d = repo.get_doc(name)
            a = repo.transitions(d) if d else []
        st = r.get("ec_doc_state")
        vlist = []
        if not D.is_state(st, C.S_PUBLISHED) and not D.is_state(st, C.S_EXPIRED):
            vlist.append({"version": r.get("ec_draft_version") or "mới", "when": V.state_label(st).lower(),
                          "note": " · ".join(x for x in (r.get("ec_change_summary") or "",
                                                       ("sửa " + r["ec_change_kind"].lower()) if r.get("ec_change_kind") else "") if x),
                          "off": False, "draft": True})
        cur_pdf = cur_docx = ""
        for v in reversed(revs.get(name, [])):
            off = v.get("status") != C.REV_EFFECTIVE
            if not off:
                cur_pdf, cur_docx = v.get("pdf") or "", v.get("docx") or ""
            vlist.append({"version": v.get("version"), "when": V.fdate(v.get("effective_from")),
                          "note": v.get("status") if off else (v.get("summary") or "Đang hiệu lực"),
                          "off": off, "draft": False})
        meta = [r.get("ec_doc_type") or "", V.dept_label(r.get("ec_department"))]
        if r.get("ec_current_version"):
            meta.append("bản %s · hiệu lực %s" % (r["ec_current_version"], V.fdate(r.get("ec_effective_from"))))
        else:
            meta.append("chưa ban hành")
        if r.get("ec_drafter") and not D.is_state(st, C.S_PUBLISHED):
            meta.append("người soạn: %s" % people.get(r["ec_drafter"], r["ec_drafter"]))
        items.append({
            "code": r.get("ec_doc_code") or name, "name": r.get("quality_procedure_name") or "",
            "meta": " · ".join(x for x in meta if x), "tag": _tag(r, a, today),
            "versions": vlist, "open": name == open_code,
            "page": ("/tai-lieu/" + (r.get("ec_doc_code") or name)) if r.get("ec_current_version") else "",
            "pdf": cur_pdf, "docx": cur_docx, "state": V.state_label(st),
            "actions": [{"action": x["action"], "next": V.state_label(x["next_state"]),
                         "danger": x["action"] in DANGER_ACTIONS} for x in a],
            "desk": ("/desk/quality-procedure/" + name) if is_mgr else "",
        })
    if items and not any(i["open"] for i in items) and flt == "cho-toi":
        items[0]["open"] = True
    depts = [{"name": d, "label": V.dept_label(d), "count": len(v)}
             for d, v in sorted(by_dept.items(), key=lambda x: V.dept_label(x[0]))]
    return {"filter": flt, "dept": dept, "q": q, "items": items, "is_manager": is_mgr,
            "counts": {"cho-toi": len(mine), "ra-soat": len(due), "dang-soan": len(drafting),
                       "het-hieu-luc": len(expired), "tat-ca": len(live)},
            "depts": depts, "total": len(live),
            "dept_options": repo.departments() if is_mgr else []}


# --------------------------------------------------------------------------- bam buoc duyet
def do_action(user, code, action, note="", repo=None):
    repo = _repo(repo)
    doc = repo.get_doc(code)
    if not doc:
        raise NotFound
    allowed = [t["action"] for t in repo.transitions(doc)]
    if action not in allowed:
        raise Forbidden("Bạn không bấm được bước này ở trạng thái hiện tại.")
    note = (note or "").strip()
    if action in RETURN_ACTIONS and len(note) < 5:
        raise DocError("Trả lại cần ghi lý do (ít nhất 5 ký tự) để người soạn biết sửa gì.")
    new = repo.apply_action(doc, action)
    if note:
        repo.add_comment(doc.name, "%s: %s" % (action, note))
    return {"code": code, "state": V.state_label(new.get(C.STATE_FIELD) if new else "")}


# --------------------------------------------------------------------------- nhap goi
def _file(f, exts=None):
    if not f:
        return None
    name = (f.get("name") or "").replace("\\", "/").split("/")[-1][:140]
    if exts and not name.lower().endswith(exts):
        raise DocError("Tệp %s không đúng loại (cần %s)." % (name, ", ".join(exts)))
    if len(f["content"]) > FILE_MAX:
        raise DocError("Tệp %s lớn hơn 20 MB: nén lại hoặc gửi Ban ISO nhập trên máy chủ." % name)
    return name


def import_package(user, pkg_raw, code="", pdf=None, docx=None, forms=None, repo=None):
    """Tao / ghi de BAN NHAP tu goi. -> {code, url, created}. Khong bao gio ban hanh."""
    repo = _repo(repo)
    if not repo.is_manager(user):
        raise Forbidden("Chỉ Ban ISO nhập được gói tài liệu.")
    try:
        pkg = json.loads(pkg_raw) if isinstance(pkg_raw, str) else pkg_raw
    except ValueError:
        raise DocError("goi.json không đọc được (JSON sai cú pháp).")
    forms = forms or []
    total = sum(len(f["content"]) for f in [pdf, docx] + list(forms) if f)
    if total > TOTAL_MAX:
        raise DocError("Tổng dung lượng tệp vượt 24 MB: nén PDF hoặc bớt biểu mẫu.")
    code = P.doc_code(pkg if isinstance(pkg, dict) else {}, (code or "").strip().upper())
    errs = P.errors(pkg, repo.departments(), code)
    by_name = {}
    for f in forms:
        by_name[_file(f, FORM_EXT)] = f
    for m in pkg.get("bieu_mau") or [] if isinstance(pkg, dict) else []:
        fn = (m.get("file") or "").replace("\\", "/").split("/")[-1] if isinstance(m, dict) else ""
        if fn and fn not in by_name:
            errs.append("Thiếu tệp biểu mẫu %s (chọn trong thư mục bieu_mau/ của gói)." % fn)
    if pdf:
        _file(pdf, (".pdf",))
    if docx:
        _file(docx, (".docx",))
    if errs:
        raise DocError("Gói chưa đạt:\n- " + "\n- ".join(errs))
    exists = repo.exists(code)
    if pkg.get("loai_goi") == "moi" and exists:
        raise DocError("Mã %s đã có trên ERP. Gói sửa đổi thì để loai_goi 'sua_doi'." % code)
    if pkg.get("loai_goi") == "sua_doi" and not exists:
        raise DocError("Chưa có tài liệu %s trên ERP để sửa đổi." % code)
    fields = P.to_fields(pkg, code, user)
    if exists:
        doc = repo.get_doc(code)
        st = doc.get(C.STATE_FIELD)
        if D.is_state(st, C.S_PUBLISHED):
            repo.apply_action(doc, "Soạn phiên bản mới")
        elif not D.is_state(st, C.S_DRAFT):
            raise DocError("%s đang ở bước \"%s\": trả về Nháp trước khi nhập gói mới." % (code, V.state_label(st)))
        fields.pop("ec_doc_code", None)
    else:
        repo.insert_doc(dict(fields, ec_steps_json=P.steps_payload(pkg)))
    urls = {}
    for m in pkg.get("bieu_mau") or []:
        fn = (m.get("file") or "").replace("\\", "/").split("/")[-1]
        if fn in by_name:
            urls[m.get("ma")] = repo.save_file(code, fn, by_name[fn]["content"])
    files = {}
    if pdf:
        files["ec_draft_pdf"] = repo.save_file(code, _file(pdf), pdf["content"])
    if docx:
        files["ec_draft_docx"] = repo.save_file(code, _file(docx), docx["content"])
    fields.update(files, ec_steps_json=P.steps_payload(pkg, urls))
    repo.update_draft(code, fields)
    return {"code": code, "created": not exists, "url": "/tai-lieu/quan-ly?loc=dang-soan&ma=" + code}
