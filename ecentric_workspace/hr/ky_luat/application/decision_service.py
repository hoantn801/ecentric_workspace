# Copyright (c) 2026, eCentric and contributors
"""Ket qua buoc CEO + xoa ky luat (D126).

  * CEO duyet (engine goi on_final_approval cua feature discipline_decision -> on_ceo_approved):
    ban hanh, gui NV + thanh phan du hop, hen ngay tu xoa. Sa thai -> danh dau ngay nghi viec
    (relieving_date = ngay cham dut) + tao Clearance (Clearance V2) - khoa tai khoan do job
    hr/offboarding lo theo relieving_date.
  * CEO tu choi = khong ky luat; CEO yeu cau bo sung = tra HR. Engine doi trang thai bang
    db.set_value (khong co hook), nen `reconcile` doc trang thai phieu va dong bo - goi ngay sau
    khi CEO bam tren trang quyet dinh + job hang ngay (phong khi CEO bam o noi khac).
"""
from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.application import access as A
from ecentric_workspace.hr.ky_luat.application.assess import assess
from ecentric_workspace.hr.ky_luat.application.common import found, hr_users, log, route_case, text
from ecentric_workspace.hr.ky_luat.domain import dates as D
from ecentric_workspace.hr.ky_luat.domain import rules as R
from ecentric_workspace.hr.ky_luat.domain.errors import FieldErrors, KyLuatError

ENGINE_APPROVED = "Approved"
ENGINE_REJECTED = "Rejected"
ENGINE_CANCELLED = "Cancelled"
ENGINE_INFO = "Information Required"


def _participants(case):
    return [case.get("employee_user"), case.get("union_rep_user"), case.get("line_manager_user"),
            case.get("hr_owner")]


def on_ceo_approved(repo, name):
    case = found(repo.get_case(name))
    if case["status"] in (C.S_ISSUED, C.S_EXPUNGED):
        return {"name": name, "status": case["status"]}             # idempotent
    if case["status"] != C.S_AT_CEO:
        repo.notify(hr_users(repo), "Quyết định kỷ luật %s được duyệt nhưng hồ sơ ở trạng thái %s - "
                                    "kiểm tra tay" % (name, case["status"]), C.CASE, name, url=route_case(name))
        return {"name": name, "status": case["status"], "skipped": True}
    today = repo.today()
    chk = assess(repo, case)
    if chk.get("expired"):
        repo.update_case(name, {"status": C.S_EXPIRED}, log(repo, None, "Hết thời hiệu trước khi ban hành",
                                                            chk["errors"][0]))
        repo.notify(hr_users(repo), "Không ban hành được quyết định %s: đã hết thời hiệu" % name, C.CASE, name,
                    url=route_case(name))
        return {"name": name, "status": C.S_EXPIRED}
    vals = {"status": C.S_ISSUED, "decision_date": today, "issued_at": repo.now(),
            "expunge_due": D.expunge_due(today, case.get("penalty"))}
    note = "%s - %s" % (case.get("card"), case.get("penalty"))
    if case.get("penalty") == C.P_DISMISS:
        vals["offboarding_note"] = _dismiss(repo, case)
        note += "; " + vals["offboarding_note"]
    repo.update_case(name, vals, log(repo, None, "CEO ký - ban hành quyết định", note))
    repo.notify(_participants(case), "Quyết định kỷ luật lao động: %s (%s)" % (case.get("penalty"), case.get("employee_name")),
                C.CASE, name, url=route_case(name), email=True,
                message=("Tự xoá kỷ luật dự kiến: %s (Điều 126) nếu không tái phạm." % vals["expunge_due"])
                if vals["expunge_due"] else "")
    return {"name": name, "status": C.S_ISSUED}


def _dismiss(repo, case):
    last = D.as_date(case.get("termination_date")) or D.as_date(case.get("effective_date")) or repo.today()
    parts = []
    try:
        repo.set_relieving_date(case["employee"], last)
        parts.append("Ngày nghỉ việc %s" % last)
    except Exception:
        repo.log_error("ky_luat: ghi relieving_date %s" % case.get("name"))
        parts.append("CHƯA ghi được ngày nghỉ việc - HR ghi tay")
    clearance = repo.create_clearance(case["employee"], "Sa thải theo quyết định kỷ luật %s" % case["name"], last)
    if clearance:
        parts.append("Clearance %s" % clearance)
    else:
        parts.append("CHƯA tạo được Clearance - HR tạo tay")
        repo.notify(hr_users(repo), "Sa thải %s: chưa tạo được Clearance tự động, HR tạo tay" % case.get("employee_name"),
                    C.CASE, case["name"], url=route_case(case["name"]))
    return "; ".join(parts)


