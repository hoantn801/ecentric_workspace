# Copyright (c) 2026, eCentric and contributors
"""nhip_gui (08/10/2026): gio yen lang 21:00-09:00 + gop tin Teams/web push.
Site-free: frappe stub voi bang Delivery Log trong RAM; nap module bang spec (khong dung
chung stub voi test_notification_center)."""
import datetime as dt
import importlib.util
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_NHIP = os.path.join(_HERE, "..", "nhip_gui.py")
_EVENTS = os.path.join(_HERE, "..", "events.py")
DT = "EC Notification Delivery Log"
OPTS = "Pending\nSent\nFailed\nSkipped\nSuppressed\nDuplicate\nHeld\nMerged"


class _Row(dict):
    __getattr__ = dict.get


def _match(row, filters):
    for k, v in (filters or {}).items():
        val = row.get(k)
        if isinstance(v, list):
            op, arg = v[0], v[1]
            if op == "in" and val not in arg:
                return False
            if op == ">=" and not (val is not None and val >= arg):
                return False
            if op == "<=" and not (val is not None and val <= arg):
                return False
        elif val != v:
            return False
    return True


def _stub(now, opts=OPTS):
    fr = types.ModuleType("frappe")
    fr.rows, fr.enq, fr.logs_read, fr.errors = [], [], set(), []
    fr.clock = [now]
    fr.flags = types.SimpleNamespace()
    fr.session = types.SimpleNamespace(user="x@e.c")
    fr.conf = {}
    fr.get_conf = lambda: fr.conf
    fr.log_error = lambda *a, **k: fr.errors.append(k or a)
    fr.get_traceback = lambda: "tb"
    fr.get_meta = lambda d: types.SimpleNamespace(
        get_field=lambda f: types.SimpleNamespace(options=opts))

    def get_all(doctype, filters=None, fields=None, pluck=None, order_by=None,
                limit_page_length=None, limit=None):
        if doctype == "Notification Log":
            names = [n for n in filters["name"][1] if n in fr.logs_read]
            return names if pluck else [{"name": n} for n in names]
        out = [r for r in fr.rows if _match(r, filters)]
        if order_by:
            key = order_by.split()[0]
            out.sort(key=lambda r: (r.get(key) is None, r.get(key)))
        n = limit_page_length or limit
        if n:
            out = out[:n]
        if pluck:
            return [r[pluck] for r in out]
        return [_Row({f: r.get(f) for f in (fields or ["name"])}) for r in out]
    fr.get_all = get_all

    def set_value(doctype, name, vals):
        for r in fr.rows:
            if r["name"] == name:
                r.update(vals)
    fr.db = types.SimpleNamespace(set_value=set_value,
                                  exists=lambda d, f: any(_match(r, f) for r in fr.rows))

    class _Doc(_Row):
        def insert(self, ignore_permissions=False):
            if self.get("status") not in opts.split("\n"):
                raise ValueError("status khong hop le: %s" % self.get("status"))
            if any(r["idempotency_key"] == self["idempotency_key"] for r in fr.rows):
                raise ValueError("trung idempotency_key")
            self["name"] = "DL-%03d" % (len(fr.rows) + 1)
            self["creation"] = fr.clock[0]
            fr.rows.append(self)
            return self
    fr.get_doc = lambda d, *a: _Doc(d)
    fr.enqueue = lambda method, **kw: fr.enq.append((method, kw.get("delivery_log")))
    fr.publish_realtime = lambda **kw: None
    fr.utils = types.SimpleNamespace(
        now_datetime=lambda: fr.clock[0],
        get_datetime=lambda x: x,
        get_url=lambda: "https://team.ecentric.vn")
    return fr


def _load(path, name, fr, extra=None):
    saved = {k: sys.modules.get(k) for k in ["frappe"] + list((extra or {}).keys())}
    sys.modules["frappe"] = fr
    for k, v in (extra or {}).items():
        sys.modules[k] = v
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _ngay_nghi(nghi=()):
    return lambda user, day: day.weekday() >= 5 or day in nghi


def _nhip(now, **kw):
    fr = _stub(now, **kw)
    m = _load(_NHIP, "nhip_gui_test", fr)
    m._la_nghi_mac_dinh = _ngay_nghi()
    return m, fr


