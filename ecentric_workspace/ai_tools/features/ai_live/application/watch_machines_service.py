# Copyright (c) 2026, eCentric and contributors
"""W17 - quet moi phut: may dang co live (len song o nhip cuoi / trong khung phien ERP) ma im lang qua N phut
(mac dinh 3) -> bao KHAN Teams / Zalo, nhac lai 5 phut/lan (dem 01:00-07:00: 15 phut/lan); co nhip tim lai
-> bao lien lac lai (kem "khoi dong lai" neu boot_at moi). Tat app dung cach (state 'stopping') / khong co live
-> khong bao. Job goi: targets() -> check(may) tung may (loi 1 may khong lam hong ca lan quet).
fix10h: moi lan mat lien lac = 1 su co (EC AI Live Incident). Da xac nhan tren ERP -> dung nhac lai (van bao co lai);
KHAN chua ai xac nhan sau 10 phut -> gui them cho kenh leo thang."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application._incident_desk import IncidentDesk
from ecentric_workspace.ai_tools.features.ai_live.domain import alert_routing as A
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import incident_rules as I
from ecentric_workspace.ai_tools.features.ai_live.domain import machine_watch_rules as W


class WatchMachinesService:
    def __init__(self, machines=None, sessions=None, health=None, alerts=None, settings=None, sender=None,
                 clock=None, link="", incidents=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_session as DS
        self.machines = machines or D.machines()
        self.sessions = sessions or DS.sessions()
        self.health = health or D.health()
        self.alerts = alerts or D.alerts()
        self.settings = settings or D.settings()
        self.sender = sender or D.sender()
        self.clock = clock or R.now_ts
        self.link = link
        self.incidents = incidents or D.incidents()
        self.cfg, self._ctx, self.desk = None, None, None

    def targets(self):
        """May dang dung va da tung gui nhip tim ([] neu tat bao dong trong cai dat)."""
        self.cfg, self._ctx = self.settings.get(with_secrets=True), None
        self.desk = IncidentDesk(self.incidents, self.alerts, self.sender, self.cfg, self.link, self.clock)
        return self.machines.heartbeats() if self.cfg.get("enabled") else []

    def check(self, m):
        """Xet 1 may; tra so tin da gui."""
        now, code = self.clock(), m["machine_code"]
        d = W.decide(m, now, self.cfg, lambda: W.expected_lives(m, *self._context(), now=now))
        ikey = I.key_of(C.IncKind.SILENT, code)
        inc = self.incidents.open_by_key(ikey) if (d["action"] != C.WatchAction.NONE or float(m.get("watch_lost_ts") or 0)) else None
        brands = (d.get("brands") or m.get("watch_brands") or sorted(A.brand_set(m.get("brands"))))
        hkey = C.MACHINE_ALERT_KEY % code
        log = {"health_key": hkey, "machine": code, "live": "", "brand": ", ".join(brands)[:140]}
        sent = 0
        if d["action"] == C.WatchAction.LOST or (d["action"] == C.WatchAction.REMIND and not inc):
            self.machines.set_watch(code, d["vals"])
            self.desk.open(C.IncKind.SILENT, ikey, d["level"], d["title"], d["text"], brands,
                           dict(log, alert_key="%s|%s" % (hkey, C.WatchCode.OFFLINE), code=C.WatchCode.OFFLINE),
                           opened_ts=float(d["vals"].get("watch_lost_ts") or m.get("watch_lost_ts") or now))
            return 1
        if d["action"] == C.WatchAction.REMIND:
            sent = self.desk.remind(inc, d["title"], d["text"], brands,
                                    dict(log, alert_key="%s|%s" % (hkey, C.WatchCode.OFFLINE), code=C.WatchCode.OFFLINE))
            if sent:
                self.machines.set_watch(code, d["vals"])
        elif d["action"] == C.WatchAction.BACK:
            self.machines.set_watch(code, d["vals"])
            return self.desk.resolve(inc, d["level"], d["title"], d["text"], brands,
                                     dict(log, alert_key="%s|%s" % (hkey, C.WatchCode.BACK), code=C.WatchCode.BACK))
        return sent + self.desk.maybe_escalate(inc, brands, dict(log, alert_key="%s|%s" % (hkey, C.WatchCode.OFFLINE),
                                                                 code=C.WatchCode.OFFLINE))

    def _context(self):
        """Phien ERP dang bat + tin hieu tung live: nap 1 lan moi luot quet, chi khi co may im lang."""
        if self._ctx is None:
            self._ctx = (self.sessions.list({"enabled": 1}), self.health.all())
        return self._ctx
