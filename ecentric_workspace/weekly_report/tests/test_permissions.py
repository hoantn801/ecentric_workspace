# Copyright (c) 2026, eCentric and contributors
"""Pham vi doc `Weekly Team Update`.

Test quan trong nhat o day khong phai "ai xem duoc" ma la CA HAI DUONG CUNG MOT
LUAT: `wtu_query_conditions` (danh sach) va `can_read` (mot ban ghi). Ten ban ghi
co khuon `WTU-2026-W39-NV00162` -- doan duoc tu tay. Neu danh sach giau ban ghi
Management ma trang chi tiet van mo, thi coi nhu chua chan gi ca, chi kho nhin
hon mot chut.

`test_dept_scope_pointing_at_management_is_ignored` la dieu ca task nay ton tai
vi no. Neu ai sau nay "sua cho tien" bang cach bo dieu kien loc Management ra
khoi vong lap scope=dept, no phai do o day.

    bench run-tests --module ecentric_workspace.weekly_report.tests.test_permissions
"""

import sys
import types
import unittest

if "frappe" not in sys.modules:
    _fr = types.ModuleType("frappe")
    _fr.get_all = lambda *a, **k: []
    _fr.get_roles = lambda u: []
    _fr.whitelist = lambda *a, **k: (lambda f: f)
    _fr._ = lambda s: s

    class _PermissionError(Exception):
        pass
    _fr.PermissionError = _PermissionError

    def _throw(msg, exc=None):
        raise (exc or Exception)(msg)
    _fr.throw = _throw
    _fr.session = types.SimpleNamespace(user="tester")
    _fr.local = types.SimpleNamespace()
    _fr.db = types.SimpleNamespace(
        get_value=lambda *a, **k: None,
        sql=lambda *a, **k: [],
        escape=lambda s: "'" + str(s).replace("'", "''") + "'",
    )
    sys.modules["frappe"] = _fr

import frappe  # noqa: E402

from ecentric_workspace.weekly_report import permissions as P  # noqa: E402

MGMT = P.MANAGEMENT_DEPARTMENT


class _Base(unittest.TestCase):
    """Dung mot the gioi gia: nhan vien, kiem nhiem, va quyen xem."""

    def setUp(self):
        self.roles = {}
        self.employees = {}        # user -> {name, department}
        self.memberships = {}      # employee name -> [department]
        self.viewer = {}           # user -> [(scope, dept)]

        frappe.local.ec_wtu_scope = {}
        frappe.get_roles = lambda u: self.roles.get(u, [])

        def get_value(doctype, filters, fields=None, as_dict=False, **k):
            if doctype == "Employee" and isinstance(filters, dict):
                if filters.get("status") != "Active":
                    return None
                return self.employees.get(filters.get("user_id"))
            if doctype == P.DOCTYPE and isinstance(filters, str):
                return self.docs.get(filters)
            return None
        frappe.db.get_value = get_value

        self.tree = []             # [{name, reports_to, department}]

        def get_all(doctype, filters=None, **k):
            filters = filters or {}
            if doctype == "EC Viewer Permission":
                return [{"scope": s, "custom_department": d}
                        for s, d in self.viewer.get(filters.get("user_email"), [])]
            if doctype == "Employee Department Membership":
                got = self.memberships.get(filters.get("parent"), [])
                return [{"name": "m1"}] if filters.get("department") in got else []
            if doctype == "Employee":
                return list(self.tree)
            return []
        frappe.get_all = get_all
        self.docs = {}

    def _clear_cache(self):
        frappe.local.ec_wtu_scope = {}


