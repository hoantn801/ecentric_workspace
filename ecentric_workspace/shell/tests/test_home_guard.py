# Copyright (c) 2026, eCentric and contributors
"""Trang chu - hop dong GHI (page_sync) va nhung bai hoc khong duoc quen.

Lich su: 21/07 Daily Cockpit bi PO tu choi -> module khoa 0-ghi (BASELINE_SHA256 = None)
cho toi khi co baseline duoc duyet. 29/09/2026 (NHIEU_LOP giai doan 2, PO duyet) baseline
do la bo cuc v2 nam trong legacy_pages/home/main_section.html. Bo test nay khoa:
  - chi co MOT duong ghi: upsert co khoa chong troi (BASELINE + SUPERSEDES), sau khi file
    khop BASELINE va Jinja render thu duoc; force chi co o code, khong qua HTTP;
  - trang khong bao gio phuc vu tinh, khong dung Website Settings, endpoint chi cho SM;
  - dau vet Cockpit khong duoc quay lai; dem toan cuc (24/07) khong duoc quay lai.
Chay khong can bench (frappe stub, moi truy cap ngoai y muon deu no)."""
import hashlib
import importlib
import inspect
import io
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
REPO = os.path.dirname(APP)
sys.path.insert(0, REPO)
HOME = os.path.join(APP, "legacy_pages", "home")


def _read(*p):
    return io.open(os.path.join(*p), encoding="utf-8").read()


class _Frappe(types.ModuleType):
    """frappe gia ghi lai moi thu sync() lam, theo thu tu."""

    def __init__(self):
        super().__init__("frappe")
        self.log = []
        self.dyn = 0
        self.render_raises = None
        self.roles = ["System Manager"]
        outer = self

        class _DB:
            def exists(self, dt, name=None):
                outer.log.append(("exists", dt, name))
                return True

            def get_value(self, dt, name, field=None, *a, **k):
                outer.log.append(("get_value", dt, name, field))
                return outer.dyn if field == "dynamic_template" else None

            def set_value(self, dt, name, field, value, *a, **k):
                outer.log.append(("set_value", dt, name, field, value))

        self.db = _DB()
        self.session = types.SimpleNamespace(user="sm@e.vn")
        self._ = lambda s: s
        self.PermissionError = type("PermissionError", (Exception,), {})
        self.whitelist = lambda *a, **k: (lambda f: f)

    def render_template(self, html, ctx):
        self.log.append(("render", len(html)))
        if self.render_raises:
            raise self.render_raises

    def get_roles(self, user=None):
        return list(self.roles)

    def throw(self, msg, exc=Exception):
        raise exc(msg)


