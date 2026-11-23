# Copyright (c) 2026, eCentric and contributors
"""Ho so the do / den - buoc 2-4 cua thu tuc (ND 145/2020 D70):

  2. Thong bao hop: ngay hop >= N ngay lam viec sau thong bao (N = 5, Settings) - he thong tinh
     ngay som nhat; gui ERP + email cho NV va dai dien cong doan (Settings) neu NV la doan vien.
     NV xac nhan tham du / khong.
  3. Hop: ghi phan hoi; vang -> "vang du da duoc thong bao", van hop (im lang KHONG = dong y);
     tai bien ban hop co ky (ai khong ky ghi ly do).
  4. Trinh CEO ky quyet dinh qua engine (1 cap, ky so neu co ho so ky so).

Moi buoc kiem lai thoi hieu va thoi gian khong duoc xu ly; vuong -> tu chuyen Hoan."""
from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.application import access as A
from ecentric_workspace.hr.ky_luat.application import case_service as CS
from ecentric_workspace.hr.ky_luat.application.assess import assess
from ecentric_workspace.hr.ky_luat.application.common import (
    found, int_setting, log, require_own_files, route_case, text)
from ecentric_workspace.hr.ky_luat.domain import dates as D
from ecentric_workspace.hr.ky_luat.domain import rules as R
from ecentric_workspace.hr.ky_luat.domain.errors import FieldErrors, KyLuatError


def _gate(repo, actor, case, on_day=None):
    """Kiem truoc moi buoc. -> (chk, ket_qua_dung) - ket_qua_dung khac None = da tu chuyen
    trang thai (het thoi hieu / hoan), nguoi goi tra ve luon."""
    chk = assess(repo, case, on_day)
    if chk.get("expired"):
        repo.update_case(case["name"], {"status": C.S_EXPIRED}, log(repo, actor, "Hết thời hiệu", chk["errors"][0]))
        return chk, {"name": case["name"], "status": C.S_EXPIRED, "check": CS._public(chk)}
    hit = chk.get("blocked")
    if hit:
        res = CS.apply_postpone(repo, case, actor, hit["reason"], D.as_date(hit["from"]), D.as_date(hit["to"]),
                                "Hệ thống phát hiện khi %s" % (on_day or "thực hiện bước"))
        return chk, res
    return chk, None


