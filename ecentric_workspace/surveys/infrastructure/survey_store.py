# Copyright (c) 2026, eCentric and contributors
"""Khao sat, phieu tra loi, nguoi tham gia - phan cua repository.py.

Tra dict thuan. Service nhan repository qua tham so (mac dinh = module nay), test thay bang
repository gia trong bo nho - xem tests/test_services.py.

Ghi chu ve khoa: lock_survey() chay SELECT ... FOR UPDATE tren dong EC Survey. Moi thao tac
dung chung bo dem cua khao sat (nop phieu khi co gioi han so phieu, cap so may man, quay
thuong, quay so) deu khoa truoc - hai nguoi bam cung luc thi nguoi sau cho nguoi truoc
commit, khong bao gio phat lo qua hon so luong.
"""
import hashlib
import json

import frappe
from frappe.utils import get_datetime, now_datetime

from ecentric_workspace.surveys import constants as C

SURVEY_LIST_FIELDS = ["name", "title", "description", "status", "open_at", "close_at",
                      "anonymous", "reward_mode", "response_limit", "response_count",
                      "accent_color", "audience_mode", "owner", "modified", "published_at",
                      "is_quiz", "form_json", "draw_scheduled_at", "draw_at", "number_range"]


def now():
    return now_datetime()


def to_datetime(v):
    return get_datetime(v) if v else None


# ------------------------------------------------------------------------- khao sat --

def get_survey(name):
    if not name or not frappe.db.exists(C.SURVEY, name):
        return None
    d = frappe.get_doc(C.SURVEY, name).as_dict()
    d["modified"] = str(d.get("modified") or "")
    return d


def lock_survey(name):
    frappe.db.sql("select name from `tabEC Survey` where name=%s for update", (name,))


def insert_survey(fields, children=None):
    doc = frappe.get_doc(dict(fields, doctype=C.SURVEY))
    for key, rows in (children or {}).items():
        for r in rows:
            doc.append(key, r)
    doc.insert(ignore_permissions=True)
    return doc.name


def save_survey(name, fields, children=None):
    doc = frappe.get_doc(C.SURVEY, name)
    doc.update(fields)
    for key, rows in (children or {}).items():
        doc.set(key, [])
        for r in rows:
            doc.append(key, r)
    doc.save(ignore_permissions=True)
    return str(doc.modified)


def update_survey(name, values):
    """Doi trang thai (phat hanh / dong / mo lai) QUA doc.save: de lai Version (track_changes)
    - ai dong khao sat luc nao phai tra lai duoc. Bo dem thi dung set_survey_values."""
    doc = frappe.get_doc(C.SURVEY, name)
    doc.update(values)
    doc.save(ignore_permissions=True)
    return str(doc.modified)


def set_survey_values(name, values):
    """Ghi bo dem / dau vet (so phieu, so may man, gio quay so) - KHONG doi `modified`, de
    khoa lac quan cua trinh soan khong bao nham "co nguoi vua sua"."""
    frappe.db.set_value(C.SURVEY, name, values, update_modified=False)


def set_prize_awarded(row_name, awarded):
    frappe.db.set_value(C.PRIZE, row_name, "awarded", awarded, update_modified=False)


def delete_survey(name):
    for dt in (C.PARTICIPANT, C.RESPONSE):
        for n in frappe.get_all(dt, filters={"survey": name}, pluck="name"):
            frappe.delete_doc(dt, n, ignore_permissions=True, force=True)
    frappe.delete_doc(C.SURVEY, name, ignore_permissions=True, force=True)


def surveys_managed_by(user, all_surveys=False):
    filters = None if all_surveys else {"owner": user}
    rows = frappe.get_all(C.SURVEY, filters=filters, fields=SURVEY_LIST_FIELDS,
                          order_by="modified desc", limit_page_length=500)
    if not all_surveys:
        shared = frappe.get_all(C.EDITOR, filters={"user": user, "parenttype": C.SURVEY},
                                pluck="parent", limit_page_length=500)
        known = {r.name for r in rows}
        extra = [n for n in set(shared) if n not in known]
        if extra:
            rows += frappe.get_all(C.SURVEY, filters={"name": ["in", extra]},
                                   fields=SURVEY_LIST_FIELDS, limit_page_length=500)
    return [dict(r) for r in rows]


def surveys_by_status(status, names=None):
    filters = {"status": status}
    if names is not None:
        filters["name"] = ["in", list(names) or ["-"]]
    return [dict(r) for r in frappe.get_all(C.SURVEY, filters=filters, fields=SURVEY_LIST_FIELDS,
                                            order_by="modified desc", limit_page_length=500)]


def surveys_by_names(names):
    if not names:
        return []
    return [dict(r) for r in frappe.get_all(C.SURVEY, filters={"name": ["in", list(names)]},
                                            fields=SURVEY_LIST_FIELDS, limit_page_length=500)]


# ---------------------------------------------------------------------- phieu tra loi --

def count_responses(survey):
    return frappe.db.count(C.RESPONSE, {"survey": survey})


