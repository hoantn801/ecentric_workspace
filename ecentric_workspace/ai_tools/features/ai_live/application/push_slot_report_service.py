# Copyright (c) 2026, eCentric and contributors
"""App bao ke hoach vs thuc te tung khung gio (hop dong A8, fix10h): upsert theo (may, live, planned_start) - ghi de.
Khung hong bi bo rieng (khong lam hong ca lo - app bo ca lo neu nhan success:false). Nhan ca live khong co tren ERP
(danh dau "ngoai ke hoach ERP"). App gui toi 20 khung / lan; ERP nhan toi 100, thua bo qua va bao lai so luong."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import slot_report_rules as SR


class PushSlotReportService:
    def __init__(self, machines=None, reports=None, sessions=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.machines = machines or D.machines()
        self.reports = reports or D.slot_reports()
        self.sessions = sessions or DS.sessions()
        self.clock = clock or R.now_ts

    def execute(self, user, machine, slots):
        m = _common.require_machine(self.machines, user, machine)
        raw = _common.parse_json(slots, "khung giờ") if isinstance(slots, str) else slots
        if not isinstance(raw, list):
            raise C.AiLiveError(C.SlotMsg.BAD % "slots phải là mảng")
        now, saved, skipped, erp = self.clock(), [], [], {}
        for rec in raw[:C.MAX_SLOT_REPORTS]:
            try:
                row = SR.sanitize(rec, now)
            except C.AiLiveError as e:
                skipped.append({"live": str((rec or {}).get("live") or "")[:40] if isinstance(rec, dict) else "", "why": str(e)})
                continue
            if row["live"] not in erp:
                erp[row["live"]] = bool(self.sessions.get(row["live"]))
            row.update(machine=m["machine_code"], off_plan=0 if erp[row["live"]] else 1, received_ts=now)
            self.reports.upsert(SR.report_key(m["machine_code"], row["live"], row["planned_start_ts"]), row)
            saved.append(row["live"])
        return {"saved": len(saved), "skipped": skipped, "ignored": max(0, len(raw) - C.MAX_SLOT_REPORTS), "server_time": now}
