# Copyright (c) 2026, eCentric and contributors
"""Quan ly tai san dot 4 - ban quyen phan mem: moc nhac han, gia han, cap / thu cho, quyen xem.

    python -m unittest ecentric_workspace.tai_san.tests.test_dot4
"""
import datetime as dt
import os
import types
import unittest

from ecentric_workspace.tai_san.tests.test_dot1 import (APP, FIN, MGR, STAFF, FakeRepo, Row, _fk,  # noqa: F401
                                                        _install, _restore)
from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import licenses as LIC
from ecentric_workspace.tai_san import lifecycle as L

TODAY = dt.date(2026, 11, 26)


def lic(**kw):
    d = {"name": "BQ1", "license_name": "Microsoft 365", "license_type": C.LT_SUBSCRIPTION,
         "billing_cycle": C.CY_YEARLY, "status": C.LS_ACTIVE, "seats": 2, "start_date": "2025-12-20",
         "current_term_start": "2025-12-20", "expiry_date": "2026-12-20", "cost_per_cycle": 12_000_000,
         "owner_employee": None, "department": "Data", "category": "Văn phòng"}
    d.update(kw)
    return Row(d)


class TestLicenseRules(unittest.TestCase):
    def test_lead_days(self):
        self.assertEqual(LIC.lead_days(lic()), 30)
        self.assertEqual(LIC.lead_days(lic(billing_cycle=C.CY_MONTHLY)), 10)
        self.assertEqual(LIC.lead_days(lic(billing_cycle=C.CY_OTHER, current_term_start="2026-12-01")), 10)
        self.assertEqual(LIC.lead_days(lic(billing_cycle=C.CY_OTHER, current_term_start="2026-06-01")), 30)
        self.assertIsNone(LIC.lead_days(lic(license_type=C.LT_PERPETUAL, expiry_date=None)))

    def test_stage_boundaries(self):
        self.assertEqual(LIC.stage(lic(expiry_date="2026-12-26"), TODAY), C.STAGE_DUE)      # dung 30 ngay
        self.assertEqual(LIC.stage(lic(expiry_date="2026-12-27"), TODAY), C.STAGE_OK)
        self.assertEqual(LIC.stage(lic(expiry_date="2026-11-25"), TODAY), C.STAGE_EXPIRED)
        m = dict(billing_cycle=C.CY_MONTHLY, current_term_start="2026-11-06")
        self.assertEqual(LIC.stage(lic(expiry_date="2026-12-07", **m), TODAY), C.STAGE_OK)  # 11 ngay
        self.assertEqual(LIC.stage(lic(expiry_date="2026-12-06", **m), TODAY), C.STAGE_DUE)  # 10 ngay
        self.assertIsNone(LIC.stage(lic(status=C.LS_CANCELLED, expiry_date="2026-11-01"), TODAY))

    def test_alert_once_per_stage_and_resets_on_new_term(self):
        x = lic(expiry_date="2026-12-10")
        self.assertEqual(LIC.needs_alert(x, TODAY), C.STAGE_DUE)
        x.update(alert_stage=C.STAGE_DUE, alert_for_expiry="2026-12-10")
        self.assertIsNone(LIC.needs_alert(x, TODAY))
        self.assertEqual(LIC.needs_alert(x, dt.date(2026, 12, 11)), C.STAGE_EXPIRED)
        x.update(expiry_date="2027-12-10")                     # gia han -> han moi
        self.assertIsNone(LIC.needs_alert(x, TODAY))           # con xa
        self.assertEqual(LIC.needs_alert(x, dt.date(2027, 11, 20)), C.STAGE_DUE)

    def test_monthly_cost_and_next_expiry(self):
        self.assertEqual(LIC.monthly_cost(lic()), 1_000_000)
        self.assertEqual(LIC.monthly_cost(lic(license_type=C.LT_PERPETUAL)), 0)
        self.assertEqual(LIC.next_expiry(lic(billing_cycle=C.CY_MONTHLY, expiry_date="2027-01-31")),
                         dt.date(2027, 2, 28))
        self.assertEqual(LIC.next_expiry(lic(expiry_date="2028-02-29")), dt.date(2029, 2, 28))