def notify_meeting(repo, ctx, name, meeting_date, place=""):
    A.require_hr(ctx)
    case = found(repo.get_case(name))
    if case["status"] != C.S_DRAFT:
        raise KyLuatError("Chỉ gửi thông báo họp khi hồ sơ đang lập.")
    errors, _rule = CS._validate(repo, case, require_record=True)
    if errors:
        raise FieldErrors(errors)
    chk, stop = _gate(repo, ctx.user, case)
    if stop:
        return stop
    today, hol, settings = repo.today(), repo.holidays(), repo.settings()
    n = int_setting(settings, "meeting_notice_days", C.DEFAULT_MEETING_NOTICE_DAYS)
    earliest = D.earliest_meeting(today, n, hol)
    try:
        md = D.as_date(meeting_date)
    except ValueError:
        md = None
    if not md:
        raise FieldErrors({"meeting_date": "Chọn ngày họp (sớm nhất %s)." % earliest})
    if md < earliest:
        raise FieldErrors({"meeting_date": "Ngày họp phải cách ngày thông báo ít nhất %d ngày làm việc - "
                                           "sớm nhất %s." % (n, earliest)})
    if md.weekday() >= 5 or md in hol:
        raise FieldErrors({"meeting_date": "Ngày họp rơi vào ngày nghỉ - chọn ngày làm việc."})
    if md > D.as_date(chk["limitation_effective_end"]):
        raise FieldErrors({"meeting_date": "Ngày họp sau hạn thời hiệu (%s)." % chk["limitation_effective_end"]})
    on_meet = assess(repo, case, md)
    if on_meet.get("blocked"):
        raise FieldErrors({"meeting_date": "Ngày họp nằm trong thời gian không được xử lý (%s đến %s) - "
                                           "chọn sau %s." % (on_meet["blocked"]["from"], on_meet["blocked"]["to"],
                                                             on_meet["blocked"]["to"])})
    rep = None
    if int(case.get("is_union_member") or 0):
        rep = settings.get("union_rep_user")
        if not rep:
            raise KyLuatError("Nhân viên là đoàn viên nhưng chưa cấu hình đại diện công đoàn "
                              "(EC Discipline Settings).")
    vals = {"status": C.S_NOTIFIED, "notice_date": today, "notice_sent_at": repo.now(),
            "earliest_meeting_date": earliest, "meeting_date": md, "meeting_place": text(place, 200) or None,
            "union_rep_user": rep, "attendance_reply": C.ATTEND_UNKNOWN,
            "limitation_effective_end": chk.get("limitation_effective_end")}
    repo.update_case(name, vals, log(repo, ctx.user, "Thông báo họp xử lý kỷ luật", "Họp ngày %s" % md))
    subject = "Thông báo họp xử lý kỷ luật lao động ngày %s" % md
    msg = "Hồ sơ: %s. Địa điểm: %s. Vui lòng xác nhận tham dự trên ERP." % (
        R.case_title(case), vals["meeting_place"] or "HR sẽ báo")
    repo.notify([case.get("employee_user")], subject, C.CASE, name, message=msg, url=route_case(name),
                email=True, severity="action_required")
    if rep:
        repo.notify([rep], "%s - nhân viên %s (đoàn viên)" % (subject, case.get("employee_name")), C.CASE, name,
                    message=msg, url=route_case(name), email=True)
    repo.notify([case.get("line_manager_user")], "%s - %s" % (subject, case.get("employee_name")), C.CASE, name,
                message="Hồ sơ: %s." % R.case_title(case), url=route_case(name))
    return {"name": name, "status": C.S_NOTIFIED, "meeting_date": str(md), "earliest": str(earliest)}


def confirm_attendance(repo, ctx, name, attend, note=""):
    case = found(repo.get_case(name))
    A.require(A.is_case_subject(ctx, case), "Chỉ nhân viên được thông báo mới xác nhận tham dự.")
    if case["status"] != C.S_NOTIFIED:
        raise KyLuatError("Cuộc họp không còn chờ xác nhận.")
    yes = str(attend).lower() in ("1", "true", "yes")
    reply = C.ATTEND_YES if yes else C.ATTEND_NO
    repo.update_case(name, {"attendance_reply": reply, "attendance_note": text(note, 1000) or None,
                            "attendance_replied_at": repo.now()},
                     log(repo, ctx.user, "Nhân viên: %s" % reply, text(note, 1000)))
    repo.notify([case.get("hr_owner")], "%s: %s họp kỷ luật" % (case.get("employee_name"), reply.lower()),
                C.CASE, name, url=route_case(name))
    return {"name": name, "attendance_reply": reply}


