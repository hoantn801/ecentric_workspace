"""Ho so nhan su 28/09/2026 - kiem tra KHONG can bench:
  * bo loc lich su thay doi (hr/privacy/version_filter.py) khong lot field permlevel cao;
  * permission query Employee (hr/privacy/employee_scope.py) dung luat cua Server Script cu;
  * ba ham ghi de trong form_load.py giu dung chu ky frappe v16, va hooks tro dung cho.
Chay: python -m unittest ecentric_workspace.hr.tests.test_employee_privacy
"""
import ast
import importlib.util
import json
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PRIV = os.path.join(HERE, "..", "privacy")


def _load(name, rel, frappe_stub=None):
    if frappe_stub is not None:
        sys.modules["frappe"] = frappe_stub
    spec = importlib.util.spec_from_file_location(name, os.path.join(PRIV, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vf = _load("ec_version_filter", "version_filter.py")

READABLE = {"employee_name", "department", "ec_sub_department", "additional_departments"}
CHILDREN = {"additional_departments": {"department"}}  # ec_contracts (L2) KHONG doc duoc


def _v(data):
    return {"name": "V1", "owner": "hr@x", "creation": "2026-09-28", "data": json.dumps(data)}


class VersionFilter(unittest.TestCase):
    def run_filter(self, data):
        return vf.filter_versions([_v(data)], READABLE, CHILDREN)

    def test_changed_hides_high_permlevel_field(self):
        out = self.run_filter({"changed": [["ec_allow_lunch", "1", "2"],
                                           ["department", "A - EC", "B - EC"]]})
        self.assertEqual(len(out), 1)
        data = json.loads(out[0]["data"])
        self.assertEqual(data["changed"], [["department", "A - EC", "B - EC"]])
        self.assertNotIn("ec_allow_lunch", out[0]["data"])

    def test_version_with_only_hidden_changes_is_dropped(self):
        self.assertEqual(self.run_filter({"changed": [["cell_number", "09", "08"],
                                                      ["bank_ac_no", "1", "2"]]}), [])

    def test_unreadable_table_rows_are_dropped(self):
        data = {"added": [["ec_contracts", {"name": "r1", "so_hop_dong": "HD-1"}]],
                "row_changed": [["ec_contracts", "r1", 1, [["so_hop_dong", "a", "b"]]]]}
        self.assertEqual(self.run_filter(data), [])

    def test_readable_table_keeps_only_readable_columns(self):
        data = {"added": [["additional_departments",
                           {"name": "r1", "idx": 1, "department": "X - EC", "secret": "s"}]],
                "row_changed": [["additional_departments", "r1", 1,
                                 [["department", "X", "Y"], ["secret", "a", "b"]]]]}
        out = json.loads(self.run_filter(data)[0]["data"])
        self.assertEqual(out["added"][0][1], {"name": "r1", "idx": 1, "department": "X - EC"})
        self.assertEqual(out["row_changed"][0][3], [["department", "X", "Y"]])

    def test_creation_entry_without_field_values_is_kept(self):
        data = {"creation": "2026-09-28", "created_by": "hr@x", "updater_reference": {"a": 1}}
        out = self.run_filter(data)
        self.assertEqual(json.loads(out[0]["data"]), data)

    def test_unparseable_data_fails_closed(self):
        self.assertEqual(vf.filter_versions([{"name": "V", "data": "{oops"}], READABLE, CHILDREN), [])

    def test_empty_input(self):
        self.assertEqual(vf.filter_versions(None, READABLE, CHILDREN), [])


class EmployeeScope(unittest.TestCase):
    def scope(self, roles, user="nv@ecentric.vn"):
        stub = types.ModuleType("frappe")
        stub.session = types.SimpleNamespace(user=user)
        stub.get_roles = lambda u=None: roles
        stub.db = types.SimpleNamespace(escape=lambda v: "'%s'" % v.replace("'", "\\'"))
        mod = _load("ec_employee_scope", "employee_scope.py", stub)
        return mod.employee_query_conditions(user, doctype="Employee")

    def test_plain_employee_sees_only_self(self):
        self.assertEqual(self.scope(["Employee"]), "`tabEmployee`.`user_id` = 'nv@ecentric.vn'")

    def test_quote_in_user_is_escaped(self):
        self.assertIn("\\'", self.scope(["Employee"], user="a'b@x"))

    def test_hr_roles_see_everyone(self):
        for role in ("System Manager", "HR Manager", "HR User", "EC CnB"):
            self.assertEqual(self.scope(["Employee", role]), "", role)

    def test_administrator_sees_everyone(self):
        self.assertEqual(self.scope([], user="Administrator"), "")


# Chu ky frappe v16 (frappe/desk/form/load.py, save.py). Lech mot ten tham so la form Desk gay.
FRAPPE_SIGNATURES = {"getdoc": ["doctype", "name"],
                     "get_docinfo": ["doc", "doctype", "name"],
                     "savedocs": ["doc", "action"]}


class Overrides(unittest.TestCase):
    def test_signatures_match_frappe(self):
        tree = ast.parse(open(os.path.join(PRIV, "form_load.py"), encoding="utf-8").read())
        found = {f.name: [a.arg for a in f.args.args] for f in tree.body
                 if isinstance(f, ast.FunctionDef)}
        self.assertEqual(found, FRAPPE_SIGNATURES)

    def test_hooks_point_to_existing_functions(self):
        hooks = open(os.path.join(HERE, "..", "..", "hooks.py"), encoding="utf-8").read()
        for name in FRAPPE_SIGNATURES:
            self.assertIn('"ecentric_workspace.hr.privacy.form_load.%s"' % name, hooks)
        self.assertIn('"ecentric_workspace.hr.privacy.employee_scope.employee_query_conditions"',
                      hooks)


if __name__ == "__main__":
    unittest.main()
