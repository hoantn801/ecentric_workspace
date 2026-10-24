# Copyright (c) 2026, eCentric and contributors
"""Ban truc su co (fix10h) - dung chung cho quet may im lang va quet tung live: mo su co + gui tin, nhac lai,
dong su co + bao "co lai / da on", leo thang khi KHAN chua ai xac nhan. Moi tin gui deu ghi EC AI Live Alert
(lich su) nhu truoc; su co (EC AI Live Incident) giu trang thai xac nhan."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application._alert_send import send_routed
from ecentric_workspace.ai_tools.features.ai_live.domain import alert_routing as A
from ecentric_workspace.ai_tools.features.ai_live.domain import incident_rules as I


class IncidentDesk:
    def __init__(self, incidents, alerts, sender, cfg, link, clock):
        self.incidents, self.alerts, self.sender = incidents, alerts, sender
        self.cfg, self.link, self.clock = cfg, link, clock

    def send(self, level, title, text, brands, log, escalation=False):
        """Gui ra kenh + ghi lich su. log: {alert_key, health_key, machine, live, brand, code}."""
        t_code, z_code = A.result_text(send_routed(self.sender, self.cfg, level, title, text, self.link, brands,
                                                   escalation=escalation))
        self.alerts.insert(dict(log, level=level, text=text, sent_ts=self.clock(), teams_result=t_code, zalo_result=z_code))
        return 1

    def open(self, kind, key, level, title, text, brands, log, opened_ts=None, **extra):
        now = self.clock()
        self.send(level, title, text, brands, log)
        row = dict({"incident_key": key, "kind": kind, "status": C.IncStatus.OPEN, "level": level, "title": title[:140],
                    "text": text, "opened_ts": opened_ts or now, "first_sent_ts": now, "last_sent_ts": now, "sent_count": 1,
                    "machine": log.get("machine") or "", "live": log.get("live") or "", "brand": log.get("brand") or "",
                    "code": log.get("code") or ""}, **extra)
        return self.incidents.insert(row)

    def remind(self, inc, title, text, brands, log):
        """Nhac lai: bo qua neu da xac nhan (tra 0)."""
        if inc and inc.get("status") == C.IncStatus.ACKED:
            return 0
        self.send(inc["level"] if inc else C.Level.CRIT, title, text, brands, log)
        if inc:
            self.incidents.update(inc["name"], {"last_sent_ts": self.clock(), "sent_count": inc["sent_count"] + 1,
                                                "text": text})
        return 1

    def resolve(self, inc, level, title, text, brands, log):
        """Dong su co + gui tin co lai / da on (ca khi da xac nhan). Kem ghi chu cua nguoi xac nhan."""
        msg = text + (I.ack_suffix(inc) if inc else "")
        # da leo thang -> nhom quan ly cung nhan tin "co lai / da on"
        self.send(level, title, msg, brands, log, escalation="both" if inc and float(inc.get("escalated_ts") or 0) else False)
        if inc:
            self.incidents.update(inc["name"], {"status": C.IncStatus.DONE, "resolved_ts": self.clock(), "resolve_text": msg})
        return 1

    def maybe_escalate(self, inc, brands, log):
        now = self.clock()
        if not inc or not I.escalate_due(inc, now, self.cfg):
            return 0
        mins = int(self.cfg.get("incident_escalate_min") or C.INC_ESCALATE_MIN)
        self.send(C.Level.CRIT, C.IncMsg.ESC_TITLE % inc["title"], C.IncMsg.ESC % (inc["text"], mins), brands,
                  dict(log, alert_key=log["alert_key"] + ".esc", code=(log.get("code") or "") + ".esc"), escalation=True)
        self.incidents.update(inc["name"], {"escalated_ts": now})
        return 1
