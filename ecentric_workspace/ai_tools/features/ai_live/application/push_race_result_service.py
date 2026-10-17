# Copyright (c) 2026, eCentric and contributors
"""App gui ket qua 1 cuoc dua vit (W20) - goi lai cung ma cuoc dua = cap nhat (trang thai trao giai, anh).
Nhan rong tay: anh hong / brand chua giao chi bao lai trong data, khong tra loi (loi lam ket hop thu cua app)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import race_rules as RR


class PushRaceResultService:
    def __init__(self, machines=None, races=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.machines = machines or DS.machines_all()
        self.races = races or DS.races()
        self.clock = clock or R.now_ts

    def execute(self, user, machine, race, png_b64=None):
        m = _common.require_machine(self.machines, user, machine)
        raw = self._parse(race)
        r = RR.sanitize_race(raw, self.clock())
        if r["brand"] and r["brand"] not in _common.machine_brands(m):
            return {"ok": True, "saved": False, "id": r["id"], "why": C.Msg.BRAND_NOT_ALLOWED % r["brand"]}
        old = self.races.get(r["id"])
        if old and old["machine"] and old["machine"] != m["machine_code"]:
            raise C.AiLivePermission(C.RaceMsg.OTHER_MACHINE % r["id"])
        winners = RR.merge_winners((old or {}).get("winners"), r["winners"])
        name = self.races.upsert(r, winners, m["machine_code"])
        return {"ok": True, "saved": True, "id": name, "created": not old, "png": self._png(name, png_b64, old)}

    def _parse(self, race):
        return race if isinstance(race, dict) else _common.parse_json(race, "kết quả đua vịt")

    def _png(self, name, png_b64, old):
        if not png_b64:
            return "none"
        try:
            data, sha = RR.decode_png(png_b64)
        except C.AiLiveError:
            return "bad"
        if old and old.get("png_sha256") == sha and old.get("png_url"):
            return "same"
        self.races.save_png(name, data, sha)
        return "saved"
