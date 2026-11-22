# Copyright (c) 2026, eCentric and contributors
"""Job 09:00 ngay lam viec cua module Ky luat (hooks.py). Moi phan tu bat loi - mot phan hong
khong chan phan khac; tung ban ghi bat loi trong service. Idempotent: chay lai trong ngay khong
doi gi them (trang thai da chuyen / da danh dau da canh bao).

  1. The vang qua han phan hoi -> "Khong phan hoi".
  2. Ho so dang trinh CEO -> dong bo voi phieu engine (CEO bam o noi khac / duyet nhanh).
  3. Ho so dang mo: het thoi hieu -> "Het thoi hieu"; con <= N ngay -> canh bao HR mot lan;
     de xuat qua han tham dinh -> nhac HR; hoan da het thoi gian cam -> nhac HR tiep tuc.
  4. Xoa ky luat toi han (D126).
"""
from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.application import decision_service, notice_service
from ecentric_workspace.hr.ky_luat.application.common import hr_users, int_setting, log, route_case
from ecentric_workspace.hr.ky_luat.domain import dates as D


def daily(repo):
    today = repo.today()
    if D.workday_after(today, 0, repo.holidays()) != today:
        return {"skipped": "ngay nghi"}
    out = {}
    for key, fn in (("notices", lambda: notice_service.auto_close_overdue(repo)),
                    ("cases", lambda: scan_open_cases(repo)),
                    ("expunge", lambda: decision_service.expunge_due_cases(repo))):
        try:
            out[key] = fn()
        except Exception:
            repo.log_error("ky_luat.jobs.daily %s" % key)
            out[key] = "error"
    return out


def scan_open_cases(repo):
    today = repo.today()
    warn_days = int_setting(repo.settings(), "limitation_warn_days", C.DEFAULT_LIMITATION_WARN_DAYS)
    stats = {"expired": 0, "warned": 0, "reconciled": 0, "reminded": 0}
    hr = None
    for c in repo.open_cases():
        try:
            if c["status"] == C.S_AT_CEO:
                if decision_service.reconcile(repo, c["name"]) != C.S_AT_CEO:
                    stats["reconciled"] += 1
                    continue
            end = D.as_date(c.get("limitation_effective_end"))
            if end and D.is_expired(end, today):
                repo.update_case(c["name"], {"status": C.S_EXPIRED},
                                 log(repo, None, "Hết thời hiệu", "Hạn %s" % end))
                hr = hr if hr is not None else hr_users(repo)
                repo.notify([c.get("hr_owner")] + hr, "Hồ sơ kỷ luật %s đã hết thời hiệu" % c["name"],
                            C.CASE, c["name"], url=route_case(c["name"]))
                stats["expired"] += 1
                continue
            if end and D.days_left(end, today) <= warn_days and not c.get("limitation_warned_at"):
                repo.update_case(c["name"], {"limitation_warned_at": repo.now()}, None)
                hr = hr if hr is not None else hr_users(repo)
                repo.notify([c["hr_owner"]] if c.get("hr_owner") else hr, "Còn %d ngày tới hết thời hiệu kỷ luật %s (%s)"
                            % (D.days_left(end, today), c["name"], end), C.CASE, c["name"],
                            url=route_case(c["name"]), severity="urgent")
                stats["warned"] += 1
            due = D.as_date(c.get("hr_review_due"))
            if c["status"] == C.S_PROPOSED and due and today > due:
                hr = hr if hr is not None else hr_users(repo)
                repo.notify(hr, "Đề xuất kỷ luật %s quá hạn thẩm định (%s)" % (c["name"], due), C.CASE, c["name"],
                            url=route_case(c["name"]))
                stats["reminded"] += 1
            bt = D.as_date(c.get("block_to"))
            if c["status"] == C.S_POSTPONED and bt and today > bt:      # nhac moi ngay toi khi HR tiep tuc
                repo.notify([c.get("hr_owner")], "Hồ sơ %s hết thời gian hoãn - có thể tiếp tục" % c["name"],
                            C.CASE, c["name"], url=route_case(c["name"]))
                stats["reminded"] += 1
        except Exception:
            repo.log_error("ky_luat: quet ho so %s" % c.get("name"))
    return stats
