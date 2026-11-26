# Copyright (c) 2026, eCentric and contributors
"""Quan ly tai san dot 1-3: vong doi, khau hao, so lieu Tong quan, va service tren kho GIA
(thay repository bang bo nho) - khong can bench.

    python -m unittest ecentric_workspace.tai_san.tests.test_dot1
"""
import datetime as dt
import json
import os
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
APP = os.path.join(ROOT, "ecentric_workspace")
sys.path.insert(0, ROOT)


def _fake_frappe():
    fk = types.ModuleType("frappe")
    utils = types.ModuleType("frappe.utils")
    utils.nowdate = lambda: "2026-11-26"
    utils.now_datetime = lambda: dt.datetime(2026, 11, 26, 10, 0)
    utils.getdate = lambda d=None: dt.date.fromisoformat(str(d or "2026-11-26")[:10])
    utils.add_days = lambda d, n: utils.getdate(d) + dt.timedelta(days=n)
    utils.strip_html = lambda s: s
    fk.utils = utils
    fk.whitelist = lambda **k: (lambda f: f)
    fk.session = types.SimpleNamespace(user="ops@x")

    class _Err(Exception):
        pass
    fk.ValidationError = fk.PermissionError = fk.DoesNotExistError = _Err
    fk.log_error = lambda *a, **k: None
    fk.throw = lambda msg, exc=None: (_ for _ in ()).throw((exc or _Err)(msg))
    return fk, utils


_fk, _utils = _fake_frappe()
sys.modules.setdefault("frappe", _fk)
sys.modules.setdefault("frappe.utils", _utils)

from ecentric_workspace.tai_san import access as A  # noqa: E402
from ecentric_workspace.tai_san import constants as C  # noqa: E402
from ecentric_workspace.tai_san import depreciation as D  # noqa: E402
from ecentric_workspace.tai_san import lifecycle as L  # noqa: E402
from ecentric_workspace.tai_san import reports as RP  # noqa: E402


class Row(dict):
    __getattr__ = dict.get


# ------------------------------------------------------------------ vong doi --
class TestLifecycle(unittest.TestCase):
    def test_assign_from_available_sets_holder(self):
        p = L.plan(C.A_ASSIGN, C.ST_AVAILABLE, None, new_holder="E1")
        self.assertEqual((p["to_status"], p["holder"], p["event"]), (C.ST_IN_USE, "E1", C.EV_ASSIGN))

    def test_assign_needs_employee(self):
        with self.assertRaises(L.TransitionError):
            L.plan(C.A_ASSIGN, C.ST_AVAILABLE, None)

    def test_cannot_assign_in_use(self):
        with self.assertRaises(L.TransitionError) as e:
            L.plan(C.A_ASSIGN, C.ST_IN_USE, "E1", new_holder="E2")
        self.assertIn("Đang dùng", str(e.exception))

    def test_return_clears_holder_and_goes_to_check(self):
        p = L.plan(C.A_RETURN, C.ST_IN_USE, "E1")
        self.assertEqual((p["to_status"], p["holder"]), (C.ST_PENDING_CHECK, None))

    def test_repair_done_back_to_holder_or_stock(self):
        self.assertEqual(L.plan(C.A_REPAIR_DONE, C.ST_UNDER_REPAIR, "E1")["to_status"], C.ST_IN_USE)
        self.assertEqual(L.plan(C.A_REPAIR_DONE, C.ST_UNDER_REPAIR, None)["to_status"], C.ST_AVAILABLE)

    def test_transfer_to_same_person_refused(self):
        with self.assertRaises(L.TransitionError):
            L.plan(C.A_TRANSFER, C.ST_IN_USE, "E1", new_holder="E1")

    def test_component_cannot_be_assigned_alone(self):
        with self.assertRaises(L.TransitionError):
            L.plan(C.A_ASSIGN, C.ST_AVAILABLE, None, new_holder="E1", is_component=True)

    def test_every_status_reachable_and_every_action_labelled(self):
        targets = {to for _src, to, _h, _e in L.TRANSITIONS.values() if to}
        targets |= {C.ST_IN_USE, C.ST_AVAILABLE}
        self.assertEqual(targets, set(C.STATUSES))
        self.assertEqual(set(L.TRANSITIONS), set(C.ACTION_LABELS))
        for _src, _to, _h, ev in L.TRANSITIONS.values():
            self.assertIn(ev, C.EVENT_TYPES)

    def test_disposed_is_terminal(self):
        self.assertEqual(L.allowed_actions(C.ST_DISPOSED), [])

    def test_event_types_match_doctype(self):
        with open(os.path.join(APP, "tai_san", "doctype", "ec_asset_event", "ec_asset_event.json"),
                  encoding="utf-8") as fh:
            opts = [f for f in json.load(fh)["fields"] if f["fieldname"] == "event_type"][0]["options"]
        self.assertEqual(opts.split("\n"), list(C.EVENT_TYPES))
        self.assertEqual(set(C.EVENT_LABELS), set(C.EVENT_TYPES))


