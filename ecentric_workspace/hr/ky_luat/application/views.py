# Copyright (c) 2026, eCentric and contributors
"""Du lieu cho man hinh: trang /ky-luat, chi tiet the vang / ho so, tab Ky luat tren ho so nhan su.

Moi ham kiem quyen qua access.py truoc khi tra; danh sach loc hai lop (truy van theo pham vi +
can_view tung dong) de mot loi truy van khong lam lo ho so cua nguoi khac."""
from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.application import access as A
from ecentric_workspace.hr.ky_luat.application import decision_service as DS
from ecentric_workspace.hr.ky_luat.application.assess import assess
from ecentric_workspace.hr.ky_luat.application.case_service import _public
from ecentric_workspace.hr.ky_luat.application.common import found, int_setting
from ecentric_workspace.hr.ky_luat.domain import dates as D
from ecentric_workspace.hr.ky_luat.domain import rules as R

TABS = (("the-vang", "Thẻ vàng"), ("ho-so", "Hồ sơ kỷ luật"))


def make_ctx(repo, user):
    roles = repo.roles_of(user)
    emp = repo.employee_of_user(user)
    return A.Ctx(user, roles, emp, repo.team_of(emp) if emp else ())


def _s(v):
    return "" if v is None else str(v)


def _notice_row(n):
    return {"name": n["name"], "employee": n.get("employee"), "employee_name": n.get("employee_name") or "",
            "behavior": n.get("behavior") or "", "incident_date": _s(n.get("incident_date")),
            "status": n.get("status"), "reply_due": _s(n.get("reply_due")), "issuer_role": n.get("issuer_role") or ""}


def _case_row(c):
    return {"name": c["name"], "employee": c.get("employee"), "employee_name": c.get("employee_name") or "",
            "card": c.get("card") or "", "penalty": c.get("penalty") or "", "status": c.get("status"),
            "violation_date": _s(c.get("violation_date")), "meeting_date": _s(c.get("meeting_date")),
            "limitation_effective_end": _s(c.get("limitation_effective_end")),
            "decision_date": _s(c.get("decision_date")), "expunge_due": _s(c.get("expunge_due"))}


def visible_notices(repo, ctx):
    if ctx.sees_all:
        rows = repo.notices()
    else:
        mine = {ctx.employee} if ctx.employee else set()
        rows = repo.notices(employees=ctx.team | mine, issued_by=ctx.user)
    return [r for r in rows if A.can_view_notice(ctx, r)]


def visible_cases(repo, ctx):
    if ctx.sees_all:
        rows = repo.cases()
    else:
        extra = [["proposed_by", "=", ctx.user], ["union_rep_user", "=", ctx.user]]
        if ctx.employee:
            extra.append(["employee", "=", ctx.employee])
        rows = repo.cases(employees=ctx.team or None, extra_or=extra)
    return [r for r in rows if A.can_view_case(ctx, r)]


def index_page(repo, ctx, tab=None, code=None):
    tab = tab if tab in dict(TABS) else "the-vang"
    settings = repo.settings()
    picker = repo.active_employees() if ctx.is_hr else repo.active_employees(sorted(ctx.team))
    can_issue = ctx.is_hr or bool(ctx.team)
    notices = [_notice_row(n) for n in visible_notices(repo, ctx)]
    cases = [_case_row(c) for c in visible_cases(repo, ctx)]
    for n in notices:
        n["mine"] = 1 if n["employee"] == ctx.employee else 0
    for c in cases:
        c["mine"] = 1 if c["employee"] == ctx.employee else 0
    return {
        "tab": tab, "tabs": [{"key": k, "label": l, "active": k == tab, "href": "%s?tab=%s" % (C.ROUTE, k)}
                             for k, l in TABS],
        "notices": notices, "cases": cases, "open_code": code or "",
        "perm": {"is_hr": ctx.is_hr, "sees_all": ctx.sees_all, "can_issue": can_issue,
                 "can_propose": can_issue, "has_team": bool(ctx.team)},
        "legal_note": settings.get("legal_note") or C.LEGAL_NOTE, "yellow_note": C.YELLOW_NOTE,
        "boot": {
            "tab": tab, "open": code or "",
            "employees": [{"value": e["name"], "label": "%s · %s" % (e.get("employee_name") or e["name"], e["name"])}
                          for e in picker if e["name"] != ctx.employee],
            "rules": [{"value": r["name"], "label": r.get("title") or r["name"], "finance": int(r.get("finance_related") or 0),
                       "sample": int(r.get("is_sample") or 0)} for r in repo.active_rules()],
            "cards": {k: list(v) for k, v in C.CARD_PENALTIES.items()},
            "grounds": [{"value": c, "label": l} for c, l in C.DISMISS_GROUNDS],
            "blocks": list(C.MANUAL_BLOCKS) + [C.BLOCK_LEAVE],
            "present": [C.PRESENT_YES, C.PRESENT_NO],
            "meeting_notice_days": int_setting(settings, "meeting_notice_days", C.DEFAULT_MEETING_NOTICE_DAYS),
            "is_hr": ctx.is_hr, "can_issue": can_issue,
        },
    }