def reconcile(repo, name):
    """Dong bo trang thai ho so voi phieu engine. Idempotent."""
    case = repo.get_case(name)
    if not case or case["status"] != C.S_AT_CEO:
        return case and case["status"]
    st = repo.decision_status(case.get("decision_request"))
    if st == ENGINE_APPROVED:
        return on_ceo_approved(repo, name)["status"]
    if st in (ENGINE_REJECTED, ENGINE_CANCELLED):
        new = C.S_NO_DISCIPLINE if st == ENGINE_REJECTED else C.S_MET
        action = "CEO quyết định không kỷ luật" if st == ENGINE_REJECTED else "Phiếu trình CEO bị huỷ - quay lại bước sau họp"
        repo.update_case(name, {"status": new}, log(repo, None, action))
        users = [case.get("hr_owner"), case.get("proposed_by")]
        if st == ENGINE_REJECTED:
            users += [case.get("employee_user"), case.get("union_rep_user")]
        repo.notify(users, "%s: %s" % (case.get("employee_name"), action), C.CASE, name, url=route_case(name))
        return new
    return case["status"]


def display_status(case, engine_status):
    """Nhan hien thi: buoc Trinh CEO tach theo trang thai phieu engine."""
    if case.get("status") == C.S_AT_CEO and engine_status == ENGINE_INFO:
        return "CEO yêu cầu bổ sung"
    return case.get("status")


def expunge_due_cases(repo):
    """Job: ky luat toi ngay xoa (D126). Co tai pham trong thoi gian cho -> KHONG tu xoa, bao HR
    mot lan (ghi expunge_hold_note). Tra (so da xoa, so giu lai)."""
    done = held = 0
    for c in repo.issued_due_for_expunge(repo.today()):
        try:
            later = repo.cases_of_employee(c["employee"], (C.S_ISSUED, C.S_EXPUNGED))
            hits = R.expunge_blocked_by(c, later)
            if hits:
                held += 1
                if not c.get("expunge_hold_note"):
                    note = "Có quyết định kỷ luật mới trong thời gian chờ xoá: " + ", ".join(hits)
                    repo.update_case(c["name"], {"expunge_hold_note": note}, log(repo, None, "Không tự xoá kỷ luật", note))
                    repo.notify(hr_users(repo), "Kỷ luật %s tới hạn xoá nhưng có tái phạm - HR xem lại" % c["name"],
                                C.CASE, c["name"], url=route_case(c["name"]))
                continue
            repo.update_case(c["name"], {"status": C.S_EXPUNGED, "expunged_at": repo.now()},
                             log(repo, None, "Tự xoá kỷ luật (Điều 126)", "Hạn %s" % c.get("expunge_due")))
            repo.notify([c.get("employee_user"), c.get("hr_owner")], "Kỷ luật %s đã được xoá (Điều 126)" % c["name"],
                        C.CASE, c["name"], url=route_case(c["name"]))
            done += 1
        except Exception:
            repo.log_error("ky_luat: xoa ky luat %s" % c.get("name"))
    return done, held


def expunge_manual(repo, ctx, name, note):
    """HR xoa ky luat bang tay sau khi xem lai truong hop bi giu (khong phai tai pham)."""
    A.require_hr(ctx)
    case = found(repo.get_case(name))
    if case["status"] != C.S_ISSUED or not case.get("expunge_due"):
        raise KyLuatError("Chỉ xoá được kỷ luật đã ban hành và có thời hạn xoá.")
    if D.as_date(case["expunge_due"]) > repo.today():
        raise KyLuatError("Chưa tới hạn xoá kỷ luật (%s)." % case["expunge_due"])
    why = text(note, 1000)
    if not why:
        raise FieldErrors({"note": "Ghi lý do (HR đã xem xét, không phải tái phạm)."})
    repo.update_case(name, {"status": C.S_EXPUNGED, "expunged_at": repo.now()},
                     log(repo, ctx.user, "HR xoá kỷ luật sau khi xem xét", why))
    return {"name": name, "status": C.S_EXPUNGED}
