# Copyright (c) 2026, eCentric and contributors
"""Ho so the do / the den - buoc 1: de xuat (LM) / lap ho so (HR), sua, hoan, tiep tuc, huy.

LM chi DE XUAT; HR lap ho so chinh thuc (bien ban vi pham + dieu khoan noi quy + the + hinh
thuc con). Moi lan luu he thong kiem thoi hieu D123 va tai pham. Buoc 2-4: procedure_service.

Tieu de (Hoan chot 23/11): BAT BUOC khi de xuat / lap ho so MOI (kiem o day, khong reqd o DocType);
ho so cu chua co tieu de: sua / luu lai khong bi bat nhap, man hinh hien tieu de du phong
(rules.case_title). HR sua tieu de khi ho so chua ban hanh (retitle) - ghi nhat ky cu -> moi."""
from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.application import access as A
from ecentric_workspace.hr.ky_luat.application.assess import assess
from ecentric_workspace.hr.ky_luat.application.common import (
    found, hr_users, int_setting, log, require_own_files, route_case, text)
from ecentric_workspace.hr.ky_luat.domain import dates as D
from ecentric_workspace.hr.ky_luat.domain import rules as R
from ecentric_workspace.hr.ky_luat.domain.errors import FieldErrors, KyLuatError

#: Truong HR sua duoc o buoc lap (KHONG co truong tien nao - D127).
EDITABLE = ("title", "card", "penalty", "extend_months", "holds_position", "dismissal_ground", "rule",
            "finance_related", "violation_date", "description", "evidence", "violation_record",
            "is_union_member", "hr_note")
EDITABLE_STATUSES = (C.S_PROPOSED, C.S_DRAFT)


def _clean(p):
    out = {}
    for k in EDITABLE:
        if k not in p:
            continue
        v = p.get(k)
        if k == "title":
            v = R.clean_title(v) or None
        elif k in ("extend_months",):
            try:
                v = int(v or 0)
            except (TypeError, ValueError):
                v = 0
        elif k in ("holds_position", "finance_related", "is_union_member"):
            v = 1 if str(v).lower() in ("1", "true", "yes", "on") else 0
        elif k == "violation_date":
            try:
                v = D.as_date(v)
            except ValueError:
                v = None
        else:
            v = text(v, 5000) or None
        out[k] = v
    return out


def _validate(repo, case, require_record=False):
    e = {}
    today = repo.today()
    v = D.as_date(case.get("violation_date"))
    if not v:
        e["violation_date"] = "Chọn ngày vi phạm."
    elif v > today:
        e["violation_date"] = "Ngày vi phạm không được sau hôm nay."
    if not text(case.get("description")):
        e["description"] = "Mô tả hành vi vi phạm."
    rule = repo.rule(case.get("rule")) if case.get("rule") else None
    if not rule:
        e["rule"] = "Chọn điều khoản nội quy bị vi phạm."
    prior = repo.cases_of_employee(case.get("employee"), (C.S_ISSUED,)) if case.get("employee") else []
    prior = [r for r in prior if r.get("name") != case.get("name")]
    e.update(R.validate_choice(dict(case, today=today), prior))
    if require_record and not case.get("violation_record"):
        e["violation_record"] = "Tải lên biên bản vi phạm."
    return e, rule


def _require_title(case, errors):
    if not case.get("title"):
        errors["title"] = "Nhập tiêu đề hồ sơ (vd “%s”)." % C.TITLE_PLACEHOLDER
    return errors


def _snapshot_employee(repo, employee):
    emp = found(repo.employee(employee), "nhân viên")
    return emp, {"employee": emp["name"], "employee_name": emp.get("employee_name"),
                 "employee_user": emp.get("user"), "department": emp.get("department"),
                 "designation": emp.get("designation"), "line_manager_user": emp.get("reports_to_user")}


def _derived(repo, case, rule):
    if rule:
        case["rule_title"] = rule.get("title")
        if int(rule.get("finance_related") or 0):
            case["finance_related"] = 1
    chk = assess(repo, case)
    case["limitation_end"] = chk.get("limitation_end")
    case["limitation_effective_end"] = chk.get("limitation_effective_end")
    case["recidivism_note"] = chk.get("recidivism_note") or None
    case["recidivism"] = 1 if chk.get("recidivism_note") else 0
    return chk