def responses(survey, limit=5000, start=0):
    rows = frappe.get_all(C.RESPONSE, filters={"survey": survey},
                          fields=["name", "respondent", "submitted_at", "updated_at", "score",
                                  "max_score", "answers_json"],
                          order_by="submitted_at desc", start=start, limit_page_length=limit)
    out = []
    for r in rows:
        d = dict(r)
        d["answers"] = _json(d.pop("answers_json"))
        out.append(d)
    return out


def get_response(name):
    if not name or not frappe.db.exists(C.RESPONSE, name):
        return None
    d = frappe.get_doc(C.RESPONSE, name).as_dict()
    d["answers"] = _json(d.get("answers_json"))
    return d


def insert_response(survey, respondent, answers, score, max_score, at):
    doc = frappe.get_doc({"doctype": C.RESPONSE, "survey": survey, "respondent": respondent or None,
                          "answers_json": json.dumps(answers, ensure_ascii=False),
                          "score": score, "max_score": max_score, "submitted_at": at})
    doc.insert(ignore_permissions=True)
    return doc.name


def update_response(name, answers, score, max_score, at):
    frappe.db.set_value(C.RESPONSE, name, {
        "answers_json": json.dumps(answers, ensure_ascii=False), "score": score,
        "max_score": max_score, "updated_at": at})


# ------------------------------------------------------------------------- tham gia --

def participant_name(survey, user):
    return "%s-%s" % (survey, hashlib.sha1(user.lower().encode("utf-8")).hexdigest()[:12])


def get_participant(survey, user):
    name = participant_name(survey, user)
    if not frappe.db.exists(C.PARTICIPANT, name):
        return None
    return dict(frappe.get_doc(C.PARTICIPANT, name).as_dict())


def insert_participant(survey, user, fields):
    """Tra name, hoac None neu nguoi nay DA nop (khoa chinh tat dinh = chong nop trung ca
    khi hai tab bam cung luc)."""
    doc = frappe.get_doc(dict(fields, doctype=C.PARTICIPANT, survey=survey, user=user))
    try:
        doc.insert(ignore_permissions=True, set_name=participant_name(survey, user))
    except frappe.DuplicateEntryError:
        return None
    return doc.name


def update_participant(name, values):
    frappe.db.set_value(C.PARTICIPANT, name, values, update_modified=False)


def participants(survey):
    return [dict(r) for r in frappe.get_all(
        C.PARTICIPANT, filters={"survey": survey},
        fields=["name", "user", "submitted_at", "response", "lucky_number", "reward_result",
                "prize", "prize_label", "rewarded_at", "spin_seq"],
        order_by="submitted_at asc", limit_page_length=20000)]


def participations_of(user):
    return [dict(r) for r in frappe.get_all(
        C.PARTICIPANT, filters={"user": user},
        fields=["survey", "submitted_at", "lucky_number", "reward_result", "prize_label"],
        order_by="submitted_at desc", limit_page_length=500)]


def winners(surveys):
    if not surveys:
        return []
    return [dict(r) for r in frappe.get_all(
        C.PARTICIPANT, filters={"survey": ["in", list(surveys)], "reward_result": C.RESULT_WIN},
        fields=["survey", "user", "prize_label", "lucky_number", "rewarded_at"],
        order_by="rewarded_at desc", limit_page_length=200)]


def count_participants(survey):
    return frappe.db.count(C.PARTICIPANT, {"survey": survey})


# ----------------------------------------------------------------- quay theo gio hen --
_DRAW_FIELDS = ["name", "title", "status", "reward_mode", "draw_scheduled_at", "draw_notified_at",
                "draw_at", "open_at", "close_at"]


def _draw_filters(extra):
    f = {"status": ["in", [C.STATUS_OPEN, C.STATUS_CLOSED]],
         "reward_mode": ["in", list(C.SCHEDULED_MODES)]}
    f.update(extra)
    return f


def pending_draws(until):
    """Luot quay CHUA chot co gio hen <= until (job moi phut)."""
    return [dict(r) for r in frappe.get_all(
        C.SURVEY, filters=_draw_filters({"draw_scheduled_at": ["<=", until], "draw_at": ["is", "not set"]}),
        fields=_DRAW_FIELDS, order_by="draw_scheduled_at asc", limit_page_length=50)]


def draw_surveys(start, end):
    """Luot quay co gio hen trong [start, end] (popup trang chu), som truoc."""
    return [dict(r) for r in frappe.get_all(
        C.SURVEY, filters=_draw_filters({"draw_scheduled_at": ["between", [start, end]]}),
        fields=_DRAW_FIELDS, order_by="draw_scheduled_at asc", limit_page_length=50)]


def count_draw_surveys(start, end):
    return frappe.db.count(C.SURVEY, _draw_filters({"draw_scheduled_at": ["between", [start, end]]}))


def count_spins(survey):
    return frappe.db.count(C.PARTICIPANT, {"survey": survey,
                                           "reward_result": ["in", [C.RESULT_WIN, C.RESULT_LOSE]]})


def _json(s):
    try:
        return json.loads(s) if s else {}
    except ValueError:
        return {}
