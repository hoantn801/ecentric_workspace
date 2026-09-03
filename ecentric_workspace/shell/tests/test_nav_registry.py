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
        self.assertGreaterEqual(len(a), 9)  # GD2 C2: create_rec/gbs.po/gbs.so + /others removed (13 -> 9)
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


class TestRoleGatedItems(unittest.TestCase):
    """`visible_when: "role:<Role>"` (03/09) - the esign ops page for System Manager.

    The static fallback nav is public HTML. A role-gated link baked into it would
    advertise an admin page to every employee, even though the page itself refuses
    them. So compose(roles=None) MUST drop such items, and only the session-aware
    boot endpoint (which can prove roles) may include them.
    """
    OPS = "/ec-esign/ops"

    def test_registry_declares_the_ops_item_as_role_gated(self):
        all_items = nav.compose(roles={"System Manager"})
        ops = [it for it in all_items if it["route"] == self.OPS]
        self.assertEqual(len(ops), 1, "esign ops item missing from approval context")
        self.assertEqual(ops[0]["visible_when"], "role:System Manager")
        self.assertEqual(nav.required_role(ops[0]), "System Manager")

    def test_static_fallback_never_shows_it(self):
        self.assertNotIn(self.OPS, [it["route"] for it in nav.compose()])
        self.assertNotIn(self.OPS, [it["route"] for it in nav.compose_all()])

    def test_hidden_from_users_without_the_role(self):
        self.assertNotIn(self.OPS, [it["route"] for it in nav.compose(roles={"Employee"})])
        self.assertNotIn(self.OPS, [it["route"] for it in nav.compose(roles=set())])

    def test_shown_to_users_with_the_role(self):
        self.assertIn(self.OPS, [it["route"] for it in nav.compose(roles={"Employee", "System Manager"})])
        self.assertIn(self.OPS, [it["route"] for it in nav.compose_all(roles={"System Manager"})])

    def test_internal_items_unaffected_by_roles(self):
        base = [it["route"] for it in nav.compose()]
        with_role = [it["route"] for it in nav.compose(roles={"System Manager"})]
        self.assertEqual([r for r in with_role if r != self.OPS], base)

    def test_malformed_role_string_rejected(self):
        for bad in ("role:", "role: ", "roles:System Manager", "admin"):
            it = dict(nav.CORE_ITEMS[0], key="x.r", route="/x-r", visible_when=bad)
            with self.assertRaises(ValueError, msg=bad):
                nav.validate([it])

    def test_no_email_hardcoded_anywhere_in_nav_providers(self):
        """Visibility is by ROLE. A user email in a nav provider is the hardcoded
        user-specific branch the project rules forbid."""
        import io, os, re
        root = os.path.dirname(os.path.dirname(os.path.abspath(nav.__file__)))
        srcs = [os.path.join(root, "shell", "nav.py"),
                os.path.join(root, "approval_center", "shared", "navigation.py")]
        for p in srcs:
            body = io.open(p, encoding="utf-8").read()
            self.assertIsNone(re.search(r"[\w.]+@ecentric\.vn", body),
                              "email hardcoded in %s" % p)

    def test_hr_nav_present_and_salary_no_prerender(self):
        """HR provider: employee-facing entries + salary marked no_prerender.
        Context split: HR items live in compose("hr") (and compose_all), NOT
        in the default approval_document sidebar."""
        items = nav.compose("hr")
        hr = [it for it in items if it.get("owner") == "hr"]
        routes = sorted(it["route"] for it in hr)
        self.assertEqual(routes, ["/ec-hr/attendance",
                                  "/ec-hr/huong-dan-cai-app",
                                  "/ec-hr/leave",
                                  "/ec-hr/salary"])
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


def _fake_frappe(conf=None, user="someone@ecentric.vn", user_type="System User",
                 roles=("Employee",)):
    f = types.ModuleType("frappe")
    f.conf = _FakeConf(conf or {})
    f.session = types.SimpleNamespace(user=user)
    f._ = lambda s: s
    f.get_roles = lambda u=None: list(roles)
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
                 "keywords", "no_prerender", "soon", "alias", "badge_source", "children"},
                "boot nav must not leak extra fields")
        self.assertEqual(set(out["user"]), {"name", "full_name", "image"})

    def test_role_gated_item_only_for_role_holders(self):
        """Boot is the ONLY place a role-gated item may appear - and only for the
        session user holding that role. Both directions checked."""
        ops = "/ec-esign/ops"
        emp = self._api(roles=("Employee",)).get_shell_boot()
        self.assertNotIn(ops, [it["route"] for it in emp["nav"]])
        self.assertNotIn(ops, [it["route"] for it in emp["all_items"]])
        self.tearDown()
        sm = self._api(roles=("Employee", "System Manager")).get_shell_boot()
        self.assertIn(ops, [it["route"] for it in sm["nav"]])
        self.assertIn(ops, [it["route"] for it in sm["all_items"]])


class TestSidebarIA(unittest.TestCase):
    """Locks the PO-approved sidebar IA (2B.1 urgent nav patch). Routes were
    extracted VERBATIM from the legacy production sidebars -- never invented."""

    def _by_key(self):
        return {it["key"]: it for it in nav.compose()}

    def test_exact_ia_map(self):
        # GD2 C2 scope: legacy.create_rec, gbs.po, gbs.so retired (+ create_vendor).
        # MSO/SO/PO kept on governed current routes.
        expected = {
            "apc.catalog": ("Phê duyệt", "Approval Center", "/approvals"),
            "apc.dashboard": ("Phê duyệt", "Dashboard", "/approvals/dashboard"),
            "tickets.all": ("Chứng từ", "Dashboard", "/all-ticket"),
            "approval.inbox": ("Chứng từ", "All Tickets", "/approval"),
            "legacy.create_mso": ("Tạo mới", "MSO Request", "/mso-plan-form"),
            "legacy.create_so": ("Tạo mới", "SO Request", "/gbs-so-form-v2"),
            "legacy.create_po": ("Tạo mới", "PO Request", "/gbs-po-form-v2"),
        }
        by = self._by_key()
        for key, (group, label, route) in expected.items():
            it = by[key]
            self.assertEqual((it["group"], it["label"], it["route"]),
                             (group, label, route), key)
        for retired in ("legacy.create_rec", "legacy.create_vendor", "gbs.po", "gbs.so"):
            self.assertNotIn(retired, by, retired)

    def test_guides_submenu(self):
        guides = self._by_key()["docs.guides"]
        self.assertEqual(guides["group"], "Hướng dẫn")
        kids = [(c["label"], c["route"]) for c in guides["children"]]
        self.assertEqual(kids, [("Docs / Architecture", "/docs/architecture"),
                                ("GBS Flow & Definitions", "/docs/gbs-flow")])

    def test_others_submenu_removed(self):
        # GD2 C2: /others removed entirely — Client/Contract Request unavailable
        # (no submit endpoint); Vendor Request retired. None of these keys/routes
        # may appear in the composed nav. Web Pages kept at published=0 (not here).
        by = self._by_key()
        for key in ("legacy.others", "legacy.create_client",
                    "legacy.create_contract", "legacy.create_vendor"):
            self.assertNotIn(key, by, key)
        routes = set()
        for it in nav.compose():
            routes.add(it["route"])
            for c in it.get("children", []):
                routes.add(c["route"])
        for gone in ("/others", "/client-request", "/contract-request", "/vendor-request"):
            self.assertNotIn(gone, routes, gone)

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
        bad = dict(items[0], key="x.dup", route="/docs/architecture")  # existing child route (guides submenu)
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
