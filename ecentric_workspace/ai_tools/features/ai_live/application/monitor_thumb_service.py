# Copyright (c) 2026, eCentric and contributors
"""Anh nho cua 1 live (OBS hoac dien thoai) cho man Giam sat, tra data URI (chi nguoi co quyen xem)."""
import base64
import re

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common

_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]{3,90}$")


class MonitorThumbService:
    def __init__(self, thumbs=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        self.thumbs = thumbs or D.thumbs()

    def execute(self, roles, key, kind):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        key, kind = str(key or ""), str(kind or "obs")
        if not _KEY_RE.match(key) or kind not in C.THUMB_KINDS:
            raise C.AiLiveError(C.MonMsg.NO_THUMB)
        got = self.thumbs.read(key, kind)
        if not got:
            raise C.AiLiveError(C.MonMsg.NO_THUMB)
        data, mime = got
        return {"data_uri": "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))}
