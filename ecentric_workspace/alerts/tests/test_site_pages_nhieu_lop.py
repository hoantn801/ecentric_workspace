# Copyright (c) 2026, eCentric and contributors
"""Alert Center - "nhieu lop" (NHIEU_LOP/brief_alert_center.md, 29/09/2026).

Kiem Y DINH, khong kiem ket qua do cua mot lan chay: HTML server phai ve san vi tri cuoi,
trang khong duoc goi API lap, khong co khoi <script|style id="..."> chen trong trang, va
asset nao doi thi `?v=` trong trang phai doi theo (Frappe Cloud giu /assets 1 nam).

Chay khong can bench (stub frappe khi khong co frappe that):
    python -m unittest ecentric_workspace.alerts.tests.test_site_pages_nhieu_lop
"""
import ast
import hashlib
import io
import os
import re
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
ALERTS = os.path.dirname(_HERE)
APP = os.path.dirname(ALERTS)
REPO = os.path.dirname(APP)
if REPO not in sys.path:
    sys.path.insert(0, REPO)


def _stub_frappe():
    try:
        import frappe  # noqa: F401
        return
    except Exception:
        pass
    f = types.ModuleType("frappe")
    f.ValidationError = type("ValidationError", (Exception,), {})
    f.PermissionError = type("PermissionError", (Exception,), {})
    f.whitelist = lambda *a, **k: (lambda fn: fn)
    f._ = lambda s: s
    f.conf = types.SimpleNamespace(get=lambda *a, **k: None)

    def _throw(msg, exc=None):
        raise (exc or f.ValidationError)(msg)
    f.throw = _throw
    f.log_error = lambda *a, **k: None
    f.session = types.SimpleNamespace(user="t@e.c")
    f.db = types.SimpleNamespace(sql=None, count=None, get_value=None, exists=None)
    f.get_all = lambda *a, **k: []
    sys.modules["frappe"] = f
    fu = types.ModuleType("frappe.utils")
    fu.nowdate = lambda: "2026-09-29"
    fu.add_days = lambda d, n: "2026-08-30"
    fu.cint = lambda v: int(v or 0)
    fu.flt = lambda v, *a: float(v or 0)
    fu.now_datetime = lambda: None
    fu.get_datetime = lambda v: v
    sys.modules["frappe.utils"] = fu


_stub_frappe()

from ecentric_workspace.alerts.site_pages import PAGE_MODULES, assets  # noqa: E402

PAGES = {k: os.path.join(ALERTS, "site_pages", k, "main_section.html") for k in PAGE_MODULES}
PAGE_JS = {"overview": "ec_alert_overview.js", "policies": "ec_alert_policies.js",
           "rules": "ec_alert_rules.js", "locks": "ec_alert_locks.js",
           "integration_health": "ec_alert_health.js"}
ASSET_DIR = os.path.join(APP, "public", "alerts")

#: sha256(<aside class="ec-shell-mount">..</aside> + "\n" + <div class="ec-shell-topbar">..</div></div>)
#: cua ban live 29/09/2026. Luat chung: KHONG dung noi dung vung menu - server dung lai no luc
#: render (shell/server_nav.py). Doi dong nay chi khi chat Shell yeu cau.
SHELL_ZONES = {
    "overview": "639ca6bf5eaec5194b1580399770b62e04ee67c2608dff03149a9bafbfb938d0",
    "policies": "297962a9d1bf8a86f762837aa72e7b655ea74c992518fca1197b76f21095aeb2",
    "rules": "e5ae8a9657cf65997e1f20321ab6cf845352d75a4f88610da77de97d37b35013",
    "locks": "c0c8d60f112c613ac48fdb3802b04423347581f45bc89040ac3957d305a0b7f4",
    "integration_health": "84408ed603764a0c378a6756184ef8f46ec4ce5f0dea358777a021e0b9ab5419",
}

#: Ban live 29/09/2026 (truoc dot nay) - lan deploy dau PHAI duoc phep ghi de len no.
LIVE_BEFORE = {
    "overview": "0a06538a47c70eca3bfcea6eae5ac2cdb9713ac2304b07f43834079e8706b6a0",
    "policies": "9353c6bcca9a27b0b59170e765113cc825048ac7dddfe29ac5f425b621278ada",
    "rules": "2cb3d306356b62e9c77e2d1ae3af16eef31a7dd59f8a7d37b6f22ad11ae0907f",
    "locks": "04c93c168192613f02aa463795b7930e898fb7edc685636d082b5ce67a8d4166",
    "integration_health": "92ef593391cb057c56f7a888d6ef3238f2a9ad2a2be94b0edcf26667f88c6834",
}