class ScopeTest(_Base):
    def test_administrator_sees_everything(self):
        self.assertTrue(P.compute_scope("Administrator")["full"])
        self.assertEqual(P.wtu_query_conditions("Administrator"), "",
                         "rong = khong han che")

    def test_system_manager_sees_everything(self):
        self.roles["sm@x.vn"] = ["System Manager", "Employee"]
        self.assertEqual(P.wtu_query_conditions("sm@x.vn"), "")

    def test_management_department_sees_everything(self):
        self.employees["ceo@x.vn"] = {"name": "EMP-1", "department": MGMT}
        self.assertTrue(P.compute_scope("ceo@x.vn")["full"])

    def test_management_via_membership_sees_everything(self):
        """Kiem nhiem Management cung tinh -- nguoi thuoc phong khac nhung ngoi
        trong ban dieu hanh van phai xem duoc."""
        self.employees["u@x.vn"] = {"name": "EMP-2", "department": "Service - EC"}
        self.memberships["EMP-2"] = [MGMT]
        self.assertTrue(P.compute_scope("u@x.vn")["full"])

    def test_viewer_scope_all_sees_everything(self):
        self.employees["hr@x.vn"] = {"name": "EMP-3", "department": "HR - EC"}
        self.viewer["hr@x.vn"] = [("all", None)]
        self.assertTrue(P.compute_scope("hr@x.vn")["full"])

    def test_plain_employee_is_limited_to_self(self):
        self.employees["nv@x.vn"] = {"name": "EMP-9", "department": "Service - EC"}
        cond = P.wtu_query_conditions("nv@x.vn")
        self.assertIn("`submitter` = 'nv@x.vn'", cond)
        self.assertIn("`employee` = 'EMP-9'", cond)
        self.assertNotIn("department", cond,
                         "khong co quyen theo phong thi khong duoc co menh de phong")

    def test_dept_viewer_gets_its_departments(self):
        self.employees["lead@x.vn"] = {"name": "EMP-4", "department": "Service - EC"}
        self.viewer["lead@x.vn"] = [("dept", "Service - EC"), ("dept", "HR - EC")]
        cond = P.wtu_query_conditions("lead@x.vn")
        self.assertIn("'Service - EC'", cond)
        self.assertIn("'HR - EC'", cond)

    def test_dept_scope_pointing_at_management_is_ignored(self):
        """Ly do cua ca task nay.

        Mot dong `EC Viewer Permission` scope=dept tro vao Management KHONG mo
        duoc bao cao Management. Nhom do chi nguoi trong nhom moi xem duoc; muon
        cho ai do xem thi phai cho ho vao nhom, khong phai cap quyen vong.
        """
        self.employees["x@x.vn"] = {"name": "EMP-5", "department": "Service - EC"}
        self.viewer["x@x.vn"] = [("dept", MGMT), ("dept", "Service - EC")]
        scope = P.compute_scope("x@x.vn")
        self.assertFalse(scope["full"])
        self.assertEqual(scope["departments"], ["Service - EC"])
        self.assertNotIn(MGMT, P.wtu_query_conditions("x@x.vn"))

    def test_inactive_employee_falls_back_to_submitter_only(self):
        """Nguoi da nghi: khong suy ra phong ban nua. Dong lai, khong mo ra."""
        self.employees["old@x.vn"] = None
        cond = P.wtu_query_conditions("old@x.vn")
        self.assertIn("`submitter` = 'old@x.vn'", cond)
        self.assertNotIn("`employee`", cond)

    def test_membership_lookup_failure_does_not_grant_access(self):
        """Bang kiem nhiem la duong PHU. No hong thi mat quyen rong, chu tuyet
        doi khong duoc thanh 'cho qua'."""
        self.employees["u@x.vn"] = {"name": "EMP-6", "department": "Service - EC"}

        def boom(*a, **k):
            raise RuntimeError("bang khong ton tai")
        frappe.get_all = boom
        self.assertFalse(P.compute_scope("u@x.vn")["full"])

    def test_user_string_is_escaped_not_interpolated(self):
        self.employees["a'b@x.vn"] = {"name": "EMP-7", "department": "Service - EC"}
        cond = P.wtu_query_conditions("a'b@x.vn")
        self.assertIn("'a''b@x.vn'", cond)


