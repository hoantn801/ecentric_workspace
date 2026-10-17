# Copyright (c) 2026, eCentric and contributors
"""Dua vit (fix10e, W20): ket qua tu app (push_race_result - idempotent, may khac, brand, anh PNG), gop trang thai trao giai
ERP / app, danh sach + CSV, cap nhat hang loat, lenh start_race / stop_race, clip chung dua vit trong Bo live - chay ngoai Frappe."""
import base64
import copy
import types
import unittest

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application.export_races_csv_service import ExportRacesCsvService
from ecentric_workspace.ai_tools.features.ai_live.application.list_races_service import ListRacesService
from ecentric_workspace.ai_tools.features.ai_live.application.push_race_result_service import PushRaceResultService
from ecentric_workspace.ai_tools.features.ai_live.application.queue_command_service import QueueCommandService
from ecentric_workspace.ai_tools.features.ai_live.application.set_prize_status_service import SetPrizeStatusService
from ecentric_workspace.ai_tools.features.ai_live.application.validate_race_service import ValidateRaceService
from ecentric_workspace.ai_tools.features.ai_live.domain import kit_plan as KP
from ecentric_workspace.ai_tools.features.ai_live.domain import race_rules as RR
from ecentric_workspace.ai_tools.tests.test_ai_live_session import MON, FakeCommands, FakeMachines, FakeSessions, sess

VIEW, NOBODY = ["EC AI Content"], ["Employee"]
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 80
PNG2 = b"\x89PNG\r\n\x1a\n" + b"\x01" * 80


def race(rid="mvcvokd3d683f4", **kw):
    d = {"id": rid, "live": "L1", "brand": "friso", "session": "L1:2026-10-19", "keyword": "vịt", "status": "done",
         "reg_started_at": "2026-10-19T05:58:00.000Z", "race_started_at": "2026-10-19T05:59:27.000Z",
         "finished_at": "2026-10-19T05:59:52.000Z",
         "tiers": [{"label": "Giải nhất", "count": 1, "prize": "1 lon Friso Gold 850g"}, {"label": "Giải nhì", "count": 1, "prize": "Bình nước"}],
         "winners": [{"tier": "Giải nhất", "prize": "1 lon Friso Gold 850g", "rank": 1, "name": "Bích Ngọc", "status": "chua_trao", "note": ""},
                     {"tier": "Giải nhì", "prize": "Bình nước", "rank": 2, "name": "=HYPERLINK(\"x\")", "status": "da_trao", "note": "đã gửi"}],
         "entrants": 30, "registered": 32,
         "excluded": {"count": 2, "reasons": [{"reason": "Tài khoản nội bộ / nhân viên", "n": 1}, {"reason": "Trong danh sách chặn", "n": 1}]},
         "seed": "95a25d93" * 8, "audit_id": rid, "algo": "hmac-sha256/fisher-yates/v1", "by": "erp", "auto": False}
    d.update(kw)
    return d


class FakeRaces:
    def __init__(self):
        self.rows, self.pngs, self.status_calls = {}, [], []

    def get(self, rid):
        r = self.rows.get(rid)
        return copy.deepcopy(r) if r else None

    def upsert(self, r, winners, machine):
        old = self.rows.get(r["id"], {})
        self.rows[r["id"]] = dict(copy.deepcopy(r), machine=machine, winners=copy.deepcopy(winners),
                                  png_url=old.get("png_url", ""), png_sha256=old.get("png_sha256", ""))
        return r["id"]

    def save_png(self, name, data, sha):
        self.pngs.append((name, sha))
        self.rows[name].update(png_url="/private/files/dua_vit_%s.png" % name, png_sha256=sha)

    def list(self, d0, d1, brand=None, live=None, outcome=None, limit=500):
        self.last = (d0, d1, brand, live, outcome, limit)
        rows = [copy.deepcopy(r) for r in self.rows.values() if d0 <= r["race_date"] <= d1
                and (not brand or r["brand"] == brand) and (not live or r["live"] == live) and (not outcome or r["outcome"] == outcome)]
        return sorted(rows, key=lambda r: -r["sort_ts"])[:limit]

    def set_prize_status(self, items, label, note=None):
        self.status_calls.append((list(items), label, note))
        n = 0
        for rid, rank in items:
            for w in self.rows.get(rid, {}).get("winners", []):
                if w["rank"] == rank:
                    w["status"] = label
                    if note is not None:
                        w["note"] = note
                    n += 1
        return n