def _events(nhip, fr):
    res = types.ModuleType("ecentric_workspace.notification_center.resolvers")
    res.resolve_notification = lambda d: d
    ev = _load(_EVENTS, "events_test", fr,
               {"ecentric_workspace.notification_center.resolvers": res,
                "ecentric_workspace.notification_center.nhip_gui": nhip})
    ev._nhip = nhip
    return ev


THU5 = dt.datetime(2026, 10, 8, 15, 0)      # thu Nam, gio lam viec
DEM_THU5 = dt.datetime(2026, 10, 8, 23, 30)
DEM_THU6 = dt.datetime(2026, 10, 9, 22, 0)  # toi thu Sau -> thu Hai
SANG_SOM = dt.datetime(2026, 10, 9, 0, 1)
ROUTE_TEAMS = {"erp": "deliver", "toast": "deliver", "sound": "deliver", "desktop": "skip",
               "teams": "deliver", "webpush": "deliver"}


class TestGioYenLang(unittest.TestCase):
    def test_dem_giu_toi_9h_sang_hom_sau(self):
        m, _ = _nhip(DEM_THU5)
        self.assertEqual(m.hen_gio("a@e.c", "teams", "action_required", "approval_required"),
                         dt.datetime(2026, 10, 9, 9, 0))

    def test_sau_nua_dem_giu_toi_9h_cung_ngay(self):
        m, _ = _nhip(SANG_SOM)
        self.assertEqual(m.hen_gio("a@e.c", "teams", "info", "mention"),
                         dt.datetime(2026, 10, 9, 9, 0))

    def test_toi_thu_sau_nhay_qua_cuoi_tuan(self):
        m, _ = _nhip(DEM_THU6)
        self.assertEqual(m.hen_gio("a@e.c", "webpush", "action_required", "approval_required"),
                         dt.datetime(2026, 10, 12, 9, 0))

    def test_nghi_phep_ngay_mai_thi_doi_tiep(self):
        m, _ = _nhip(DEM_THU5)
        m._la_nghi_mac_dinh = _ngay_nghi({dt.date(2026, 10, 9)})
        self.assertEqual(m.hen_gio("a@e.c", "teams", "info", "mention"),
                         dt.datetime(2026, 10, 12, 9, 0))

    def test_8h30_van_la_gio_yen_lang_tru_nhac_cham_cong(self):
        m, _ = _nhip(dt.datetime(2026, 10, 8, 8, 30))
        self.assertEqual(m.hen_gio("a@e.c", "teams", "info", "task_assigned"),
                         dt.datetime(2026, 10, 8, 9, 0))
        self.assertIsNone(m.hen_gio("a@e.c", "teams", "info", "attendance_missing"))

    def test_khong_giu_urgent_kenh_trong_app_va_khi_tat(self):
        m, fr = _nhip(DEM_THU5)
        self.assertIsNone(m.hen_gio("a@e.c", "teams", "urgent", "task_overdue"))
        self.assertIsNone(m.hen_gio("a@e.c", "erp", "info", "mention"))
        self.assertIsNone(m.hen_gio("a@e.c", "toast", "info", "mention"))
        fr.conf["ec_notify_pacing"] = {"tat": 1}
        self.assertIsNone(m.hen_gio("a@e.c", "teams", "info", "mention"))

    def test_chua_migrate_status_held_thi_gui_ngay(self):
        m, _ = _nhip(DEM_THU5, opts="Pending\nSent\nFailed\nSkipped\nSuppressed\nDuplicate")
        self.assertIsNone(m.hen_gio("a@e.c", "teams", "info", "mention"))

    def test_doi_khung_gio_qua_site_config(self):
        m, fr = _nhip(dt.datetime(2026, 10, 8, 21, 30))
        fr.conf["ec_notify_pacing"] = {"dem_tu": "22:00"}
        self.assertIsNone(m.hen_gio("a@e.c", "teams", "info", "mention"))


