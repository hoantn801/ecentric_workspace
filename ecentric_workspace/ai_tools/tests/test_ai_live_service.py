# Copyright (c) 2026, eCentric and contributors
"""AI Live (cau hinh may phat, chi phi, cai dat dung chung) - service chay ngoai Frappe voi repository gia."""
import json
import types
import unittest

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import brand_config_rules
from ecentric_workspace.ai_tools.features.ai_live.application.cost_summary_service import CostSummaryService
from ecentric_workspace.ai_tools.features.ai_live.application.get_config_service import GetConfigService
from ecentric_workspace.ai_tools.features.ai_live.application.push_cost_service import PushCostService
from ecentric_workspace.ai_tools.features.ai_live.application.put_brand_settings_service import PutBrandSettingsService
from ecentric_workspace.ai_tools.features.ai_live.application.register_machine_service import RegisterMachineService


class FakeMachines:
    def __init__(self):
        self.rows = {"MAY01": {"machine_code": "MAY01", "label": "Máy 1", "enabled": 1, "user": "u1", "brands": "friso\nwilmar"},
                     "MAY02": {"machine_code": "MAY02", "label": "", "enabled": 0, "user": "u2", "brands": "friso"}}
        self.rotated = []

    def by_user(self, user):
        return next((dict(m) for m in self.rows.values() if m["user"] == user), None)

    def get(self, code):
        return self.rows.get(code)

    def upsert(self, code, label, brands):
        m = self.rows.setdefault(code, {"machine_code": code, "label": "", "enabled": 1, "user": None, "brands": ""})
        if label is not None:
            m["label"] = label
        if brands is not None:
            m["brands"] = brands
        return code

    def ensure_user(self, code):
        self.rows[code]["user"] = "u-" + code
        return "u-" + code

    def rotate_keys(self, user):
        self.rotated.append(user)
        return "k%d:s%d" % (len(self.rotated), len(self.rotated))

    def record_fetch(self, code, ts, version):    # fix10g: may da tai lich ban nao
        self.rows[code].update(cfg_fetched_ts=ts, cfg_version=version)


class FakeSchedule:
    """fix10g: so phien ban lich + nhat ky phat hanh (thay ScheduleRepository)."""

    def __init__(self, version=0, lock_min=15, refresh=1):
        self.version, self.lock_min, self.refresh, self.log = version, lock_min, refresh, []

    def settings(self):
        return {"version": self.version, "lock_min": self.lock_min, "refresh_on_publish": self.refresh,
                "last_published_by": "", "last_published_at": ""}

    def next_version(self, user, ts):
        self.version += 1
        return self.version

    def insert_version(self, row):
        self.log.append(row)

    def versions(self, limit=40):
        return [{"version": r["version"], "source": r["source"], "by": r["published_by"], "ts": r["published_ts"],
                 "note": r.get("note") or "", "changes": r["changes"], "machines": r["machines"]} for r in reversed(self.log)][:limit]


class FakeBrands:
    def __init__(self):
        self.rows = {
            "friso": {"brand": "friso", "brand_name": "Friso", "enabled": 1, "gpu_url": "http://gpu1:8000", "mode": "full",
                      "break_sec": "20", "kit_folder": "G:\\AI Live\\friso", "minimax_group": "g1", "daily_cost_cap_usd": 5,
                      "claude_key": "sk-ant-x", "minimax_key": "mm", "kie_key": "", "plenx_key": "px",
                      "shopee_partner_id": 123, "shopee_shop_id": "456", "shopee_partner_key": "spk",
                      "shopee_access_token": "sat", "shopee_refresh_token": "srt",
                      "templates_json": '{"greet1": ["Chào {ten}"]}', "playlist_json": "[broken", "cooldowns_json": None,
                      "updated_at": "2026-10-17 10:00:00"},
            "wilmar": {"brand": "wilmar", "brand_name": "Wilmar", "enabled": 0, "mode": "lite", "break_sec": "30"}}
        self.saved = []

    def get(self, brand, with_keys=False):
        r = self.rows.get(brand)
        if not r:
            return None
        r = dict(r)
        if not with_keys:
            for f in C.KEY_FIELDS:
                r.pop(f, None)
        return r

    def list_names(self):
        return sorted(self.rows)

    def set_settings(self, brand, values):
        self.saved.append((brand, values))
        self.rows[brand].update(values)
        return "2026-10-17 11:00:00"