def _read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def _asset(name):
    return _read(os.path.join(ASSET_DIR, name))


class TestPageSources(unittest.TestCase):
    def test_khong_con_khoi_chen_co_id(self):
        """do_lop_trang.js dem `.page_content script[id], style[id]` - phai la 0."""
        for key, path in PAGES.items():
            with self.subTest(page=key):
                self.assertEqual(re.findall(r'<(?:script|style)\s+id="([^"]+)"', _read(path)), [])

    def test_khong_con_boc_fetch(self):
        for key, path in PAGES.items():
            with self.subTest(page=key):
                self.assertNotIn("ec-csrf-fetch-patch", _read(path))
        for name in os.listdir(ASSET_DIR):
            with self.subTest(asset=name):
                self.assertNotRegex(_asset(name), r"window\.fetch\s*=")

    def test_moi_trang_nap_dung_asset_voi_v_dung(self):
        for key, path in PAGES.items():
            html = _read(path)
            with self.subTest(page=key):
                names = [n for n, _v in assets.refs(html)]
                self.assertEqual(names, ["ec_alert_center.css", "ec_alert_shared.js", PAGE_JS[key]])
                self.assertEqual(assets.stale(html), [],
                                 "asset doi ma ?v= chua doi -> trinh duyet giu ban cu 1 nam. Chay "
                                 "`python -m ecentric_workspace.alerts.site_pages.assets --stamp`.")
                # CSS nam o dung cho khoi <style> cu (truoc noi dung trang), JS chung truoc JS trang
                self.assertLess(html.index("ec_alert_center.css"), html.index('<div class="ecentric-app">'))
                self.assertLess(html.index("ec_alert_shared.js"), html.index(PAGE_JS[key]))

    def test_vung_menu_giu_nguyen_byte_live(self):
        for key, path in PAGES.items():
            html = _read(path)
            with self.subTest(page=key):
                a = re.search(r'<aside class="ec-shell-mount"[\s\S]*?</aside>', html).group(0)
                t = re.search(r'<div class="ec-shell-topbar"[\s\S]*?</div></div>', html).group(0)
                self.assertEqual(hashlib.sha256((a + "\n" + t).encode("utf-8")).hexdigest(),
                                 SHELL_ZONES[key])

    def test_khoa_chong_troi_nhan_ban_live_cu(self):
        import importlib
        for key in PAGE_MODULES:
            mod = importlib.import_module("ecentric_workspace.alerts.site_pages.%s.page_sync" % key)
            with self.subTest(page=key):
                self.assertEqual(mod.BASELINE_SHA256,
                                 hashlib.sha256(_read(PAGES[key]).encode("utf-8")).hexdigest())
                self.assertIn(LIVE_BEFORE[key], mod.SUPERSEDES_SHA256)

    def test_khong_trung_id_voi_skin_dang_nhap(self):
        """ec-login-skin (Website Settings > head_html) co #ec-brand{position:fixed}: donut brand
        tung mang id do va troi o dau /alerts."""
        for key, path in PAGES.items():
            with self.subTest(page=key):
                self.assertNotIn('id="ec-brand"', _read(path))
        self.assertNotIn('"ec-brand"', _asset("ec_alert_overview.js"))
        self.assertIn('id="al-ch-brand"', _read(PAGES["overview"]))

    def test_bang_du_lieu_co_cot_co_dinh(self):
        pol = _read(PAGES["policies"])
        m = re.search(r'<table class="al-tbl al-tbl-fixed al-tbl-pl">\s*<!--[\s\S]*?-->\s*<colgroup>(.*?)</colgroup>', pol)
        self.assertTrue(m, "bang Price Setup mat table-layout:fixed/colgroup")
        self.assertEqual(m.group(1).count("<col"), 10)
        self.assertIn('<div class="al-tbl-wrap al-hold">', pol)
        ih = _read(PAGES["integration_health"])
        m = re.search(r'<table class="al-tbl al-tbl-fixed al-tbl-ih">\s*<colgroup>(.*?)</colgroup>', ih)
        self.assertTrue(m, "bang Integration Health mat table-layout:fixed/colgroup")
        self.assertEqual(m.group(1).count("<col"), 17)

    def test_khoi_phu_thuoc_du_lieu_o_vi_tri_cuoi(self):
        ih = _read(PAGES["integration_health"])
        self.assertLess(ih.index('id="ih-rows"'), ih.index('id="ih-cap-panel"'),
                        "khoi dung luong (chi SM) phai nam DUOI bang - hien ra khong day nut Lam moi")
        lk = _read(PAGES["locks"])
        self.assertLess(lk.index('id="lk-count"'), lk.index('id="lk-rows"'),
                        "phan trang Locks phai nam TREN bang")


