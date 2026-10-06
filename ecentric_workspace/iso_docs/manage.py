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
EDITOR = "/tai-lieu/soan"


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
        facts = [("type", r.get("ec_doc_type") or ""), ("dept", V.dept_label(r.get("ec_department")))]
        if r.get("ec_current_version"):
            facts += [("ver", "bản " + r["ec_current_version"]),
                      ("date", "hiệu lực " + V.fdate(r.get("ec_effective_from")))]
        else:
            facts.append(("date", "chưa ban hành"))
        if r.get("ec_drafter") and not D.is_state(st, C.S_PUBLISHED):
            facts.append(("who", "người soạn: %s" % people.get(r["ec_drafter"], r["ec_drafter"])))
        meta = [t for _k, t in facts if t]
        items.append({
            "code": r.get("ec_doc_code") or name, "name": r.get("quality_procedure_name") or "",
            "meta": " · ".join(meta), "facts": [f for f in facts if f[1]], "tag": _tag(r, a, today),
            "versions": vlist, "open": name == open_code,
            "page": ("/tai-lieu/" + (r.get("ec_doc_code") or name)) if r.get("ec_current_version") else "",
            "pdf": cur_pdf, "docx": cur_docx, "state": V.state_label(st),
            "actions": [{"action": x["action"], "next": V.state_label(x["next_state"]),
                         "danger": x["action"] in DANGER_ACTIONS} for x in a],
            "edit": EDITOR + "?ma=" + (r.get("ec_doc_code") or name),
            "can_edit": D.is_state(st, C.S_DRAFT) and D.can_write(r, user, is_mgr),
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
    state = new.get(C.STATE_FIELD) if new else ""
    # Soan phien ban moi -> sang trang soan luon (PO 05/10: khong qua man quan tri)
    nxt = (EDITOR + "?ma=" + code) if D.is_state(state, C.S_DRAFT) else ""
    return {"code": code, "state": V.state_label(state), "next": nxt}


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


# --------------------------------------------------------------------------- trang soan
EDIT_FIELDS = ("quality_procedure_name", "ec_doc_type", "ec_department", "ec_company_wide", "ec_notify_home",
               "ec_notify_summary", "ec_change_kind", "ec_change_summary", "ec_changed_sections",
               "ec_draft_version", "ec_review_months")


def editor_page(user, code="", repo=None):
    """Trang /tai-lieu/soan: tao moi (khong co ma, chi Ban ISO) hoac sua ban nhap (?ma=)."""
    repo = _repo(repo)
    is_mgr = repo.is_manager(user)
    base = {"types": [n for _p, n in C.DOC_TYPES], "kinds": list(C.KINDS), "departments": repo.departments(),
            "is_manager": is_mgr}
    if not code:
        if not is_mgr:
            raise Forbidden("Chỉ Ban ISO tạo được tài liệu mới.")
        return dict(base, mode="new", code="", editable=True, reason="", doc=dict({k: "" for k in EDIT_FIELDS}, ec_company_wide=1, ec_notify_home=0,
                    ec_review_months=C.REVIEW_MONTHS_DEFAULT), rows=[], tom_tat={}, files={"pdf": "", "docx": ""}, forms=[],
                    actions=[], history=[], state="", scope=[], current_version="", page="")
    doc = repo.get_doc(code)
    if not doc:
        raise NotFound
    st = doc.get(C.STATE_FIELD)
    d = {k: doc.get(k) for k in ("ec_doc_state", "ec_drafter", "ec_dept_head", "ec_current_version")}
    editable = D.is_state(st, C.S_DRAFT) and D.can_write(d, user, is_mgr)
    if not D.is_state(st, C.S_DRAFT):
        reason = "Tài liệu đang ở bước \"%s\". Muốn sửa thì bấm \"Soạn phiên bản mới\" (bản đang hiệu lực vẫn áp dụng)" \
                 % V.state_label(st) if D.is_state(st, C.S_PUBLISHED) else \
                 "Tài liệu đang ở bước \"%s\": chỉ xem, trả về Nháp mới sửa được." % V.state_label(st)
    elif not editable:
        reason = "Chỉ người soạn và Ban ISO sửa được bản nháp này."
    else:
        reason = ""
    steps_raw = doc.get("ec_steps_json") or ""
    if not steps_raw:
        eff = [r for r in doc.get("ec_revisions") or [] if r.get("status") == C.REV_EFFECTIVE]
        steps_raw = eff[0].get("steps_json") if eff else ""
    data = V.load_steps(steps_raw)
    return dict(base, mode="edit", code=doc.get("ec_doc_code") or doc.name, editable=editable, reason=reason,
                doc={k: doc.get(k) for k in EDIT_FIELDS + ("ec_doc_code",)},
                rows=P.rows_from_steps(steps_raw), tom_tat=data.get("tom_tat") or {},
                forms=[f for f in data.get("bieu_mau") or [] if isinstance(f, dict) and f.get("url")],
                files={"pdf": doc.get("ec_draft_pdf") or "", "docx": doc.get("ec_draft_docx") or ""},
                scope=[r.get("department") for r in doc.get("ec_scope_departments") or []],
                actions=[{"action": t["action"], "next": V.state_label(t["next_state"]),
                          "danger": t["action"] in DANGER_ACTIONS} for t in repo.transitions(doc)],
                history=repo.history(doc.name), state=V.state_label(st),
                current_version=doc.get("ec_current_version") or "",
                page=("/tai-lieu/" + (doc.get("ec_doc_code") or doc.name)) if doc.get("ec_current_version") else "")


def save_draft(user, data, pdf=None, docx=None, forms=None, repo=None):
    """Luu trang soan. Moi: chi Ban ISO, tao o Nhap. Sua: chi khi Nhap + nguoi soan / Ban ISO.
    Bang buoc -> steps_json + so do (package.steps_from_rows). -> {code, created, url}."""
    repo = _repo(repo)
    is_mgr = repo.is_manager(user)
    code = (data.get("code") or "").strip().upper()
    creating = not data.get("existing")
    if creating:
        if not is_mgr:
            raise Forbidden("Chỉ Ban ISO tạo được tài liệu mới.")
        ce = D.code_error(code, data.get("ec_doc_type"))
        if ce:
            raise DocError(ce)
        if repo.exists(code):
            raise DocError("Mã %s đã có trên ERP." % code)
    else:
        doc = repo.get_doc(code)
        if not doc:
            raise NotFound
        d = {k: doc.get(k) for k in ("ec_doc_state", "ec_drafter", "ec_dept_head", "ec_current_version")}
        if not D.is_state(doc.get(C.STATE_FIELD), C.S_DRAFT):
            raise DocError("Tài liệu không ở bước Nháp: không sửa được.")
        if not D.can_write(d, user, is_mgr):
            raise Forbidden("Chỉ người soạn và Ban ISO sửa được bản nháp này.")
    if not (data.get("quality_procedure_name") or "").strip():
        raise DocError("Thiếu tên tài liệu.")
    if data.get("ec_department") not in repo.departments():
        raise DocError("Chọn phòng ban chủ trì.")
    fields = {k: data.get(k) for k in EDIT_FIELDS if k in data}
    fields["quality_procedure_name"] = fields["quality_procedure_name"].strip()[:140]
    for k in ("ec_company_wide", "ec_notify_home"):
        fields[k] = 1 if data.get(k) else 0
    if not fields["ec_company_wide"]:
        fields["ec_notify_home"] = 0
    fields["scope_departments"] = [] if fields["ec_company_wide"] else \
        [x for x in data.get("scope") or [] if x in repo.departments()]
    tom_tat = {k: (data.get("tom_tat") or {}).get(k, "").strip() for k in ("muc_dich", "dung_khi", "chuan_bi", "ket_qua")}
    tom_tat = {k: v for k, v in tom_tat.items() if v}
    keep_forms = [f for f in data.get("forms_keep") or [] if isinstance(f, dict) and f.get("url")]
    if creating:
        fields.update(ec_doc_code=code, ec_drafter=user, ec_source="Soạn trên ERP")
        repo.insert_doc(dict(fields))
        fields.pop("ec_doc_code")
    for f in forms or []:
        name = _file(f, FORM_EXT)
        keep_forms.append({"ma": "", "ten": name.rsplit(".", 1)[0], "url": repo.save_file(code, name, f["content"])})
    try:
        steps_raw, mermaid = P.steps_from_rows(data.get("rows") or [], tom_tat, keep_forms)
    except ValueError as e:
        raise DocError(str(e))
    if not steps_raw and (tom_tat or keep_forms):
        steps_raw = json.dumps({"tom_tat": tom_tat, "vai_tro": [], "buoc": [], "bieu_mau": keep_forms},
                               ensure_ascii=False, indent=1)
    fields.update(ec_steps_json=steps_raw, ec_mermaid=mermaid)
    if pdf:
        fields["ec_draft_pdf"] = repo.save_file(code, _file(pdf, (".pdf",)), pdf["content"])
    if docx:
        fields["ec_draft_docx"] = repo.save_file(code, _file(docx, (".docx",)), docx["content"])
    repo.update_draft(code, fields)
    return {"code": code, "created": creating, "url": EDITOR + "?ma=" + code}
