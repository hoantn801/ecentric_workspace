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
    use = dict(flow["facts"]).get("Dùng khi", "")
    return {"code": r.get("ec_doc_code") or r.get("name"), "name": r.get("quality_procedure_name") or "",
            "type": r.get("ec_doc_type") or "", "dept": V.dept_label(r.get("ec_department")),
            "dept_name": r.get("ec_department") or "", "version": r.get("ec_current_version") or "",
            "since": V.fdate(r.get("ec_effective_from")), "use": use,
            "drafting": not D.is_state(r.get("ec_doc_state"), C.S_PUBLISHED),
            "ec_doc_type": r.get("ec_doc_type"), "ec_doc_code": r.get("ec_doc_code")}


def library_page(user, view="phong-ban", dept="", q="", repo=None):
    repo = _repo(repo)
    rows = _effective(repo.list_docs())
    revs = {r["parent"]: r for r in repo.revisions([r["name"] for r in rows], effective_only=True)}
    cards = [_card(r, revs.get(r["name"])) for r in rows]
    view = view if view in VIEWS else "phong-ban"
    counts = {}
    for c in cards:
        counts[c["dept_name"]] = counts.get(c["dept_name"], 0) + 1
    depts = [{"name": d, "label": V.dept_label(d), "count": n}
             for d, n in sorted(counts.items(), key=lambda x: V.dept_label(x[0]))]
    if dept not in counts:
        dept = depts[0]["name"] if depts else ""
    ctx = {"view": view, "q": q, "total": len(cards), "depts": depts, "dept": dept,
           "dept_label": V.dept_label(dept), "results": None, "groups": [], "tasks": [], "system": []}
    if q.strip():
        ctx["results"] = [c for c in cards if _match(c, q)]
        return ctx
    if view == "phong-ban":
        ctx["groups"] = V.group_by_type([c for c in cards if c["dept_name"] == dept])
    elif view == "viec":
        ctx["tasks"] = sorted((c for c in cards if c["use"] and c["type"] in ("Quy trình", "Hướng dẫn")),
                              key=lambda c: c["name"])
    else:
        ctx["system"] = [c for c in cards if V.code_dept(c["code"]) == "ISO"]
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
        "children": [{"code": r.get("ec_doc_code") or r.get("name"), "name": r.get("quality_procedure_name") or "",
                      "version": r.get("ec_current_version") or ""}
                     for r in _effective(repo.list_docs()) if r.get("ec_parent_doc") == doc.name],
    }