class FakeLR:
    def __init__(self, lics=None):
        self.lics = {x["name"]: Row(x) for x in (lics or [])}
        self.seats_, self.ren, self.logs = {}, [], []

    def licenses(self, filters=None):
        rows = list(self.lics.values())
        st = (filters or {}).get("status")
        if st:
            rows = [r for r in rows if r["status"] in st[1]]
        names = (filters or {}).get("name")
        if names:
            rows = [r for r in rows if r["name"] in names[1]]
        return [Row(r) for r in rows]

    def license(self, name):
        if name not in self.lics:
            raise _fk.DoesNotExistError(name)
        return Row(self.lics[name])

    def lock_license(self, name):
        return self.license(name)

    def lock_active_seats(self, license_name):
        return self.active_seats(license_name)

    def lock_seat(self, name):
        return self.seat(name)

    def set_license_if(self, name, expiry, values):
        if str(self.lics[name].get("expiry_date") or "")[:10] != str(expiry or "")[:10]:
            return False
        self.lics[name].update(values)
        return True

    def department_exists(self, name):
        return name in ("Data", "HR")

    def add_log(self, name, text, user):
        self.logs.append((name, text))

    def insert_license(self, values):
        name = "BQ%d" % (len(self.lics) + 1)
        self.lics[name] = Row(dict(values, name=name))
        return name

    def set_license(self, name, values):
        self.lics[name].update(values)

    def add_renewal(self, name, row):
        self.ren.append(dict(row, parent=name))

    def renewals(self, name):
        return [Row(r) for r in self.ren if r["parent"] == name]

    def user_names(self, users):
        return {u: u.split("@")[0] for u in users if u}

    def seats(self, filters=None):
        rows = [Row(s) for s in self.seats_.values()]
        if filters and filters.get("license"):
            rows = [r for r in rows if r["license"] == filters["license"]]
        return rows

    def active_seats(self, license_name=None, employees=None):
        return [Row(s) for s in self.seats_.values() if s["status"] == C.SEAT_ACTIVE
                and (not license_name or s["license"] == license_name)
                and (employees is None or s["employee"] in employees)]

    def seat(self, name):
        return Row(self.seats_[name])

    def insert_seat(self, values):
        name = "S%d" % (len(self.seats_) + 1)
        self.seats_[name] = dict(values, name=name, employee_name=None, revoked_on=None, ref_doctype=None,
                                 ref_name=None)
        return name

    def revoke_seat(self, name, user, note=None, ref_doctype=None, ref_name=None):
        self.seats_[name].update(status=C.SEAT_REVOKED, revoked_by=user, note=note, ref_doctype=ref_doctype,
                                 ref_name=ref_name)