def propose(repo, ctx, payload):
    """LM (hoac HR) de xuat. HR tham dinh trong N ngay lam viec."""
    p = payload or {}
    emp, snap = _snapshot_employee(repo, text(p.get("employee")))
    A.require(A.can_propose_case(ctx, emp["name"]), "Chỉ quản lý trực tiếp hoặc HR đề xuất được kỷ luật.")
    case = dict(snap, **_clean(p))
    case.pop("hr_note", None)
    require_own_files(repo, ctx, case)
    errors, rule = _validate(repo, case)
    if not p.get("rule"):
        errors.pop("rule", None)          # LM co the chua biet dieu khoan - HR chon khi lap
    _require_title(case, errors)
    if errors:
        raise FieldErrors(errors)
    _derived(repo, case, rule)
    days = int_setting(repo.settings(), "hr_review_days", C.DEFAULT_HR_REVIEW_DAYS)
    case.update({"status": C.S_PROPOSED, "proposed_by": ctx.user, "proposed_at": repo.now(),
                 "hr_review_due": D.workday_after(repo.today(), days, repo.holidays())})
    name = repo.insert_case(case, log(repo, ctx.user, "Đề xuất kỷ luật", "%s - %s - %s" % (case["title"], case["card"], case["penalty"])))
    repo.notify(hr_users(repo), "Đề xuất kỷ luật mới: %s (%s) - %s" % (emp.get("employee_name"), case["card"], case["title"]),
                C.CASE, name, message="HR thẩm định trước %s." % case["hr_review_due"], url=route_case(name))
    return {"name": name}


def create(repo, ctx, payload):
    """HR lap ho so chinh thuc (Dang lap). Tu de xuat: truyen `from_proposal`."""
    A.require_hr(ctx)
    p = payload or {}
    if p.get("from_proposal"):
        return update(repo, ctx, text(p["from_proposal"]), dict(p, accept=1))
    emp, snap = _snapshot_employee(repo, text(p.get("employee")))
    A.require(emp["name"] != ctx.employee, "Không lập hồ sơ kỷ luật cho chính mình.")
    case = dict(snap, **_clean(p))
    require_own_files(repo, ctx, case)
    errors, rule = _validate(repo, case)
    _require_title(case, errors)
    if errors:
        raise FieldErrors(errors)
    chk = _derived(repo, case, rule)
    if chk.get("expired"):
        raise KyLuatError(chk["errors"][0])
    case.update({"status": C.S_DRAFT, "hr_owner": ctx.user})
    name = repo.insert_case(case, log(repo, ctx.user, "Lập hồ sơ", "%s - %s - %s" % (case["title"], case["card"], case["penalty"])))
    return {"name": name, "check": _public(chk)}


def update(repo, ctx, name, payload):
    A.require_hr(ctx)
    case = found(repo.get_case(name))
    if case["status"] not in EDITABLE_STATUSES:
        raise KyLuatError("Hồ sơ đang ở bước “%s” - không sửa được." % case["status"])
    p = payload or {}
    cleaned = _clean(p)
    if not cleaned.get("title"):
        cleaned.pop("title", None)        # o trong = giu tieu de cu (ho so cu: van hien du phong)
    merged = dict(case, **cleaned)
    require_own_files(repo, ctx, merged, case)
    errors, rule = _validate(repo, merged)
    if errors:
        raise FieldErrors(errors)
    chk = _derived(repo, merged, rule)
    vals = {k: merged.get(k) for k in EDITABLE + ("rule_title", "limitation_end", "limitation_effective_end",
                                                  "recidivism", "recidivism_note")}
    action, note = "Cập nhật hồ sơ", ""
    if R.clean_title(case.get("title")) != R.clean_title(merged.get("title")):
        note = "Tiêu đề: “%s” → “%s”" % (R.clean_title(case.get("title")) or R.case_title(case), merged.get("title"))
    if case["status"] == C.S_PROPOSED and int(p.get("accept") or 0):
        vals.update({"status": C.S_DRAFT, "hr_owner": ctx.user})
        action = "HR nhận đề xuất, lập hồ sơ"
        repo.notify([case.get("proposed_by")], "HR đã nhận đề xuất kỷ luật %s" % case.get("employee_name"),
                    C.CASE, name, url=route_case(name))
    repo.update_case(name, vals, log(repo, ctx.user, action, note))
    return {"name": name, "check": _public(chk)}


def can_retitle(ctx, case):
    return ctx.is_hr and case.get("status") in C.CASE_RETITLE_STATUSES


def retitle(repo, ctx, name, title):
    """HR sua tieu de ho so CHUA ban hanh. Ghi nhat ky (cu -> moi). Dang trinh CEO: cap nhat luon
    tieu de phieu quyet dinh (qua cong discipline_decision) - loi o day khong chan viec sua."""
    A.require_hr(ctx)
    case = found(repo.get_case(name))
    if case["status"] not in C.CASE_RETITLE_STATUSES:
        raise KyLuatError("Hồ sơ ở bước “%s” - không sửa tiêu đề được nữa." % case["status"])
    new = R.clean_title(title)
    if not new:
        raise FieldErrors({"title": "Nhập tiêu đề."})
    old = R.clean_title(case.get("title"))
    if new == old:
        return {"name": name, "title": new, "changed": False}
    repo.update_case(name, {"title": new}, log(repo, ctx.user, "Sửa tiêu đề",
                                               "“%s” → “%s”" % (old or R.case_title(case), new)))
    if case.get("decision_request"):
        try:
            repo.retitle_decision(dict(case, title=new, case_title=new))
        except Exception:
            repo.log_error("ky_luat: doi tieu de phieu quyet dinh %s" % name)
    return {"name": name, "title": new, "changed": True}


