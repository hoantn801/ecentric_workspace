# Copyright (c) 2026, eCentric and contributors
"""Trang nhan vien: /tai-lieu (thu vien) va /tai-lieu/<ma> (mot tai lieu). Mockup D, PO duyet 04/10.

Chi doc qua repo.list_docs / repo.get_doc - deu qua quyen Frappe (permission_query + has_permission),
khong ignore_permissions. Thu vien chi hien tai lieu DA CO phien ban hieu luc.
"""
from ecentric_workspace.iso_docs import constants as C
from ecentric_workspace.iso_docs import domain as D
from ecentric_workspace.iso_docs import view as V
from ecentric_workspace.iso_docs.errors import NotFound

VIEWS = ("phong-ban", "viec", "he-thong")
LEGACY_SOURCE = "Nhập file cũ"     # = legacy.SOURCE: ban chuyen tu SharePoint, cho soan lai


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.iso_docs import repository
    return repository


def _effective(rows):
    return [r for r in rows if r.get("ec_current_version") and not D.is_state(r.get("ec_doc_state"), C.S_EXPIRED)]


def _match(c, q):
    """c: the da dung (_card). Khop moi tu, khong phan biet dau, tren ma + ten + "Dung khi"."""
    hay = D.norm_state(" ".join([c.get("code") or "", c.get("name") or "", c.get("use") or ""]))
    return all(w in hay for w in D.norm_state(q).split())


def _card(r, rev):
    flow = V.flow(rev.get("steps_json") if rev else "")
    facts = dict(flow["facts"])
    use = facts.get("Dùng khi") or facts.get("Mục đích") or ""
    return {"code": r.get("ec_doc_code") or r.get("name"), "name": r.get("quality_procedure_name") or "",
            "type": r.get("ec_doc_type") or "", "dept": V.dept_label(r.get("ec_department")),
            "dept_name": r.get("ec_department") or "", "version": r.get("ec_current_version") or "",
            "since": V.fdate(r.get("ec_effective_from")), "use": use,
            "drafting": not D.is_state(r.get("ec_doc_state"), C.S_PUBLISHED),
            "legacy": bool(rev) and rev.get("source") == LEGACY_SOURCE,
            "ec_doc_type": r.get("ec_doc_type"), "ec_doc_code": r.get("ec_doc_code")}


def library_page(user, view="phong-ban", dept="", q="", loai="", repo=None):
    """Thu vien nhan vien (PO 06/10): mot man the theo phong ban - loc theo loai tai lieu (chip) va
    phong ban (cot trai, "Tat ca" = moi phong, moi phong mot khoi). Tab "He thong ISO" giu rieng.
    view "viec" cu (tab Theo viec can lam) -> phong-ban: link cu khong chet."""
    repo = _repo(repo)
    rows = _effective(repo.list_docs())
    revs = {r["parent"]: r for r in repo.revisions([r["name"] for r in rows], effective_only=True)}
    cards = [_card(r, revs.get(r["name"])) for r in rows]
    view = view if view in VIEWS else "phong-ban"
    view = "phong-ban" if view == "viec" else view
    ctx = {"view": view, "q": q, "total": len(cards), "results": None, "types": [], "depts": [],
           "dept": "", "dept_label": "", "loai": "", "sections": [], "system": []}
    if q.strip():
        ctx["results"] = [c for c in cards if _match(c, q)]
        return ctx
    if view == "he-thong":
        ctx["system"] = [c for c in cards if V.code_dept(c["code"]) == "ISO"]
        return ctx
    # loai: dem tren phong dang chon; phong: dem tren loai dang chon -> so tren chip luon khop ket qua
    dept_names = {c["dept_name"] for c in cards}
    dept = dept if dept in dept_names else ""
    in_dept = [c for c in cards if not dept or c["dept_name"] == dept]
    tcount = {}
    for c in in_dept:
        tcount[c["type"] or "Khác"] = tcount.get(c["type"] or "Khác", 0) + 1
    loai = loai if loai in tcount else ""
    order = V.TYPE_ORDER + sorted(k for k in tcount if k not in V.TYPE_ORDER)
    ctx["types"] = [{"name": t, "label": V.TYPE_PLURAL.get(t, t), "count": tcount[t]} for t in order if t in tcount]
    of_type = [c for c in cards if not loai or (c["type"] or "Khác") == loai]
    dcount = {}
    for c in of_type:
        dcount[c["dept_name"]] = dcount.get(c["dept_name"], 0) + 1
    ctx["depts"] = [{"name": d, "label": V.dept_label(d), "count": dcount.get(d, 0)}
                    for d in sorted(dept_names, key=V.dept_label)]
    ctx["all_count"] = len(of_type)
    shown = [c for c in of_type if not dept or c["dept_name"] == dept]
    groups = {}
    for c in shown:
        groups.setdefault(c["dept_name"], []).append(c)
    t_rank = {t: i for i, t in enumerate(order)}
    ctx["sections"] = [{"dept": d, "label": V.dept_label(d),
                        "cards": sorted(groups[d], key=lambda c: (t_rank.get(c["type"] or "Khác", 99), c["name"]))}
                       for d in sorted(groups, key=V.dept_label)]
    ctx.update(dept=dept, dept_label=V.dept_label(dept) if dept else "", loai=loai)
    return ctx


def _rev_rows(doc):
    return sorted(list(doc.get("ec_revisions") or []), key=lambda r: r.get("idx") or 0)


def doc_page(user, code, version="", repo=None):
    repo = _repo(repo)
    doc = repo.get_doc(code)
    if not doc:
        raise NotFound
    revs = _rev_rows(doc)
    eff = next((r for r in revs if r.get("status") == C.REV_EFFECTIVE), None)
    row = next((r for r in revs if r.get("version") == version), None) if version else eff
    if row is None:
        raise NotFound
    flow = V.flow(row.get("steps_json"))
    is_old = row.get("status") != C.REV_EFFECTIVE
    drafting = (not is_old) and not D.is_state(doc.get("ec_doc_state"), C.S_PUBLISHED)
    names = repo.full_names([r.get("approver") for r in revs])
    history = [{"version": r.get("version"), "status": r.get("status"), "since": V.fdate(r.get("effective_from")),
                "until": V.fdate(r.get("effective_to")), "summary": r.get("summary") or "",
                "approver": names.get(r.get("approver"), r.get("approver") or ""), "pdf": r.get("pdf") or "",
                "on": r is row} for r in reversed(revs)]
    repo.mark_seen(doc.name, user, row.get("version"))
    return {
        "code": doc.get("ec_doc_code") or doc.name, "name": doc.get("quality_procedure_name") or "",
        "type": doc.get("ec_doc_type") or "", "dept": V.dept_label(doc.get("ec_department")),
        "dept_name": doc.get("ec_department") or "",
        "version": row.get("version"), "since": V.fdate(row.get("effective_from")),
        "until": V.fdate(row.get("effective_to")), "status": row.get("status"),
        "is_old": is_old, "drafting": drafting, "current_version": eff.get("version") if eff else "",
        "pdf": row.get("pdf") or "", "docx": row.get("docx") or "",
        "mermaid": (row.get("mermaid") or "").strip(), "flow": flow, "history": history,
        "parent": doc.get("ec_parent_doc") or "",
        "legacy": row.get("source") == LEGACY_SOURCE,
        "children": [{"code": r.get("ec_doc_code") or r.get("name"), "name": r.get("quality_procedure_name") or "",
                      "version": r.get("ec_current_version") or ""}
                     for r in _effective(repo.list_docs()) if r.get("ec_parent_doc") == doc.name],
    }
