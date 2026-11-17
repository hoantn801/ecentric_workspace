# Copyright (c) 2026, eCentric and contributors
"""Trang Ban quyen - doc: 4 o so + cong tac + trang thai khoa (co / thieu, KHONG tra noi dung), bang may, goi, nhat ky."""
from ecentric_workspace.ai_tools.features.ai_live import license_constants as L
from ecentric_workspace.ai_tools.features.ai_live.application import _license_deps as D
from ecentric_workspace.ai_tools.features.ai_live.domain import license_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import license_view as V


class LicenseQueryService:
    def __init__(self, settings=None, machines=None, dists=None, events=None, clock=None, dt=None):
        self.settings, self.machines = settings or D.settings(), machines or D.machines()
        self.dists, self.events, self.clock = dists or D.dists(), events or D.events(), clock or D.clock()
        if dt is None:
            from ecentric_workspace.ai_tools.features.ai_live.repositories.license_machine_repository import dt_str as dt
        self.dt = dt

    def summary(self, roles):
        D.require_admin(roles)
        now = self.clock()
        st = self.settings.get()
        secrets = {p: R.secret_state(p, self.settings.secret(p)) for p in L.PRODUCTS}
        secrets["dist"] = "ok" if self.settings.dist_secret() else "missing"
        return {"counts": self.machines.counts(self.dt(now - L.RUNNING_HOURS * 3600)),
                "mode": {"enabled": st["enabled"], "log_only": st["log_only"], "killed": st["killed"]},
                "secrets": secrets, "teams": bool(self.settings.teams_webhook()),
                "office_ips": len(R.office_ips(st["office_ips"])), "now": self.dt(now)}

    def badge(self, roles):
        """Huy hieu menu "Ban quyen": nguoi khong co quyen -> 0 (khong 403: shell goi cho moi trang)."""
        if not set(roles or ()) & set(L.ADMIN_ROLES):
            return {"pending": 0}
        return {"pending": self.machines.counts(self.dt(self.clock()))["pending"]}

    def machines_page(self, roles, filters, page):
        D.require_admin(roles)
        now = self.clock()
        flt, q, order = V.machine_filters(filters, self.dt(now - L.RUNNING_HOURS * 3600),
                                          self.dt(now - L.STALE_DAYS * 86400))
        rows, more = self.machines.search(flt, q, order, V.page_no(page))
        dl = self.dists.labels([r.get("source_dist") for r in rows])
        ml = self.machines.labels([r.get("parent_machine") for r in rows])
        return {"rows": [V.machine_row(r, dl, ml) for r in rows], "more": more, "now": self.dt(now),
                "stale_days": L.STALE_DAYS}

    def dists_page(self, roles):
        D.require_admin(roles)
        rows = self.dists.all()
        pend = self.machines.count_pending_by_dist()
        ml = self.machines.labels([r.get("first_machine") for r in rows])
        out = [{"name": r["name"], "label": r.get("label") or "", "package_label": r.get("package_label") or "",
                "kind": r.get("kind") or "", "kind_label": L.DIST_KIND_LABEL.get(r.get("kind"), r.get("kind") or ""),
                "package": r.get("package") or "", "created_at": r.get("created_at") or "",
                "first_machine": {"name": r.get("first_machine") or "", "label": ml.get(r.get("first_machine"), "")},
                "first_seen": str(r.get("first_seen") or ""), "issued": int(r.get("issued_count") or 0),
                "pending": pend.get(r["name"], 0)} for r in rows]
        return {"rows": out, "no_dist_pending": pend.get("", 0)}

    def events_page(self, roles, filters, page):
        D.require_admin(roles)
        rows, more = self.events.search(V.event_filters(filters), V.page_no(page))
        ml = self.machines.labels([r.get("machine") for r in rows])
        out = [dict(V.event_row(r), machine_label=ml.get(r.get("machine"), "")) for r in rows]
        return {"rows": out, "more": more, "kinds": list(L.KINDS)}
