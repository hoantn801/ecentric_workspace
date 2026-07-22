# Copyright (c) 2026, eCentric and contributors
"""Pure tests for the ERP Shell v1 nav registry + boot API gating.
Run WITHOUT a bench:  python3 -m unittest ecentric_workspace.shell.tests.test_nav_registry
(frappe is stubbed for the api tests; nav.py itself never imports frappe)."""
import sys
import types
import unittest

from ecentric_workspace.shell import nav


class TestRegistryCompose(unittest.TestCase):
    def test_compose_is_valid_and_deterministic(self):
        a, b = nav.compose(), nav.compose()
        self.assertEqual(a, b)
        self.assertGreaterEqual(len(a), 13)  # full IA (docs pair collapsed into 1 parent)
        keys = [it["key"] for it in a]
        self.assertEqual(len(keys), len(set(keys)))

    def test_group_ordering(self):
        items = nav.compose()
        groups = [it["group"] for it in items]
        # ungrouped (home) first, then "Phê duyệt"
        self.assertEqual(groups[0], "")
        self.assertIn("Phê duyệt", groups)
        self.assertEqual(groups, sorted(groups, key=lambda g: nav._group_rank(g)))

    def test_required_fields_present(self):
        for it in nav.compose():
            for f in nav.REQUIRED_FIELDS:
                self.assertIn(f, it, "%s missing %s" % (it.get("key"), f))

    def test_duplicate_key_rejected(self):
        items = nav.compose()
        dup = dict(items[0]); dup["route"] = "/definitely-unique-route"
        with self.assertRaises(ValueError):
            nav.validate(items + [dup])

    def test_duplicate_route_rejected(self):
        items = nav.compose()
        dup = dict(items[0]); dup["key"] = "x.unique"
        with self.assertRaises(ValueError):
            nav.validate(items + [dup])

    def test_bad_pattern_rejected(self):
        bad = dict(nav.CORE_ITEMS[0], key="x.bad", route="/x",
                   active_patterns=["no-slash"])
        with self.assertRaises(ValueError):
            nav.validate([bad])

    def test_hr_nav_present_and_salary_no_prerender(self):
        """HR provider: employee-facing entries + salary marked no_prerender.
        Context split: HR items live in compose("hr") (and compose_all), NOT
        in the default approval_document sidebar."""
        items = nav.compose("hr")
        hr = [it for it in items if it.get("owner") == "hr"]
        routes = sorted(it["route"] for it in hr)
        self.assertEqual(routes, ["/ec-hr/attendance", "/ec-hr/salary"])
        for it in hr:
            self.assertEqual(it["group"], "Nhân sự")
            self.assertEqual(it["visible_when"], "internal")
        sal = next(it for it in hr if it["route"] == "/ec-hr/salary")
        att = next(it for it in hr if it["route"] == "/ec-hr/attendance")
        self.assertTrue(sal.get("no_prerender") is True,
                        "salary route MUST be flagged no_prerender (never warmed)")
        self.assertNotIn("no_prerender", att,
                         "attendance uses normal shell nav behavior")

    def test_no_business_data_fields(self):
        # registry payload must stay navigation-only
        allowed = set(nav.REQUIRED_FIELDS) | {"badge_source", "keywords", "children", "no_prerender"}
        for it in nav.compose():
            self.assertTrue(set(it) <= allowed, "unexpected fields: %s" % (set(it) - allowed))


