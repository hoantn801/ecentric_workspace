# Copyright (c) 2026, eCentric and contributors
"""fix10h - su co AI Live: may im lang thanh su co (xac nhan dung nhac lai, van bao co lai), leo thang KHAN chua
xac nhan sau 10 phut cho kenh quan ly, bao dong app nho ERP gui ho (forward: gui 1 lan, nhac 5/15 phut, "da on"
sau 1 nhip vang ma). Hop dong eC Live 1.0.21 muc 11.1 / 11.2, test T17 / T23. Chay ngoai Frappe."""
import unittest

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application.incidents_service import AckIncidentService, ListIncidentsService
from ecentric_workspace.ai_tools.features.ai_live.domain import alert_routing as A
from ecentric_workspace.ai_tools.tests.test_ai_live_machine_watch import NIGHT, T0, World
from ecentric_workspace.ai_tools.tests.test_ai_live_monitor import VIEW, live

ESC = [{"enabled": 1, "group_name": "Quản lý", "brands": "", "escalation_only": 1, "teams_enabled": 1,
        "teams_webhook_url": "https://boss"}]


def fwd(level="critical", code="esync_down", text="Mất kết nối eSync"):
    return [{"code": code, "level": level, "text": text, "forward": True}]


class TestSilentIncident(unittest.TestCase):
    def test_incident_ack_stops_reminders_but_back_still_sent(self):
        w = World(T0, incident_escalate_min=60)
        w.push()
        self.assertEqual(w.at(4).watch(), 1)
        inc = w.incidents.open_all()[0]
        self.assertEqual((inc["kind"], inc["status"], inc["level"], inc["sent_count"]), (C.IncKind.SILENT, "Open", "critical", 1))
        self.assertEqual(inc["opened_ts"], T0)                      # mo tu lan cuoi thay may
        with self.assertRaises(C.AiLiveError):                      # KHAN: bat buoc ghi chu
            AckIncidentService(w.incidents, w.clock).execute("truc@ec", VIEW, inc["name"], "")
        AckIncidentService(w.incidents, w.clock).execute("truc@ec", VIEW, inc["name"], "Đã gọi kỹ thuật")
        self.assertEqual(sum(w.at(1).watch() for _ in range(20)), 0)    # da xac nhan -> khong nhac
        w.push()
        self.assertEqual(w.at(0.5).watch(), 1)
        self.assertIn("đã liên lạc lại", w.last()["text"])
        self.assertIn("(Đã xác nhận: truc@ec – Đã gọi kỹ thuật.)", w.last()["text"])
        self.assertEqual(w.incidents.get(inc["name"])["status"], C.IncStatus.DONE)
        self.assertEqual(w.incidents.open_all(), [])

    def test_escalate_once_after_10_minutes_to_manager_group(self):
        w = World(T0, channels=ESC)
        w.push()
        w.at(4).watch()
        self.assertNotIn("https://boss", [s[2] for s in w.sender.sent])      # nhom leo thang khong nhan tin thuong
        n = len(w.sender.sent)
        self.assertEqual(sum(w.at(1).watch() for _ in range(10)), 3)         # nhac luc 5' + 10', leo thang 10' sau lan bao dau
        esc = [s for s in w.sender.sent[n:] if s[4].startswith("[LEO THANG]")]
        self.assertEqual(sorted(s[2] for s in esc if s[0] == "teams"), ["https://boss", "https://hook"])
        self.assertIn("chưa ai xác nhận sau 10 phút", esc[0][5])
        self.assertTrue(w.incidents.open_all()[0]["escalated_ts"])
        self.assertEqual(sum(1 for _ in range(10) if w.at(1).watch() and w.last()["code"].endswith(".esc")), 0)

    def test_escalation_counts_from_first_alert_not_last_heartbeat(self):
        w = World(T0, [], channels=ESC)
        w.push([live(state="idle", schedule=[])])
        w.sessions.rows.append({"id": "toi", "title": "Tối", "brand": "friso", "machine": "MAY01", "enabled": 1,
                                "slots": [{"days": [1, 2, 3, 4, 5, 6, 7], "date": None, "start": "21:00", "end": "23:00"}]})
        w.at(60).watch()                                              # 21:00 vao gio, may im tu 20:00 -> KHAN ngay
        self.assertEqual(w.incidents.open_all()[0]["opened_ts"], T0)
        self.assertEqual(sum(1 for _ in range(9) if w.at(1).watch() and w.last()["code"].endswith(".esc")), 0)

    def test_back_after_escalation_reaches_managers(self):
        w = World(T0, channels=ESC)
        w.push()
        w.at(4).watch()
        for _ in range(10):
            w.at(1).watch()
        n = len(w.sender.sent)
        w.push()
        w.at(0.5).watch()
        self.assertIn("https://boss", [s[2] for s in w.sender.sent[n:]])

    def test_night_repeat_15(self):                                  # T17 dem: 15 phut moi nhac
        w = World(NIGHT, incident_escalate_min=60)
        w.push([live(schedule=[])])
        w.at(3.2).watch()
        self.assertEqual([w.at(1).watch() for _ in range(15)].count(1), 1)