class TestRaceRules(unittest.TestCase):
    def test_sanitize(self):
        r = RR.sanitize_race(race(status="cancelled_stopped_by_user"), MON)
        self.assertEqual((r["outcome"], r["race_date"], r["by"], r["entrants"], r["excluded_count"]), ("cancelled", "2026-10-19", "erp", 30, 2))
        self.assertEqual([w["status"] for w in r["winners"]], ["Chưa trao", "Đã trao"])
        self.assertEqual(r["finished_ts"] - r["race_started_ts"], 25)
        self.assertEqual(RR.sanitize_race(race(status="weird", by="robot", winners=[{"rank": 0}, {"rank": "3", "status": "?"}]), MON)["winners"],
                         [{"rank": 3, "tier": "", "prize": "", "name": "", "status": "Chưa trao", "note": ""}])
        for bad in (None, race(id="ab"), race(id="a b c d e f"), race(live="")):
            with self.assertRaises(C.AiLiveError):
                RR.sanitize_race(bad, MON)

    def test_merge_last_change_wins(self):
        app1 = RR.sanitize_race(race(), MON)["winners"]
        first = RR.merge_winners(None, app1)
        first[0].update(status="Đã trao", note="ERP: gửi GHN 123")            # nguoi dung sua tren ERP
        again = RR.merge_winners(first, app1)                                  # app gui lai (vd them anh) - giu ERP
        self.assertEqual((again[0]["status"], again[0]["note"]), ("Đã trao", "ERP: gửi GHN 123"))
        app2 = copy.deepcopy(app1)
        app2[0].update(status="Không liên lạc được", note="gọi 3 lần")         # app doi tiep -> lay app
        last = RR.merge_winners(again, app2)
        self.assertEqual((last[0]["status"], last[0]["note"], last[0]["app_status"]), ("Không liên lạc được", "gọi 3 lần", "Không liên lạc được"))
        self.assertEqual(last[1]["status"], "Đã trao")

    def test_png_args_csv(self):
        data, sha = RR.decode_png("data:image/png;base64," + base64.b64encode(PNG).decode())
        self.assertEqual((data, len(sha)), (PNG, 64))
        for bad in ("data:image/jpeg;base64," + base64.b64encode(PNG).decode(), base64.b64encode(b"GIF89a" + b"0" * 80).decode(), "@@@"):
            with self.assertRaises(C.AiLiveError):
                RR.decode_png(bad)
        a = RR.start_args({"keyword": " vịt  vàng ", "regSeconds": "90", "excludeWinners": "today", "junk": 1,
                           "tiers": [{"label": "Giải nhất", "count": 2, "prize": "Sữa"}]})
        self.assertEqual(a, {"keyword": "vịt vàng", "regSeconds": 90, "excludeWinners": "today",
                             "tiers": [{"label": "Giải nhất", "count": 2, "prize": "Sữa"}]})
        self.assertEqual(RR.start_args({}), {})
        for bad in ({"regSeconds": 5}, {"raceSeconds": 61}, {"announceOrder": "random"}, {"tiers": [{"label": "", "count": 1}]},
                    {"tiers": [{"label": "A", "count": 0}]}, {"keyword": "x" * 31}):
            with self.assertRaises(C.AiLiveError):
                RR.start_args(bad)
        r = dict(RR.sanitize_race(race(), MON), winners=RR.sanitize_race(race(), MON)["winners"])
        empty = dict(RR.sanitize_race(race(rid="xyz789", status="not_enough", winners=[]), MON))
        out = RR.to_csv([r, empty])
        lines = out.lstrip("﻿").strip().split("\r\n")
        self.assertTrue(out.startswith("﻿") and lines[0].startswith("Ngày,Giờ về đích,Brand"))
        self.assertEqual(len(lines), 4)                                        # tieu de + 2 nguoi thang + 1 dong trong
        self.assertIn("'=HYPERLINK", lines[2])                                 # chong chen cong thuc Excel
        self.assertIn("12:59:52", lines[1])                                    # gio VN
        self.assertIn("Chưa đủ người", lines[3])


