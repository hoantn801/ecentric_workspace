# Copyright (c) 2026, eCentric and contributors
"""Lam sach phan CAI DAT ma trinh soan gui len (cot EC Survey + 3 bang con). Payload HTTP
luon la chuoi / JSON tu trinh duyet - khong tin kieu, khong tin khoa."""
import json
import re

from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.application import view
from ecentric_workspace.surveys.domain.errors import SurveyError

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_DT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(:\d{2})?$")
_DT_LABELS = {"open_at": "Giờ mở", "close_at": "Giờ đóng", "draw_scheduled_at": "Giờ quay"}


def parse_json(payload):
    if isinstance(payload, dict):
        return payload
    try:
        data = json.loads(payload or "{}")
    except ValueError:
        raise SurveyError("Dữ liệu gửi lên không hợp lệ.")
    if not isinstance(data, dict):
        raise SurveyError("Dữ liệu gửi lên không hợp lệ.")
    return data


def _dt(v, label):
    v = (v or "").strip()
    if not v:
        return None
    m = _DT_RE.match(v)
    if not m:
        raise SurveyError("%s không đúng định dạng ngày giờ." % label)
    return "%s %s:00" % (m.group(1), m.group(2))


def clean_settings(raw, repo):
    out = {}
    for f in view.SETTINGS_FIELDS:
        if f not in raw:
            continue
        v = raw.get(f)
        if f in view.CHECK_FIELDS:
            out[f] = 1 if v in (1, True, "1", "true") else 0
        elif f in view.INT_FIELDS:
            try:
                out[f] = max(0, min(100000, int(v or 0)))
            except (TypeError, ValueError):
                out[f] = 0
        elif f in view.DATETIME_FIELDS:
            out[f] = _dt(v, _DT_LABELS.get(f, f))
        else:
            out[f] = ("" if v is None else str(v)).strip()
    if "title" in out:
        out["title"] = out["title"][:200] or "Khảo sát không tên"
    if "description" in out:
        out["description"] = out["description"][:C.MAX_DESC]
    if "confirmation_message" in out:
        out["confirmation_message"] = out["confirmation_message"][:1000]
    if "reward_note" in out:
        out["reward_note"] = out["reward_note"][:1000]
    if "accent_color" in out and not _COLOR_RE.match(out["accent_color"]):
        out["accent_color"] = "#2C3DA6"
    if out.get("audience_mode") not in (None,) + C.AUDIENCE_MODES:
        out["audience_mode"] = C.AUDIENCE_ALL
    if out.get("reward_mode") not in (None,) + C.REWARD_MODES:
        out["reward_mode"] = C.REWARD_NONE
    if "number_range" in out:
        out["number_range"] = max(C.NUMBER_RANGE_MIN, min(C.NUMBER_RANGE_MAX,
                                                          out["number_range"] or C.NUMBER_RANGE_DEFAULT))
    if out.get("open_at") and out.get("close_at") and out["close_at"] <= out["open_at"]:
        raise SurveyError("Giờ đóng phải sau giờ mở.")
    return out


def clean_targets(rows, repo):
    out, seen = [], set()
    for r in rows or []:
        if not isinstance(r, dict) or r.get("kind") not in C.TARGET_KINDS:
            continue
        if r["kind"] == C.TARGET_DEPARTMENT:
            key, row = ("D", r.get("department")), {"kind": r["kind"], "department": r.get("department")}
        else:
            key, row = (r["kind"], r.get("user")), {"kind": r["kind"], "user": r.get("user")}
        if not key[1] or key in seen:
            continue
        seen.add(key)
        out.append(row)
    if len(out) > 2000:
        raise SurveyError("Danh sách đối tượng quá dài.")
    return out


def clean_editors(rows, owner, repo):
    out = []
    for r in rows or []:
        u = (r.get("user") if isinstance(r, dict) else r) or ""
        if u and u != owner and u not in [x["user"] for x in out]:
            if not repo.user_exists(u):
                raise SurveyError("Không tìm thấy người dùng %s." % u)
            out.append({"user": u})
    return out[:30]


def clean_prizes(rows, survey):
    """Giu `name` (= ma qua) cua dong cu de so qua da trao khong bi xoa khi luu."""
    existing = {p.get("name"): p for p in survey.get("prizes") or []}
    out = []
    for r in (rows or [])[:C.MAX_PRIZES]:
        if not isinstance(r, dict):
            continue
        label = ("" if r.get("label") is None else str(r.get("label"))).strip()[:80]
        try:
            qty = max(0, min(10000, int(r.get("quantity") or 0)))
        except (TypeError, ValueError):
            qty = 0
        color = r.get("color") if _COLOR_RE.match(str(r.get("color") or "")) else ""
        old = existing.get(r.get("id"))
        awarded = int(old.get("awarded") or 0) if old else 0
        if not label and not awarded:
            continue
        if qty < awarded:
            raise SurveyError("Quà “%s” đã trao %d phần - số lượng không được ít hơn."
                              % (label, awarded))
        row = {"label": label or "Quà", "quantity": qty, "awarded": awarded, "color": color}
        if old:
            row["name"] = old.get("name")
        out.append(row)
    for name, old in existing.items():
        if int(old.get("awarded") or 0) and name not in [x.get("name") for x in out]:
            raise SurveyError("Không xoá được quà “%s” vì đã có người trúng." % old.get("label"))
    return out


def reward_started(survey):
    return bool(survey.get("lucky_seq")) or bool(survey.get("draw_at")) or any(
        int(p.get("awarded") or 0) for p in survey.get("prizes") or [])


def guard_reward_change(survey, fields, max_number=0):
    """Khoa nhung thay doi lam sai ket qua da co.

    max_number : so lon nhat dang co nguoi giu (de khong thu dai so xuong duoi so do).
    """
    if reward_started(survey) and "reward_mode" in fields and fields["reward_mode"] != survey.get("reward_mode"):
        raise SurveyError("Đã có người nhận quà / số may mắn - không đổi được kiểu phần thưởng nữa.")
    if survey.get("draw_at"):
        if "draw_scheduled_at" in fields and \
                (fields["draw_scheduled_at"] or "")[:16] != view.dt(survey.get("draw_scheduled_at"))[:16]:
            raise SurveyError("Đã quay xong - không đổi được giờ quay nữa.")
        if "number_range" in fields and int(fields["number_range"] or 0) != view.number_top(survey):
            raise SurveyError("Đã quay xong - không đổi được dải số nữa.")
    if max_number and int(fields.get("number_range") or max_number) < max_number:
        raise SurveyError("Đang có người giữ số %d - dải số không được nhỏ hơn." % max_number)


def guard_anonymous_change(survey, fields):
    """Doi an danh sau khi da co phieu thi nua tap phieu co ten, nua khong - nguoi tra loi da
    nop theo mot loi hua khac. Khoa ca hai chieu."""
    if "anonymous" in fields and int(fields["anonymous"]) != int(survey.get("anonymous") or 0) \
            and int(survey.get("response_count") or 0) > 0:
        raise SurveyError("Đã có phiếu trả lời - không đổi được chế độ ẩn danh nữa.")


def copy_rows(rows, keys):
    return [{k: r.get(k) for k in keys} for r in rows or []]
