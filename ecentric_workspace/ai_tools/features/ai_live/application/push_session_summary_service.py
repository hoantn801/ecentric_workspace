# Copyright (c) 2026, eCentric and contributors
"""App gui tong ket khi 1 phien live ket thuc (thoi luong, comment, da tra loi, da chao, FAQ, AI, chi phi, bao dong).
Goi lai cung ma phien -> ghi de (app gui lai khi mat mang khong tao dong trung)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S


class PushSessionSummaryService:
    def __init__(self, machines=None, logs=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.machines = machines or DS.machines_all()
        self.logs = logs or DS.logs()
        self.clock = clock or R.now_ts

    def execute(self, user, machine, live, brand, summary):
        m = _common.require_machine(self.machines, user, machine)
        return self.save(m, live, brand, summary)

    def save(self, m, live, brand, summary):
        """Dung chung cho push_heartbeat (lives[].session_summary)."""
        live, brand = str(live or ""), str(brand or "")
        if not C.LIVE_RE.match(live):
            raise C.AiLiveError(C.MonMsg.BAD_HB % "mã live")
        if brand and brand not in _common.machine_brands(m):
            raise C.AiLiveError(C.Msg.BRAND_NOT_ALLOWED % brand)
        raw = _common.parse_json(summary, "tổng kết phiên") if isinstance(summary, str) else summary
        row = dict(S.sanitize_summary(raw, self.clock()), live=live, machine=m["machine_code"], brand=brand)
        key = "%s__%s" % (R.key_of(m["machine_code"], live), row["session"])
        return {"id": self.logs.upsert(key[:140], row), "session": row["session"]}
