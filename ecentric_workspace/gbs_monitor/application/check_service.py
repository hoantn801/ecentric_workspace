# Copyright (c) 2026, eCentric and contributors
"""Use-case: kiem 1 lan - do IP, goi thu boxme, so voi lan truoc, bao neu can."""

from ecentric_workspace.gbs_monitor import domain


class CheckBoxmeAccessService:
    def __init__(self, probe=None, state=None, notify=None, now=None, today=None):
        if probe is None:
            from ecentric_workspace.gbs_monitor.infrastructure import probe
        if state is None:
            from ecentric_workspace.gbs_monitor.infrastructure import state
        if notify is None or now is None or today is None:
            import frappe
            from ecentric_workspace.notification_center.events import publish_notification_event
            notify = notify or publish_notification_event
            now = now or frappe.utils.now
            today = today or frappe.utils.today
        self.probe, self.state, self.notify, self.now, self.today = probe, state, notify, now, today

    def execute(self, dry_run=False):
        prev = self.state.load()
        ip = self.probe.egress_ip()
        code, user = self.probe.boxme_whoami()
        status = domain.classify(code)
        alerts = domain.decide(prev["ip"], prev["status"], ip, status)
        result = {"ip": ip, "prev_ip": prev["ip"], "http": code, "boxme_user": user,
                  "status": status, "alerts": [a[0] for a in alerts], "sent": 0}
        if dry_run:
            return result
        for kind, suffix in alerts:
            title, msg = domain.message(kind, prev["ip"], ip, code, user)
            key = "gbs_monitor|%s|%s" % (kind, suffix)
            if kind == "auth_fail":
                key += "|" + str(self.today())
            for rcpt in self.state.recipients():
                self.notify("system_critical", rcpt, title, msg, severity="urgent",
                            dedupe_key=key + "|" + rcpt, from_user="Administrator")
                result["sent"] += 1
        # 'down' giu trang thai cu de lan sau van so dung voi lan ok/auth_fail gan nhat.
        self.state.save(ip or prev["ip"], status if status != "down" else prev["status"], self.now())
        return result