class TestGopTin(unittest.TestCase):
    def _publish(self, ev, fr, n, recipient="phuong@e.c", gop=False, nhip=None):
        def one(i):
            ev.route_delivery("ev%02d" % i, recipient, ROUTE_TEAMS, "approval_required",
                              "action_required", "k%d" % i, "NL-%d" % i,
                              "https://x/approvals/pay?id=P%d" % i, "EC Payment Request",
                              "P%d" % i, "Cần duyệt: Phiếu chi %d" % i, "", "x@e.c")
        if gop:
            with nhip.gop_tin():
                for i in range(n):
                    one(i)
        else:
            for i in range(n):
                one(i)

    def _teams(self, fr):
        return [r for r in fr.rows if r["channel"] == "teams"]

    def test_tin_dau_gui_ngay_tin_sau_giu_roi_gop_mot(self):
        m, fr = _nhip(THU5)
        ev = _events(m, fr)
        self._publish(ev, fr, 22)
        t = self._teams(fr)
        self.assertEqual([r["status"] for r in t].count("Pending"), 1)
        self.assertEqual([r["status"] for r in t].count("Held"), 21)
        self.assertEqual(sum(1 for x in fr.enq if x[0].endswith("teams.deliver")), 1)
        self.assertEqual([r for r in fr.rows if r["channel"] == "erp"][0]["status"], "Sent")
        fr.clock[0] = THU5 + dt.timedelta(minutes=2)
        self.assertEqual(m.xa_tin_giu()["gop"], 0)        # chua het cua so
        fr.clock[0] = THU5 + dt.timedelta(minutes=3)
        out = m.xa_tin_giu()
        self.assertEqual(out["gop"], 2)                     # teams + webpush
        gop = [r for r in fr.rows if r.get("dedupe_key", "").startswith("gop|") and r["channel"] == "teams"]
        self.assertEqual(len(gop), 1)
        self.assertEqual(gop[0]["title"], "Bạn có 21 phiếu cần xử lý")
        self.assertIn("… và 15 thông báo khác", gop[0]["message"])
        self.assertEqual(gop[0]["action_url"], "https://team.ecentric.vn/viec-cua-toi")
        self.assertEqual(gop[0]["event_type"], "approval_required")
        merged = [r for r in self._teams(fr) if r["status"] == "Merged"]
        self.assertEqual(len(merged), 21)
        self.assertTrue(all(r["provider"] == "gop:" + gop[0]["name"] for r in merged))
        self.assertIn(("ecentric_workspace.notification_center.providers.teams.deliver",
                       gop[0]["name"]), fr.enq)
        self.assertEqual(m.xa_tin_giu(), {"don": 0, "gop": 0, "da_doc": 0})  # idempotent

    def test_job_nhac_gop_ca_tin_dau(self):
        m, fr = _nhip(dt.datetime(2026, 10, 8, 9, 0, 5))
        ev = _events(m, fr)
        self._publish(ev, fr, 5, gop=True, nhip=m)
        self.assertTrue(all(r["status"] == "Held" for r in self._teams(fr)))
        self.assertFalse(getattr(fr.flags, "ec_gop_tin", None))   # tra co sau khoi
        fr.clock[0] = dt.datetime(2026, 10, 8, 9, 3, 5)
        m.xa_tin_giu()
        sent = [x for x in fr.enq if x[0].endswith("teams.deliver")]
        self.assertEqual(len(sent), 1)

    def test_mot_tin_don_le_gui_nguyen_ban(self):
        m, fr = _nhip(DEM_THU5)
        ev = _events(m, fr)
        self._publish(ev, fr, 1)
        t = self._teams(fr)[0]
        self.assertEqual((t["status"], t["next_retry_at"]), ("Held", dt.datetime(2026, 10, 9, 9, 0)))
        fr.clock[0] = dt.datetime(2026, 10, 9, 9, 0, 20)
        self.assertEqual(m.xa_tin_giu()["don"], 2)
        self.assertEqual(t["status"], "Pending")
        self.assertIn(("ecentric_workspace.notification_center.providers.teams.deliver", t["name"]), fr.enq)

    def test_da_doc_tren_erp_thi_khong_ban(self):
        m, fr = _nhip(DEM_THU5)
        ev = _events(m, fr)
        self._publish(ev, fr, 3)
        fr.logs_read.update({"NL-0", "NL-1"})
        fr.clock[0] = dt.datetime(2026, 10, 9, 9, 1)
        out = m.xa_tin_giu()
        self.assertEqual(out["da_doc"], 4)
        self.assertEqual(out["don"], 2)
        self.assertEqual([r["error_code"] for r in self._teams(fr) if r["status"] == "Suppressed"],
                         ["DA_DOC", "DA_DOC"])

    def test_dem_nhieu_tin_9h_ra_mot_tin(self):
        m, fr = _nhip(DEM_THU5)
        ev = _events(m, fr)
        self._publish(ev, fr, 10)
        fr.clock[0] = dt.datetime(2026, 10, 9, 0, 1)
        self._publish(ev, fr, 1, recipient="phuong@e.c")   # trung idempotency -> bo qua
        fr.clock[0] = dt.datetime(2026, 10, 9, 9, 0)
        m.xa_tin_giu()
        self.assertEqual(sum(1 for x in fr.enq if x[0].endswith("teams.deliver")), 1)

    def test_tin_luc_9h_nhap_dot_dem(self):
        m, fr = _nhip(DEM_THU5)
        ev = _events(m, fr)
        self._publish(ev, fr, 2)
        fr.clock[0] = dt.datetime(2026, 10, 9, 9, 0, 30)
        ev.route_delivery("evX", "phuong@e.c", ROUTE_TEAMS, "approval_required",
                          "action_required", "kX", "NL-X", "", "", "", "Cần duyệt: X", "", "")
        x = [r for r in self._teams(fr) if r["event_id"] == "evX"][0]
        self.assertEqual(x["next_retry_at"], dt.datetime(2026, 10, 9, 9, 0))
        m.xa_tin_giu()
        gop = [r for r in self._teams(fr) if r.get("dedupe_key", "").startswith("gop|")]
        self.assertEqual(gop[0]["title"], "Bạn có 3 phiếu cần xử lý")

    def test_nguoi_khac_khong_bi_gop_chung(self):
        m, fr = _nhip(THU5)
        ev = _events(m, fr)
        self._publish(ev, fr, 1, recipient="a@e.c")
        self._publish(ev, fr, 1, recipient="b@e.c")
        self.assertEqual([r["status"] for r in self._teams(fr)], ["Pending", "Pending"])

    def test_noi_dung_gop_hon_hop(self):
        m, _ = _nhip(THU5)
        nd = m.noi_dung_gop([
            {"event_type": "task_assigned", "severity": "action_required", "title": "Task A"},
            {"event_type": "task_assigned", "severity": "info", "title": "Task B"},
            {"event_type": "approval_required", "severity": "action_required", "title": "Phiếu C"}])
        self.assertEqual(nd["title"], "Bạn có 3 thông báo mới trên ERP")
        self.assertEqual(nd["event_type"], "task_assigned")
        self.assertEqual(nd["severity"], "action_required")
        self.assertEqual(nd["message"].split("\n"), ["• Task A", "• Task B", "• Phiếu C"])