class TestPushRace(unittest.TestCase):
    def setUp(self):
        self.races = FakeRaces()
        self.svc = PushRaceResultService(FakeMachines(), self.races, clock=lambda: MON)

    def test_create_update_png(self):
        b64 = "data:image/png;base64," + base64.b64encode(PNG).decode()
        out = self.svc.execute("u1", "MAY01", race(), b64)
        self.assertEqual((out["ok"], out["saved"], out["created"], out["png"]), (True, True, True, "saved"))
        self.races.rows["mvcvokd3d683f4"]["winners"][0].update(status="Đã trao")          # ERP sua
        again = self.svc.execute("u1", "MAY01", race(), b64)                                # app gui lai cung anh
        self.assertEqual((again["created"], again["png"]), (False, "same"))
        self.assertEqual(self.races.rows["mvcvokd3d683f4"]["winners"][0]["status"], "Đã trao")
        self.assertEqual(self.svc.execute("u1", "MAY01", race(), base64.b64encode(PNG2).decode())["png"], "saved")
        self.assertEqual(self.svc.execute("u1", "MAY01", race(), "data:image/png;base64,AAAA")["png"], "bad")
        self.assertEqual(self.svc.execute("u1", "MAY01", '{"id":"abc12345","live":"L2","winners":[]}', None)["png"], "none")
        self.assertEqual(len(self.races.pngs), 2)
        self.assertEqual(self.races.rows["abc12345"]["machine"], "MAY01")

    def test_guards(self):
        self.svc.execute("u1", "MAY01", race(), None)
        with self.assertRaises(C.AiLivePermission):
            self.svc.execute("u2", "MAY02", race(brand=""), None)                  # cung ma, may khac
        with self.assertRaises(C.AiLivePermission):
            self.svc.execute("u1", "MAY02", race(), None)                          # token may khac
        with self.assertRaises(C.AiLivePermission):
            self.svc.execute("nobody", "MAY01", race(), None)
        skip = self.svc.execute("u2", "MAY02", race(rid="other123", brand="wilmar"), None)
        self.assertEqual((skip["saved"], "other123" in self.races.rows), (False, False))
        with self.assertRaises(C.AiLiveError):
            self.svc.execute("u1", "MAY01", race(id="!!"), None)
        with self.assertRaises(C.AiLiveError):
            self.svc.execute("u1", "MAY01", "{not json", None)


class TestRacePages(unittest.TestCase):
    def setUp(self):
        self.races = FakeRaces()
        push = PushRaceResultService(FakeMachines(), self.races, clock=lambda: MON)
        push.execute("u1", "MAY01", race(), None)
        push.execute("u1", "MAY01", race(rid="old00001", finished_at="2026-10-01T05:00:00Z", reg_started_at=None, race_started_at=None), None)
        push.execute("u1", "MAY01", race(rid="nope0001", status="not_enough", winners=[]), None)

    def test_list_filters_and_csv(self):
        lst = ListRacesService(self.races, clock=lambda: MON)
        d = lst.execute(VIEW)
        self.assertEqual((d["date_from"], d["date_to"], d["totals"]["races"], d["totals"]["winners"]), ("2026-10-13", "2026-10-19", 2, 2))
        self.assertEqual((d["totals"]["chua_trao"], d["totals"]["da_trao"]), (1, 1))
        self.assertNotIn("app_status", d["races"][0]["winners"][0])
        self.assertEqual(len(lst.execute(VIEW, prize="da_trao")["races"]), 1)
        self.assertEqual(len(lst.execute(VIEW, date_from="2026-09-25", date_to="2026-10-19")["races"]), 3)
        self.assertEqual(lst.execute(VIEW, live="L1", outcome="done")["totals"]["races"], 1)
        for bad in ({"date_from": "2026-10-20", "date_to": "2026-10-01"}, {"date_from": "hôm qua"}, {"prize": "lost"},
                    {"date_from": "2025-01-01", "date_to": "2026-10-19"}):
            with self.assertRaises(C.AiLiveError):
                lst.execute(VIEW, **bad)
        with self.assertRaises(C.AiLivePermission):
            lst.execute(NOBODY)
        csv = ExportRacesCsvService(self.races, clock=lambda: MON).execute(VIEW, live="L1")
        self.assertEqual((csv["filename"], csv["rows"]), ("dua_vit_2026-10-13_2026-10-19_L1.csv", 3))

    def test_bulk_status(self):
        calls = []
        svc = SetPrizeStatusService(self.races, atomic=lambda fn: calls.append(1) or fn())
        out = svc.execute(VIEW, '[{"race":"mvcvokd3d683f4","rank":1},{"race":"mvcvokd3d683f4","rank":"2"},{"race":"bad id","rank":1}]', "da_trao", " xong ")
        self.assertEqual((out, calls), ({"updated": 2, "status": "Đã trao"}, [1]))
        self.assertEqual(self.races.status_calls[-1], ([("mvcvokd3d683f4", 1), ("mvcvokd3d683f4", 2)], "Đã trao", "xong"))
        self.assertEqual(svc.execute(VIEW, [{"race": "mvcvokd3d683f4", "rank": 1}], "Không liên lạc được")["updated"], 1)
        self.assertIsNone(self.races.status_calls[-1][2])                       # khong gui ghi chu -> giu nguyen
        for items, st in (([], "da_trao"), ([{"race": "mvcvokd3d683f4", "rank": 1}], "lost"), ([{"race": "x" * 3, "rank": 1}], "da_trao")):
            with self.assertRaises(C.AiLiveError):
                svc.execute(VIEW, items, st)
        with self.assertRaises(C.AiLiveError):
            svc.execute(VIEW, [{"race": "mvcvokd3d683f4", "rank": 1}] * (C.RACE_BULK_MAX + 1), "da_trao")
        with self.assertRaises(C.AiLivePermission):
            svc.execute(NOBODY, [{"race": "mvcvokd3d683f4", "rank": 1}], "da_trao")

    def test_validate_counts(self):
        rows = [types.SimpleNamespace(prize_status=s, note=n) for s, n in (("da_trao", " a "), ("Đã trao", ""), ("?", None), ("Không liên lạc được", ""))]
        doc = ValidateRaceService().execute(types.SimpleNamespace(winners=rows))
        self.assertEqual((doc.winners_n, doc.awarded_n, doc.unreachable_n), (4, 2, 1))
        self.assertEqual([r.prize_status for r in rows], ["Đã trao", "Đã trao", "Chưa trao", "Không liên lạc được"])
        self.assertEqual(rows[0].note, "a")