def notice_detail(repo, ctx, name):
    n = found(repo.get_notice(name), "thẻ vàng")
    A.require(A.can_view_notice(ctx, n))
    owner = A.is_notice_owner(ctx, n)
    out = {k: _s(n.get(k)) for k in ("name", "employee", "employee_name", "department", "behavior", "content",
                                     "incident_date", "rule", "evidence", "status", "sent_at", "reply_due",
                                     "read_at", "response", "responded_at", "issued_by", "issuer_role",
                                     "cancel_reason")}
    out["logs"] = [{k: _s(v) for k, v in r.items()} for r in n.get("logs") or []]
    open_ = n.get("status") in (C.NOTICE_PENDING, C.NOTICE_READ)
    out["actions"] = {"read": owner and n.get("status") == C.NOTICE_PENDING, "reply": owner and open_,
                      "cancel": (ctx.is_hr or n.get("issued_by") == ctx.user) and n.get("status") != C.NOTICE_CANCELLED}
    out["note"] = C.YELLOW_NOTE
    if ctx.sees_all:
        out["hint"] = R.yellow_hint(repo.notice_dates(n["employee"]), repo.today())
    return out


CASE_FIELDS = ("name", "employee", "employee_name", "department", "designation", "status", "card", "penalty",
               "extend_months", "holds_position", "dismissal_ground", "rule", "rule_title", "finance_related",
               "violation_date", "description", "evidence", "violation_record", "proposed_by", "hr_owner",
               "hr_review_due", "limitation_end", "limitation_effective_end", "recidivism_note", "is_union_member",
               "union_rep_user", "block_reason", "block_from", "block_to", "block_note", "notice_date",
               "earliest_meeting_date", "meeting_date", "meeting_place", "attendance_reply", "attendance_note",
               "employee_present", "employee_statement", "meeting_minutes", "unsigned_notes", "ceo_due",
               "decision_draft", "effective_date", "termination_date", "decision_request", "decision_date",
               "expunge_due", "expunged_at", "expunge_hold_note", "offboarding_note", "hr_note")


def case_detail(repo, ctx, name):
    c = found(repo.get_case(name))
    A.require(A.can_view_case(ctx, c))
    engine = repo.decision_status(c.get("decision_request")) if c.get("decision_request") else None
    out = {k: _s(c.get(k)) for k in CASE_FIELDS}
    out = A.redact_case(ctx, out)
    out["display_status"] = DS.display_status(c, engine)
    out["engine_status"] = engine or ""
    out["ground_label"] = dict(C.DISMISS_GROUNDS).get(_s(c.get("dismissal_ground")), "")
    # Nhat ky: nguoi ngoai HR/CEO chi thay hanh dong + thoi diem, khong thay ghi chu noi bo.
    out["logs"] = [{"at": _s(r.get("at")), "actor": _s(r.get("actor")), "action": _s(r.get("action")),
                    "note": _s(r.get("note")) if ctx.sees_all else ""} for r in c.get("logs") or []]
    st, hr = c.get("status"), ctx.is_hr
    out["actions"] = {
        "edit": hr and st in (C.S_PROPOSED, C.S_DRAFT), "accept": hr and st == C.S_PROPOSED,
        "notify": hr and st == C.S_DRAFT, "attend": A.is_case_subject(ctx, c) and st == C.S_NOTIFIED,
        "record": hr and st == C.S_NOTIFIED, "submit": hr and st == C.S_MET,
        "resubmit": hr and st == C.S_AT_CEO and engine == DS.ENGINE_INFO,
        "postpone": hr and st in (C.S_DRAFT, C.S_NOTIFIED, C.S_MET), "resume": hr and st == C.S_POSTPONED,
        "cancel": hr and st in (C.S_PROPOSED, C.S_DRAFT, C.S_POSTPONED, C.S_NOTIFIED, C.S_MET),
        "expunge": hr and st == C.S_ISSUED and bool(c.get("expunge_hold_note")),
    }
    if hr and st in C.CASE_OPEN:
        out["check"] = _public(assess(repo, c))
        if st == C.S_DRAFT:
            n = int_setting(repo.settings(), "meeting_notice_days", C.DEFAULT_MEETING_NOTICE_DAYS)
            out["earliest_meeting"] = str(D.earliest_meeting(repo.today(), n, repo.holidays()))
    if c.get("decision_request"):
        out["decision_url"] = "%s?id=%s" % (C.ROUTE_DECISION, c["decision_request"])
    return out


def employee_discipline(repo, ctx, employee):
    """Tab "Ky luat" tren ho so nhan su (/tong-quan): the vang + ho so do/den cua MOT nguoi."""
    emp = found(repo.employee(employee), "nhân viên")
    A.require(ctx.sees_all or ctx.manages(emp["name"]) or emp["name"] == ctx.employee)
    notices = [n for n in repo.notices(employees=[emp["name"]]) if A.can_view_notice(ctx, n)]
    cases = [c for c in repo.cases_of_employee(emp["name"]) if A.can_view_case(ctx, c)]
    today = repo.today()
    out = {"employee": emp["name"], "employee_name": emp.get("employee_name"),
           "notices": [_notice_row(n) for n in notices], "cases": [_case_row(c) for c in cases],
           "active": [_case_row(c) for c in R.active_disciplines(cases, today)],
           "route": C.ROUTE}
    if ctx.sees_all:
        out["hint"] = R.yellow_hint([n.get("incident_date") for n in notices
                                     if n.get("status") != C.NOTICE_CANCELLED], today)
    return out
