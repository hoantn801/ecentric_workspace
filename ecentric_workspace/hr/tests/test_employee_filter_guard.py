"""Chan "do gia tri bang filter" tren Employee (hr/privacy/filter_refs.py + filter_guard.py).
KHONG can bench. Chay: python -m unittest ecentric_workspace.hr.tests.test_employee_filter_guard
"""
import importlib.util
import json
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PRIV = os.path.join(HERE, "..", "privacy")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(PRIV, rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fr = _load("ecentric_workspace.hr.privacy.filter_refs", "filter_refs.py")

EMP = "Employee"
CHILD = "EC Employee Contract"
TABLES = {"ec_contracts": CHILD}
# HR User: khong co L1 (bank_ac_no, cell_number...), co L2 (bang hop dong).
HR_USER_RESTRICTED = {EMP: {"bank_ac_no", "cell_number", "date_of_birth", "passport_number"},
                      CHILD: set()}
# Nhan vien thuong: khong co L1 lan L2 -> ca cot cua bang hop dong cung khong doc duoc.
STAFF_RESTRICTED = {EMP: HR_USER_RESTRICTED[EMP] | {"ec_contracts", "ec_laptop"},
                    CHILD: {"so_hop_dong", "tu_ngay", "den_ngay"}}


def bad(params, restricted=HR_USER_RESTRICTED, base=EMP):
    return fr.violations(fr.referenced_fields(params, base, TABLES), restricted)


class FilterShapes(unittest.TestCase):
    def test_dict_filter(self):
        self.assertEqual(bad({"filters": {"bank_ac_no": ["like", "9%"]}}), ["Employee.bank_ac_no"])

    def test_dict_filter_as_json_string(self):
        self.assertEqual(bad({"filters": json.dumps({"bank_ac_no": "123"})}),
                         ["Employee.bank_ac_no"])

    def test_three_part_list(self):
        self.assertEqual(bad({"filters": json.dumps([["bank_ac_no", "like", "9%"]])}),
                         ["Employee.bank_ac_no"])

    def test_four_part_list_with_doctype(self):
        self.assertEqual(bad({"filters": [[EMP, "bank_ac_no", "like", "9%"]]}),
                         ["Employee.bank_ac_no"])

    def test_single_unwrapped_condition(self):
        self.assertEqual(bad({"filters": ["cell_number", "like", "09%"]}), ["Employee.cell_number"])

    def test_or_filters_and_current_filters(self):
        self.assertEqual(bad({"or_filters": [["date_of_birth", ">", "2000-01-01"]]}),
                         ["Employee.date_of_birth"])
        self.assertEqual(bad({"current_filters": json.dumps([[EMP, "passport_number", "like", "0%"]])}),
                         ["Employee.passport_number"])

    def test_child_table_filter_for_staff(self):
        params = {"filters": [[CHILD, "so_hop_dong", "like", "HD%"]]}
        self.assertEqual(bad(params, STAFF_RESTRICTED), ["EC Employee Contract.so_hop_dong"])
        self.assertEqual(bad(params), [])  # HR User co L2 -> duoc

    def test_order_by_group_by_fields(self):
        self.assertEqual(bad({"order_by": "`tabEmployee`.`bank_ac_no` desc"}), ["Employee.bank_ac_no"])
        self.assertEqual(bad({"group_by": "date_of_birth"}), ["Employee.date_of_birth"])
        self.assertEqual(bad({"order_by": "ec_contracts.so_hop_dong asc"}, STAFF_RESTRICTED),
                         ["EC Employee Contract.so_hop_dong"])

    def test_select_columns_left_to_frappe(self):
        # Frappe tu bo cot khong doc duoc khoi SELECT -> khong tu choi, de report cua HR User chay.
        self.assertEqual(bad({"fields": json.dumps(["name", "bank_ac_no", "sum(cell_number) as x"]),
                              "fieldname": "bank_ac_no"}), [])

    def test_sidebar_and_search_params(self):
        self.assertEqual(bad({"field": "bank_ac_no"}), ["Employee.bank_ac_no"])
        self.assertEqual(bad({"searchfield": "cell_number"}), ["Employee.cell_number"])
        self.assertEqual(bad({"stats": json.dumps(["bank_ac_no"])}), ["Employee.bank_ac_no"])

    def test_allowed_fields_pass(self):
        params = {"filters": {"department": "Service - EC", "status": "Active"},
                  "fields": ["name", "employee_name", "count(*) as c"],
                  "order_by": "modified desc", "group_by": "department"}
        self.assertEqual(bad(params), [])

    def test_values_are_not_mistaken_for_fields(self):
        # gia tri trung ten field khong phai la tham chieu
        self.assertEqual(bad({"filters": [["employee_name", "=", "bank_ac_no"]]}), [])
        self.assertEqual(bad({"order_by": "field(status, 'bank_ac_no')"}), [])

    def test_get_value_with_plain_name_filter(self):
        self.assertEqual(bad({"filters": "HR-EMP-00002", "fieldname": "employee_name"}), [])

    def test_broken_json_still_inspected(self):
        self.assertEqual(bad({"filters": '[["bank_ac_no","like"'}), ["Employee.bank_ac_no"])


def _frappe_stub(path, form, roles_restricted, user="tran.bui@x"):
    class PermissionError(Exception):
        pass

    stub = types.ModuleType("frappe")
    stub.PermissionError = PermissionError
    stub._ = lambda s: s
    stub.session = types.SimpleNamespace(user=user)
    stub.request = types.SimpleNamespace(path=path, method="GET")
    stub.form_dict = dict(form)
    stub.logged = []
    stub.log_error = lambda **k: stub.logged.append(k)

    def throw(msg, exc=Exception):
        raise exc(msg)
    stub.throw = throw
    sys.modules["frappe"] = stub

    pl = types.ModuleType("ecentric_workspace.hr.privacy.permlevels")
    pl.restricted_fields = lambda dt: (roles_restricted, TABLES)
    pl.child_doctypes = lambda dt: {CHILD}
    sys.modules["ecentric_workspace.hr.privacy.permlevels"] = pl
    pkg = sys.modules.setdefault("ecentric_workspace.hr.privacy",
                                 types.ModuleType("ecentric_workspace.hr.privacy"))
    pkg.permlevels = pl
    return stub, _load("ec_filter_guard", "filter_guard.py")


NOTHING_RESTRICTED = {EMP: set(), CHILD: set()}


class Guard(unittest.TestCase):
    def call(self, path, form, restricted, user="tran.bui@x"):
        stub, guard = _frappe_stub(path, form, restricted, user)
        guard.guard_employee_filters()
        return stub

    def test_hr_user_filter_bank_account_rejected(self):
        stub, guard = _frappe_stub("/api/resource/Employee",
                                   {"filters": '[["bank_ac_no","like","9%"]]'}, HR_USER_RESTRICTED)
        with self.assertRaises(stub.PermissionError):
            guard.guard_employee_filters()

    def test_hr_user_filter_department_allowed(self):
        self.call("/api/resource/Employee", {"filters": '[["department","=","Service - EC"]]'},
                  HR_USER_RESTRICTED)

    def test_hr_manager_filter_bank_account_allowed(self):
        self.call("/api/method/frappe.client.get_list",
                  {"doctype": EMP, "filters": {"bank_ac_no": ["like", "9%"]}}, NOTHING_RESTRICTED)

    def test_every_listed_entry_point_is_guarded(self):
        form = {"doctype": EMP, "filters": {"bank_ac_no": ["like", "9%"]}}
        entries = ["/api/resource/Employee", "/api/v2/document/Employee",
                   "/api/v2/doctype/Employee/count"]
        entries += ["/api/method/" + m for m in (
            "frappe.client.get_list", "frappe.client.get_count", "frappe.client.get_value",
            "frappe.desk.reportview.get", "frappe.desk.reportview.get_count",
            "frappe.desk.reportview.export_query", "frappe.desk.search.search_link",
            "frappe.desk.search.search_widget")]
        entries.append("/api/v2/method/frappe.desk.reportview.get")
        for path in entries:
            stub, guard = _frappe_stub(path, form, HR_USER_RESTRICTED)
            with self.assertRaises(stub.PermissionError, msg=path):
                guard.guard_employee_filters()

    def test_group_by_sidebar_field(self):
        stub, guard = _frappe_stub("/api/method/frappe.desk.listview.get_group_by_count",
                                   {"doctype": EMP, "current_filters": "[]", "field": "bank_ac_no"},
                                   HR_USER_RESTRICTED)
        with self.assertRaises(stub.PermissionError):
            guard.guard_employee_filters()

    def test_child_doctype_with_parent_employee(self):
        stub, guard = _frappe_stub("/api/method/frappe.client.get_list",
                                   {"doctype": CHILD, "parent": EMP,
                                    "filters": [["so_hop_dong", "like", "HD%"]]}, STAFF_RESTRICTED)
        with self.assertRaises(stub.PermissionError):
            guard.guard_employee_filters()

    def test_other_doctypes_and_single_doc_untouched(self):
        self.call("/api/resource/Customer", {"filters": '[["bank_ac_no","like","9%"]]'},
                  HR_USER_RESTRICTED)
        self.call("/api/resource/Employee/HR-EMP-00002", {}, HR_USER_RESTRICTED)
        self.call("/api/method/frappe.client.get_list",
                  {"doctype": CHILD, "parent": "Other", "filters": [["so_hop_dong", "=", "x"]]},
                  STAFF_RESTRICTED)

    def test_administrator_skipped(self):
        self.call("/api/resource/Employee", {"filters": '[["bank_ac_no","like","9%"]]'},
                  HR_USER_RESTRICTED, user="Administrator")



class AfterAuthentication(unittest.TestCase):
    """Loi 28/09 17:10: hook dang ky o before_request chay TRUOC validate_auth(), nen request dung
    API token bi coi la Guest va moi filter Employee bi 403. Nay hook o auth_hooks: luc chay,
    frappe.session.user da la chu token. Cac test duoi gia lap dung trang thai do."""

    def test_registered_in_auth_hooks_not_before_request(self):
        hooks = open(os.path.join(HERE, "..", "..", "hooks.py"), encoding="utf-8").read()
        path = '"ecentric_workspace.hr.privacy.filter_guard.guard_employee_filters"'
        self.assertIn("auth_hooks = [" + path + "]", hooks)
        before = [l for l in hooks.splitlines() if l.startswith("before_request")]
        self.assertFalse(any("filter_guard" in l for l in before), before)

    def test_hr_manager_token_filter_status_allowed(self):
        stub, guard = _frappe_stub("/api/resource/Employee",
                                   {"filters": '[["status","=","Active"]]'},
                                   NOTHING_RESTRICTED, user="hr.manager@x")
        guard.guard_employee_filters()

    def test_hr_user_token_filter_bank_account_rejected(self):
        stub, guard = _frappe_stub("/api/resource/Employee",
                                   {"filters": '[["bank_ac_no","like","9%"]]'},
                                   HR_USER_RESTRICTED, user="tran.bui@x")
        with self.assertRaises(stub.PermissionError):
            guard.guard_employee_filters()

    def test_hr_user_token_filter_status_allowed(self):
        stub, guard = _frappe_stub("/api/resource/Employee",
                                   {"filters": '[["status","=","Active"]]'},
                                   HR_USER_RESTRICTED, user="tran.bui@x")
        guard.guard_employee_filters()

    def test_guest_left_to_frappe(self):
        # Guest o auth_hooks = chua dang nhap that: Frappe tu tra 401/403, hook khong chen vao.
        everything = {EMP: {"status", "bank_ac_no"}, CHILD: set()}
        stub, guard = _frappe_stub("/api/resource/Employee",
                                   {"filters": '[["status","=","Active"]]'},
                                   everything, user="Guest")
        guard.guard_employee_filters()


if __name__ == "__main__":
    unittest.main()
