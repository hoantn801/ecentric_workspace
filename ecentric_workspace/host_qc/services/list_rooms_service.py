# Copyright (c) 2026, eCentric and contributors
"""list_rooms (spec muc 7.6): phong live dang hoat dong cho o "Phong live" trong Cai dat app.

Phong khong gan brand co dinh (brand theo tung phien), nen platform / shop lay tu phien dang chay cua
phong, khong co thi phien Ready gan nhat trong [now-60', now+12h]; khong co phien -> chuoi rong."""
import datetime as _dt

from ecentric_workspace.host_qc.constants.rules import NEXT_SESSION_BEFORE_MIN
from ecentric_workspace.host_qc.constants.statuses import SessionStatus
from ecentric_workspace.host_qc.repositories.room_repository import RoomRepository
from ecentric_workspace.host_qc.repositories.session_repository import SessionRepository
from ecentric_workspace.host_qc.utils.time import now

LOOKAHEAD_H = 12


class ListRoomsService:
    def __init__(self, rooms=None, sessions=None, clock=now):
        self.rooms = rooms or RoomRepository()
        self.sessions = sessions or SessionRepository()
        self.clock = clock

    def execute(self):
        rooms = self.rooms.active()
        at = self.clock()
        current = self._current([r["room_id"] for r in rooms], at)
        out = []
        for r in rooms:
            s = current.get(r["room_id"]) or {}
            out.append({"id": r["room_id"], "name": r.get("room_name") or r["room_id"],
                        "platform": s.get("platform") or "", "shop": s.get("tiktok_username") or s.get("brand") or ""})
        return out

    def _current(self, room_ids, at):
        if not room_ids:
            return {}
        rows = self.sessions.for_rooms(room_ids, (SessionStatus.RUNNING.value, SessionStatus.READY.value),
                                       at - _dt.timedelta(minutes=NEXT_SESSION_BEFORE_MIN),
                                       at + _dt.timedelta(hours=LOOKAHEAD_H))
        best = {}
        for s in rows:                                   # da sap planned_start tang dan
            old = best.get(s["live_room"])
            if old is None or (s["status"] == SessionStatus.RUNNING.value and old["status"] != s["status"]):
                best[s["live_room"]] = s
        return best