class SingleRecordTest(_Base):
    """`can_read` phai khop TUNG DONG voi menh de WHERE o tren."""

    def setUp(self):
        _Base.setUp(self)
        self.employees["nv@x.vn"] = {"name": "EMP-9", "department": "Service - EC"}
        self.docs = {
            "WTU-W39-CEO": {"submitter": "ceo@x.vn", "employee": "EMP-1",
                            "department": MGMT},
            "WTU-W39-ME": {"submitter": "nv@x.vn", "employee": "EMP-9",
                           "department": "Service - EC"},
            "WTU-W39-PEER": {"submitter": "ban@x.vn", "employee": "EMP-8",
                             "department": "Service - EC"},
        }

    def test_own_report_is_readable(self):
        self.assertTrue(P.can_read("WTU-W39-ME", "nv@x.vn"))

    def test_management_report_is_not_readable_by_name(self):
        """Lo hong `?view=`: doan ten ban ghi roi mo thang. Phai chan o day, vi
        `frappe.db.get_value` khong di qua lop quyen nao."""
        self.assertFalse(P.can_read("WTU-W39-CEO", "nv@x.vn"))

    def test_peer_in_same_department_is_not_readable_without_scope(self):
        """Cung phong KHONG tu dong cho xem. Phai co dong scope=dept."""
        self.assertFalse(P.can_read("WTU-W39-PEER", "nv@x.vn"))

    def test_peer_becomes_readable_with_dept_scope(self):
        self.viewer["nv@x.vn"] = [("dept", "Service - EC")]
        self._clear_cache()
        self.assertTrue(P.can_read("WTU-W39-PEER", "nv@x.vn"))

    def test_dept_scope_on_management_still_cannot_read_management(self):
        self.viewer["nv@x.vn"] = [("dept", MGMT)]
        self._clear_cache()
        self.assertFalse(P.can_read("WTU-W39-CEO", "nv@x.vn"),
                         "cap quyen vong khong duoc mo duoc nhom Management")

    def test_unknown_record_is_refused_not_allowed(self):
        """Ban ghi khong doc duoc -> dict rong -> khong khop gi -> tu choi."""
        self.assertFalse(P.can_read("WTU-KHONG-CO", "nv@x.vn"))

    def test_assert_raises_permission_error(self):
        with self.assertRaises(frappe.PermissionError):
            P.assert_can_read("WTU-W39-CEO", "nv@x.vn")

    def test_hook_only_tightens_read(self):
        """Moi ptype khac nhuong cho DocPerm: siet them o day se lam hong luong
        NOP bao cao, mot loi nang hon loi dang sua."""
        for ptype in ("write", "create", "submit", "delete"):
            self.assertTrue(P.wtu_has_permission("WTU-W39-CEO", ptype, "nv@x.vn"),
                            "ptype %s phai nhuong cho DocPerm" % ptype)
        self.assertFalse(P.wtu_has_permission("WTU-W39-CEO", "read", "nv@x.vn"))

    def test_hook_accepts_a_doc_object_not_only_a_name(self):
        doc = types.SimpleNamespace(submitter="ceo@x.vn", employee="EMP-1",
                                    department=MGMT)
        self.assertFalse(P.wtu_has_permission(doc, "read", "nv@x.vn"))


