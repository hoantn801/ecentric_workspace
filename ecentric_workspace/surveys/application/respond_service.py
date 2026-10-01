# Copyright (c) 2026, eCentric and contributors
"""Phia NGUOI TRA LOI: danh sach khao sat cua toi, mo form, nop / sua phieu.

An danh that su: khao sat an danh thi EC Survey Response KHONG mang ten nguoi tra loi va
EC Survey Participant KHONG tro toi phieu. Nguoi tao (va ca System Manager doc DB) chi biet
"ai da nop", khong noi duoc nguoi voi cau tra loi. Doi lai: phieu an danh khong sua duoc sau
khi nop (khong con duong nao tim lai phieu cua minh).
"""
from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.application import access, view
from ecentric_workspace.surveys.application import submit_reward
from ecentric_workspace.surveys.domain import answers as A
from ecentric_workspace.surveys.domain import summary
from ecentric_workspace.surveys.domain.errors import (AnswerErrors, SurveyError, SurveyNotFound,
                                                      SurveyPermissionError)
from ecentric_workspace.surveys.infrastructure import repository as default_repo


def hub(ctx, repo=default_repo):
    """Trang /khao-sat: dang mo cho toi, da lam, bang vang."""
    mine = {p["survey"]: p for p in repo.participations_of(ctx.user)}
    cache, open_cards = {}, []
    for s in repo.surveys_by_status(C.STATUS_OPEN):
        eff = view.effective(repo, s)
        if eff not in (C.EFFECTIVE_OPEN, C.EFFECTIVE_SCHEDULED) or s["name"] in mine:
            continue
        full = repo.get_survey(s["name"])
        if access.is_eligible(repo, ctx, full, cache):
            open_cards.append(view.card(repo, s, {"prizes": [p["label"] for p in view.prizes(full)]}))
    done = []
    for s in repo.surveys_by_names(list(mine)):
        p = mine[s["name"]]
        done.append(view.card(repo, s, {"submitted_at": view.dt(p.get("submitted_at")),
                                        "lucky_number": p.get("lucky_number") or 0,
                                        "reward_result": p.get("reward_result") or "",
                                        "prize_label": p.get("prize_label") or ""}))
    done.sort(key=lambda c: c["submitted_at"], reverse=True)
    open_cards.sort(key=lambda c: (c["close_at"] or "9999", c["title"]))
    visible = [c["name"] for c in open_cards] + [c["name"] for c in done]
    wins = repo.winners(visible)
    names = repo.user_names([w["user"] for w in wins])
    titles = {c["name"]: c["title"] for c in open_cards + done}
    board = [{"name": names.get(w["user"], w["user"]), "me": w["user"] == ctx.user,
              "prize": w.get("prize_label") or "", "survey": titles.get(w["survey"], ""),
              "at": view.dt(w.get("rewarded_at"))} for w in wins[:30]]
    return {"open": open_cards, "done": done, "board": board, "can_create": ctx.can_create}


def _load(ctx, name, repo):
    survey = repo.get_survey(name)
    if not survey or survey.get("status") == C.STATUS_DRAFT and not access.can_manage(ctx, survey):
        raise SurveyNotFound("Không tìm thấy khảo sát.")
    return survey


def get_form(ctx, name, preview=False, repo=default_repo):
    survey = _load(ctx, name, repo)
    manage = access.can_manage(ctx, survey)
    if preview and not manage:
        raise SurveyPermissionError("Chỉ người soạn mới xem trước được.")
    eligible = access.is_eligible(repo, ctx, survey)
    if not eligible and not manage:
        raise SurveyPermissionError("Khảo sát này không dành cho bạn.")
    part = repo.get_participant(name, ctx.user)
    mine = None
    if part and part.get("response") and survey.get("allow_edit"):
        resp = repo.get_response(part["response"])
        mine = resp and resp.get("answers")
    return {
        "name": name, "title": survey.get("title"), "description": survey.get("description") or "",
        "settings": {k: view.settings(survey)[k] for k in (
            "accent_color", "anonymous", "allow_edit", "show_progress", "shuffle_questions",
            "is_quiz", "close_at", "open_at", "reward_mode", "reward_note", "show_summary")},
        "effective": view.effective(repo, survey), "form": view.public_form(view.form_of(survey)),
        "eligible": eligible, "preview": bool(preview), "can_manage": manage,
        "prizes": [{"id": p["id"], "label": p["label"], "color": p["color"]} for p in view.prizes(survey)],
        "submitted": bool(part), "my_answers": mine,
        "reward": submit_reward.state(survey, part) if part else None,
    }