# ----------------------------------------------------------------- khau hao --
def laptop(**kw):
    a = {"name": "A1", "net_purchase_amount": 10_000_000, "available_for_use_date": "2025-02-01",
         "purchase_date": "2025-02-01", C.OPS_STATUS_FIELD: C.ST_IN_USE, "asset_category": "LAPTOP"}
    a.update(kw)
    return a


class TestDepreciation(unittest.TestCase):
    def test_doc_example_22_of_36(self):
        d = D.compute(laptop(), 36, (2026, 11))
        self.assertEqual(d["months_done"], 22)
        self.assertEqual(d["monthly"], 277778.0)
        self.assertEqual(d["end"], "2028-01")
        self.assertAlmostEqual(d["accumulated"] + d["nbv"], 10_000_000)
        self.assertEqual(d["this_month"], 277778.0)

    def test_schedule_sums_exactly(self):
        rows = D.schedule(10_000_000, 0, 36, (2025, 2))
        self.assertEqual(len(rows), 36)
        self.assertEqual(sum(rows), 10_000_000)
        self.assertEqual(sum(D.schedule(650_000, 50_000, 24, (2026, 3))), 600_000)

    def test_fully_depreciated_after_life(self):
        d = D.compute(laptop(), 36, (2028, 5))
        self.assertTrue(d["fully_depreciated"])
        self.assertEqual(d["nbv"], 0)
        self.assertEqual(d["this_month"], 0)

    def test_before_start_nothing(self):
        d = D.compute(laptop(), 36, (2025, 1))
        self.assertEqual((d["months_done"], d["accumulated"], d["this_month"]), (0, 0, 0))

    def test_end_date_stops(self):
        d = D.compute(laptop(ec_end_date="2025-04-15"), 36, (2026, 11))
        self.assertEqual(d["months_done"], 3)
        self.assertEqual(d["this_month"], 0)
        self.assertEqual(D.compute(laptop(ec_end_date="2025-04-15"), 36, (2025, 4))["this_month"], 277778.0)

    def test_life_resolution(self):
        self.assertEqual(D.life_of(None, 24), 24)
        self.assertEqual(D.life_of(12, 24), 12)
        self.assertEqual(D.life_of(None, None), C.DEFAULT_LIFE_MONTHS)
        self.assertEqual(D.compute(laptop(ec_useful_life_months=12), 36, (2026, 11))["fully_depreciated"], True)

    def test_custom_start_and_salvage(self):
        d = D.compute(laptop(ec_depreciation_start="2026-01-10", ec_salvage_value=1_000_000), 36, (2026, 11))
        self.assertEqual(d["months_done"], 11)
        self.assertEqual(d["monthly"], 250000.0)

    def test_no_price(self):
        self.assertEqual(D.compute(laptop(net_purchase_amount=0), 36)["accumulated"], 0)

    def test_curve_ends_at_salvage(self):
        c = D.nbv_curve(laptop(), 36)
        self.assertEqual(c[-1], ("2028-01", 0.0))
        self.assertEqual(len(D.nbv_curve(laptop(), 36, points=12)) <= 14, True)