class ManagerChainTest(_Base):
    """Chuoi quan ly -- them 28/09 sau khi deploy lam lo ra khe ho.

    `/team-pulse` cho quan ly xem cap duoi theo `reports_to` tu 20/07, con luat
    port tu `ec_wtu_list_scope` thi khong biet den chuoi do. Bat luat len la 4
    quan ly nhin thay tom tat cua 10 cap duoi nhung bam vao thi bi tu choi.
    Do do o day lay hop cua hai ban.
    """

    def setUp(self):
        _Base.setUp(self)
        self.employees["sep@x.vn"] = {"name": "EMP-SEP", "department": "Service - EC"}
        self.tree = [
            {"name": "EMP-SEP", "reports_to": None, "department": "Service - EC"},
            {"name": "EMP-A", "reports_to": "EMP-SEP", "department": "Service - EC"},
            {"name": "EMP-B", "reports_to": "EMP-SEP", "department": "Media - EC"},
            {"name": "EMP-C", "reports_to": "EMP-A", "department": "Service - EC"},
            {"name": "EMP-NGOAI", "reports_to": None, "department": "HR - EC"},
        ]

    def test_direct_and_indirect_subordinates_are_visible(self):
        sc = P.compute_scope("sep@x.vn")
        self.assertEqual(sorted(sc["subordinates"]), ["EMP-A", "EMP-B", "EMP-C"],
                         "phai lay ca cap duoi cua cap duoi")

    def test_crosses_department_boundaries(self):
        """EMP-B o phong khac nhung van duoi quyen -- /team-pulse van cho xem."""
        self.assertIn("EMP-B", P.compute_scope("sep@x.vn")["subordinates"])

    def test_people_outside_the_chain_stay_invisible(self):
        self.assertNotIn("EMP-NGOAI", P.compute_scope("sep@x.vn")["subordinates"])

    def test_self_is_not_listed_as_own_subordinate(self):
        self.assertNotIn("EMP-SEP", P.compute_scope("sep@x.vn")["subordinates"])

    def test_chain_never_passes_through_management(self):
        """Neu `reports_to` tro vao Management thi nhom do van phai kin --
        khong duoc lay ca nguoi nam DUOI nguoi Management do."""
        self.tree = [
            {"name": "EMP-SEP", "reports_to": None, "department": "Service - EC"},
            {"name": "EMP-MGMT", "reports_to": "EMP-SEP", "department": MGMT},
            {"name": "EMP-DUOI-MGMT", "reports_to": "EMP-MGMT",
             "department": "Service - EC"},
        ]
        subs = P.compute_scope("sep@x.vn")["subordinates"]
        self.assertNotIn("EMP-MGMT", subs)
        self.assertNotIn("EMP-DUOI-MGMT", subs,
                         "khong duoc di XUYEN qua nut Management")

    def test_a_loop_in_reports_to_does_not_hang(self):
        """`reports_to` la du lieu nguoi nhap. Mot vong tro nguoc khong duoc
        lam treo request.

        Cai chan vong o day la phep khu trung `c not in out`, KHONG phai bien
        dem -- test nay xanh ngay ca khi bo bien dem. Bien dem duoc ghim rieng
        o `test_depth_is_capped` ben duoi; hai luoi khac nhau, thu rieng.
        """
        self.tree = [
            {"name": "EMP-SEP", "reports_to": "EMP-X", "department": "Service - EC"},
            {"name": "EMP-X", "reports_to": "EMP-SEP", "department": "Service - EC"},
        ]
        subs = P.compute_scope("sep@x.vn")["subordinates"]
        self.assertEqual(subs, ["EMP-X"])

    def test_depth_is_capped(self):
        """Chuoi dai hon gioi han thi bi cat, khong duyet vo han.

        Con so 15 khong tu tien: `team_pulse_data` dung dung so do. Hai ben le
        nhau thi lai sinh ra dung cai khe ho ma ban va nay sinh ra de vá.
        """
        self.assertEqual(P.CHAIN_MAX_DEPTH, 15)
        chain = [{"name": "EMP-SEP", "reports_to": None, "department": "Service - EC"}]
        for i in range(20):
            chain.append({"name": "EMP-%02d" % i,
                          "reports_to": "EMP-SEP" if i == 0 else "EMP-%02d" % (i - 1),
                          "department": "Service - EC"})
        self.tree = chain
        subs = P.compute_scope("sep@x.vn")["subordinates"]
        self.assertEqual(len(subs), P.CHAIN_MAX_DEPTH,
                         "phai dung o dung %d tang" % P.CHAIN_MAX_DEPTH)

    def test_where_clause_carries_the_chain(self):
        cond = P.wtu_query_conditions("sep@x.vn")
        self.assertIn("'EMP-A'", cond)
        self.assertIn("'EMP-C'", cond)

    def test_can_read_a_subordinate_record(self):
        self.docs = {"WTU-CAP-DUOI": {"submitter": "a@x.vn", "employee": "EMP-C",
                                      "department": "Service - EC"}}
        self.assertTrue(P.can_read("WTU-CAP-DUOI", "sep@x.vn"))

    def test_still_cannot_read_management_even_as_a_manager(self):
        self.docs = {"WTU-CEO": {"submitter": "ceo@x.vn", "employee": "EMP-1",
                                 "department": MGMT}}
        self.assertFalse(P.can_read("WTU-CEO", "sep@x.vn"))

    def test_someone_with_no_reports_gets_an_empty_chain(self):
        self.employees["le@x.vn"] = {"name": "EMP-C", "department": "Service - EC"}
        self.assertEqual(P.compute_scope("le@x.vn")["subordinates"], [])

    def test_employee_lookup_failure_does_not_open_the_chain(self):
        def boom(*a, **k):
            raise RuntimeError("DB sap")
        orig = frappe.get_all
        frappe.get_all = lambda dt, **k: (boom() if dt == "Employee" else orig(dt, **k))
        self._clear_cache()
        self.assertEqual(P.compute_scope("sep@x.vn")["subordinates"], [])