class _FakeConf(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


def _fake_frappe(conf=None, user="someone@ecentric.vn", user_type="System User"):
    f = types.ModuleType("frappe")
    f.conf = _FakeConf(conf or {})
    f.session = types.SimpleNamespace(user=user)
    f._ = lambda s: s
    class PermissionError_(Exception):
        pass
    f.PermissionError = PermissionError_
    def throw(msg, exc=Exception):
        raise exc(msg)
    f.throw = throw
    class _DB:
        def get_value(self, doctype, name, fields, as_dict=False):
            if fields == "user_type":
                return user_type
            return {"full_name": "Some One", "user_image": ""}
    f.db = _DB()
    f.whitelist = lambda **kw: (lambda fn: fn)
    return f


class TestBootApiGating(unittest.TestCase):
    """shell.api logic with frappe stubbed (kill switch / guest / non-internal)."""

    def _api(self, **kw):
        import importlib
        sys.modules["frappe"] = _fake_frappe(**kw)
        sys.modules.pop("ecentric_workspace.shell.api", None)
        return importlib.import_module("ecentric_workspace.shell.api")

    def tearDown(self):
        sys.modules.pop("frappe", None)
        sys.modules.pop("ecentric_workspace.shell.api", None)

    def test_kill_switch_disables(self):
        api = self._api(conf={"ec_shell_disabled": 1})
        out = api.get_shell_boot()
        self.assertEqual(out, {"enabled": False, "reason": "kill_switch"})

    def test_guest_rejected(self):
        api = self._api(user="Guest")
        with self.assertRaises(Exception):
            api.get_shell_boot()

    def test_website_user_fail_closed(self):
        api = self._api(user_type="Website User")
        self.assertFalse(api.get_shell_boot()["enabled"])

    def test_enabled_payload_shape(self):
        api = self._api()
        out = api.get_shell_boot()
        self.assertTrue(out["enabled"])
        self.assertTrue(out["nav"])
        for it in out["nav"]:
            self.assertEqual(
                set(it),
                {"key", "label", "route", "icon", "group", "active_patterns",
                 "keywords", "no_prerender", "soon", "children"},
                "boot nav must not leak extra fields")
        self.assertEqual(set(out["user"]), {"name", "full_name", "image"})


class TestSidebarIA(unittest.TestCase):
    """Locks the PO-approved sidebar IA (2B.1 urgent nav patch). Routes were
    extracted VERBATIM from the legacy production sidebars -- never invented."""

    def _by_key(self):
        return {it["key"]: it for it in nav.compose()}

    def test_exact_ia_map(self):
        expected = {
            "apc.catalog": ("Phê duyệt", "Approval Center", "/approvals"),
            "apc.dashboard": ("Phê duyệt", "Dashboard", "/approvals/dashboard"),
            "tickets.all": ("Chứng từ", "Dashboard", "/all-ticket"),
            "approval.inbox": ("Chứng từ", "All Tickets", "/approval"),
            "legacy.create_mso": ("Tạo mới", "MSO Request", "/mso-form"),
            "legacy.create_so": ("Tạo mới", "SO Request", "/so-form"),
            "legacy.create_po": ("Tạo mới", "PO Request", "/form-po"),
            "legacy.create_rec": ("Tạo mới", "REC Request", "/form-rec"),
            "gbs.po": ("GBS", "GBS Purchase Order", "/gbs-po-form"),
            "gbs.so": ("GBS", "GBS Sales Order", "/gbs-so-form"),
        }
        by = self._by_key()
        for key, (group, label, route) in expected.items():
            it = by[key]
            self.assertEqual((it["group"], it["label"], it["route"]),
                             (group, label, route), key)

    def test_guides_submenu(self):
        guides = self._by_key()["docs.guides"]
        self.assertEqual(guides["group"], "Hướng dẫn")
        kids = [(c["label"], c["route"]) for c in guides["children"]]
        self.assertEqual(kids, [("Docs / Architecture", "/docs/architecture"),
                                ("GBS Flow & Definitions", "/docs/gbs-flow")])

    def test_others_submenu(self):
        others = self._by_key()["legacy.others"]
        kids = [(c["label"], c["route"]) for c in others["children"]]
        self.assertEqual(kids, [("Client Request", "/client-request"),
                                ("Vendor Request", "/vendor-request"),
                                ("Contract Request", "/contract-request")])

    def test_stale_duplicate_absent(self):
        routes = set()
        for it in nav.compose():
            routes.add(it["route"])
            for c in it.get("children", []):
                routes.add(c["route"])
        for stale in ("/all-tickets", "/all-internal-requests", "/po-form", "/rec-form"):
            self.assertNotIn(stale, routes, stale)

    def test_child_duplicate_rejected(self):
        items = nav.compose()
        bad = dict(items[0], key="x.dup", route="/client-request")  # child route exists
        with self.assertRaises(ValueError):
            nav.validate(items + [bad])

    def test_nested_children_rejected(self):
        base = dict(nav.CORE_ITEMS[0])
        child = {"key": "c.x", "label": "X", "route": "/cx", "icon": "doc", "order": 1,
                 "active_patterns": ["/cx"], "visible_when": "internal", "owner": "t",
                 "children": []}
        parent = dict(base, key="p.x", route="/px", children=[child])
        with self.assertRaises(ValueError):
            nav.validate([parent])


if __name__ == "__main__":
    unittest.main()
