# Copyright (c) 2026, eCentric and contributors
"""fix10g: man Dong bo cua Lich live - ban nhap cho phat hanh (thay doi, kiem tra, du kien giu gio cu), trang thai
nhan lich tung may, lan dang giu gio cu, nhat ky phat hanh (ca thay doi app gui ve)."""
from datetime import datetime

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import schedule_rules as P


class SyncOverviewService:
    def __init__(self, sessions=None, machines=None, schedule=None, publisher=None, clock=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.sessions = sessions or DS.sessions()
        self.machines = machines or DS.machines_all()
        self.schedule = schedule or DS.schedule()
        self.clock = clock or R.now_ts
        self._publisher = publisher

    def execute(self, roles):
        _common.require_role(roles, C.VIEW_ROLES, C.Msg.NEED_VIEW)
        now, cfg = self.clock(), self.schedule.settings()
        sessions = self.sessions.list()
        drafts = [s for s in sessions if s.get("draft")]
        afters = {s["id"]: P.draft_view(s) for s in drafts if P.draft_state(s) == C.DraftState.READY}
        holds, errors = self.publisher().plan(sessions, afters) if afters else ({}, [])
        err_by = {}
        for e in errors:
            err_by.setdefault(e["id"], []).append(e["error"])
        states = self.machines.sync_states()
        dead = C.DEAD_MAN_MIN * 60
        return {
            "version": cfg["version"], "lock_min": cfg["lock_min"], "refresh_on_publish": cfg["refresh_on_publish"],
            "last_published_by": cfg["last_published_by"], "last_published_at": cfg["last_published_at"],
            "drafts": [self._draft(s, holds.get(s["id"]), err_by.get(s["id"], [])) for s in drafts],
            "machines": [dict(code=m["machine_code"], label=m["label"], enabled=m["enabled"], app_version=m["hb_version"],
                              last_seen_ts=m["hb_last_seen_ts"], sync=P.machine_sync(m, sessions, now, dead),
                              lives=[x["live"] for x in m.get("hb_lives") or []]) for m in states],
            "holds": [{"id": s["id"], "title": s["title"], "machine": (s.get("prev") or {}).get("machine") or s["machine"],
                       "until": s["held_until_ts"], "why": s.get("held_why") or "", "why_text": C.HOLD_TEXT.get(s.get("held_why"), ""),
                       "diff": P.diff_texts(s["prev"], P.published_view(s))}
                      for s in sessions if s.get("prev") and float(s.get("held_until_ts") or 0) > now],
            "versions": [dict(v, source_text=C.PUB_SOURCE_TEXT.get(v["source"], v["source"]),
                              changes=[{k: c.get(k) for k in ("session", "title", "texts", "held_until", "held_why")}
                                       for c in v["changes"]]) for v in self.schedule.versions()],
            "server_time": now}

    def publisher(self):
        if self._publisher is None:
            from ecentric_workspace.ai_tools.features.ai_live.application.publish_schedule_service import PublishScheduleService
            self._publisher = PublishScheduleService(sessions=self.sessions, machines=self.machines, schedule=self.schedule,
                                                     clock=self.clock)
        return self._publisher

    @staticmethod
    def _draft(s, hold, errors):
        before, after = P.published_view(s), P.draft_view(s)
        st = P.draft_state(s)
        return {"id": s["id"], "title": s["title"], "brand": s["brand"], "machine_before": before["machine"],
                "machine_after": after["machine"], "state": st, "diff": P.diff_texts(before, after), "errors": errors,
                "hold_until": hold[0] if hold else 0, "hold_why": hold[1] if hold else "",
                "hold_text": (C.HOLD_TEXT.get(hold[1], "") + " · giữ tới " +
                              datetime.fromtimestamp(hold[0], R._VN).strftime("%H:%M")) if hold else "",
                "published_version": s.get("published_version") or 0, "base_version": s.get("draft_base_version") or 0,
                "by": s.get("draft_by") or "", "at": s.get("draft_at") or ""}
