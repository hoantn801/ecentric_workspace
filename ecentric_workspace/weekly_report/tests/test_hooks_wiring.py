# Copyright (c) 2026, eCentric and contributors
"""Day noi giua hooks.py va luat phan quyen bao cao tuan.

VI SAO CAN: moi phep kiem khac deu goi THANG vao ham. Chung xanh ngay ca khi
duong module trong hooks.py go sai mot chu -- ham van tinh dung, ma Frappe thi
khong tim thay hook nen KHONG CHAN GI. Kieu hong do khong sinh loi, khong ai
bao, va chi lo ra khi co nguoi doc duoc thu khong duoc phep doc.

Bo test nay doc hooks.py bang AST (khong import, khong can site) va doi chieu
ba thu:
  1. hooks.py tro toi ham CO THAT trong permissions.py
  2. hang so trong api.py khop voi hooks.py -- neu lech, `hooks_loaded.ok` se
     bao sai vinh vien ma khong ai hieu vi sao
  3. khong ai vo tinh go mot trong ba hook ra

    bench run-tests --module ecentric_workspace.weekly_report.tests.test_hooks_wiring
"""

import ast
import io
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.dirname(os.path.dirname(_HERE))          # .../ecentric_workspace
DOCTYPE = "Weekly Team Update"


def _read(*parts):
    with io.open(os.path.join(_APP, *parts), encoding="utf-8") as fh:
        return fh.read()


def _top_level_assigns(src):
    """{ten: gia tri} cho cac gan o cap cao nhat ma doc duoc bang literal_eval."""
    out = {}
    for node in ast.parse(src).body:
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if isinstance(t, ast.Name):
                try:
                    out[t.id] = ast.literal_eval(node.value)
                except Exception:
                    pass
    return out


def _defined_functions(src):
    return {n.name for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef)}


class HooksPointAtRealFunctionsTest(unittest.TestCase):
    def setUp(self):
        self.hooks = _top_level_assigns(_read("hooks.py"))
        self.perm_funcs = _defined_functions(_read("weekly_report", "permissions.py"))

    def _target(self, hook_name):
        m = self.hooks.get(hook_name) or {}
        self.assertIn(DOCTYPE, m,
                      "hooks.py khong con dang ky %s cho %s" % (hook_name, DOCTYPE))
        return m[DOCTYPE]

    def _assert_points_at_real_function(self, path):
        mod, fn = path.rsplit(".", 1)
        rel = mod.replace("ecentric_workspace.", "").replace(".", os.sep) + ".py"
        self.assertTrue(os.path.exists(os.path.join(_APP, rel)),
                        "hooks.py tro toi module khong ton tai: " + mod)
        self.assertIn(fn, _defined_functions(_read(rel)),
                      "module %s khong co ham %s" % (mod, fn))

    def test_query_condition_hook_points_at_a_real_function(self):
        self._assert_points_at_real_function(self._target("permission_query_conditions"))

    def test_has_permission_hook_points_at_a_real_function(self):
        self._assert_points_at_real_function(self._target("has_permission"))

    def test_jinja_method_is_registered_and_real(self):
        methods = (self.hooks.get("jinja") or {}).get("methods") or []
        hits = [m for m in methods if m.endswith(".can_view_weekly_record")]
        self.assertTrue(hits, "khong con dang ky can_view_weekly_record trong jinja."
                              " Trang /weekly-update se VO khi render ?view=.")
        self._assert_points_at_real_function(hits[0])

    def test_all_three_doors_are_still_registered(self):
        """Ba cua, mot luat. Go mot cua ra la mo lai dung duong do."""
        self.assertIn(DOCTYPE, self.hooks.get("permission_query_conditions") or {})
        self.assertIn(DOCTYPE, self.hooks.get("has_permission") or {})
        self.assertTrue((self.hooks.get("jinja") or {}).get("methods"))

    def test_other_modules_hooks_are_not_disturbed(self):
        """Them ten cua minh vao dict dung chung thi khong duoc dung toi ten
        nguoi khac. `Employee` la cua chat HR (#621), Task/Project la cua PM."""
        qc = self.hooks.get("permission_query_conditions") or {}
        for other in ("Task", "Project", "Employee", "EC SLA Obligation"):
            self.assertIn(other, qc, "da lam mat dang ky cua " + other)


class ApiConstantsMatchHooksTest(unittest.TestCase):
    """`_hooks_loaded()` so sanh voi hang so trong api.py. Hang so lech hooks.py
    thi no bao `ok: False` vinh vien -- phep kiem tu bao dong gia, kieu hong
    lam nguoi ta thoi tin vao phep kiem."""

    def setUp(self):
        self.hooks = _top_level_assigns(_read("hooks.py"))
        self.api = _top_level_assigns(_read("weekly_report", "api.py"))

    def test_query_hook_constant_matches(self):
        self.assertEqual(self.api.get("WTU_QUERY_HOOK"),
                         (self.hooks.get("permission_query_conditions") or {}).get(DOCTYPE))

    def test_perm_hook_constant_matches(self):
        self.assertEqual(self.api.get("WTU_PERM_HOOK"),
                         (self.hooks.get("has_permission") or {}).get(DOCTYPE))

    def test_jinja_hook_constant_matches(self):
        methods = (self.hooks.get("jinja") or {}).get("methods") or []
        self.assertIn(self.api.get("WTU_JINJA_HOOK"), methods)


if __name__ == "__main__":
    unittest.main()