def _check_files(repo, ctx, form, clean):
    for url in A.file_urls(form, clean):
        f = repo.file_by_url(url)
        if not f or f.get("owner") != ctx.user or not f.get("is_private"):
            raise SurveyError("Tệp đính kèm không hợp lệ hoặc không phải bạn tải lên.")
        if f.get("attached_to_name"):
            raise SurveyError("Tệp %s đã dùng ở nơi khác - tải lại tệp." % f.get("file_name"))


def submit(ctx, name, raw_answers, repo=default_repo):
    survey = _load(ctx, name, repo)
    if view.effective(repo, survey) == C.EFFECTIVE_SCHEDULED:
        raise SurveyError("Khảo sát chưa mở.")
    if view.effective(repo, survey) != C.EFFECTIVE_OPEN:
        raise SurveyError("Khảo sát đã đóng.")
    if not access.is_eligible(repo, ctx, survey):
        raise SurveyPermissionError("Khảo sát này không dành cho bạn.")
    form = view.form_of(survey)
    clean, errors = A.clean(form, raw_answers)
    if errors:
        raise AnswerErrors(A.first_error(form, errors) or "Câu trả lời chưa hợp lệ.", errors)
    _check_files(repo, ctx, form, clean)
    sc = A.score(form, clean) if survey.get("is_quiz") else {"score": 0, "max_score": 0, "detail": {}}
    now = repo.now()
    part = repo.get_participant(name, ctx.user)
    if part:
        if not (survey.get("allow_edit") and part.get("response")):
            raise SurveyError("Bạn đã nộp khảo sát này rồi.")
        repo.update_response(part["response"], clean, sc["score"], sc["max_score"], now)
        resp_name, edited = part["response"], True
    else:
        repo.lock_survey(name)
        if survey.get("response_limit") and repo.count_responses(name) >= int(survey["response_limit"]):
            raise SurveyError("Khảo sát đã đủ số phiếu.")
        anon = bool(survey.get("anonymous"))
        resp_name = repo.insert_response(name, None if anon else ctx.user, clean, sc["score"],
                                         sc["max_score"], now)
        pname = repo.insert_participant(name, ctx.user, {
            "submitted_at": now, "response": None if anon else resp_name})
        if not pname:
            raise SurveyError("Bạn đã nộp khảo sát này rồi.")
        part = submit_reward.on_submit(repo, survey, pname, now)
        repo.set_survey_values(name, {"response_count": repo.count_responses(name)})
        edited = False
    for url in A.file_urls(form, clean):
        repo.attach_file(repo.file_by_url(url)["name"], C.RESPONSE, resp_name)
    return _after_submit(repo, survey, form, sc, part, edited)


def _after_submit(repo, survey, form, sc, part, edited):
    out = {"submitted": True, "edited": edited,
           "message": survey.get("confirmation_message") or "Cảm ơn bạn đã trả lời khảo sát!",
           "reward": submit_reward.state(survey, part) if part else None}
    if survey.get("is_quiz") and survey.get("show_score"):
        out["score"] = sc
    if survey.get("show_summary"):
        out["summary"] = summary.public_summary(form, [r["answers"] for r in repo.responses(survey["name"])])
    return out


def public_summary(ctx, name, repo=default_repo):
    survey = _load(ctx, name, repo)
    if not survey.get("show_summary") and not access.can_manage(ctx, survey):
        raise SurveyPermissionError("Người tạo không bật xem tóm tắt kết quả.")
    if not repo.get_participant(name, ctx.user) and not access.can_manage(ctx, survey):
        raise SurveyPermissionError("Nộp khảo sát xong mới xem được tóm tắt.")
    form = view.form_of(survey)
    return summary.public_summary(form, [r["answers"] for r in repo.responses(name)])