class TestForward(unittest.TestCase):
    def test_send_once_repeat_and_ok(self):                           # T23
        w = World(T0, incident_escalate_min=60)
        w.push([live(alerts=fwd())])
        self.assertEqual(w.tick(), 1)
        a = w.last()
        self.assertEqual((a["code"], a["level"]), ("fwd.esync_down", "critical"))
        self.assertIn("Mất kết nối eSync (app trên máy không tự gửi được, ERP gửi hộ).", a["text"])
        for _ in range(4):
            w.at(1).push([live(alerts=fwd())])
            self.assertEqual(w.tick(), 0)
        w.at(1).push([live(alerts=fwd())])
        self.assertEqual(w.tick(), 1)                                  # 5 phut nhac lai
        self.assertIn("Vẫn còn sau 5 phút.", w.last()["text"])
        w.at(0.5).push([live()])                                       # ma bien mat
        self.assertEqual(w.tick(), 0)                                  # cho them 1 nhip
        w.at(0.5).push([live()])
        self.assertEqual(w.at(0.6).tick(), 1)
        self.assertEqual(w.last()["text"], "Đã ổn: Mất kết nối eSync (sau 7 phút).")
        self.assertEqual(w.incidents.open_all(), [])

    def test_flapping_code_does_not_close(self):
        w = World(T0)
        w.push([live(alerts=fwd())])
        w.tick()
        w.at(0.5).push([live()])
        w.tick()
        w.at(0.5).push([live(alerts=fwd())])                           # lai co ma -> giu su co
        self.assertEqual(w.at(0.5).tick(), 0)
        self.assertEqual(len(w.incidents.open_all()), 1)
        self.assertEqual(w.incidents.open_all()[0]["missing_since_ts"], 0)

    def test_without_forward_flag_not_sent(self):
        w = World(T0)
        w.push([live(alerts=[{"code": "esync_down", "level": "critical", "text": "Mất eSync"}])])
        self.assertEqual(w.tick(), 0)                                  # app da tu gui -> ERP khong gui trung
        self.assertEqual(w.incidents.open_all(), [])

    def test_app_own_warn_not_escalated_by_erp(self):
        w = World(T0)
        own = [{"code": "cpu_high", "level": "warn", "text": "CPU 97%"}]
        for _ in range(7):
            w.at(1).push([live(alerts=own)])
            self.assertEqual(w.tick(), 0)                              # app tu gui -> ERP khong nang / gui trung

    def test_warn_raised_to_khan_after_5_minutes_then_escalates(self):
        w = World(T0, channels=ESC)
        w.push([live(alerts=fwd("warn", "cpu_high", "CPU 97%"))])
        self.assertEqual(w.tick(), 1)
        for _ in range(4):
            w.at(1).push([live(alerts=fwd("warn", "cpu_high", "CPU 97%"))])
            self.assertEqual(w.tick(), 0)                              # vang < 5 phut: khong nhac
        for _ in range(11):
            w.at(1).push([live(alerts=fwd("warn", "cpu_high", "CPU 97%"))])
            w.tick()
        codes = [r["code"] for r in w.alerts.rows]
        self.assertNotIn("cpu_high.esc", codes)                        # duong ".esc" cu khong gui trung
        self.assertEqual(codes.count("fwd.cpu_high"), 4)               # lan dau + nhac luc 5', 10', 15' (da thanh KHAN)
        self.assertIn("fwd.cpu_high.esc", codes)                       # KHAN chua xac nhan 10' sau lan bao dau
        self.assertEqual(w.incidents.open_all()[0]["level"], "critical")

    def test_ack_stops_forward_reminders(self):
        w = World(T0)
        w.push([live(alerts=fwd())])
        w.tick()
        AckIncidentService(w.incidents, w.clock).execute("a@ec", VIEW, w.incidents.open_all()[0]["name"], "đang xử lý")
        for _ in range(20):
            w.at(1).push([live(alerts=fwd())])
            self.assertEqual(w.tick(), 0)

    def test_forward_closes_when_live_stops_and_machine_alive(self):
        w = World(T0)
        w.push([live(alerts=fwd())])
        w.tick()
        for _ in range(3):
            w.at(1).push([live(live="L2", schedule=[])])              # may van gui nhip, L1 bien mat
        w.tick()
        self.assertEqual(w.incidents.open_all(C.IncKind.FORWARD), [])
        self.assertTrue(any("live đã dừng" in r["text"] for r in w.alerts.rows))

    def test_machine_silent_does_not_close_forward(self):
        w = World(T0)
        w.push([live(alerts=fwd())])
        w.tick()
        w.at(5)
        w.tick()
        self.assertEqual(len(w.incidents.open_all(C.IncKind.FORWARD)), 1)