class TestAssets(unittest.TestCase):
    def test_css_giu_cho(self):
        css = _asset("ec_alert_center.css")
        for rule in ('.greeting p[id$="-scope-line"]{min-height:24px',
                     ".al-charts3>*{min-width:0}",
                     "html{scrollbar-gutter:stable}",
                     ".al-tbl.al-tbl-fixed{table-layout:fixed}",
                     "#ru-defaults{min-height:60vh}"):
            with self.subTest(rule=rule):
                self.assertIn(rule, css)
        # Khong che roi hien (luat chung, test Shell cung cam)
        for bad in ("ec-shell-reveal", "ec-shell-fadein"):
            self.assertNotIn(bad, css)

    def test_goi_api_qua_ecapi(self):
        sh = _asset("ec_alert_shared.js")
        self.assertIn("window.ecApi.post(", sh)
        self.assertNotIn("fetch(API+m", sh)

    def test_khong_goi_lap_luc_mo_trang(self):
        ov = _asset("ec_alert_overview.js")
        self.assertIn('"api_dashboard.by_dimensions"', ov)
        self.assertNotIn('"api_dashboard.by_dimension"', ov)
        self.assertIn("function reload(){loadDash();if(listShown())loadRows();", ov)
        pol = _asset("ec_alert_policies.js")
        body = pol[pol.index("function loadCoverageSummary(){"):pol.index("function openMissingView(){")]
        self.assertIn('"api_sku_catalog.policy_coverage_summary"', body)
        self.assertNotIn("policy_missing_skus", body)
        lk = _asset("ec_alert_locks.js")
        self.assertIn('"api_actions.lock_queue"', lk)
        self.assertNotIn('"api_actions.list_actions"', lk)
        # gan hash bang replaceState: khong ban hashchange -> khong tai lai lan 2
        self.assertEqual(re.findall(r"window\.location\.hash\s*=(?!=)", lk), ["window.location.hash="],
                         "chi con nhanh du phong trong setHash duoc gan hash truc tiep")

    def test_moi_A_call_tro_vao_ham_whitelist_that(self):
        """Ten endpoint go sai -> 404 luc chay, khong test nao khac bat."""
        seen = set()
        for name in os.listdir(ASSET_DIR):
            if name.endswith(".js"):
                seen.update(re.findall(r'A\.call\("([a-z_]+)\.([a-z_]+)"', _asset(name)))
        self.assertTrue(seen)
        for mod, fn in sorted(seen):
            with self.subTest(endpoint=mod + "." + fn):
                path = os.path.join(ALERTS, mod + ".py")
                self.assertTrue(os.path.isfile(path), path)
                tree = ast.parse(_read(path))
                defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
                self.assertIn(fn, defs)
                decos = [ast.unparse(d) for d in defs[fn].decorator_list]
                self.assertTrue(any(d.startswith("frappe.whitelist") for d in decos), decos)


class _Perms:
    ALL_BRANDS = "*"

    def __init__(self, allowed):
        self.allowed = allowed

    def require_alert_center_access(self, user=None):
        return self.allowed


