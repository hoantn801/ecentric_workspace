# Copyright (c) 2026, eCentric and contributors
"""Tab "Kết quả" cua trinh soan: tong hop, tung phieu, ai da / chua lam, xuat Excel, tai tep.
Chi nguoi quan ly khao sat. Khao sat an danh: khong bao gio tra ten nguoi o phieu."""
from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.application import access, export_format, view
from ecentric_workspace.surveys.domain import rewards, schema, summary
from ecentric_workspace.surveys.domain.errors import SurveyError
from ecentric_workspace.surveys.infrastructure import repository as default_repo


def _survey(ctx, name, repo):
    survey = repo.get_survey(name)
    access.require_manage(ctx, survey)
    return survey


def overview(ctx, name, repo=default_repo):
    survey = _survey(ctx, name, repo)
    form = view.form_of(survey)
    rows = repo.responses(name)
    parts = repo.participants(name)
    eligible = access.eligible_set(repo, survey)
    out = {"summary": summary.summarize(form, [r["answers"] for r in rows]),
           "eligible": len(eligible), "submitted": len(parts),
           "submitted_eligible": len({p["user"] for p in parts} & eligible),
           "anonymous": int(survey.get("anonymous") or 0)}
    if survey.get("is_quiz"):
        scored = [r for r in rows if r.get("max_score")]
        out["quiz"] = {"average": round(sum(r["score"] or 0 for r in scored) / len(scored), 2) if scored else None,
                       "max_score": scored[0]["max_score"] if scored else schema_max(form)}
    if survey.get("reward_mode") != C.REWARD_NONE:
        # Da nop ma chua chon so (chi khi chua quay) - nguoi quan ly nhac rieng; toi gio may boc giup.
        unpicked = [p["user"] for p in parts if not p.get("lucky_number")] \
            if survey.get("reward_mode") == C.REWARD_NUMBER and not survey.get("draw_at") else []
        names = repo.user_names([p["user"] for p in parts if p.get("reward_result") == C.RESULT_WIN] + unpicked)
        top = view.number_top(survey)
        out["reward"] = {
            "mode": survey.get("reward_mode"), "prizes": view.prizes(survey),
            "spins": sum(1 for p in parts if p.get("spin_seq") or (survey.get("reward_mode") == C.REWARD_WHEEL
                                                                    and p.get("reward_result"))),
            "numbers": sum(1 for p in parts if p.get("lucky_number")), "number_range": top,
            "racers": len(parts) if survey.get("reward_mode") == C.REWARD_RACE else 0,
            "draw_scheduled_at": view.dt(survey.get("draw_scheduled_at")),
            "draw_at": view.dt(survey.get("draw_at")),
            "unpicked": sorted(({"user": u, "name": names.get(u, u)} for u in unpicked), key=lambda x: x["name"]),
            "auto_picked": int((view.draw_results(survey) or {}).get("auto") or 0)
            if isinstance(view.draw_results(survey), dict) else 0,
            "empty_numbers": [rewards.format_number(i["number"], top)
                              for i in (view.draw_results(survey) or {}).get("items", []) if not i.get("user")]
            if isinstance(view.draw_results(survey), dict) else [],
            "winners": [{"name": names.get(p["user"], p["user"]), "user": p["user"],
                         "prize": p.get("prize_label") or "",
                         "lucky_number": rewards.format_number(p["lucky_number"], top) if p.get("lucky_number") else "",
                         "at": view.dt(p.get("rewarded_at"))}
                        for p in parts if p.get("reward_result") == C.RESULT_WIN]}
    return out


def schema_max(form):
    return sum(q.get("points") or 0 for q in schema.questions(form))


def response_at(ctx, name, index, repo=default_repo):
    """Phieu thu `index` (0 = moi nhat). Tra kem tong so de trang lam nut truoc / sau."""
    survey = _survey(ctx, name, repo)
    total = repo.count_responses(name)
    index = max(0, min(int(index or 0), max(total - 1, 0)))
    rows = repo.responses(name, limit=1, start=index)
    if not rows:
        return {"total": 0}
    r = rows[0]
    who = ""
    if not survey.get("anonymous") and r.get("respondent"):
        who = repo.user_names([r["respondent"]]).get(r["respondent"], r["respondent"])
    return {"total": total, "index": index, "respondent": who,
            "submitted_at": view.dt(r.get("submitted_at")), "updated_at": view.dt(r.get("updated_at")),
            "score": r.get("score"), "max_score": r.get("max_score"), "answers": r["answers"]}


def participation(ctx, name, repo=default_repo):
    """Ai da nop / chua nop trong doi tuong. Ca khao sat an danh cung co danh sach nay (biet
    AI da nop, khong biet ho tra loi gi) - de nhac nguoi chua lam."""
    survey = _survey(ctx, name, repo)
    done = {p["user"]: p for p in repo.participants(name)}
    eligible = access.eligible_set(repo, survey)
    emps = {e["user_id"]: e for e in repo.employees()}
    users = sorted(eligible | set(done))
    names = repo.user_names(users)
    out = []
    for u in users:
        p = done.get(u)
        out.append({"user": u, "name": names.get(u, u),
                    "department": (emps.get(u) or {}).get("department") or "",
                    "done": bool(p), "submitted_at": view.dt(p and p.get("submitted_at")),
                    "in_audience": u in eligible})
    out.sort(key=lambda x: (x["done"], x["name"].lower()))
    return {"people": out}


def export(ctx, name, repo=default_repo):
    """(ten_file, [[o]]) - controller doi sang xlsx."""
    survey = _survey(ctx, name, repo)
    form = view.form_of(survey)
    rows = repo.responses(name, limit=20000)
    names = {} if survey.get("anonymous") else repo.user_names([r.get("respondent") for r in rows])
    table = export_format.table(form, rows, names, anonymous=bool(survey.get("anonymous")),
                                quiz=bool(survey.get("is_quiz")))
    return "%s.xlsx" % name, table


def file_for_download(ctx, name, url, repo=default_repo):
    _survey(ctx, name, repo)
    f = repo.file_by_url(url)
    if not f or f.get("attached_to_doctype") != C.RESPONSE:
        raise SurveyError("Không tìm thấy tệp.")
    resp = repo.get_response(f.get("attached_to_name"))
    if not resp or resp.get("survey") != name:
        raise SurveyError("Không tìm thấy tệp.")
    return repo.file_content(f["name"])
