# Copyright (c) 2026, eCentric and contributors
"""Quet moi phut: live nao mat tin hieu trong gio live (mat dien / mat mang / app tat) -> bao do;
canh bao vang keo dai qua N phut -> nang len do; co tin hieu lai -> bao. Gui Teams + Zalo, chong lap.
Job goi: targets() -> check(row) tung live (loi 1 live khong lam hong ca lan quet) -> purge()."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R


class MonitorTickService:
    def __init__(self, health=None, samples=None, alerts=None, settings=None, sender=None, clock=None, link=""):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        self.health = health or D.health()
        self.samples = samples or D.samples()
        self.alerts = alerts or D.alerts()
        self.settings = settings or D.settings()
        self.sender = sender or D.sender()
        self.clock = clock or R.now_ts
        self.link = link
        self.cfg = None

    def targets(self):
        """Danh sach live can xet ([] neu tat bao dong trong cai dat)."""
        self.cfg = self.settings.get(with_secrets=True)
        return self.health.all() if self.cfg.get("enabled") else []

    def check(self, row):
        """Xet 1 live; tra so tin da gui."""
        cfg, now = self.cfg, self.clock()
        ev = R.evaluate(row, now, cfg)
        if ev["level"] == C.Level.OFF:
            if not row.get("offline_alerted"):
                self.health.set_flag(row["key"], True)
            return self._send(row, "offline", C.Level.CRIT, ev["reasons"][0]["text"], now)
        sent = 0
        if row.get("offline_alerted") and ev["stale_s"] <= cfg["dead_man_min"] * 60:
            self.health.set_flag(row["key"], False)
            sent += self._send(row, "back", C.Level.INFO, C.MonMsg.BACK, now, dedupe=False)
        for r in ev["reasons"]:
            if r.get("escalated"):
                text = "%s (%s)" % (r["text"], C.MonMsg.ESCALATED % cfg["escalate_min"])
                sent += self._send(row, r["code"] + ".esc", C.Level.CRIT, text, now)
            elif r["level"] == C.Level.CRIT and (r.get("forward") or r.get("src") == "server"):
                sent += self._send(row, r["code"], C.Level.CRIT, r["text"], now)
        return sent

    def purge(self):
        now = self.clock()
        self.samples.purge(now - C.SAMPLE_KEEP_HOURS * 3600)
        self.alerts.purge(now - C.ALERT_KEEP_DAYS * 86400)

    def _send(self, row, code, level, text, now, dedupe=True):
        akey = "%s|%s" % (row["key"], code)
        if dedupe and not R.should_send(self.alerts.last_sent(akey), level, now, self.cfg["dedupe_min"]):
            return 0
        title, body = R.format_alert(level, row, text)
        t_ok, t_code = self.sender.send_teams(self.cfg, level, title, body, self.link)
        z_ok, z_code = self.sender.send_zalo(self.cfg, title, body, self.link)
        self.alerts.insert({"alert_key": akey, "health_key": row["key"], "machine": row.get("machine"),
                            "live": row.get("live"), "brand": row.get("brand") or "", "level": level, "code": code,
                            "text": body, "sent_ts": now, "teams_result": t_code, "zalo_result": z_code})
        return 1
