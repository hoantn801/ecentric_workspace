# Copyright (c) 2026, eCentric and contributors
"""Gui Teams (chay nen): may moi cho duyet / nghi nhan ban - moi may 1 lan (co notified_* da dat luc ghi may).
Moi chu tu may gui len deu escape truoc khi dua vao the. Ket qua gui ghi vao nhat ky (khong ghi URL webhook)."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live import license_constants as L
from ecentric_workspace.ai_tools.features.ai_live.application import _license_deps as D
from ecentric_workspace.ai_tools.features.ai_live.domain import license_rules as R


class LicenseNotifyService:
    def __init__(self, settings=None, machines=None, dists=None, events=None, sender=None, site_url=None):
        self.settings, self.machines = settings or D.settings(), machines or D.machines()
        self.dists, self.events = dists or D.dists(), events or D.events()
        if sender is None:
            from ecentric_workspace.ai_tools.features.ai_live.infrastructure import alert_channels as sender
        if site_url is None:
            def site_url(path):
                import frappe
                return frappe.utils.get_url(path)
        self.sender, self.site_url = sender, site_url

    def execute(self, kind, name):
        m = self.machines.get(name)
        if not m:
            return False
        url = self.settings.teams_webhook()
        if not url:
            self.events.add(name, "", L.Kind.NOTIFY, "", "system", "Chưa cấu hình Teams (teams_webhook) – không gửi tin")
            return False
        title, text = self._compose(kind, m)
        ok, code = self.sender.send_teams_url(url, self.settings.get().get("teams_format"),
                                              C.Level.WARN if kind == "pending" else C.Level.CRIT, title, text,
                                              self.site_url(L.DEEP_LINK % name), L.Msg.TEAMS_BUTTON)
        self.events.add(name, "", L.Kind.NOTIFY, "", "system",
                        "Teams %s: %s" % ("chờ duyệt" if kind == "pending" else "nghi nhân bản", "đã gửi" if ok else code))
        return ok

    def _compose(self, kind, m):
        host = R.md_escape(m.get("label") or m.get("host") or m["name"])
        if kind == "clone":
            return L.Msg.TEAMS_CLONE_TITLE, L.Msg.TEAMS_CLONE % (host, m["name"], R.md_escape(m.get("clone_host")))
        apps = ", ".join(L.PRODUCT_LABEL.get(i["product"], i["product"]) for i in m.get("installs") or []) or "?"
        dist = (self.dists.get(m.get("source_dist")) or {}) if m.get("source_dist") else {}
        dist_label = R.md_escape(dist.get("label") or dist.get("name", "")[:8]) if dist else L.Msg.NO_DIST
        src = ""
        if m.get("parent_machine"):
            src = R.md_escape(self.machines.labels([m["parent_machine"]]).get(m["parent_machine"]) or "")
            src = "%s (%s)" % (src, m["parent_machine"]) if src else m["parent_machine"]
        return L.Msg.TEAMS_TITLE, L.Msg.TEAMS_PENDING % (host, apps, dist_label, src or L.Msg.NO_SOURCE,
                                                          R.md_escape(m.get("reason")))