class TestBatchedEndpoints(unittest.TestCase):
    def test_coverage_summary_hai_cau_sql_cho_moi_so_brand(self):
        from ecentric_workspace.alerts.services import policy_coverage as pc
        calls = []
        orig = (pc.missing_counts, pc.order_sku_totals)
        try:
            pc.missing_counts = lambda brands, days=None: calls.append(("m", tuple(brands))) or {"A": 3}
            pc.order_sku_totals = lambda brands, days=None: calls.append(("t", tuple(brands))) or {"A": 10, "B": 4}
            out = pc.coverage_summary(["A", "B", "A", "", "C"], days=30)
        finally:
            pc.missing_counts, pc.order_sku_totals = orig
        self.assertEqual(calls, [("m", ("A", "B", "C")), ("t", ("A", "B", "C"))])
        self.assertEqual(out, {"A": {"checked": 10, "missing": 3},
                               "B": {"checked": 4, "missing": 0},
                               "C": {"checked": 0, "missing": 0}})

    def test_order_sku_totals_mot_cau_group_by(self):
        import frappe
        from ecentric_workspace.alerts.services import policy_coverage as pc
        seen = []
        orig = frappe.db.sql
        try:
            frappe.db.sql = lambda q, p=None, as_dict=False: seen.append((q, p)) or [{"brand": "A", "n": 7}]
            self.assertEqual(pc.order_sku_totals(["A", "B"], days=30), {"A": 7})
        finally:
            frappe.db.sql = orig
        self.assertEqual(len(seen), 1)
        q, p = seen[0]
        self.assertIn("COUNT(DISTINCT oi.seller_sku)", q)
        self.assertIn("GROUP BY " + pc._RESOLVED_BRAND, q)
        self.assertEqual(p["brands"], ("A", "B"))
        self.assertEqual(pc.order_sku_totals([], days=30), {})

    def test_policy_coverage_summary_bo_brand_ngoai_pham_vi(self):
        from ecentric_workspace.alerts import api_sku_catalog as api
        got = {}
        orig = (api.perms, api.policy_coverage.coverage_summary)
        try:
            api.perms = _Perms({"A": "kam"})
            api.policy_coverage.coverage_summary = lambda brands, days=None: got.setdefault("b", list(brands)) and {
                "A": {"checked": 10, "missing": 3}}
            res = api.policy_coverage_summary(brands='["A","B"]', days=30)
        finally:
            api.perms, api.policy_coverage.coverage_summary = orig
        self.assertEqual(got["b"], ["A"])
        self.assertEqual((res["checked"], res["missing"]), (10, 3))

    def test_lock_queue_dem_giong_4_the_cu(self):
        """4 the KPI cu = list_actions({review_status|status: X}, page_len=1).total."""
        import frappe
        from ecentric_workspace.alerts import api_actions as api
        counted = []
        orig = (api.perms, frappe.db.count, frappe.get_all)
        try:
            api.perms = _Perms({"A": "kam", "B": "manager"})
            frappe.db.count = lambda dt, filters=None: counted.append(filters) or 5
            frappe.get_all = lambda *a, **k: []
            res = api.lock_queue(filters={"brand": "A"}, start=0, page_len=50)
        finally:
            api.perms, frappe.db.count, frappe.get_all = orig
        self.assertEqual(res["counts"], {"Pending Review": 5, "Approved": 5, "Rejected": 5, "Skipped": 5})
        base = [["action_type", "=", "Stock Safety Lock"]]
        scope = ["brand", "in", ["A", "B"]]
        self.assertEqual(counted[1:], [
            base + [["review_status", "=", "Pending Review"], scope],
            base + [["review_status", "=", "Approved"], scope],
            base + [["review_status", "=", "Rejected"], scope],
            base + [["status", "=", "Skipped"], scope],
        ])
        # bang van theo bo loc dang chon (brand A)
        self.assertEqual(counted[0], base + [["brand", "in", ["A"]]])

    def test_by_dimensions_mot_lan_loc_nhieu_chieu(self):
        from ecentric_workspace.alerts import api_dashboard as api
        n = {"flt": 0}
        orig = (api._flt, api._group_count)
        try:
            api._flt = lambda f=None, **k: n.__setitem__("flt", n["flt"] + 1) or [["brand", "=", "A"]]
            api._group_count = lambda flt, field, limit=12: [{"key": field, "n": 1}]
            res = api.by_dimensions(dims=["brand", "platform", "rule_code"], filters={})
            with self.assertRaises(Exception):
                api.by_dimensions(dims=["nope"])
        finally:
            api._flt, api._group_count = orig
        self.assertEqual(n["flt"], 1)
        self.assertEqual(sorted(res["dims"]), ["brand", "platform", "rule_code"])
        self.assertEqual(res["dims"]["rule_code"], [{"key": "rule_code", "n": 1}])


if __name__ == "__main__":
    unittest.main()