# ----------------------------------------------------------------- Tong quan --
class TestReports(unittest.TestCase):
    def setUp(self):
        self.assets = [
            laptop(name="A1"),
            laptop(name="A2", **{C.OPS_STATUS_FIELD: C.ST_AVAILABLE}),
            laptop(name="R1", asset_category="RAM", net_purchase_amount=650_000,
                   **{C.INSTALLED_ON_FIELD: "A1"}),
            laptop(name="A3", **{C.OPS_STATUS_FIELD: C.ST_DISPOSED}),
            laptop(name="T1", ec_ownership=C.OWN_RENTED, ec_monthly_rent=1_500_000,
                   net_purchase_amount=0),
        ]
        self.cats = {"LAPTOP": Row(ec_default_life_months=36), "RAM": Row(ec_default_life_months=24)}

    def test_kpis_exclude_installed_components_and_disposed(self):
        k = RP.kpis(self.assets)
        self.assertEqual(k["total"], 3)
        self.assertEqual(k["components_installed"], 1)
        self.assertEqual(k["available"], 1)

    def test_finance_month_cost(self):
        f = RP.finance(self.assets, self.cats, (2026, 11), {"2026-11": 1_200_000})
        mc = f["month_cost"]
        self.assertEqual(mc["rent"], 1_500_000)
        self.assertEqual(mc["repair"], 1_200_000)
        self.assertAlmostEqual(mc["depreciation"], 277778 * 2 + round(650_000 / 24))
        self.assertAlmostEqual(mc["total"], mc["depreciation"] + mc["repair"] + mc["rent"])
        self.assertAlmostEqual(f["nbv"], f["gross"] - f["accumulated"])

    def test_cost_series_12_months_oldest_first(self):
        s = RP.cost_series(self.assets, self.cats, (2026, 11), {})
        self.assertEqual(len(s), 12)
        self.assertEqual((s[0]["month"], s[-1]["month"]), ("2025-12", "2026-11"))

    def test_by_department_hides_money_without_cost_right(self):
        rows = RP.by_department(self.assets, self.cats, (2026, 11), with_cost=False)
        self.assertNotIn("nbv", rows[0])
        self.assertEqual(rows[0]["department"], C.STOCK_BUCKET)

    def test_age_buckets(self):
        ages = {b["bucket"]: b["count"] for b in RP.age_buckets(self.assets, (2026, 11))}
        self.assertEqual(ages["1–2 năm"], 3)

    def test_warranty_and_idle(self):
        a = laptop(name="W", ec_warranty_until="2026-12-20")
        self.assertEqual(RP.warranty_alerts([a], dt.date(2026, 11, 26))[0]["days_left"], 24)
        idle = RP.idle_assets([laptop(name="I", **{C.OPS_STATUS_FIELD: C.ST_AVAILABLE})], {},
                              dt.date(2026, 11, 26))
        self.assertEqual(idle[0]["asset"], "I")


# ------------------------------------------------------------ service (kho gia) --
class FakeRepo:
    """Thay cac ham repository dung toi trong service / repair / component / flows."""

    def __init__(self, assets, employees=None, categories=None):
        self.assets = {a["name"]: Row(a) for a in assets}
        self.emps = {k: Row(v) for k, v in (employees or {}).items()}
        self.cats = {k: Row(v) for k, v in (categories or {}).items()}
        self.events, self.repairs_, self.notes, self.damage_ = [], {}, [], {}

    # tai san
    def asset(self, name):
        if name not in self.assets:
            raise _fk.DoesNotExistError(name)
        return Row(self.assets[name])

    def lock_asset(self, name):
        pass

    def set_asset(self, name, values):
        self.assets[name].update(values)

    def components_of(self, parent):
        return [Row(a) for a in self.assets.values() if a.get(C.INSTALLED_ON_FIELD) == parent]

    def employees(self, ids):
        return {i: self.emps[i] for i in ids if i in self.emps}

    def employee_user(self, e):
        return (self.emps.get(e) or {}).get("user_id")

    def categories(self):
        return self.cats

    def insert_event(self, row):
        self.events.append(dict(row))
        return "EV%d" % len(self.events)

    def unacknowledged_events(self, employee):
        return [Row(name="EV%d" % (i + 1), asset=e["asset"]) for i, e in enumerate(self.events)
                if e.get("to_employee") == employee and e["event_type"] in (C.EV_ASSIGN, C.EV_TRANSFER)
                and not e.get("acknowledged_at")]

    def set_acknowledged(self, name):
        self.events[int(name[2:]) - 1]["acknowledged_at"] = "now"

    def notify(self, users, subject, link=None):
        self.notes.append((tuple(users), subject))

    def notify_role(self, role, subject, link=None):
        self.notes.append((role, subject))

    # sua chua
    def open_repair_of(self, asset):
        return next((n for n, r in self.repairs_.items() if r["asset"] == asset
                     and r["status"] in (C.REP_OPEN, C.REP_IN_REPAIR)), None)

    def insert_repair(self, values):
        name = "TS-SC-%d" % (len(self.repairs_) + 1)
        self.repairs_[name] = dict(values, name=name)
        return name

    def repair(self, name):
        return Row(self.repairs_[name])

    def set_repair(self, name, values):
        self.repairs_[name].update(values)

    def lock_repair(self, name):
        pass

    def repairs_using_damage_request(self, name):
        return [n for n, r in self.repairs_.items() if r.get("damage_request") == name
                and r["status"] != C.REP_CANCELLED]

    def damage_request(self, name):
        return Row(self.damage_.get(name)) if name in self.damage_ else None

    def specs(self, name):
        return []

    def replace_specs(self, name, rows):
        self.assets[name]["_specs"] = rows