class TestListAndRouting(unittest.TestCase):
    def test_list_counts_and_order(self):
        w = World(T0, incident_escalate_min=60)
        w.push([live(alerts=fwd("warn", "cpu_high", "CPU 97%"))])
        w.tick()
        w.at(4).watch()
        out = ListIncidentsService(w.incidents, w.clock).execute(VIEW, "open")
        self.assertEqual([r["kind"] for r in out["rows"]], [C.IncKind.SILENT, C.IncKind.FORWARD])   # KHAN truoc
        self.assertEqual(out["counts"], {"open": 2, "acked": 0, "done": 0})
        self.assertEqual(out["rows"][0]["status_text"], "Đang mở")
        with self.assertRaises(C.AiLiveError):
            ListIncidentsService(w.incidents, w.clock).execute(VIEW, "xx")
        with self.assertRaises(C.AiLivePermission):
            ListIncidentsService(w.incidents, w.clock).execute(["Employee"], "open")

    def test_warn_ack_without_note_ok_and_double_ack_refused(self):
        w = World(T0)
        w.push([live(alerts=fwd("warn", "cpu_high", "CPU 97%"))])
        w.tick()
        name = w.incidents.open_all()[0]["name"]
        svc = AckIncidentService(w.incidents, w.clock)
        self.assertEqual(svc.execute("a@ec", VIEW, name)["status"], C.IncStatus.ACKED)
        with self.assertRaises(C.AiLiveError):
            svc.execute("b@ec", VIEW, name, "x")

    def test_escalation_groups_only_on_escalation(self):
        cfg = {"teams_enabled": 1, "teams_webhook_url": "https://hook", "channels": ESC}
        self.assertEqual([c["group"] for c in A.channels_for(cfg, ["friso"])], [""])
        self.assertEqual([c["group"] for c in A.channels_for(cfg, ["friso"], escalation=True)], ["", "Quản lý"])
        self.assertEqual([c["group"] for c in A.channels_for(cfg, [], all_groups=True)], ["", "Quản lý"])


if __name__ == "__main__":
    unittest.main()