class LicenseCase(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepo([], employees={
            "E1": {"name": "E1", "employee_name": "An", "department": "Data", "user_id": "an@x", "status": "Active"},
            "E2": {"name": "E2", "employee_name": "Binh", "department": "HR", "user_id": "b@x", "status": "Active"},
            "E3": {"name": "E3", "employee_name": "Chi", "department": "Data", "user_id": "c@x", "status": "Left"}})
        self.saved = _install(self.repo)
        from ecentric_workspace.tai_san import license_repository as LRm
        self.lr = FakeLR([lic()])
        self.lr_saved = {}
        for n in dir(FakeLR):
            if not n.startswith("_") and hasattr(LRm, n):
                self.lr_saved[n] = getattr(LRm, n)
                setattr(LRm, n, getattr(self.lr, n))
        self.LRm = LRm
        from ecentric_workspace.tai_san import license_service, license_views
        self.LS, self.LV = license_service, license_views
        self.LV._today = lambda: TODAY

    def tearDown(self):
        for n, f in self.lr_saved.items():
            setattr(self.LRm, n, f)
        _restore(self.saved)


class TestLicenseService(LicenseCase):
    def test_create_subscription_needs_expiry(self):
        with self.assertRaises(L.TransitionError):
            self.LS.create(MGR, {"license_name": "Adobe CC", "license_type": C.LT_SUBSCRIPTION})
        r = self.LS.create(MGR, {"license_name": "Adobe CC", "expiry_date": "2027-11-26", "seats": 3,
                                 "billing_cycle": C.CY_MONTHLY, "cost_per_cycle": 900_000})
        x = self.lr.lics[r["license"]]
        self.assertEqual((x.seats, x.status, x.current_term_start), (3, C.LS_ACTIVE, x.start_date))

    def test_staff_cannot_create(self):
        with self.assertRaises(A.AccessDenied):
            self.LS.create(STAFF, {"license_name": "X", "license_type": C.LT_PERPETUAL})

    def test_assign_limits(self):
        self.LS.assign(MGR, "BQ1", "E1")
        with self.assertRaises(L.TransitionError):          # trung nguoi
            self.LS.assign(MGR, "BQ1", "E1")
        with self.assertRaises(L.TransitionError):          # nguoi da nghi
            self.LS.assign(MGR, "BQ1", "E3")
        self.LS.assign(MGR, "BQ1", "E2")
        self.lr.lics["BQ1"]["seats"] = 2
        self.repo.emps["E3"]["status"] = "Active"
        with self.assertRaises(L.TransitionError):          # het cho
            self.LS.assign(MGR, "BQ1", "E3")
        self.assertIn((("an@x",), "Bạn được cấp bản quyền Microsoft 365 - xem trong Tài sản của tôi."),
                      self.repo.notes)

    def test_cannot_shrink_below_used(self):
        self.LS.assign(MGR, "BQ1", "E1")
        self.LS.assign(MGR, "BQ1", "E2")
        with self.assertRaises(L.TransitionError):
            self.LS.update(MGR, "BQ1", {"seats": 1})

    def test_cost_edit_finance_only(self):
        with self.assertRaises(A.AccessDenied):
            self.LS.update(MGR, "BQ1", {"cost_per_cycle": 1})
        self.LS.update(FIN, "BQ1", {"cost_per_cycle": 13_000_000})
        self.assertEqual(self.lr.lics["BQ1"]["cost_per_cycle"], 13_000_000)

    def test_fix_wrong_expiry_and_blank_guards(self):
        self.lr.lics["BQ1"].update(alert_stage=C.STAGE_DUE, alert_for_expiry="2026-12-20")
        with self.assertRaises(L.TransitionError):
            self.LS.update(MGR, "BQ1", {"expiry_date": "2025-12-01"})     # truoc dau ky
        self.LS.update(MGR, "BQ1", {"expiry_date": "2026-12-25"})
        x = self.lr.lics["BQ1"]
        self.assertEqual((x.expiry_date, x.alert_stage), ("2026-12-25", None))
        with self.assertRaises(L.TransitionError):
            self.LS.update(MGR, "BQ1", {"license_name": "  "})
        self.LS.update(MGR, "BQ1", {"start_date": ""})                      # de trong = giu nguyen
        self.assertEqual(self.lr.lics["BQ1"]["start_date"], "2025-12-20")

    def test_renew_rules_and_history(self):
        with self.assertRaises(L.TransitionError):
            self.LS.renew(MGR, "BQ1", "2026-12-01")         # truoc han cu
        self.lr.lics["BQ1"].update(alert_stage=C.STAGE_DUE, alert_for_expiry="2026-12-20")
        self.LS.renew(MGR, "BQ1", "2027-12-20", cost=12_500_000, note="gia han nam")
        x = self.lr.lics["BQ1"]
        self.assertEqual((x.expiry_date, x.alert_stage, x.current_term_start), ("2027-12-20", None, "2026-12-20"))
        self.assertEqual(self.lr.ren[0]["old_expiry"], "2026-12-20")

    def test_cancel_revokes_all_and_blocks_assign(self):
        self.LS.assign(MGR, "BQ1", "E1")
        self.assertEqual(self.LS.cancel(MGR, "BQ1")["revoked"], 1)
        with self.assertRaises(L.TransitionError):
            self.LS.assign(MGR, "BQ1", "E2")

    def test_leaver_loses_seats(self):
        self.LS.assign(MGR, "BQ1", "E1")
        self.assertEqual(self.LS.revoke_for_leaver(MGR, "E1", ref_doctype=C.SRC_CLEARANCE, ref_name="CLR1"),
                         ["BQ1"])
        self.assertEqual(self.lr.active_seats(employees=["E1"]), [])


class TestLicenseViews(LicenseCase):
    def test_department_head_sees_only_own_staff_and_no_money(self):
        self.lr.lics["BQ2"] = lic(name="BQ2", license_name="Figma", department="HR")
        self.LS.assign(MGR, "BQ1", "E1")
        self.LS.assign(MGR, "BQ2", "E2")
        head = A.Ctx("h@x", ["Employee"], {"name": "E9"}, ["Data"])
        d = self.LV.licenses_view(head)
        self.assertEqual([r["name"] for r in d["rows"]], ["BQ1"])
        self.assertNotIn("cost_per_cycle", d["rows"][0])
        self.assertNotIn("monthly_cost", d["summary"])
        with self.assertRaises(A.AccessDenied):
            self.LV.license_detail(head, "BQ2")
        self.assertIn("monthly_cost", self.LV.licenses_view(FIN)["summary"])

    def test_staff_cannot_list_but_sees_own_seat(self):
        with self.assertRaises(A.AccessDenied):
            self.LV.licenses_view(STAFF)
        self.LS.assign(MGR, "BQ1", "E1")
        mine = self.LV.my_licenses("E1")
        self.assertEqual(mine[0]["license_name"], "Microsoft 365")
        self.assertNotIn("cost_per_cycle", mine[0])

    def test_filters_and_dashboard_todo(self):
        self.lr.lics["BQ2"] = lic(name="BQ2", license_name="ChatGPT Team", billing_cycle=C.CY_MONTHLY,
                                  current_term_start="2026-11-01", expiry_date="2026-12-01")
        self.lr.lics["BQ3"] = lic(name="BQ3", license_name="Windows", license_type=C.LT_PERPETUAL,
                                  expiry_date=None, billing_cycle=None)
        due = self.LV.licenses_view(MGR, {"stage": "due"})["rows"]
        self.assertEqual(sorted(r["name"] for r in due), ["BQ1", "BQ2"])   # BQ1 con 24 ngay (< 30)
        self.assertEqual([r["name"] for r in self.LV.licenses_view(MGR, {"stage": "perpetual"})["rows"]], ["BQ3"])
        self.assertEqual([r["name"] for r in self.LV.dashboard_block(MGR)["todo"]], ["BQ2", "BQ1"])  # gan han truoc


class TestLicenseJob(LicenseCase):
    def test_alerts_once_and_marks_expired(self):
        from ecentric_workspace.tai_san import jobs
        _fk.db = types.SimpleNamespace(commit=lambda: None, rollback=lambda: None)
        saved_utils = (jobs.getdate, jobs.nowdate)
        jobs.nowdate = lambda: "2026-11-26"
        self.lr.lics["BQ2"] = lic(name="BQ2", license_name="Canva", expiry_date="2026-11-20")
        try:
            self.assertEqual(jobs.license_alerts()["alerts"], 2)   # BQ1 sap het (24 ngay) + BQ2 qua han
            self.assertEqual(self.lr.lics["BQ2"]["status"], C.LS_EXPIRED)
            self.assertEqual(self.lr.lics["BQ1"]["alert_stage"], C.STAGE_DUE)
            self.assertEqual(jobs.license_alerts()["alerts"], 0)   # khong bao lai
        finally:
            jobs.getdate, jobs.nowdate = saved_utils


class TestReview2Fixes(LicenseCase):
    """Ra soat doc lap dot 4 (26/11 toi) - moi test khoa mot loi."""

    def test_locking_read_returns_fresh_row(self):
        from ecentric_workspace.tai_san import repository as Rm
        seen = []
        _fk.db = types.SimpleNamespace(sql=lambda q, p, as_dict=False: seen.append((q, p)) or [Row(name="A1")])
        row = Rm.locked_rows("tabAsset", ["name", "custom_asset_"], "name=%s", ("A1",))
        self.assertEqual(row[0].name, "A1")
        self.assertTrue(seen[0][0].endswith("for update"))
        self.assertIn("`custom_asset_`", seen[0][0])

    def test_job_skips_license_renewed_mid_run(self):
        from ecentric_workspace.tai_san import jobs
        _fk.db = types.SimpleNamespace(commit=lambda: None, rollback=lambda: None)
        self.lr.lics["BQ2"] = lic(name="BQ2", license_name="Canva", expiry_date="2026-11-20")
        stale = self.lr.licenses
        snapshot = [Row(x) for x in self.lr.lics.values()]
        self.lr.lics["BQ2"]["expiry_date"] = "2027-11-20"      # vua gia han sau khi job doc danh sach
        self.LRm.licenses = lambda filters=None: snapshot
        saved = jobs.nowdate
        jobs.nowdate = lambda: "2026-11-26"
        try:
            jobs.license_alerts()
            self.assertEqual(self.lr.lics["BQ2"]["status"], C.LS_ACTIVE)
            self.assertFalse([n for n in self.repo.notes if "Canva" in n[1]])
        finally:
            jobs.nowdate = saved
            self.LRm.licenses = stale

    def test_head_does_not_see_key_location_account_note(self):
        self.lr.lics["BQ1"].update(account="it@x", key_location="Kho mat khau IT", note="gia 12tr")
        self.LS.assign(MGR, "BQ1", "E1")
        head = A.Ctx("h@x", ["Employee"], {"name": "E9"}, ["Data"])
        row = self.LV.licenses_view(head)["rows"][0]
        for k in ("account", "key_location", "note"):
            self.assertNotIn(k, row)
        self.assertEqual(self.LV.licenses_view(MGR)["rows"][0]["key_location"], "Kho mat khau IT")

    def test_update_logged_and_validated(self):
        self.LS.update(MGR, "BQ1", {"seats": 5})
        self.assertIn("seats: 2 → 5", self.lr.logs[-1][1])
        with self.assertRaises(L.TransitionError):
            self.LS.update(MGR, "BQ1", {"seats": "nam"})
        with self.assertRaises(L.TransitionError):
            self.LS.update(MGR, "BQ1", {"department": "Phong Ma"})
        self.LS.update(MGR, "BQ1", {"start_date": "2026-01-05"})
        self.assertEqual(self.lr.lics["BQ1"]["current_term_start"], "2026-01-05")

    def test_assign_refused_when_past_expiry_before_job_runs(self):
        self.lr.lics["BQ1"]["expiry_date"] = "2026-11-20"         # status van Active
        with self.assertRaises(L.TransitionError):
            self.LS.assign(MGR, "BQ1", "E1")

    def test_expired_license_costs_nothing_monthly(self):
        self.assertEqual(LIC.monthly_cost(lic(status=C.LS_EXPIRED)), 0)


class TestByDepartmentFix(unittest.TestCase):
    def test_stock_and_missing_department_are_separate(self):
        from ecentric_workspace.tai_san import reports as RP
        st = C.OPS_STATUS_FIELD
        assets = [{"name": "A", st: C.ST_IN_USE, "custodian": "E1", "department": "Data"},
                  {"name": "B", st: C.ST_IN_USE, "custodian": "E2", "department": None},
                  {"name": "C", st: C.ST_AVAILABLE, "custodian": None, "department": None},
                  {"name": "D", st: C.ST_BROKEN, "custodian": None, "department": "Data"},
                  {"name": "E", st: C.ST_LOST, "custodian": None, "department": None}]
        rows = {r["department"]: (r["count"], r["in_use"]) for r in RP.by_department(assets, {}, (2026, 11), False)}
        self.assertEqual(rows, {"Data": (1, 1), C.NO_DEPT_BUCKET: (1, 1), C.STOCK_BUCKET: (2, 0)})


class TestWiringDot4(unittest.TestCase):
    def test_hooks_patches_and_doctypes(self):
        with open(os.path.join(APP, "hooks.py"), encoding="utf-8") as fh:
            hooks = fh.read()
        self.assertIn('"20 8 * * *"', hooks)
        self.assertIn("ecentric_workspace.tai_san.jobs.license_alerts", hooks)
        self.assertIn('"source": "/it-asset-management-system", "target": "/tai-san"', hooks)
        with open(os.path.join(APP, "patches.txt"), encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        for p in ("ecentric_workspace.tai_san.patches.p003_dot4",
                  "ecentric_workspace.approval_center.patches.p575_tai_san_ban_quyen"):
            self.assertIn(p, lines)
        import json
        for key, name in (("ec_software_license", C.LICENSE_DT), ("ec_software_license_seat", C.LICENSE_SEAT_DT),
                          ("ec_software_license_renewal", C.LICENSE_RENEWAL_DT)):
            with open(os.path.join(APP, "tai_san", "doctype", key, key + ".json"), encoding="utf-8") as fh:
                d = json.load(fh)
            self.assertEqual((d["name"], d["module"]), (name, C.MODULE))
            self.assertEqual(d["field_order"], [f["fieldname"] for f in d["fields"]])
            self.assertFalse([p for p in d["permissions"] if p["role"] != "System Manager"
                              and (p.get("write") or p.get("create"))])
        with open(os.path.join(APP, "tai_san", "doctype", "ec_software_license", "ec_software_license.json"),
                  encoding="utf-8") as fh:
            f = {x["fieldname"]: x.get("options") for x in json.load(fh)["fields"]}
        self.assertEqual(f["category"].split("\n"), list(C.LICENSE_CATEGORIES))
        self.assertEqual(f["billing_cycle"].split("\n"), list(C.BILLING_CYCLES))
        self.assertEqual(f["status"].split("\n"), list(C.LICENSE_STATUSES))


if __name__ == "__main__":
    unittest.main()
