# Copyright (c) 2026, eCentric and contributors
"""Dong bo theo file kiem ke IT + nhap ban quyen Microsoft 365 (27/11/2026).

    python -m unittest ecentric_workspace.tai_san.tests.test_dot7
"""
import unittest

from ecentric_workspace.tai_san.tests.test_dot1 import MGR, Row
from ecentric_workspace.tai_san.tests.test_dot4 import LicenseCase
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import repository as R


def dev(name, tag, status, holder=None, item="LT1"):
    return {"name": name, C.TAG_FIELD: tag, C.OPS_STATUS_FIELD: status, "custodian": holder,
            "item_code": item, "asset_category": "LAPTOP", "department": None}


class SyncCase(LicenseCase):
    def setUp(self):
        super().setUp()
        self.repo.assets = {a["name"]: Row(a) for a in [
            dev("A1", "EC202400002", C.ST_IN_USE, "E2"),          # chuyen
            dev("A2", "ec202400005", C.ST_AVAILABLE),             # cap, ma chu thuong
            dev("A3", "EC202400024", C.ST_LOST),                  # mat -> tim thay -> cap
            dev("A4", "EC202400013", C.ST_IN_USE, "E2"),          # tra kho
            dev("A5", "EC202400025", C.ST_IN_USE, "E2"),          # sua mau
            dev("A6", "EC202400006-1", C.ST_AVAILABLE),           # chi doi ma
            dev("A7", "PC-0001", C.ST_AVAILABLE)]}                # ma khac: giu nguyen
        self.repo.emps["E4"] = Row(name="E4", employee_name="Dung", user_id="d@x", status="Active")
        users = {e.user_id: e for e in self.repo.emps.values()}
        items = [Row(name="LT1", item_name="LENOVO V14 G4", asset_category="LAPTOP"),
                 Row(name="MN1", item_name="MONITOR - LENOVO ThinkVision S27i-30", asset_category="MONITOR")]
        self.r_saved = {n: getattr(R, n) for n in ("assets", "employee_of_user", "fixed_asset_items")}
        R.assets = lambda filters=None: [Row(a) for a in self.repo.assets.values()]
        R.employee_of_user = lambda u: users.get(u)
        R.fixed_asset_items = lambda: items
        from ecentric_workspace.tai_san import sync_service
        self.SY = sync_service
        self.rows = [{"old_tag": "EC202400002", "email": "an@x"}, {"old_tag": "EC202400005", "email": "d@x"},
                     {"old_tag": "EC202400024", "email": "an@x"}, {"old_tag": "EC202400013", "email": None},
                     {"old_tag": "EC202400099", "email": "an@x"}, {"old_tag": "EC202400006-1", "email": "c@x"}]
        self.fixes = [{"old_tag": "EC202400025", "item_contains": "S27I-30"}]

    def tearDown(self):
        for n, f in self.r_saved.items():
            setattr(R, n, f)
        super().tearDown()

    def _run(self):
        rep = self.SY.rename_tags(MGR)
        return rep, self.SY.sync_devices(MGR, self.rows, "Kiểm kê", self.fixes)


