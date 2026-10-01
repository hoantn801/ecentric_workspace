# Copyright (c) 2026, eCentric and contributors
"""Phat hanh / dong / mo lai khao sat + bao tin cho doi tuong.

Bao tin di qua notification_center (chuong ERP + web push; KHONG ban Teams - event
"announcement" khoa cung teams=False vi gui cho ca cong ty). Gui trong job nen (enqueue sau
commit) de nut "Phat hanh" khong phai cho vai tram lan ghi Notification Log.
Moi nguoi mot khoa dedupe -> bam phat hanh lai / job chay lai khong bao trung.
"""
from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.application import access, draw_feed, submit_reward, view
from ecentric_workspace.surveys.domain import schema
from ecentric_workspace.surveys.domain.errors import SurveyError
from ecentric_workspace.surveys.infrastructure import repository as default_repo

JOB = "ecentric_workspace.surveys.application.publish_service.run_notify"


def problems(repo, survey):
    form = view.form_of(survey)
    out = schema.publish_problems(form, anonymous=bool(survey.get("anonymous")),
                                  quiz=bool(survey.get("is_quiz")))
    if survey.get("audience_mode") == C.AUDIENCE_CUSTOM and not any(
            t.get("kind") in (C.TARGET_DEPARTMENT, C.TARGET_USER) for t in survey.get("targets") or []):
        out.append("Chưa chọn phòng ban hoặc người tham gia.")
    elif not access.eligible_set(repo, survey):
        out.append("Đối tượng đang chọn không có ai (kiểm tra danh sách loại trừ).")
    if survey.get("reward_mode") != C.REWARD_NONE and not any(p["quantity"] > 0 for p in view.prizes(survey)):
        out.append("Đã bật phần thưởng nhưng chưa nhập quà nào.")
    out += draw_problems(repo, survey)
    close_at = repo.to_datetime(survey.get("close_at"))
    if close_at and close_at <= repo.now():
        out.append("Giờ đóng đã qua - chọn giờ đóng mới hoặc để trống.")
    return out


def draw_problems(repo, survey):
    """Quay theo gio hen: phai co gio quay o tuong lai, sau gio mo; dai so du cho moi nguoi."""
    if survey.get("reward_mode") not in C.SCHEDULED_MODES or survey.get("draw_at"):
        return []
    out = []
    at = repo.to_datetime(survey.get("draw_scheduled_at"))
    open_at = repo.to_datetime(survey.get("open_at"))
    if not at:
        out.append("Chưa chọn giờ quay (tab Phần thưởng).")
    elif at <= repo.now():
        out.append("Giờ quay đã qua - chọn giờ quay mới.")
    elif open_at and at <= open_at:
        out.append("Giờ quay phải sau giờ mở khảo sát.")
    if survey.get("reward_mode") == C.REWARD_NUMBER:
        n = len(access.eligible_set(repo, survey))
        if view.number_top(survey) < n:
            out.append("Dải số (1-%d) ít hơn số người tham gia (%d) - tăng dải số để ai cũng chọn được."
                       % (view.number_top(survey), n))
    return out


def publish(ctx, name, repo=default_repo):
    survey = repo.get_survey(name)
    access.require_manage(ctx, survey)
    if survey.get("status") == C.STATUS_OPEN:
        return {"status": C.STATUS_OPEN, "notified": False}
    probs = problems(repo, survey)
    if probs:
        raise SurveyError("Chưa phát hành được:\n• " + "\n• ".join(probs))
    first = not survey.get("published_at")
    values = {"status": C.STATUS_OPEN}
    if first:
        values.update({"published_at": repo.now(), "published_by": ctx.user})
    repo.update_survey(name, values)
    if survey.get("reward_mode") == C.REWARD_WHEEL and not view.wheel_plan(survey):
        submit_reward.make_plan(repo, repo.get_survey(name))
    if survey.get("reward_mode") in C.SCHEDULED_MODES:
        draw_feed.invalidate(repo)
    notified = bool(first and survey.get("notify_on_publish"))
    if notified:
        repo.enqueue(JOB, name=name, kind="open")
    return {"status": C.STATUS_OPEN, "notified": notified}


def close(ctx, name, repo=default_repo):
    survey = repo.get_survey(name)
    access.require_manage(ctx, survey)
    repo.update_survey(name, {"status": C.STATUS_CLOSED})
    return {"status": C.STATUS_CLOSED}


def reopen(ctx, name, repo=default_repo):
    survey = repo.get_survey(name)
    access.require_manage(ctx, survey)
    close_at = repo.to_datetime(survey.get("close_at"))
    if close_at and close_at <= repo.now():
        raise SurveyError("Giờ đóng đã qua. Sửa giờ đóng trong Cài đặt rồi mở lại.")
    repo.update_survey(name, {"status": C.STATUS_OPEN})
    return {"status": C.STATUS_OPEN}


def remind(ctx, name, repo=default_repo):
    """Nhac nguoi CHUA lam. Toi da mot lan / nguoi / ngay (khoa dedupe theo ngay)."""
    survey = repo.get_survey(name)
    access.require_manage(ctx, survey)
    if view.effective(repo, survey) != C.EFFECTIVE_OPEN:
        raise SurveyError("Khảo sát không ở trạng thái đang mở.")
    done = {p["user"] for p in repo.participants(name)}
    todo = sorted(access.eligible_set(repo, survey) - done)
    if todo:
        repo.enqueue(JOB, name=name, kind="remind", users=todo)
    return {"queued": len(todo)}


def run_notify(name, kind="open", users=None, repo=default_repo):
    """Job nen. Loi tung nguoi khong lam chet ca dot."""
    survey = repo.get_survey(name)
    if not survey:
        return {"sent": 0}
    if users is None:
        users = sorted(access.eligible_set(repo, survey))
    day = str(repo.now())[:10]
    title = ("Khảo sát mới: %s" if kind == "open" else "Nhắc bạn làm khảo sát: %s") % survey.get("title")
    close_at = view.dt(survey.get("close_at"))
    msg = ("Hạn chót %s." % close_at[:16]) if close_at else "Mời bạn dành vài phút trả lời."
    open_at = repo.to_datetime(survey.get("open_at"))
    if open_at and open_at > repo.now():
        msg = "Mở từ %s. %s" % (view.dt(open_at)[:16], msg)
    if survey.get("reward_mode") != C.REWARD_NONE:
        msg += " Làm xong có quà may mắn!"
    sent = 0
    for u in users:
        try:
            key = "survey|%s|%s|%s" % (kind, name, u) + ("|" + day if kind == "remind" else "")
            repo.notify(u, title, msg, C.fill_url(name), name, key)
            sent += 1
        except Exception:
            repo.log_error("survey notify %s %s" % (name, u))
    return {"sent": sent}
