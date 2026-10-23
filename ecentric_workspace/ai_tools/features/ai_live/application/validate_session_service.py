# Copyright (c) 2026, eCentric and contributors
"""Kiem tra EC AI Live Session khi luu: ma phien, san, username TikTok, cong OBS, brand giao cho may,
khung gio (chuan hoa, khong trung nhau) va suc chua may phat (toi da N live cung luc)."""
from datetime import datetime

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S


class ValidateSessionService:
    def __init__(self, sessions=None, machines=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as D
        self.sessions = sessions or D.sessions()
        self.machines = machines or D.machines_all()
        self.clock = clock or R.now_ts

    def execute(self, doc):
        """doc: DocType (hoac doi tuong co thuoc tinh giong vay). Sua doc tai cho; loi -> AiLiveError."""
        sid = str(doc.live_id or doc.name or "").strip()
        if not C.SESSION_ID_RE.match(sid):                 # fix10g: khop app eC Live (khong dau cham, <= 32)
            raise C.AiLiveError(C.ContractMsg.BAD_SESSION_ID)
        doc.live_id = sid
        if doc.platform not in C.PLATFORMS:
            raise C.AiLiveError(C.SessMsg.BAD_PLATFORM)
        self._tiktok(doc)
        self._watch(doc)
        if (doc.mode or "") not in ("",) + C.MODES:
            raise C.AiLiveError(C.Msg.BAD_MODE)
        slots = S.norm_slots([{"days": r.days, "date": str(r.on_date or "")[:10] or None, "start": r.slot_start,
                               "end": r.slot_end} for r in (doc.slots or [])])
        for row, s in zip(doc.slots or [], slots):
            row.days = ",".join(str(d) for d in s["days"]) if not s["date"] else ""
            row.slot_start, row.slot_end = s["start"], s["end"]
        today = datetime.fromtimestamp(self.clock(), R._VN).date()
        clash = S.self_overlap(slots, today)
        if clash:
            raise C.AiLiveError(C.SessMsg.SLOT_OVERLAP % (clash[1], clash[0]))
        publishing = bool(getattr(getattr(doc, "flags", None), "ec_publish", False))
        if doc.machine and not publishing:      # fix10g: phat hanh lich da kiem suc chua / cong OBS tren ca bo
            self._machine(doc, sid, slots, today)
        return doc

    def _tiktok(self, doc):
        u = str(doc.tiktok_username or "").strip().lstrip("@")
        if doc.platform == "TikTok" and not u:
            raise C.AiLiveError(C.SessMsg.NEED_TIKTOK)
        if u and not C.TIKTOK_USER_RE.match(u):
            raise C.AiLiveError(C.SessMsg.BAD_TIKTOK % u)
        doc.tiktok_username = u

    def _watch(self, doc):
        url, serial = str(doc.watch_url or "").strip(), str(doc.phone_serial or "").strip()
        if url and not C.WATCH_URL_RE.match(url):
            raise C.AiLiveError(C.SessMsg.BAD_URL)
        if serial and not C.PHONE_SERIAL_RE.match(serial):
            raise C.AiLiveError(C.SessMsg.BAD_SERIAL)
        doc.watch_url, doc.phone_serial = url, serial

    def _machine(self, doc, sid, slots, today):
        m = self.machines.get(doc.machine)
        if not m:
            raise C.AiLiveError(C.SessMsg.NO_MACHINE)
        if doc.brand and doc.brand not in _common.machine_brands(m):
            raise C.AiLiveError(C.SessMsg.BRAND_OFF % (doc.brand, m["machine_code"]))
        others = [s for s in self.sessions.by_machine(m["machine_code"]) if s["id"] != sid]
        port = int(doc.obs_port or 0)
        if port and not (C.OBS_PORT_RANGE[0] <= port <= C.OBS_PORT_RANGE[1]):
            raise C.AiLiveError(C.SessMsg.BAD_PORT)
        taken = next((s for s in others if port and s["obs_port"] == port), None)
        if taken:
            raise C.AiLiveError(C.SessMsg.PORT_TAKEN % (port, taken["id"]))
        if not int(doc.enabled or 0):
            return
        group = [{"id": sid, "slots": slots}] + [{"id": s["id"], "slots": s["slots"]} for s in others if s["enabled"]]
        bad = [c for c in S.capacity_conflicts(group, m["max_lives"], today) if sid in c["ids"]]
        if bad:
            when = datetime.fromtimestamp(bad[0]["start"], R._VN).strftime("%d/%m %H:%M")
            raise C.AiLiveError(C.SessMsg.CAPACITY % (m["machine_code"], m["max_lives"], when,
                                                      ", ".join(i for i in bad[0]["ids"] if i != sid)))