def _install(repo):
    from ecentric_workspace.tai_san import repository as R
    saved = {}
    for n in dir(FakeRepo):
        if not n.startswith("_") and hasattr(R, n) and n not in ("repairs_", "damage_"):
            saved[n] = getattr(R, n)
            setattr(R, n, getattr(repo, n))
    return saved


def _restore(saved):
    from ecentric_workspace.tai_san import repository as R
    for n, f in saved.items():
        setattr(R, n, f)


MGR = A.Ctx("ops@x", [C.ROLE_MANAGER], {"name": "E0"})
STAFF = A.Ctx("an@x", ["Employee"], {"name": "E1"})
FIN = A.Ctx("fin@x", [C.ROLE_HOF], {"name": "E9"})


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepo(
            [laptop(name="L1", **{C.OPS_STATUS_FIELD: C.ST_AVAILABLE, "custodian": None}),
             laptop(name="L2", **{C.OPS_STATUS_FIELD: C.ST_AVAILABLE, "custodian": None}),
             laptop(name="R1", asset_category="RAM", net_purchase_amount=650_000,
                    **{C.OPS_STATUS_FIELD: C.ST_AVAILABLE, "custodian": None})],
            employees={"E1": {"name": "E1", "employee_name": "An", "department": "Data", "user_id": "an@x",
                              "status": "Active"},
                       "E2": {"name": "E2", "employee_name": "Binh", "department": "HR", "user_id": "b@x",
                              "status": "Active"}},
            categories={"LAPTOP": {"ec_is_component": 0}, "RAM": {"ec_is_component": 1}})
        self.saved = _install(self.repo)
        from ecentric_workspace.tai_san import component_service, repair_service, service
        self.S, self.RS, self.CS = service, repair_service, component_service

    def tearDown(self):
        _restore(self.saved)


class TestService(ServiceCase):
    def test_assign_writes_holder_department_event_and_notifies(self):
        self.S.transition(MGR, "L1", C.A_ASSIGN, employee="E1", note="NV mới")
        a = self.repo.assets["L1"]
        self.assertEqual((a[C.OPS_STATUS_FIELD], a["custodian"], a["department"]), (C.ST_IN_USE, "E1", "Data"))
        ev = self.repo.events[-1]
        self.assertEqual((ev["event_type"], ev["from_status"], ev["to_employee"]),
                         (C.EV_ASSIGN, C.ST_AVAILABLE, "E1"))
        self.assertEqual(self.repo.notes[-1][0], ("an@x",))

    def test_staff_cannot_assign(self):
        with self.assertRaises(A.AccessDenied):
            self.S.transition(STAFF, "L1", C.A_ASSIGN, employee="E1")
        self.assertEqual(self.repo.events, [])

    def test_only_finance_disposes(self):
        with self.assertRaises(A.AccessDenied):
            self.S.transition(MGR, "L1", C.A_DISPOSE)
        self.S.transition(FIN, "L1", C.A_DISPOSE)
        self.assertEqual(self.repo.assets["L1"][C.END_DATE_FIELD], "2026-11-26")

    def test_component_follows_mother(self):
        self.CS.install(MGR, "R1", "L1")
        self.assertEqual(self.repo.assets["R1"][C.INSTALLED_ON_FIELD], "L1")
        self.S.transition(MGR, "L1", C.A_ASSIGN, employee="E1")
        self.assertEqual((self.repo.assets["R1"][C.OPS_STATUS_FIELD], self.repo.assets["R1"]["custodian"]),
                         (C.ST_IN_USE, "E1"))
        comp_events = [e for e in self.repo.events if e["asset"] == "R1" and e["event_type"] == C.EV_ASSIGN]
        self.assertEqual(comp_events[0]["related_asset"], "L1")
        self.CS.remove(MGR, "R1")
        self.assertEqual((self.repo.assets["R1"][C.OPS_STATUS_FIELD], self.repo.assets["R1"]["custodian"]),
                         (C.ST_AVAILABLE, None))

    def test_non_component_cannot_be_installed(self):
        with self.assertRaises(L.TransitionError):
            self.CS.install(MGR, "L2", "L1")

    def test_reserve_then_assign_clears_reservation(self):
        self.S.transition(MGR, "L1", C.A_RESERVE, employee="E2")
        self.assertEqual(self.repo.assets["L1"][C.RESERVED_FOR_FIELD], "E2")
        self.S.transition(MGR, "L1", C.A_ASSIGN, employee="E2")
        self.assertIsNone(self.repo.assets["L1"][C.RESERVED_FOR_FIELD])

    def test_acknowledge_only_by_holder(self):
        self.S.transition(MGR, "L1", C.A_ASSIGN, employee="E1")
        with self.assertRaises(A.AccessDenied):
            self.S.acknowledge(A.Ctx("b@x", [], {"name": "E2"}), "L1")
        self.assertEqual(self.S.acknowledge(STAFF, "L1"), {"acknowledged": True})
        self.assertEqual(self.repo.events[-1]["event_type"], C.EV_ACK)
        self.assertEqual(self.S.acknowledge(STAFF, "L1"), {"acknowledged": False})

    def test_report_full_damage_breaks_but_keeps_holder(self):
        self.S.transition(MGR, "L1", C.A_ASSIGN, employee="E1")
        self.S.report_damage(STAFF, "L1", C.DAMAGE_FULL, ["Màn hình"], "vỡ")
        a = self.repo.assets["L1"]
        self.assertEqual((a[C.OPS_STATUS_FIELD], a["custodian"], a["ec_condition"]),
                         (C.ST_BROKEN, "E1", C.COND_FULL))

    def test_report_partial_keeps_in_use(self):
        self.S.transition(MGR, "L1", C.A_ASSIGN, employee="E1")
        self.S.report_damage(STAFF, "L1", C.DAMAGE_PARTIAL, ["Bàn phím"])
        self.assertEqual(self.repo.assets["L1"][C.OPS_STATUS_FIELD], C.ST_IN_USE)

    def test_life_over_36_refused_under_threshold(self):
        with self.assertRaises(L.TransitionError):
            self.S.update_info(FIN, "L1", {"ec_useful_life_months": 48})

    def test_manager_cannot_change_price(self):
        with self.assertRaises(A.AccessDenied):
            self.S.update_info(MGR, "L1", {"net_purchase_amount": 1})