class TestRaceCommandsAndKit(unittest.TestCase):
    def test_start_stop_race_commands(self):
        cmds = FakeCommands()
        q = QueueCommandService(FakeSessions([sess("L1")]), cmds, clock=lambda: MON)
        cid = q.execute("op@ec", VIEW, "L1", "start_race", '{"keyword":"vịt","raceSeconds":40,"tiers":[{"label":"Giải nhất","count":1,"prize":"Sữa"}]}')["id"]
        self.assertEqual(cmds.rows[cid]["args"], {"keyword": "vịt", "raceSeconds": 40, "tiers": [{"label": "Giải nhất", "count": 1, "prize": "Sữa"}]})
        self.assertEqual(cmds.rows[q.execute("op@ec", VIEW, "L1", "start_race")["id"]]["args"], {})
        sid = q.execute("op@ec", VIEW, "L1", "stop_race", '{"junk":1}')["id"]
        self.assertEqual((cmds.rows[sid]["action"], cmds.rows[sid]["args"]), ("stop_race", {}))
        with self.assertRaises(C.AiLiveError):
            q.execute("op@ec", VIEW, "L1", "start_race", '{"regSeconds":1000}')

    def test_kit_race_groups(self):
        defs = KP.generic_defaults()
        self.assertEqual((defs["race_commentary"]["min"], defs["race_commentary"]["max"], len(defs["race_commentary"]["scripts"])), (3, 4, 4))
        for g in ("race_call", "race_commentary", "race_winner", "race_claim"):
            self.assertTrue(all(len(s) <= C.MAX_SCRIPT_CHARS for s in defs[g]["scripts"]), g)
        gen = KP.normalize_generic({"race_call": [{"file": "/private/files/dua_moi_1.mp3", "dur": 6.2}], "cho": []})
        step = KP.build_step({"name": "K1", "brand": "friso", "host_key": "H_ABC", "background": ""}, [], [], gen,
                             {"/private/files/dua_moi_1.mp3": "kits/k1/dua_moi_1.mp3"})
        self.assertEqual(step["generic"]["race_call"], [{"audio": "kits/k1/dua_moi_1.mp3", "dur": 6.2, "version": 1, "name": "dua_moi_1.mp3"}])
        self.assertEqual(set(step["generic"]), set(C.GENERIC_GROUPS))
        self.assertIn(("race_call_1", gen["race_call"][0]), KP.audio_entries([], [], gen))


if __name__ == "__main__":
    unittest.main()