class TestSyncDevices(SyncCase):
    def test_new_tag(self):
        self.assertEqual(self.SY.new_tag("ec202400046"), "EC202600046")
        self.assertEqual(self.SY.new_tag("EC202400006-1"), "EC202600006-1")
        self.assertIsNone(self.SY.new_tag("PC-0001"))

    def test_sync_follows_lifecycle_quietly_and_is_idempotent(self):
        renamed, rep = self._run()
        a = self.repo.assets
        self.assertEqual([a[n][C.TAG_FIELD] for n in ("A1", "A2", "A6", "A7")],
                         ["EC202600002", "EC202600005", "EC202600006-1", "PC-0001"])
        self.assertEqual(len(renamed), 6)
        self.assertEqual((a["A1"][C.OPS_STATUS_FIELD], a["A1"]["custodian"]), (C.ST_IN_USE, "E1"))
        self.assertEqual((a["A2"][C.OPS_STATUS_FIELD], a["A2"]["custodian"]), (C.ST_IN_USE, "E4"))
        self.assertEqual((a["A3"][C.OPS_STATUS_FIELD], a["A3"]["custodian"]), (C.ST_IN_USE, "E1"))
        self.assertEqual((a["A4"][C.OPS_STATUS_FIELD], a["A4"]["custodian"]), (C.ST_AVAILABLE, None))
        self.assertEqual(a["A5"]["item_code"], "MN1")
        types = [e["event_type"] for e in self.repo.events if e["asset"] == "A3"]
        self.assertEqual(types[-3:], [C.EV_FOUND, C.EV_CHECK_PASS, C.EV_ASSIGN])
        self.assertTrue(all(e.get("note") == "Kiểm kê" for e in self.repo.events
                            if e["event_type"] != C.EV_EDIT and e["asset"] != "A5"))
        self.assertEqual(self.repo.notes, [])                              # khong bao nguoi giu
        out = dict(rep)
        self.assertIn("chưa có", out["EC202400099"])
        self.assertIn("không thấy nhân viên", out["EC202400006-1"])     # E3 da nghi
        # chay lai: khong them su kien nao
        n = len(self.repo.events)
        renamed2, rep2 = self._run()
        self.assertEqual(len(self.repo.events), n)
        self.assertEqual(renamed2, [])
        self.assertEqual(dict(rep2)["EC202400002"], "đã đúng")


class TestImportLicenses(SyncCase):
    G = [{"product_name": "Power BI Pro", "vendor": "Microsoft", "category": "Dữ liệu",
          "emails": ["an@x", "b@x", "c@x", "zz@x"], "shared": ["data.agent@x"]}]

    def test_import_creates_quiet_seats_and_reruns_clean(self):
        rep = self.SY.import_licenses(MGR, self.G, "M365-TEST")
        lic = [x for x in self.lr.lics.values() if "M365-TEST" in (x.note or "")]
        self.assertEqual(len(lic), 1)
        x = lic[0]
        self.assertEqual((x.seats, x.license_type, x.expiry_date), (5, C.LT_SUBSCRIPTION, None))
        self.assertIn("data.agent@x", x.note)
        seats = [s for s in self.lr.seats_.values() if s["license"] == x.name and s["status"] == C.SEAT_ACTIVE]
        self.assertEqual(sorted(s["employee"] for s in seats), ["E1", "E2"])   # c@x nghi, zz@x khong co
        self.assertEqual(self.repo.notes, [])
        self.assertIn("c@x", rep[0][1])
        self.SY.import_licenses(MGR, self.G, "M365-TEST")
        self.assertEqual(len([y for y in self.lr.lics.values() if "M365-TEST" in (y.note or "")]), 1)
        self.assertEqual(len([s for s in self.lr.seats_.values() if s["license"] == x.name]), 2)

    def test_reuses_single_manual_license_and_raises_seats(self):
        # "Microsoft 365" (PM1) da co ban quyen BQ1 nhap tay -> dung lai, nang so cho
        g = [dict(self.G[0], product_name="Microsoft 365", emails=["an@x", "b@x"], shared=["x@x", "y@x"])]
        before = len(self.lr.lics)
        self.SY.import_licenses(MGR, g, "M365-TEST")
        self.assertEqual(len(self.lr.lics), before)
        self.assertEqual(self.lr.lics["BQ1"].seats, 4)


class TestDataFiles(unittest.TestCase):
    def test_kiem_ke_2026_11_files(self):
        from ecentric_workspace.tai_san import sync_service as SY
        lic = SY.load("kiem_ke_2026_11_m365.json")
        seats = {g["product_name"]: len(g["emails"]) + len(g["shared"]) for g in lic["groups"]}
        self.assertEqual(seats, {"Microsoft 365 Business Standard": 43, "Microsoft 365 Business Basic": 66,
                                 "Power BI Pro": 2, "Power Automate Premium": 4})
        self.assertTrue(all(g["category"] in C.LICENSE_CATEGORIES for g in lic["groups"]))
        dev_ = SY.load("kiem_ke_2026_11_thiet_bi.json")
        self.assertEqual(len(dev_["rows"]), 13)
        self.assertTrue(all(SY.new_tag(r["old_tag"]) for r in dev_["rows"]))


if __name__ == "__main__":
    unittest.main()