class TestRepair(ServiceCase):
    def test_repair_cycle_with_loaner(self):
        self.S.transition(MGR, "L1", C.A_ASSIGN, employee="E1")
        res = self.RS.open_repair(MGR, "L1", {"damage_level": C.DAMAGE_FULL, "repair_mode": C.MODE_WARRANTY,
                                              "vendor": "Dell", "loaner_asset": "L2", "expected_cost": 0})
        self.assertEqual(self.repo.assets["L1"][C.OPS_STATUS_FIELD], C.ST_UNDER_REPAIR)
        self.assertEqual(self.repo.assets["L2"]["custodian"], "E1")
        self.RS.close_repair(MGR, res["repair"], {"result": C.RES_FIXED, "actual_cost": 0})
        self.assertEqual((self.repo.assets["L1"][C.OPS_STATUS_FIELD], self.repo.assets["L1"]["custodian"]),
                         (C.ST_IN_USE, "E1"))
        self.assertEqual(self.repo.assets["L2"][C.OPS_STATUS_FIELD], C.ST_PENDING_CHECK)

    def test_costly_repair_needs_approval(self):
        res = self.RS.open_repair(MGR, "L1", {"expected_cost": 5_000_000})
        self.assertTrue(res["need_approval"])
        self.assertEqual(self.repo.repairs_, {})

    def test_unfixable_goes_broken(self):
        res = self.RS.open_repair(MGR, "L1", {"expected_cost": 100})
        self.RS.close_repair(MGR, res["repair"], {"result": C.RES_UNFIXABLE})
        self.assertEqual(self.repo.assets["L1"][C.OPS_STATUS_FIELD], C.ST_BROKEN)

    def test_one_open_repair_per_asset(self):
        self.RS.open_repair(MGR, "L1", {})
        with self.assertRaises(L.TransitionError):
            self.RS.open_repair(MGR, "L1", {})


