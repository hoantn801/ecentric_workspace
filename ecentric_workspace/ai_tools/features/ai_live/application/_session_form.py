# Copyright (c) 2026, eCentric and contributors
"""18/11: dung chung cho Tao phien / Sua phien tren /ai-live - doc form tu trang, kiem tung o, ghep vao "view" ban nhap.
Loi -> AiLiveError(code="field_invalid", data={"field": ...}) de trang hien duoi dung o."""
from datetime import datetime

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P
from ecentric_workspace.ai_tools.features.ai_live.domain import session_form_rules as F

TIKTOK = "TikTok"


def parse(form):
    raw = _common.parse_json(form, "phiên") if isinstance(form, str) else form
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise C.AiLiveError(C.SessMsg.BAD_FORM)
    return raw


def today(now):
    return datetime.fromtimestamp(now, R._VN).date()


def apply(view, form, machine_row, kit_exists, sessions, self_id=None):
    """Ghep cac o co mat trong `form` vao `view` (sua tai cho). Tra view.
    - username chi giu khi san TikTok;
    - ten trong -> "<Brand> <San> <so>" (so = thu tu phien cung brand + san)."""
    vals = F.fields({k: form[k] for k in form if k in C.SESSION_DRAFT_FIELDS or k == "lc_open_before_min"},
                    machine_row, kit_exists)
    view.update(vals)
    if view.get("platform") != TIKTOK:
        view["tiktok_username"] = ""
    if not F.text(view.get("title")):
        view["title"] = auto_title(sessions, view.get("brand"), view.get("platform"), self_id)
    return view


def auto_title(sessions, brand, platform, self_id=None):
    n = 1 + sum(1 for s in sessions or [] if s["id"] != self_id and (s.get("brand") or "") == (brand or "")
                and (s.get("platform") or "") == (platform or ""))
    return F.default_title(brand, platform, n)


def result(sess):
    """Ket qua tra ve trang sau khi luu: phien + trang thai nhap + dien giai + canh bao TikTok."""
    pub, view = P.published_view(sess), P.draft_view(sess)
    return {"session": sess, "state": P.draft_state(sess), "diff": P.diff_texts(pub, view),
            "warning": F.tiktok_warning(view.get("platform"), view.get("tiktok_username")),
            "unpublished": P.is_new(sess)}
