# Copyright (c) 2026, eCentric and contributors
"""Thu vien tai lieu ISO - nghiep vu khi luu / chuyen buoc mot tai lieu (Quality Procedure).

Goi tu events.py (doc_events). Khong import frappe o day: `repo` tiem vao duoc, test chay
bang repo gia, khong can bench.

  validate  : dien truong BP theo phong ban, kiem du lieu (domain.validate), va khi trang thai
              chuyen sang "Ban hanh" thi ghi lich su ban hanh (domain.publish_plan) NGAY TRONG
              lan luu do - mot giao dich, khong co cho nao luu trang thai song song.
  on_update : sau khi ban hanh da ghi xong -> thong bao trang chu (neu tich + toan cong ty).
              Loi thong bao KHONG chan ban hanh: announce_service chay trong savepoint, loi ->
              rollback dung phan thong bao + Error Log (spec PO 04/10, muc 4).
"""
from ecentric_workspace.iso_docs import constants as C
from ecentric_workspace.iso_docs import domain as D
from ecentric_workspace.iso_docs.errors import DocError

#: truong ban nhap chep sang dong lich su khi ban hanh: (truong tren tai lieu, cot dong lich su)
_DRAFT_TO_ROW = (
    ("ec_change_summary", "summary"), ("ec_changed_sections", "changed_sections"),
    ("ec_draft_pdf", "pdf"), ("ec_draft_docx", "docx"), ("ec_mermaid", "mermaid"),
    ("ec_steps_json", "steps_json"), ("ec_source", "source"), ("ec_drafter", "drafter"),
)
_CHECKED = ("ec_doc_code", "ec_doc_type", "ec_company_wide", "ec_notify_home", "ec_change_kind",
            "ec_draft_version", "ec_current_version", "ec_review_months")


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.iso_docs import repository
    return repository


def _rows(doc, field):
    return list(doc.get(field) or [])


def _row_dict(r):
    return {"version": r.get("version"), "status": r.get("status")}


def check(doc):
    """-> danh sach loi cua tai lieu (rong = hop le)."""
    d = {k: doc.get(k) for k in _CHECKED}
    d["scope_departments"] = [r.get("department") for r in _rows(doc, "ec_scope_departments")
                              if r.get("department")]
    return D.validate(d)


def on_validate(doc, repo=None):
    repo = _repo(repo)
    if doc.get("ec_doc_code"):
        doc.ec_doc_code = doc.ec_doc_code.strip().upper()
    if doc.get("ec_department"):
        head = repo.dept_head(doc.ec_department)
        if head:
            doc.ec_dept_head = head
    if not doc.get("ec_review_months"):
        doc.ec_review_months = C.REVIEW_MONTHS_DEFAULT
    errs = check(doc)
    if errs:
        raise DocError("\n".join(errs))

    before = repo.state_before(doc)
    after = doc.get(C.STATE_FIELD)
    kind = D.transition_kind(before, after)
    user = repo.session_user()
    if kind == "iso_review":
        doc.ec_iso_reviewer = user
    elif kind == "publish":
        _publish(doc, before, user, repo)
    elif kind == "withdraw":
        rows = _rows(doc, "ec_revisions")
        for i, upd in D.withdraw_plan([_row_dict(r) for r in rows], repo.today()):
            for k, v in upd.items():
                setattr(rows[i], k, v)
        doc.flags.ec_withdrawn = True
    return kind


def _publish(doc, before, user, repo):
    rows = _rows(doc, "ec_revisions")
    reviewer = user if before == C.S_ISO else (doc.get("ec_iso_reviewer") or None)
    extra = {col: doc.get(f) for f, col in _DRAFT_TO_ROW if doc.get(f)}
    plan = D.publish_plan([_row_dict(r) for r in rows], doc.get("ec_current_version"),
                          doc.get("ec_draft_version"), doc.get("ec_change_kind"), repo.today(),
                          approver=user, reviewer=reviewer,
                          review_months=doc.get("ec_review_months"), extra=extra)
    summary = doc.get("ec_notify_summary") or doc.get("ec_change_summary") or ""
    if not plan["already"]:
        for i, upd in plan["close"]:
            for k, v in upd.items():
                setattr(rows[i], k, v)
        doc.append("ec_revisions", plan["row"])
        for k, v in plan["doc"].items():
            setattr(doc, k, v)
        doc.ec_iso_reviewer = ""
    doc.flags.ec_published_version = plan["version"]
    doc.flags.ec_published_summary = summary


def on_update(doc, repo=None):
    """Sau khi luu. -> ten EC Home Announcement vua tao / da co, hoac None."""
    repo = _repo(repo)
    flags = doc.flags
    name = None
    version = getattr(flags, "ec_published_version", None)
    if version:
        flags.ec_published_version = None
        if D.should_announce(doc.get("ec_notify_home"), doc.get("ec_company_wide")):
            payload = D.announcement_payload(doc.get("ec_doc_code") or doc.name,
                                             doc.get("quality_procedure_name"), version,
                                             doc.get("ec_effective_from") or repo.today(),
                                             getattr(flags, "ec_published_summary", "") or "")
            name = repo.publish_announcement(doc.name, version, payload)
            if name:
                repo.link_announcement(doc.name, version, name)
    if getattr(flags, "ec_withdrawn", False):
        flags.ec_withdrawn = False
        repo.withdraw_announcements(doc.name)
    return name
