# Copyright (c) 2026, eCentric and contributors
"""Soan khao sat: tao (tu mau / nhan ban), mo de sua, luu (tu luu), xoa ban nhap.
Phat hanh / dong / mo lai nam o publish_service.py."""
import json

from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.application import access, view
from ecentric_workspace.surveys.application import settings_input as SI
from ecentric_workspace.surveys.domain import audience, lifecycle, schema, templates
from ecentric_workspace.surveys.domain.errors import SurveyError
from ecentric_workspace.surveys.infrastructure import repository as default_repo


def _dump(form):
    return json.dumps(form, ensure_ascii=False)


def create(ctx, template="blank", source=None, repo=default_repo):
    """Tao ban nhap moi tu mau, hoac nhan ban `source` (dot khao sat hang thang)."""
    access.require_create(ctx)
    if source:
        src = repo.get_survey(source)
        access.require_manage(ctx, src)
        fields = {f: src.get(f) for f in view.SETTINGS_FIELDS}
        fields["title"] = ("%s (bản sao)" % (src.get("title") or ""))[:200]
        fields["open_at"] = fields["close_at"] = None
        children = {"targets": SI.copy_rows(src.get("targets"), ("kind", "department", "user")),
                    "prizes": SI.copy_rows(src.get("prizes"), ("label", "quantity", "color"))}
        form = view.form_of(src)
    else:
        t = templates.get(template)
        fields = dict(view.DEFAULTS, title=t["title"])
        fields.update(t["settings"])
        children, form = {}, schema.normalize(t["form"])
        if fields.get("reward_mode") not in (None, C.REWARD_NONE):
            # Mau co bat qua thi kem san mot dong qua de tab Phan thuong khong trong tron.
            children["prizes"] = [{"label": "Quà may mắn", "quantity": 1, "color": "#f5b800"}]
    fields.update({"status": C.STATUS_DRAFT, "form_json": _dump(form)})
    return {"name": repo.insert_survey(fields, children)}


def get(ctx, name, repo=default_repo):
    survey = repo.get_survey(name)
    access.require_manage(ctx, survey)
    names = repo.user_names([r.get("user") for r in survey.get("targets") or []]
                            + [r.get("user") for r in survey.get("editors") or []] + [survey.get("owner")])
    depts = {d["name"]: d.get("department_name") or d["name"] for d in repo.departments()}
    eligible = access.eligible_set(repo, survey)
    return {
        "name": name, "status": survey.get("status"), "effective": view.effective(repo, survey),
        "modified": survey.get("modified"), "owner": survey.get("owner"),
        "owner_name": names.get(survey.get("owner")) or survey.get("owner"),
        "is_owner": survey.get("owner") == ctx.user or ctx.is_admin,
        "settings": view.settings(survey), "form": view.form_of(survey),
        "targets": [dict(kind=r.get("kind"), department=r.get("department") or "",
                         user=r.get("user") or "",
                         label=depts.get(r.get("department")) or names.get(r.get("user")) or r.get("user") or "")
                    for r in survey.get("targets") or []],
        "editors": [{"user": r.get("user"), "label": names.get(r.get("user")) or r.get("user")}
                    for r in survey.get("editors") or []],
        "prizes": view.prizes(survey),
        "stats": {"responses": int(survey.get("response_count") or 0), "eligible": len(eligible),
                  "audience": audience.describe(survey.get("audience_mode"), survey.get("targets"),
                                                lambda d: depts.get(d, d), lambda u: names.get(u, u)),
                  "reward_started": bool(survey.get("lucky_seq")) or any(p["awarded"] for p in view.prizes(survey))},
        "published_at": view.dt(survey.get("published_at")),
    }


def save(ctx, name, payload, repo=default_repo):
    """Luu toan bo trinh soan (tu luu ~1s sau moi lan go). Khoa lac quan bang `modified`:
    hai nguoi cung soan thi nguoi luu sau duoc bao tai lai, khong ghi de im lang."""
    survey = repo.get_survey(name)
    access.require_manage(ctx, survey)
    data = SI.parse_json(payload)
    if data.get("modified") and data["modified"] != survey.get("modified"):
        raise SurveyError("Có người vừa sửa khảo sát này ở nơi khác. Tải lại trang để xem bản mới nhất.")
    fields = SI.clean_settings(data.get("settings") or {}, repo)
    children = {"targets": SI.clean_targets(data.get("targets"), repo),
                "editors": SI.clean_editors(data.get("editors"), survey.get("owner"), repo),
                "prizes": SI.clean_prizes(data.get("prizes"), survey)}
    SI.guard_reward_change(survey, fields)
    SI.guard_anonymous_change(survey, fields)
    if "form" in data:
        if not lifecycle.can_edit_questions(survey.get("status")):
            raise SurveyError("Khảo sát đã đóng - mở lại trước khi sửa câu hỏi.")
        fields["form_json"] = _dump(schema.normalize(data["form"]))
    if survey.get("owner") != ctx.user and not ctx.is_admin:
        children.pop("editors")          # chi nguoi tao doi duoc ai cung quan ly
    modified = repo.save_survey(name, fields, children)
    # Tra lai ma qua: dong qua moi chi co ma sau khi luu, trang can no cho lan luu sau.
    return {"modified": modified, "prizes": view.prizes(repo.get_survey(name))}


def delete(ctx, name, repo=default_repo):
    survey = repo.get_survey(name)
    access.require_manage(ctx, survey)
    if survey.get("owner") != ctx.user and not ctx.is_admin:
        raise SurveyError("Chỉ người tạo mới xoá được khảo sát.")
    if survey.get("status") != C.STATUS_DRAFT and not ctx.is_admin:
        raise SurveyError("Chỉ xoá được bản nháp. Khảo sát đã phát hành thì đóng lại để giữ kết quả.")
    repo.delete_survey(name)
    return {"deleted": name}


def list_mine(ctx, repo=default_repo):
    rows = repo.surveys_managed_by(ctx.user, all_surveys=ctx.is_admin)
    names = repo.user_names([r.get("owner") for r in rows])
    return {"can_create": ctx.can_create, "templates": templates.catalog(),
            "surveys": [view.card(repo, r, {"owner_name": names.get(r.get("owner"), r.get("owner"))})
                        for r in rows]}


def directory(ctx, repo=default_repo):
    """Danh ba cho o chon phong ban / nguoi (chi nguoi duoc tao khao sat)."""
    access.require_create(ctx)
    people = [{"user": e["user_id"], "name": e.get("employee_name") or e["user_id"],
               "department": e.get("department") or ""}
              for e in repo.employees() if e.get("status") == audience.ACTIVE]
    depts = [{"name": d["name"], "label": d.get("department_name") or d["name"],
              "parent": d.get("parent_department") or ""} for d in repo.departments()]
    return {"people": sorted(people, key=lambda p: p["name"].lower()), "departments": depts}
