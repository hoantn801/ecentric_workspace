# Copyright (c) 2026, eCentric and contributors
"""heartbeat: cap nhat trang thai may + bang "Micro tren may"; tra rules_version de app biet tai lai nguong.

Mic: them dong moi, cap nhat last_seen dong cu; KHONG xoa dong cu (mic rut ra van giu de biet)."""
from ecentric_workspace.host_qc.constants.rules import MAX_MICS
from ecentric_workspace.host_qc.repositories.machine_repository import MachineRepository
from ecentric_workspace.host_qc.repositories.settings_repository import SettingsRepository
from ecentric_workspace.host_qc.utils.time import iso, now


def _int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


class RecordHeartbeatService:
    def __init__(self, machines=None, settings=None, clock=now):
        self.machines = machines or MachineRepository()
        self.settings = settings or SettingsRepository()
        self.clock = clock

    def execute(self, machine, payload):
        at = self.clock()
        mid = machine["name"]
        obs = payload.get("obs") if isinstance(payload.get("obs"), dict) else {}
        self.machines.update_heartbeat(mid, {
            "last_seen": at, "app_version": str(payload.get("app_version") or "")[:40],
            "state": str(payload.get("state") or "")[:40], "load_level": _int(payload.get("load_level")),
            "obs_connected": 1 if obs.get("connected") else 0, "obs_streaming": 1 if obs.get("streaming") else 0,
            "obs_skipped_pct": float(obs.get("skipped_pct") or 0)})
        if isinstance(payload.get("audio_inputs"), list):
            self._mics(mid, payload["audio_inputs"][:MAX_MICS], at)
        return {"rules_version": self.settings.get().get("rules_version") or "", "server_time": iso(at)}

    def _mics(self, mid, items, at):
        rows = self.machines.mics(mid)
        known = {(r["device_name"], r.get("hostapi") or ""): r for r in rows}
        idx = max([r.get("idx") or 0 for r in rows] or [0])
        for it in items:
            if not isinstance(it, dict) or not str(it.get("name") or "").strip():
                continue
            key = (str(it["name"]).strip()[:140], str(it.get("hostapi") or "").strip()[:60])
            ch = _int(it.get("channels"))
            if key in known:
                self.machines.touch_mic(known[key]["name"], ch, at)
            elif len(known) < MAX_MICS:
                idx += 1
                self.machines.add_mic(mid, idx, key[0], key[1], ch, at)
                known[key] = {"name": None}