class TestTaskPM(unittest.TestCase):
    def test_task_pm_ban_dem_giu_va_web_push_that_su_duoc_gui(self):
        m, fr = _nhip(dt.datetime(2026, 10, 6, 2, 5))
        ev = _events(m, fr)
        teams = types.ModuleType("ecentric_workspace.notification_center.providers.teams")
        teams.get_config = lambda: {"provider": "power_automate_copilot"}
        prov = types.ModuleType("ecentric_workspace.notification_center.providers")
        prov.teams = teams
        saved = {k: sys.modules.get(k) for k in (prov.__name__, teams.__name__)}
        sys.modules[prov.__name__], sys.modules[teams.__name__] = prov, teams
        try:
            ev.get_preference = lambda u: {"_exists": False, "minimum_severity": "info"}
            ev.publish_task_assignment_delivery("a@e.c", "TASK-1", "Ban duoc giao: X")
            fr.clock[0] = dt.datetime(2026, 10, 6, 14, 0)
            ev.publish_task_assignment_delivery("b@e.c", "TASK-2", "Ban duoc giao: Y")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        a = {r["channel"]: r["status"] for r in fr.rows if r["recipient"] == "a@e.c"}
        b = {r["channel"]: r["status"] for r in fr.rows if r["recipient"] == "b@e.c"}
        self.assertEqual((a["teams"], a["webpush"]), ("Held", "Held"))
        self.assertEqual((b["teams"], b["webpush"]), ("Pending", "Pending"))
        wp = [r["name"] for r in fr.rows if r["recipient"] == "b@e.c" and r["channel"] == "webpush"][0]
        self.assertIn(("ecentric_workspace.notification_center.providers.webpush.deliver", wp), fr.enq)


if __name__ == "__main__":
    unittest.main()