class TestWiringDot1(unittest.TestCase):
    def test_hooks_cron_and_patch(self):
        with open(os.path.join(APP, "hooks.py"), encoding="utf-8") as fh:
            hooks = fh.read()
        self.assertIn('"40 0 * * *"', hooks)
        self.assertIn("ecentric_workspace.tai_san.jobs.return_due_today", hooks)
        self.assertIn("ecentric_workspace.tai_san.jobs.monthly_snapshot", hooks)
        with open(os.path.join(APP, "patches.txt"), encoding="utf-8") as fh:
            self.assertIn("ecentric_workspace.tai_san.patches.p002_dot1", fh.read().split("\n"))

    def test_new_doctypes_in_module(self):
        for key, name in (("ec_asset_event", C.EVENT_DT), ("ec_asset_repair", C.REPAIR_DT),
                          ("ec_asset_monthly", C.MONTHLY_DT), ("ec_asset_count", C.COUNT_DT),
                          ("ec_asset_count_item", C.COUNT_ITEM_DT)):
            with open(os.path.join(APP, "tai_san", "doctype", key, key + ".json"), encoding="utf-8") as fh:
                d = json.load(fh)
            self.assertEqual((d["name"], d["module"]), (name, C.MODULE))
            self.assertEqual(d["field_order"], [f["fieldname"] for f in d["fields"]])

    def test_repair_selects_match_constants(self):
        with open(os.path.join(APP, "tai_san", "doctype", "ec_asset_repair", "ec_asset_repair.json"),
                  encoding="utf-8") as fh:
            f = {x["fieldname"]: x.get("options") for x in json.load(fh)["fields"]}
        self.assertEqual(f["status"].split("\n"), list(C.REPAIR_STATUSES))
        self.assertEqual(f["repair_mode"].split("\n"), list(C.REPAIR_MODES))
        self.assertEqual([x for x in f["result"].split("\n") if x], list(C.REPAIR_RESULTS))

    def test_api_has_no_actor_param(self):
        import ast
        with open(os.path.join(APP, "tai_san", "controllers", "api.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]:
            names = [a.arg for a in fn.args.args]
            self.assertFalse({"user", "actor"} & set(names), fn.name)


class FakeCount:
    def __init__(self, items):
        self.name, self.title, self.status, self.started_on = "TS-KK-1", "Kiem ke 11/2026", C.CNT_OPEN, "2026-11-20"
        self.items = [types.SimpleNamespace(**dict(dict.fromkeys(
            ("result", "actual_holder", "self_confirmed", "note", "counted_at", "counted_by")),
            name="CI%d" % n, **i)) for n, i in enumerate(items)]


class TestCount(ServiceCase):
    def setUp(self):
        super().setUp()
        from ecentric_workspace.tai_san import repository as R
        self.R, self.cnt = R, FakeCount([
            {"asset": "L1", "expected_holder": "E1", "expected_status": C.ST_IN_USE},
            {"asset": "L2", "expected_holder": None, "expected_status": C.ST_AVAILABLE}])
        self.repo.assets["L1"][C.TAG_FIELD] = "EC-L1"
        self.repo.assets["L1"]["asset_name"] = "Dell 5440"
        self.cnt_saved = {n: getattr(R, n) for n in ("open_count", "count_doc", "assets", "lock_count_item",
                                                      "set_count_item", "set_count")}
        R.open_count = lambda: Row(name=self.cnt.name, title=self.cnt.title, started_on=self.cnt.started_on)
        R.count_doc = lambda name: self.cnt
        R.assets = lambda filters=None: [Row(a) for a in self.repo.assets.values()]
        items = {i.name: i for i in self.cnt.items}
        R.lock_count_item = lambda cnt, asset: next((Row(vars(i)) for i in self.cnt.items if i.asset == asset), None)
        R.set_count_item = lambda name, values: vars(items[name]).update(values)
        R.set_count = lambda name, values: vars(self.cnt).update(values)
        from ecentric_workspace.tai_san import count_service
        self.KK = count_service

    def tearDown(self):
        for n, f in self.cnt_saved.items():
            setattr(self.R, n, f)
        super().tearDown()

    def test_summary_has_names_and_rights(self):
        d = self.KK.summary(FIN)
        r = {x["asset"]: x for x in d["rows"]}
        self.assertEqual((r["L1"]["tag"], r["L1"]["asset_name"], r["L1"]["expected_holder_name"]),
                         ("EC-L1", "Dell 5440", "An"))
        self.assertFalse(d["can"]["manage"])
        self.assertTrue(self.KK.summary(MGR)["can"]["manage"])

    def test_closed_count_still_reports_rights(self):
        self.R.open_count = lambda: None
        self.assertEqual(self.KK.summary(MGR)["count"], None)
        self.assertTrue(self.KK.summary(MGR)["can"]["manage"])

    def test_self_confirm_survives_reload(self):
        self.KK.self_confirm(STAFF, "L1", ok=False, note="man hinh vo")
        self.assertEqual(self.KK.my_confirmations("E1"), {"L1": "wrong"})
        self.assertEqual(self.KK.my_confirmations("E2"), {})

    def test_cannot_confirm_someone_elses_machine(self):
        with self.assertRaises(A.AccessDenied):
            self.KK.self_confirm(STAFF, "L2")


class TestApiEnvelope(unittest.TestCase):
    def test_denied_is_flagged_for_redirect(self):
        _fk.db = types.SimpleNamespace(rollback=lambda: None)
        from ecentric_workspace.tai_san.controllers import api
        saved = api._ctx
        api._ctx = lambda: STAFF
        try:
            env = api._run(lambda c: A.require(False, "Chi quan ly."))
            self.assertEqual((env["success"], env["data"]), (False, {"denied": True}))
            env = api._run(lambda c: (_ for _ in ()).throw(L.TransitionError("Sai trang thai.")))
            self.assertEqual((env["success"], env["data"]), (False, None))
        finally:
            api._ctx = saved

    def test_shell_rail_roles_match_cost_roles(self):
        from ecentric_workspace.shell import nav
        self.assertEqual(tuple(nav._TS_COST_ROLES), tuple(C.COST_ROLES))
        keys = [it["key"] for it in nav.HOME_PORTAL_ITEMS]
        self.assertNotIn("home.portal.tai_san", keys)  # alias doi vo shell cua module khac


class TestReviewFixes(ServiceCase):
    """Cac loi ban ra soat doc lap 26/11 tim ra - moi test khoa mot loi."""

    def _install_ram(self, parent="L1"):
        self.CS.install(MGR, "R1", parent)

    def test_installed_component_refuses_every_own_action(self):
        self._install_ram()
        for act in (C.A_BREAK, C.A_LOST, C.A_DISPOSE):
            with self.assertRaises(L.TransitionError):
                self.S.transition(FIN if act == C.A_DISPOSE else MGR, "R1", act)

    def test_cascade_skips_diverged_component(self):
        self._install_ram()
        self.repo.assets["R1"][C.OPS_STATUS_FIELD] = C.ST_DISPOSED  # du lieu cu da lech
        self.S.transition(MGR, "L1", C.A_ASSIGN, employee="E1")
        self.assertEqual(self.repo.assets["R1"][C.OPS_STATUS_FIELD], C.ST_DISPOSED)

    def test_cannot_install_into_disposed_machine(self):
        self.repo.assets["L1"][C.OPS_STATUS_FIELD] = C.ST_DISPOSED
        with self.assertRaises(L.TransitionError):
            self._install_ram()

    def test_unlinked_user_cannot_break_stock_machine(self):
        nobody = A.Ctx("x@x", ["Employee"], None)
        with self.assertRaises(A.AccessDenied):
            self.S.report_damage(nobody, "L1", C.DAMAGE_FULL)
        self.assertEqual(self.repo.assets["L1"][C.OPS_STATUS_FIELD], C.ST_AVAILABLE)

    def test_dispose_after_lost_keeps_end_date(self):
        self.repo.assets["L1"][C.OPS_STATUS_FIELD] = C.ST_LOST
        self.repo.assets["L1"][C.END_DATE_FIELD] = "2026-03-10"
        self.S.transition(FIN, "L1", C.A_DISPOSE)
        self.assertEqual(self.repo.assets["L1"][C.END_DATE_FIELD], "2026-03-10")

    def test_assign_to_left_employee_refused(self):
        self.repo.emps["E2"]["status"] = "Left"
        with self.assertRaises(L.TransitionError):
            self.S.transition(MGR, "L1", C.A_ASSIGN, employee="E2")

    def test_manager_cannot_set_rent(self):
        with self.assertRaises(A.AccessDenied):
            self.S.update_info(MGR, "L1", {"ec_monthly_rent": 500_000})

    def test_money_rules_shared(self):
        with self.assertRaises(L.TransitionError):
            self.S.validate_money(10_000_000, 120)
        with self.assertRaises(L.TransitionError):
            self.S.validate_money(50_000_000, 0)
        self.S.validate_money(50_000_000, 60)
        with self.assertRaises(L.TransitionError):
            self.S.validate_money(10_000_000, 36, salvage=20_000_000)

    def test_money_change_not_written_in_log(self):
        self.S.update_info(FIN, "L1", {"net_purchase_amount": 9_000_000})
        note = self.repo.events[-1]["note"]
        self.assertNotIn("9000000", note)
        self.assertIn("net_purchase_amount", note)

    def test_unapproved_damage_request_does_not_skip_threshold(self):
        self.repo.damage_["DL1"] = {"name": "DL1", "asset_code": "L1", "estimated_repair_cost": 9_000_000,
                                    "approval_status": "Pending"}
        with self.assertRaises(L.TransitionError):
            self.RS.open_repair(MGR, "L1", {"expected_cost": 5_000_000, "damage_request": "DL1"})
        self.repo.damage_["DL2"] = dict(self.repo.damage_["DL1"], name="DL2", asset_code="L2",
                                        approval_status=C.APPROVED)
        with self.assertRaises(L.TransitionError):
            self.RS.open_repair(MGR, "L1", {"expected_cost": 5_000_000, "damage_request": "DL2"})

    def test_close_over_threshold_needs_approval_or_finance(self):
        res = self.RS.open_repair(MGR, "L1", {"expected_cost": 1_000_000})
        with self.assertRaises(L.TransitionError):
            self.RS.close_repair(MGR, res["repair"], {"result": C.RES_FIXED, "actual_cost": 4_000_000})
        self.repo.damage_["DL3"] = {"name": "DL3", "asset_code": "L1", "estimated_repair_cost": 4_500_000,
                                    "approval_status": C.APPROVED}
        self.repo.repairs_[res["repair"]]["damage_request"] = "DL3"
        self.RS.close_repair(MGR, res["repair"], {"result": C.RES_FIXED, "actual_cost": 4_000_000})
        self.assertEqual(self.repo.repairs_[res["repair"]]["actual_cost"], 4_000_000)
        self.assertNotIn("4000000", self.repo.events[-1]["note"] or "")

    def test_full_damage_report_drags_installed_component(self):
        self.S.transition(MGR, "L1", C.A_ASSIGN, employee="E1")
        self._install_ram()
        self.S.report_damage(STAFF, "L1", C.DAMAGE_FULL)
        self.assertEqual(self.repo.assets["R1"][C.OPS_STATUS_FIELD], C.ST_BROKEN)
        self.RS.open_repair(MGR, "L1", {})
        self.assertEqual(self.repo.assets["R1"][C.OPS_STATUS_FIELD], C.ST_UNDER_REPAIR)

    def test_damage_request_single_use_and_serial_match(self):
        self.repo.assets["L1"][C.SERIAL_FIELD] = "SN-123"
        self.repo.damage_["DL4"] = {"name": "DL4", "asset_code": " sn-123 ", "estimated_repair_cost": 5_000_000,
                                    "approval_status": C.APPROVED}
        with self.assertRaises(L.TransitionError):  # vuot so da duyet
            self.RS.open_repair(MGR, "L1", {"expected_cost": 6_000_000, "damage_request": "DL4"})
        res = self.RS.open_repair(MGR, "L1", {"expected_cost": 5_000_000, "damage_request": "DL4"})
        self.RS.close_repair(MGR, res["repair"], {"result": C.RES_FIXED, "actual_cost": 5_000_000})
        with self.assertRaises(L.TransitionError):  # dung lai phieu
            self.RS.open_repair(MGR, "L1", {"expected_cost": 5_000_000, "damage_request": "DL4"})

    def test_repair_row_hides_cost_without_right(self):
        from ecentric_workspace.tai_san import views
        rep = Row(name="R", asset="L1", status=C.REP_IN_REPAIR, expected_cost=1, actual_cost=2,
                  expected_return=None, repair_mode=C.MODE_EXTERNAL)
        head = A.Ctx("h@x", ["Employee"], {"name": "E5"}, ["Data"])
        self.assertNotIn("actual_cost", views._repair_row(head, rep, {}))
        self.assertIn("actual_cost", views._repair_row(FIN, rep, {}))


class TestMonthlySnapshot(unittest.TestCase):
    def test_depreciation_is_difference_of_accumulated_and_rerun_skips_done(self):
        from ecentric_workspace.tai_san import jobs, repository as R
        a = laptop(name="L1")
        rows = []
        patch = {"monthly_assets": lambda m: {r["asset"] for r in rows if r["month"] == m},
                 "monthly_accumulated": lambda m: {"L1": 1_000_000.0},  # thang truoc chot thieu (vd may bi mat)
                 "categories": lambda: {"LAPTOP": {"ec_default_life_months": 36}},
                 "repairs": lambda f=None, **k: [], "assets": lambda f=None: [Row(a)],
                 "insert_monthly": rows.append}
        saved = {k: getattr(R, k) for k in patch}
        _fk.db = types.SimpleNamespace(commit=lambda: None, rollback=lambda: None)
        try:
            for k, v in patch.items():
                setattr(R, k, v)
            jobs.monthly_snapshot("2026-10")
            d = D.compute(a, 36, (2026, 10))
            self.assertAlmostEqual(rows[0]["depreciation"], d["accumulated"] - 1_000_000, places=2)
            jobs.monthly_snapshot("2026-10")
            self.assertEqual(len(rows), 1)
        finally:
            for k, v in saved.items():
                setattr(R, k, v)

    def test_event_doctype_cannot_be_written_by_roles(self):
        with open(os.path.join(APP, "tai_san", "doctype", "ec_asset_event", "ec_asset_event.json"),
                  encoding="utf-8") as fh:
            d = json.load(fh)
        self.assertFalse([p for p in d["permissions"] if p.get("create") or p.get("write")])
        self.assertEqual([f.get("read_only") for f in d["fields"] if f["fieldname"] == "acknowledged_at"], [1])


if __name__ == "__main__":
    unittest.main()
