# Copyright (c) 2026, eCentric and contributors
"""Kiem cau hinh phien truoc khi luu: ma phien, gio, host trung, mic trung, mic phai co tren may da chon.

Phien do may tao (QC ngoai lich, flags.from_machine) chi kiem mic trung - mic do chinh may vua bao."""
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
        self._hosts(doc)

    def _hosts(self, doc):
        seen_host, seen_mic = set(), set()
        known = None
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
            if getattr(doc.flags, "from_machine", False) or not doc.machine:
                continue
            if known is None:
                known = {r["device_name"] for r in self.machines.mics(doc.machine)}
            if mic not in known:
                raise InvalidInput(M.MIC_NOT_ON_MACHINE % (mic, doc.machine))
