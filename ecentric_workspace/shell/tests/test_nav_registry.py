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
        self.assertGreaterEqual(len(a), 4)  # home + 3 approval items in v1
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

    def test_no_business_data_fields(self):
        # registry payload must stay navigation-only
        allowed = set(nav.REQUIRED_FIELDS) | {"badge_source"}
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
                set(it), {"key", "label", "route", "icon", "group", "active_patterns"},
                "boot nav must not leak extra fields")
        self.assertEqual(set(out["user"]), {"name", "full_name", "image"})


if __name__ == "__main__":
    unittest.main()
