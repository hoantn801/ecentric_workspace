# Copyright (c) 2026, eCentric and contributors
"""Danh sach "Micro tren may" cho o chon mic cua host tren form phien (kem co "khong thay tu <gio>")."""
import datetime as _dt

from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.roles import VIEW
from ecentric_workspace.host_qc.constants.rules import MIC_STALE_MIN
from ecentric_workspace.host_qc.exceptions import ForbiddenError
from ecentric_workspace.host_qc.repositories.machine_repository import MachineRepository
from ecentric_workspace.host_qc.utils.time import now, to_dt


class MachineMicsService:
    def __init__(self, machines=None, clock=now):
        self.machines = machines or MachineRepository()
        self.clock = clock

    def execute(self, roles, machine_id, room_id=None):
        if not set(roles or ()) & set(VIEW):
            raise ForbiddenError(M.NEED_VIEWER)
        if not machine_id and room_id:                  # phien theo phong: mic cua may dang khai phong
            found = self.machines.in_room(room_id)
            machine_id = found[0] if found else None
        limit = self.clock() - _dt.timedelta(minutes=MIC_STALE_MIN)
        out = []
        for r in self.machines.mics(machine_id) if machine_id else []:
            seen = to_dt(r.get("last_seen"))
            out.append({"device_name": r["device_name"], "hostapi": r.get("hostapi") or "",
                        "channels": r.get("channels") or 0,
                        "last_seen": seen.strftime("%d/%m %H:%M") if seen else "",
                        "stale": bool(seen and seen < limit)})
        return out