def record_meeting(repo, ctx, name, payload):
    A.require_hr(ctx)
    case = found(repo.get_case(name))
    if case["status"] != C.S_NOTIFIED:
        raise KyLuatError("Chỉ ghi biên bản họp sau khi đã thông báo họp.")
    md = D.as_date(case.get("meeting_date"))
    if md and md > repo.today():
        raise KyLuatError("Chưa tới ngày họp (%s)." % md)
    chk, stop = _gate(repo, ctx.user, case, md)
    if stop:
        return stop
    p = payload or {}
    present = p.get("employee_present")
    errors = {}
    if present not in (C.PRESENT_YES, C.PRESENT_NO):
        errors["employee_present"] = "Chọn nhân viên có mặt hay vắng."
    statement = text(p.get("employee_statement"), 5000)
    if present == C.PRESENT_YES and not statement:
        errors["employee_statement"] = "Ghi ý kiến / phản hồi của nhân viên tại cuộc họp."
    if not p.get("meeting_minutes"):
        errors["meeting_minutes"] = "Tải lên biên bản họp có chữ ký."
    if errors:
        raise FieldErrors(errors)
    require_own_files(repo, ctx, {"meeting_minutes": text(p.get("meeting_minutes"), 500)}, case)
    if present == C.PRESENT_NO:
        statement = (C.ABSENT_NOTE + ("\n" + statement if statement else ""))
    days = int_setting(repo.settings(), "ceo_sign_days", C.DEFAULT_CEO_SIGN_DAYS)
    vals = {"status": C.S_MET, "employee_present": present, "employee_statement": statement,
            "meeting_minutes": text(p.get("meeting_minutes"), 500), "unsigned_notes": text(p.get("unsigned_notes"), 1000) or None,
            "meeting_recorded_at": repo.now(), "ceo_due": D.workday_after(md or repo.today(), days, repo.holidays())}
    repo.update_case(name, vals, log(repo, ctx.user, "Ghi biên bản họp", present))
    return {"name": name, "status": C.S_MET, "ceo_due": str(vals["ceo_due"])}


def _decision_fields(repo, case, p):
    e, vals = {}, {}
    if p.get("decision_draft") or case.get("decision_draft"):
        vals["decision_draft"] = text(p.get("decision_draft"), 500) or case.get("decision_draft")
    else:
        e["decision_draft"] = "Tải lên dự thảo quyết định kỷ luật."
    try:
        vals["effective_date"] = D.as_date(p.get("effective_date") or case.get("effective_date")) or repo.today()
    except ValueError:
        e["effective_date"] = "Ngày hiệu lực không hợp lệ."
    if case.get("penalty") == C.P_DISMISS:
        try:
            td = D.as_date(p.get("termination_date") or case.get("termination_date"))
        except ValueError:
            td = None
        if not td:
            e["termination_date"] = "Sa thải: nhập ngày chấm dứt hợp đồng."
        elif td < repo.today():
            e["termination_date"] = "Ngày chấm dứt không được trước hôm nay."
        vals["termination_date"] = td
    if e:
        raise FieldErrors(e)
    return vals


def submit_to_ceo(repo, ctx, name, payload):
    A.require_hr(ctx)
    case = found(repo.get_case(name))
    if case["status"] != C.S_MET:
        raise KyLuatError("Chỉ trình CEO sau khi đã họp và ghi biên bản.")
    vals = _decision_fields(repo, case, payload or {})
    require_own_files(repo, ctx, vals, case)
    chk, stop = _gate(repo, ctx.user, case)
    if stop:
        return stop
    merged = dict(case, case_title=R.case_title(case), **vals)
    decision = repo.create_decision(merged, ctx.user)
    vals.update({"status": C.S_AT_CEO, "decision_request": decision, "submitted_to_ceo_at": repo.now()})
    repo.update_case(name, vals, log(repo, ctx.user, "Trình CEO ký quyết định", decision))
    return {"name": name, "status": C.S_AT_CEO, "decision_request": decision}


def resubmit_to_ceo(repo, ctx, name, payload):
    """CEO “Yeu cau bo sung” -> HR sua du thao / ngay hieu luc -> gui lai (cung phieu engine)."""
    A.require_hr(ctx)
    case = found(repo.get_case(name))
    if case["status"] != C.S_AT_CEO or repo.decision_status(case.get("decision_request")) != "Information Required":
        raise KyLuatError("CEO không yêu cầu bổ sung hồ sơ này.")
    vals = _decision_fields(repo, case, payload or {})
    require_own_files(repo, ctx, vals, case)
    chk, stop = _gate(repo, ctx.user, case)
    if stop:
        return stop
    repo.resubmit_decision(dict(case, case_title=R.case_title(case), **vals), ctx.user)
    repo.update_case(name, vals, log(repo, ctx.user, "Gửi lại CEO sau bổ sung"))
    return {"name": name, "status": C.S_AT_CEO}
