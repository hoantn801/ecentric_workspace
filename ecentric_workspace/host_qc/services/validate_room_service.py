# Copyright (c) 2026, eCentric and contributors
"""Kiem ma phong live: chu khong dau, so, khoang trang, . _ - (app luu nguyen ma nay)."""
from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.rules import ROOM_ID_RE
from ecentric_workspace.host_qc.exceptions import InvalidInput


class ValidateRoomService:
    def execute(self, doc):
        rid = (doc.room_id or "").strip()
        if not ROOM_ID_RE.match(rid):
            raise InvalidInput(M.BAD_ROOM_ID)
        doc.room_id = rid