def check(repo, ctx, name, on_day=None):
    case = found(repo.get_case(name))
    A.require(A.can_view_case(ctx, case))
    A.require_hr(ctx)
    return _public(assess(repo, case, on_day))


def cancel(repo, ctx, name, reason):
    """HR huy (hoac tu choi de xuat). Chi khi chua trinh CEO."""
    A.require_hr(ctx)
    case = found(repo.get_case(name))
    why = text(reason, 1000)
    if not why:
        raise FieldErrors({"reason": "Nhập lý do."})
    if case["status"] not in (C.S_PROPOSED, C.S_DRAFT, C.S_POSTPONED, C.S_NOTIFIED, C.S_MET):
        raise KyLuatError("Không huỷ được hồ sơ ở bước “%s”." % case["status"])
    repo.update_case(name, {"status": C.S_CANCELLED}, log(repo, ctx.user, "Huỷ hồ sơ", why))
    users = [case.get("proposed_by")]
    if case["status"] in (C.S_NOTIFIED, C.S_MET):
        users += [case.get("employee_user"), case.get("union_rep_user")]
    repo.notify(users, "Hồ sơ kỷ luật %s đã huỷ: %s" % (name, R.case_title(case)), C.CASE, name, message=why,
                url=route_case(name))
    return {"name": name, "status": C.S_CANCELLED}


def postpone(repo, ctx, name, reason, block_from, block_to, note=""):
    """HR ghi thoi gian khong duoc xu ly (D122.4) -> Hoan; thoi hieu tu keo dai (D123.2)."""
    A.require_hr(ctx)
    case = found(repo.get_case(name))
    if case["status"] not in (C.S_DRAFT, C.S_NOTIFIED, C.S_MET, C.S_POSTPONED):
        raise KyLuatError("Không hoãn được hồ sơ ở bước “%s”." % case["status"])
    if reason not in C.MANUAL_BLOCKS + (C.BLOCK_LEAVE,):
        raise FieldErrors({"block_reason": "Chọn lý do hoãn theo Điều 122.4."})
    try:
        a, b = D.as_date(block_from), D.as_date(block_to)
    except ValueError:
        a = b = None
    if not a or not b or a > b:
        raise FieldErrors({"block_to": "Nhập khoảng thời gian (từ ngày - đến ngày) hợp lệ."})
    return apply_postpone(repo, case, ctx.user, reason, a, b, note)


def apply_postpone(repo, case, actor, reason, a, b, note=""):
    periods = list(case.get("block_periods") or []) + [[str(a), str(b), reason]]
    merged = dict(case, block_periods=periods, block_reason=None)
    chk = assess(repo, merged)
    vals = {"status": C.S_POSTPONED, "block_periods": periods, "block_reason": reason,
            "block_from": a, "block_to": b, "block_note": text(note, 1000) or None,
            "limitation_effective_end": chk.get("limitation_effective_end")}
    repo.update_case(case["name"], vals, log(repo, actor, "Hoãn (Điều 122.4)",
                                             "%s: %s - %s; thời hiệu đến %s" % (reason, a, b, vals["limitation_effective_end"])))
    if case["status"] in (C.S_NOTIFIED, C.S_MET):
        repo.notify([case.get("employee_user"), case.get("union_rep_user")],
                    "Cuộc họp xử lý kỷ luật được hoãn", C.CASE, case["name"], url=route_case(case["name"]),
                    email=True)
    return {"name": case["name"], "status": C.S_POSTPONED, "check": _public(chk)}


def resume(repo, ctx, name):
    """Het thoi gian cam -> quay lai Dang lap (phai thong bao hop LAI)."""
    A.require_hr(ctx)
    case = found(repo.get_case(name))
    if case["status"] != C.S_POSTPONED:
        raise KyLuatError("Hồ sơ không ở trạng thái hoãn.")
    chk = assess(repo, dict(case, block_reason=None))
    if chk.get("blocked"):
        raise KyLuatError(chk["errors"][-1])
    if chk.get("expired"):
        repo.update_case(name, {"status": C.S_EXPIRED}, log(repo, ctx.user, "Hết thời hiệu", chk["errors"][0]))
        return {"name": name, "status": C.S_EXPIRED, "check": _public(chk)}
    repo.update_case(name, {"status": C.S_DRAFT, "block_reason": None, "meeting_date": None,
                            "notice_sent_at": None, "attendance_reply": None,
                            "limitation_effective_end": chk.get("limitation_effective_end")},
                     log(repo, ctx.user, "Tiếp tục sau hoãn", "Thời hiệu đến %s" % chk.get("limitation_effective_end")))
    return {"name": name, "status": C.S_DRAFT, "check": _public(chk)}


def _public(chk):
    out = dict(chk)
    out["prior_cases"] = [{"name": r.get("name"), "penalty": r.get("penalty"),
                           "decision_date": str(r.get("decision_date") or "")}
                          for r in chk.get("prior_cases") or []]
    return out