class JinjaGateTest(_Base):
    """Cua ma trang /weekly-update goi. Cua nay chua lo hong `?view=`."""

    def setUp(self):
        _Base.setUp(self)
        frappe.get_traceback = lambda: "traceback gia"
        self.logged = []
        frappe.log_error = lambda **k: self.logged.append(k)
        self.employees["nv@x.vn"] = {"name": "EMP-9", "department": "Service - EC"}
        self.docs = {
            "WTU-W39-CEO": {"submitter": "ceo@x.vn", "employee": "EMP-1",
                            "department": MGMT},
            "WTU-W39-ME": {"submitter": "nv@x.vn", "employee": "EMP-9",
                           "department": "Service - EC"},
        }
        frappe.session.user = "nv@x.vn"

    def tearDown(self):
        frappe.session.user = "tester"

    def test_blocks_the_guessed_management_record(self):
        self.assertFalse(P.can_view_weekly_record("WTU-W39-CEO"))

    def test_allows_own_record(self):
        self.assertTrue(P.can_view_weekly_record("WTU-W39-ME"))

    def test_empty_name_is_false_not_true(self):
        self.assertFalse(P.can_view_weekly_record(""))
        self.assertFalse(P.can_view_weekly_record(None))

    def test_never_raises_because_an_exception_blanks_the_whole_page(self):
        """Mot ngoai le trong Jinja lam VO CA TRANG, ke ca phan nop bao cao cua
        chinh nguoi do. Chan phai la chan mot muc, khong phai hong ca trang."""
        def boom(*a, **k):
            raise RuntimeError("DB sap")
        frappe.db.get_value = boom
        self._clear_cache()
        try:
            got = P.can_view_weekly_record("WTU-W39-ME")
        except Exception as exc:
            self.fail("khong duoc nem loi ra Jinja: %r" % (exc,))
        self.assertFalse(got, "hong thi phai coi nhu KHONG duoc xem")
        self.assertTrue(self.logged, "va phai de lai dau vet de con truy")


class ListAndRecordAgreeTest(_Base):
    """Luoi cuoi: hai duong khong duoc lech nhau.

    Khong chay duoc SQL that o day, nen thay bang mot bo loc Python dich sat
    menh de WHERE. Khong bang SQL that, nhung du de bat truong hop mot ben doi
    ma ben kia quen.
    """

    def _rows_visible_by_condition(self, user, docs):
        scope = P.compute_scope(user)
        if scope["full"]:
            return set(docs)
        out = set()
        for name, d in docs.items():
            if (d["submitter"] == user
                    or (scope["employee"] and d["employee"] == scope["employee"])
                    or d["department"] in scope["departments"]
                    or d["employee"] in scope["subordinates"]):
                out.add(name)
        return out

    def test_both_paths_agree_for_every_shape_of_user(self):
        self.employees["nv@x.vn"] = {"name": "EMP-9", "department": "Service - EC"}
        self.employees["ceo@x.vn"] = {"name": "EMP-1", "department": MGMT}
        self.employees["lead@x.vn"] = {"name": "EMP-4", "department": "Service - EC"}
        self.viewer["lead@x.vn"] = [("dept", "Service - EC"), ("dept", MGMT)]
        self.roles["sm@x.vn"] = ["System Manager"]
        # Mot quan ly co cap duoi o phong KHAC: nhanh chuoi quan ly phai duoc
        # hai duong doi xu giong nhau, khong chi nhanh phong ban.
        self.employees["sep@x.vn"] = {"name": "EMP-SEP", "department": "Service - EC"}
        self.tree = [
            {"name": "EMP-SEP", "reports_to": None, "department": "Service - EC"},
            {"name": "EMP-7", "reports_to": "EMP-SEP", "department": "HR - EC"},
            {"name": "EMP-1", "reports_to": "EMP-SEP", "department": MGMT},
        ]

        docs = {
            "A": {"submitter": "ceo@x.vn", "employee": "EMP-1", "department": MGMT},
            "B": {"submitter": "nv@x.vn", "employee": "EMP-9",
                  "department": "Service - EC"},
            "C": {"submitter": "ban@x.vn", "employee": "EMP-8",
                  "department": "Service - EC"},
            "D": {"submitter": "hr@x.vn", "employee": "EMP-7", "department": "HR - EC"},
        }
        self.docs = docs

        for user in ("nv@x.vn", "ceo@x.vn", "lead@x.vn", "sm@x.vn", "sep@x.vn", "la@x.vn"):
            self._clear_cache()
            by_list = self._rows_visible_by_condition(user, docs)
            self._clear_cache()
            by_record = {n for n in docs if P.can_read(n, user)}
            self.assertEqual(by_list, by_record,
                             "danh sach va ban ghi le lech nhau voi %s" % user)

    def test_nobody_outside_management_sees_the_management_record(self):
        self.employees["nv@x.vn"] = {"name": "EMP-9", "department": "Service - EC"}
        self.viewer["nv@x.vn"] = [("dept", MGMT)]
        self.docs = {"A": {"submitter": "ceo@x.vn", "employee": "EMP-1",
                           "department": MGMT}}
        self.assertFalse(P.can_read("A", "nv@x.vn"))


if __name__ == "__main__":
    unittest.main()
