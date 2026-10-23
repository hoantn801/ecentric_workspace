# Copyright (c) 2026, eCentric and contributors
"""Quet moi phut: live nao mat tin hieu trong gio live (mat dien / mat mang / app tat) -> bao do;
canh bao vang keo dai qua N phut -> nang len do; co tin hieu lai -> bao. Gui Teams + Zalo, chong lap.
Job goi: targets() -> check(row) tung live (loi 1 live khong lam hong ca lan quet) -> purge().
fix10h: bao dong app nho ERP gui ho (alerts[].forward = true, hop dong 11.2) thanh su co rieng: gui khi moi xuat hien,
KHAN nhac lai 5/15 phut toi khi xac nhan, leo thang sau 10 phut, "da on" khi ma bien mat (cho them 1 nhip)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application._alert_send import send_routed
from ecentric_workspace.ai_tools.features.ai_live.application._incident_desk import IncidentDesk
from ecentric_workspace.ai_tools.features.ai_live.domain import alert_routing as A
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import incident_rules as I
from ecentric_workspace.ai_tools.features.ai_live.domain import machine_watch_rules as W


class MonitorTickService:
    def __init__(self, health=None, samples=None, alerts=None, settings=None, sender=None, clock=None, link="",
                 machines=None, incidents=None, reports=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        self.health = health or D.health()
        self.samples = samples or D.samples()
        self.alerts = alerts or D.alerts()
        self.settings = settings or D.settings()
        self.sender = sender or D.sender()
        self.clock = clock or R.now_ts
        self.link = link
        self.machines = machines or D.machines()   # fix10f: ca may im lang -> bao theo may (watch_machines_job)
        self.incidents = incidents or D.incidents()
        self._reports = reports
        self.cfg, self.hb, self.fwd, self.desk = None, {}, {}, None

    def targets(self):
        """Danh sach live can xet ([] neu tat bao dong trong cai dat)."""
        self.cfg = self.settings.get(with_secrets=True)
        if not self.cfg.get("enabled"):
            return []
        self.hb = {m["machine_code"]: m for m in self.machines.heartbeats()}
        self.fwd = {}
        for inc in self.incidents.open_all(C.IncKind.FORWARD):
            self.fwd.setdefault((inc["machine"], inc["live"]), {})[inc["code"]] = inc
        self.desk = IncidentDesk(self.incidents, self.alerts, self.sender, self.cfg, self.link, self.clock)
        return self.health.all()

    def check(self, row):
        """Xet 1 live; tra so tin da gui."""
        cfg, now = self.cfg, self.clock()
        ev = R.evaluate(row, now, cfg)
        sent = self._forward(row, now)            # fix10h: truoc moi nhanh - live dung han cung dong su co gui ho
        if ev["level"] == C.Level.OFF:
            if W.covers_live_offline(self.hb.get(row.get("machine")), now, cfg["dead_man_min"]):
                return sent                       # fix10f: ca may im lang / tat app dung cach -> bao theo may
            if not row.get("offline_alerted"):
                self.health.set_flag(row["key"], True)
            return sent + self._send(row, "offline", C.Level.CRIT, ev["reasons"][0]["text"], now)
        if row.get("offline_alerted") and ev["stale_s"] <= cfg["dead_man_min"] * 60:
            self.health.set_flag(row["key"], False)
            sent += self._send(row, "back", C.Level.INFO, C.MonMsg.BACK, now, dedupe=False)
        for r in ev["reasons"]:
            if r.get("escalated") and r.get("src") == "server":   # fix10h: app tu gui -> khong gui trung; forward -> su co
                text = "%s (%s)" % (r["text"], C.MonMsg.ESCALATED % cfg["escalate_min"])
                sent += self._send(row, r["code"] + ".esc", C.Level.CRIT, text, now)
            elif r["level"] == C.Level.CRIT and r.get("src") == "server":   # forward: su co rieng (_forward)
                sent += self._send(row, r["code"], C.Level.CRIT, r["text"], now)
        return sent

    def purge(self, commands=None, logs=None):
        """commands / logs (fix10d): repo lenh cho app + lich su phien - job truyen vao; khong truyen thi bo qua."""
        now = self.clock()
        self.samples.purge(now - C.SAMPLE_KEEP_HOURS * 3600)
        self.alerts.purge(now - C.ALERT_KEEP_DAYS * 86400)
        if commands is not None:
            commands.purge(now - C.CMD_KEEP_DAYS * 86400)
        if logs is not None:
            logs.purge(now - C.LOG_KEEP_DAYS * 86400)
        self.incidents.purge(now - C.INC_KEEP_DAYS * 86400)          # fix10h
        if self._reports is not None:
            self._reports.purge(now - C.SLOT_REPORT_KEEP_DAYS * 86400)

    def _forward(self, row, now):
        """Bao dong app khong tu gui duoc -> ERP gui ho, theo doi bang su co (machine, live, ma)."""
        opened = self.fwd.get((row.get("machine"), row.get("live")), {})
        sent = 0
        if opened and now - float(row.get("last_seen_ts") or 0) > self.cfg["dead_man_min"] * 60 and \
                not W.covers_live_offline(self.hb.get(row.get("machine")), now, self.cfg["dead_man_min"]):
            for code, inc in opened.items():      # may van song ma live khong gui nua = live da dung -> dong su co
                title, body = R.format_alert(C.Level.INFO, row, C.IncMsg.FWD_STOPPED % inc["text"].split(" (app trên máy")[0])
                log = {"alert_key": "%s|fwd.%s.ok" % (row["key"], code), "health_key": row["key"], "machine": row.get("machine"),
                       "live": row.get("live"), "brand": row.get("brand") or "", "code": "fwd." + code}
                sent += self.desk.resolve(inc, C.Level.INFO, title, body, [row.get("brand")], log)
            self.fwd.pop((row.get("machine"), row.get("live")), None)
            return sent
        for act, code, a, inc in I.forward_plan(row, opened, now, self.cfg["dead_man_min"]):
            key = I.key_of(C.IncKind.FORWARD, row.get("machine"), row.get("live"), code)
            log = {"alert_key": "%s|fwd.%s" % (row["key"], code), "health_key": row["key"], "machine": row.get("machine"),
                   "live": row.get("live"), "brand": row.get("brand") or "", "code": "fwd." + code}
            brands = [row.get("brand")]
            if act == "new":
                title, body = R.format_alert(a["level"], row, C.IncMsg.FWD % a["text"])
                self.desk.open(C.IncKind.FORWARD, key, a["level"], title, body, brands, log,
                               opened_ts=min(now, float(a.get("since") or now)), code=code)
                sent += 1
                continue
            if act in ("still", "back_again"):
                if act == "back_again":
                    self.incidents.update(inc["name"], {"missing_since_ts": 0})
                aged = now - float(a.get("since") or now) >= self.cfg["escalate_min"] * 60     # vang keo dai -> KHAN
                if (a["level"] == C.Level.CRIT or aged) and inc["level"] != C.Level.CRIT:
                    self.incidents.update(inc["name"], {"level": C.Level.CRIT})      # vang -> do: nhac + leo thang
                    inc = dict(inc, level=C.Level.CRIT)
                if I.repeat_due(inc, now, self.cfg):
                    title, body = R.format_alert(C.Level.CRIT, row, C.IncMsg.FWD % a["text"] +
                                                 C.IncMsg.FWD_STILL % I.minutes_since(inc["opened_ts"], now))
                    sent += self.desk.remind(inc, title, body, brands, log)
                sent += self.desk.maybe_escalate(inc, brands, log)
            elif act == "missing":
                self.incidents.update(inc["name"], {"missing_since_ts": now})
            elif act == "ok":
                text = C.IncMsg.FWD_OK % (inc["text"].split(" (app trên máy")[0], I.minutes_since(inc["opened_ts"], now))
                title, body = R.format_alert(C.Level.INFO, row, text)
                sent += self.desk.resolve(inc, C.Level.INFO, title, body, brands, dict(log, alert_key=log["alert_key"] + ".ok"))
        return sent

    def _send(self, row, code, level, text, now, dedupe=True):
        akey = "%s|%s" % (row["key"], code)
        if dedupe and not R.should_send(self.alerts.last_sent(akey), level, now, self.cfg["dedupe_min"]):
            return 0
        title, body = R.format_alert(level, row, text)
        t_code, z_code = A.result_text(send_routed(self.sender, self.cfg, level, title, body, self.link, [row.get("brand")]))
        self.alerts.insert({"alert_key": akey, "health_key": row["key"], "machine": row.get("machine"),
                            "live": row.get("live"), "brand": row.get("brand") or "", "level": level, "code": code,
                            "text": body, "sent_ts": now, "teams_result": t_code, "zalo_result": z_code})
        return 1