class FakeCosts:
    def __init__(self):
        self.rows = {}

    def upsert(self, key, row):
        self.rows[key] = dict(row)

    def day_total(self, brand, date):
        return sum(r["usd"] for r in self.rows.values() if r["brand"] == brand and r["date"] == date)

    def summary(self, since, brand=None):
        out = {}
        for r in self.rows.values():
            if r["date"] >= since and (not brand or r["brand"] == brand):
                o = out.setdefault((r["brand"], r["date"]), {"brand": r["brand"], "date": r["date"], "usd": 0, "sessions": 0, "machines": 0})
                o["usd"] += r["usd"]
                o["sessions"] += 1
        return list(out.values())


class TestGetConfig(unittest.TestCase):
    def setUp(self):
        self.svc = GetConfigService(FakeMachines(), FakeBrands(), sessions=types.SimpleNamespace(list=lambda: []),
                                    schedule=FakeSchedule())

    def test_returns_enabled_brands_with_keys(self):
        d = self.svc.execute("u1", "MAY01")
        self.assertEqual(d["machine"], "MAY01")
        self.assertEqual([b["brand"] for b in d["brands"]], ["friso"])        # wilmar dang tat
        b = d["brands"][0]
        self.assertEqual(b["claude_key"], "sk-ant-x")
        self.assertEqual(b["break_sec"], 20)
        self.assertEqual(b["templates"], {"greet1": ["Chào {ten}"]})
        self.assertIsNone(b["playlist"])                                    # JSON hong -> None, khong vo
        self.assertEqual(set(C.KEY_FIELDS) - set(b), set())
        self.assertEqual((b["shopee_partner_id"], b["shopee_shop_id"], b["shopee_access_token"]), ("123", "456", "sat"))

    def test_rejects_non_machine_and_wrong_code(self):
        with self.assertRaises(C.AiLivePermission):
            self.svc.execute("someone", "MAY01")
        with self.assertRaises(C.AiLivePermission):
            self.svc.execute("u1", "MAY02")
        with self.assertRaises(C.AiLivePermission):
            self.svc.execute("u2", "MAY02")                                  # may bi tat


class TestPushCost(unittest.TestCase):
    def setUp(self):
        self.costs = FakeCosts()
        self.svc = PushCostService(FakeMachines(), self.costs, FakeBrands())
        self.base = {"machine": "MAY01", "brand": "friso", "session": "live-1", "date": "2026-10-17", "usd": 2.5,
                     "items": [{"kind": "llm", "usd": 2, "n": 40}, {"kind": "tts", "usd": 0.5, "n": 12}]}

    def test_upsert_is_idempotent_and_reports_cap(self):
        r = self.svc.execute("u1", dict(self.base))
        self.assertEqual(r["brand_day_usd"], 2.5)
        r = self.svc.execute("u1", dict(self.base, usd=3.0))                # luy ke -> ghi de
        self.assertEqual(len(self.costs.rows), 1)
        self.assertEqual(r["brand_day_usd"], 3.0)
        self.assertFalse(r["over_cap"])
        r = self.svc.execute("u1", dict(self.base, session="live-2", usd=2.0))
        self.assertTrue(r["over_cap"])                                     # 3 + 2 >= tran 5
        self.assertEqual(json.loads(list(self.costs.rows.values())[0]["items_json"])[0]["kind"], "llm")

    def test_rejects_bad_input(self):
        for bad in ({"session": "x y"}, {"date": "17/10"}, {"usd": -1}, {"usd": "abc"},
                    {"items": "x"}, {"items": [1]}, {"usd": float("nan")}):
            with self.assertRaises(C.AiLiveError, msg=str(bad)):
                self.svc.execute("u1", dict(self.base, **bad))
        with self.assertRaises(C.AiLivePermission):
            self.svc.execute("u1", dict(self.base, machine="MAY02"))

    def test_unknown_brand_is_kept_not_403(self):
        """Hop dong 1.0.21 #7: brand rong (kem live) / chua giao -> van luu, gan co; 403 se lam app dung ca hang cho."""
        r = self.svc.execute("u1", dict(self.base, brand="", live="L1", usd=0.4))
        self.assertEqual((r["brand_day_usd"], r["over_cap"]), (0.4, False))
        r2 = self.svc.execute("u1", dict(self.base, brand="nivea"))
        self.assertFalse(r2["over_cap"])
        flags = sorted((x["brand"], x["brand_unknown"], x["live"]) for x in self.costs.rows.values())
        self.assertEqual(flags, [("", 1, "L1"), ("nivea", 1, "")])


