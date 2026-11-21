# Copyright (c) 2026, eCentric and contributors
"""gbs_monitor: canh bao khi IP doi / boxme chan - khong can bench, khong mang."""

import unittest

from ecentric_workspace.gbs_monitor import domain
from ecentric_workspace.gbs_monitor.application.check_service import CheckBoxmeAccessService


class DomainTest(unittest.TestCase):
    def test_classify(self):
        self.assertEqual([domain.classify(c) for c in (200, 401, 403, 0, 502, 504)],
                         ["ok", "auth_fail", "auth_fail", "down", "down", "down"])

    def test_ip_change_alerts_even_if_boxme_still_ok(self):
        self.assertEqual(domain.decide("13.228.14.29", "ok", "1.2.3.4", "ok"), [("ip_changed", "1.2.3.4")])

    def test_unknown_ip_never_triggers_change(self):
        self.assertEqual(domain.decide("13.228.14.29", "ok", "", "ok"), [])
        self.assertEqual(domain.decide("13.228.14.29", "ok", "<html>", "ok"), [])

    def test_auth_fail_and_recovery(self):
        self.assertEqual(domain.decide("1.1.1.1", "ok", "1.1.1.1", "auth_fail"), [("auth_fail", "1.1.1.1")])
        self.assertEqual(domain.decide("1.1.1.1", "auth_fail", "1.1.1.1", "ok"), [("recovered", "1.1.1.1")])

    def test_down_is_silent(self):
        self.assertEqual(domain.decide("1.1.1.1", "ok", "1.1.1.1", "down"), [])


class FakeProbe:
    def __init__(self, ip, code):
        self.ip, self.code = ip, code

    def egress_ip(self):
        return self.ip

    def boxme_whoami(self):
        return self.code, "commercial@ecentric.vn" if self.code == 200 else ""


class FakeState:
    def __init__(self, ip="13.228.14.29", status="ok", rcpts=("a@x", "b@x")):
        self.data = {"ip": ip, "status": status, "checked": ""}
        self.rcpts = list(rcpts)

    def load(self):
        return dict(self.data)

    def save(self, ip, status, now):
        self.data = {"ip": ip, "status": status, "checked": now}

    def recipients(self):
        return self.rcpts


def make(probe, state):
    sent = []
    svc = CheckBoxmeAccessService(probe=probe, state=state, notify=lambda *a, **k: sent.append((a, k)),
                                  now=lambda: "2026-11-19 10:00:00", today=lambda: "2026-11-19")
    return svc, sent


class ServiceTest(unittest.TestCase):
    def test_all_good_sends_nothing_and_records(self):
        st = FakeState()
        svc, sent = make(FakeProbe("13.228.14.29", 200), st)
        res = svc.execute()
        self.assertEqual((sent, res["status"], st.data["ip"]), ([], "ok", "13.228.14.29"))

    def test_ip_change_notifies_every_recipient_with_new_ip(self):
        st = FakeState()
        svc, sent = make(FakeProbe("5.6.7.8", 200), st)
        svc.execute()
        self.assertEqual(len(sent), 2)
        args, kw = sent[0]
        self.assertEqual(args[0], "system_critical")
        self.assertIn("5.6.7.8", args[3])
        self.assertEqual(kw["severity"], "urgent")
        self.assertEqual(st.data["ip"], "5.6.7.8")

    def test_auth_fail_dedupe_key_is_per_day(self):
        svc, sent = make(FakeProbe("13.228.14.29", 403), FakeState())
        svc.execute()
        self.assertTrue(sent[0][1]["dedupe_key"].startswith("gbs_monitor|auth_fail|13.228.14.29|2026-11-19|"))

    def test_down_keeps_previous_status(self):
        st = FakeState(status="auth_fail")
        svc, sent = make(FakeProbe("13.228.14.29", 0), st)
        svc.execute()
        self.assertEqual((sent, st.data["status"]), ([], "auth_fail"))

    def test_dry_run_sends_and_saves_nothing(self):
        st = FakeState()
        svc, sent = make(FakeProbe("9.9.9.9", 403), st)
        res = svc.execute(dry_run=True)
        self.assertEqual((sent, st.data["ip"]), ([], "13.228.14.29"))
        self.assertEqual(res["alerts"], ["ip_changed", "auth_fail"])


class ProbeTest(unittest.TestCase):
    def test_egress_ip_falls_back_to_text_service(self):
        from ecentric_workspace.gbs_monitor.infrastructure import probe

        class R:
            def __init__(self, code, text):
                self.status_code, self.text = code, text

            def json(self):
                import json
                return json.loads(self.text)

        class H:
            def get(self, url, timeout=None):
                return R(503, "") if "ipify" in url else R(200, "13.228.14.29\n")
        self.assertEqual(probe.egress_ip(http=H()), "13.228.14.29")


if __name__ == "__main__":
    unittest.main()
