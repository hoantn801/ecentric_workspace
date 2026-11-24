# Copyright (c) 2026, eCentric and contributors
"""Kiem cau hinh phien truoc khi luu: ma phien, gio, host trung, mic trung, mic phai co tren may da chon.

Phien do may tao (QC ngoai lich, flags.from_machine) chi kiem mic trung - mic do chinh may vua bao.
Phien theo phong live chua gan may: mic lay tu may dang khai phong do (chua may nao thi chua kiem)."""
from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.rules import SESSION_ID_RE
from ecentric_workspace.host_qc.exceptions import InvalidInput
from ecentric_workspace.host_qc.repositories.machine_repository import MachineRepository
from ecentric_workspace.host_qc.utils.time import to_dt


class ValidateSessionService:
    def __init__(self, machines=None):
        self.machines = machines or MachineRepository()

    def execute(self, doc):
        sid = (doc.session_id or "").strip()
        if not SESSION_ID_RE.match(sid):
            raise InvalidInput(M.BAD_SESSION_ID)
        doc.session_id = sid
        start, end = to_dt(doc.planned_start), to_dt(doc.planned_end)
        if start and end and end < start:
            raise InvalidInput(M.END_BEFORE_START)
        if not doc.machine and not doc.get("live_room"):
            raise InvalidInput(M.SESSION_NEEDS_TARGET)
        self._hosts(doc)

    def _hosts(self, doc):
        seen_host, seen_mic = set(), set()
        known, machine = None, False             # False = chua tra may
        for h in doc.get("hosts") or []:
            hid = (h.host_id or "").strip()
            if hid in seen_host:
                raise InvalidInput(M.HOST_DUPLICATE % hid)
            seen_host.add(hid)
            mic = (h.mic_device or "").strip()
            if not mic:
                continue
            if mic in seen_mic:
                raise InvalidInput(M.MIC_DUPLICATE % mic)
            seen_mic.add(mic)
            if getattr(doc.flags, "from_machine", False):
                continue
            if machine is False:
                machine = self._machine(doc)
                known = {r["device_name"] for r in self.machines.mics(machine)} if machine else None
            if known is not None and mic not in known:
                raise InvalidInput(M.MIC_NOT_ON_MACHINE % (mic, machine))

    def _machine(self, doc):
        if doc.machine:
            return doc.machine
        room = doc.get("live_room")
        found = self.machines.in_room(room) if room else []
        return found[0] if found else None