class TestPutBrandSettings(unittest.TestCase):
    def setUp(self):
        self.brands = FakeBrands()
        self.svc = PutBrandSettingsService(FakeMachines(), self.brands)

    def test_machine_updates_own_brand(self):
        r = self.svc.execute("u1", [], {"brand": "friso", "templates": {"greet1": ["Dạ chào {xung} {ten}"]}, "playlist": None})
        self.assertTrue(r["saved"])
        brand, vals = self.brands.saved[-1]
        self.assertEqual(list(vals), ["templates_json"])
        self.assertIn("{xung}", vals["templates_json"])

    def test_permissions_and_validation(self):
        with self.assertRaises(C.AiLivePermission):
            self.svc.execute("u-other", [], {"brand": "friso", "templates": {}})
        with self.assertRaises(C.AiLiveError):
            self.svc.execute("u1", [], {"brand": "friso", "cooldowns": "{bad json"})
        with self.assertRaises(C.AiLiveError):
            self.svc.execute("x", ["System Manager"], {"brand": "nivea", "templates": {}})
        r = self.svc.execute("x", ["EC AI Video Admin"], {"brand": "wilmar", "playlist": [1, 2]})
        self.assertTrue(r["saved"])
        self.assertFalse(self.svc.execute("u1", [], {"brand": "friso"})["saved"])


class TestRegisterMachine(unittest.TestCase):
    def test_admin_creates_machine_and_token(self):
        ms = FakeMachines()
        svc = RegisterMachineService(ms, FakeBrands())
        r = svc.execute(["System Manager"], "MAY03", "Phòng live 3", "friso\n wilmar ")
        self.assertEqual(r["token"], "k1:s1")
        self.assertEqual(ms.rows["MAY03"]["brands"], "friso\nwilmar")
        r = svc.execute(["System Manager"], "MAY03", new_token=False)
        self.assertIsNone(r["token"])
        self.assertEqual(ms.rows["MAY03"]["brands"], "friso\nwilmar")      # khong gui brands -> giu nguyên

    def test_rejects(self):
        svc = RegisterMachineService(FakeMachines(), FakeBrands())
        with self.assertRaises(C.AiLivePermission):
            svc.execute(["EC AI Content"], "MAY03")
        with self.assertRaises(C.AiLiveError):
            svc.execute(["System Manager"], "máy 3")
        with self.assertRaises(C.AiLiveError):
            svc.execute(["System Manager"], "MAY03", brands="nivea")


class TestCostSummaryAndRules(unittest.TestCase):
    def test_summary_marks_over_cap(self):
        import datetime
        costs = FakeCosts()
        costs.upsert("a", {"brand": "friso", "date": "2026-10-17", "usd": 6.0})
        costs.upsert("b", {"brand": "friso", "date": "2026-10-01", "usd": 1.0})
        svc = CostSummaryService(costs, FakeBrands(), today=lambda: datetime.date(2026, 10, 17))
        r = svc.execute(["EC AI Content"], days=7)
        self.assertEqual(r["since"], "2026-10-11")
        self.assertEqual(len(r["rows"]), 1)
        self.assertTrue(r["rows"][0]["over_cap"])
        with self.assertRaises(C.AiLivePermission):
            svc.execute(["Guest"])

    def test_brand_rules(self):
        def doc(**k):
            d = types.SimpleNamespace(brand="friso", mode="", break_sec="", gpu_url="http://g:8000/", daily_cost_cap_usd=-1,
                                      templates_json=None, playlist_json="[]", cooldowns_json=None)
            d.__dict__.update(k)
            d.get = lambda f: getattr(d, f, None)
            return d
        d = doc()
        brand_config_rules.validate_brand(d)
        self.assertEqual((d.mode, d.break_sec, d.gpu_url, d.daily_cost_cap_usd), ("full", "20", "http://g:8000", 0))
        for bad in (dict(brand="Friso"), dict(mode="x"), dict(break_sec="15"), dict(playlist_json="{x")):
            with self.assertRaises(C.AiLiveError, msg=str(bad)):
                brand_config_rules.validate_brand(doc(**bad))
        m = types.SimpleNamespace(machine_code=" MAY01 ", brands="friso, wilmar\n\n")
        brand_config_rules.validate_machine(m)
        self.assertEqual((m.machine_code, m.brands), ("MAY01", "friso\nwilmar"))


if __name__ == "__main__":
    unittest.main()