class TestHomeSync(unittest.TestCase):
    def setUp(self):
        self._saved = sys.modules.get("frappe")
        self.fr = _Frappe()
        sys.modules["frappe"] = self.fr
        for m in ("ecentric_workspace.legacy_pages.home.page_sync",
                  "ecentric_workspace.approval_center.page_sync_util",
                  "ecentric_workspace.approval_center.shared.page_sync"):
            sys.modules.pop(m, None)
        self.ps = importlib.import_module("ecentric_workspace.legacy_pages.home.page_sync")
        self.calls = []
        util = self.ps.page_sync_util

        def upsert(route, name, title, html, publish=1, expect_sha=None):
            self.fr.log.append(("upsert", route, name, title, publish, expect_sha))
            self.calls.append(html)
            return self.result

        self.result = {"action": "updated", "route": "home", "name": "ecentric-workspace"}
        self._orig = (util.upsert_web_page, util.record_live_sha)
        util.upsert_web_page = upsert
        util.record_live_sha = lambda route, name: self.fr.log.append(("record", route, name))

    def tearDown(self):
        util = self.ps.page_sync_util
        util.upsert_web_page, util.record_live_sha = self._orig
        if self._saved is not None:
            sys.modules["frappe"] = self._saved
        else:
            sys.modules.pop("frappe", None)

    def test_baseline_is_pinned_and_supersedes_live(self):
        sha = hashlib.sha256(io.open(os.path.join(HOME, "main_section.html"), "rb").read()).hexdigest()
        self.assertEqual(self.ps.BASELINE_SHA256, sha)
        # ban live truoc giai doan 2, roi ban p224 (nut cham cong xuong dong) - theo thu tu
        self.assertEqual(self.ps.SUPERSEDES_SHA256, (
            "2a4c6826a8f091a203a960e44be652dea97486f5ad75fef09188294e5c9bcf76",
            "0a77f921665a2a619232041647cfaa3158216cf070fa6905b1a03020a81fdb5d",
            "52d1d24463601e8c41cd75fb569dce3bde22c563ee4e22ca39aca2fe5d4b0faa",
            # p227 (go chat cu) - ban live truoc khi p228 them popup "Hom nay o eCentric"
            "7bfda03ccb1e779f481347c7b8e54b9affc3a8072d45c42e1c14bea685d18aec",
            # p228 (popup) - ban live truoc khi p230 them nut mo lai popup
            "633e6dd057e87f240e8dcee5aa6e62b4c623745f5ba775248e8c566a12b90baf",
            # p230 (nut mo lai popup) - ban live truoc khi p241 doi menu "AI Tool" -> "SI Tool"
            "cfb286e5c4f0d5672e67d236ece09c1225ab4cd3fc7090d2d86fdcf7f31118f0",
            # p241 (SI Tool) - ban live truoc khi p246 them Tin noi bo (menu + khoi trang chu)
            "a347101b1c8d6e61e4816c4e281340be6ed0418399f9f429ebb58362201c76c2",
            # p246 (Tin noi bo o Workspace) - ban truoc khi p247 chuyen vao Tai nguyen thay Intranet
            "852634753df07a7c299822ebced929e974b8bb7518cb39a020d33b03f3d5a849",
            # p247 (Tin noi bo vao Tai nguyen) - ban live truoc khi p248 them muc "Khảo sát"
            "0884ba8f5749ffd97447c4bd33e48c4c2981e348205305990417406f9b2457e0"))

    def test_sync_writes_the_file_under_the_drift_lock_after_a_render_check(self):
        res = self.ps.sync()
        self.assertEqual(res["action"], "updated")
        kinds = [x[0] for x in self.fr.log]
        self.assertLess(kinds.index("render"), kinds.index("upsert"), "render thu TRUOC khi ghi")
        up = [x for x in self.fr.log if x[0] == "upsert"][0]
        self.assertEqual(up[1:5], ("home", "ecentric-workspace", "eCentric Workspace", "preserve"))
        self.assertEqual(up[5], (self.ps.BASELINE_SHA256,) + self.ps.SUPERSEDES_SHA256)
        self.assertEqual(self.calls, [self.ps._html()])
        # trang Jinja: dynamic_template = 1 neu dang tat; nho sha cua lan ghi nay
        self.assertIn(("set_value", "Web Page", "ecentric-workspace", "dynamic_template", 1), self.fr.log)
        self.assertEqual(res.get("dynamic_template"), "set")
        self.assertIn(("record", "home", "ecentric-workspace"), self.fr.log)

    def test_dynamic_template_already_on_is_left_alone(self):
        self.fr.dyn = 1
        res = self.ps.sync()
        self.assertNotIn("dynamic_template", res)
        self.assertFalse([x for x in self.fr.log if x[0] == "set_value"])

    def test_refused_drift_touches_nothing_else(self):
        self.result = {"action": "refused", "route": "home", "name": "ecentric-workspace", "live_sha": "x"}
        res = self.ps.sync()
        self.assertEqual(res["action"], "refused")
        self.assertFalse([x for x in self.fr.log if x[0] in ("set_value", "record")])

    def test_jinja_error_means_no_write(self):
        self.fr.render_raises = RuntimeError("UndefinedError: 'ec_x' is undefined")
        with self.assertRaises(RuntimeError):
            self.ps.sync()
        self.assertEqual(self.calls, [])

    def test_edited_file_without_bump_is_refused(self):
        orig = self.ps._html
        self.ps._html = lambda: orig() + "<!-- sua tay -->"
        try:
            with self.assertRaises(ValueError):
                self.ps.sync()
        finally:
            self.ps._html = orig
        self.assertEqual(self.calls, [])

    def test_cockpit_markup_can_never_return(self):
        for mk in self.ps.COCKPIT_MARKERS:
            with self.assertRaises(ValueError):
                self.ps.check_source(self.ps._html().replace("</body>", mk + "</body>") + mk)
        for mk in ('class="ec-ck', "ec-cockpit-js", "ec-ck-grid", "data-ec-shell-quickaccess"):
            self.assertNotIn(mk, self.ps._html(), mk)

    def test_force_only_from_code(self):
        self.ps.sync(force=1)
        up = [x for x in self.fr.log if x[0] == "upsert"][0]
        self.assertIsNone(up[5])
        self.assertIn("def sync_home_page():", _read(HOME, "page_sync.py"))   # khong tham so

    def test_endpoint_is_sm_only(self):
        self.fr.roles = ["Employee"]
        with self.assertRaises(self.fr.PermissionError):
            self.ps.sync_home_page()
        self.assertEqual(self.calls, [])
        self.fr.roles = ["System Manager"]
        self.assertEqual(self.ps.sync_home_page()["action"], "updated")


class TestHomeSourceText(unittest.TestCase):
    def test_no_static_serving_and_no_website_settings(self):
        src = _read(HOME, "page_sync.py")
        self.assertNotIn("ensure_static_serving", src, "trang chu la Jinja (render theo nguoi)")
        self.assertNotIn('"Website Settings"', src)
        self.assertIn("System Manager", src)

    def test_single_write_path(self):
        import ast
        tree = ast.parse(_read(HOME, "page_sync.py"))
        code = ast.unparse(ast.Module(body=[n for n in tree.body if not (
            isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant))], type_ignores=[]))
        self.assertEqual(code.count("upsert_web_page("), 1)
        # hai phep bien doi 22-24/07 da nam san trong nguon: khong con duong ghi thu hai
        for gone in ("transform_home", "neutralize_legacy_action_counts", ".save(", "ENABLE_SHELL_BOUNDARY"):
            self.assertNotIn(gone, code, gone)

    def test_no_global_action_counts(self):
        """24/07: dem toan cuc Leave Application / Sales Order bi go; badge + KPI la cho cua
        widget Action Center, khong bao gio la mot so 0 sai."""
        s = _read(HOME, "main_section.html")
        self.assertNotIn("frappe.db.count(", s)
        self.assertEqual(s.count('data-ec-ac-badge="1" hidden'), 1)
        self.assertIn('<div class="stat-value" data-ec-ac-kpi="approval">—</div>', s)
        self.assertEqual(s.count('data-ec-ac-kpi-meta="1"'), 1)
        self.assertNotIn('<div class="stat-value">0</div>', s)

    def test_action_provider_backend_intact(self):
        api = _read(APP, "action_center", "api.py")
        for keep in ("def get_action_items", "def get_my_requests_summary", "def get_reminder_summary"):
            self.assertIn(keep, api, keep)
        feed = _read(APP, "action_center", "feed.py")
        for keep in ("def build_feed", "def classify", "counts[bucket] += 1"):
            self.assertIn(keep, feed, keep)


if __name__ == "__main__":
    unittest.main()
