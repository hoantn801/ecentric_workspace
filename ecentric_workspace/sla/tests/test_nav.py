# Copyright (c) 2026, eCentric and contributors
"""Muc /sla co xuat hien tren sidebar khong - chay bang python3 tran.

    python3 -m unittest ecentric_workspace.sla.tests.test_nav -v

VI SAO PHAI CO TEST CHO MOT DONG MENU. Dang ky mot muc nav can BA thay doi o ba
tep khac nhau: khai muc (sla/nav.py), dang ky provider, va them provider vao
ngu canh. Lam hai trong ba thi khong co gi bao loi - trang /sla van mo duoc,
chi la no ve mot sidebar cua module khac, va khong ai vao duoc tu menu. Day la
dung loai loi khong bao gio bi phat hien trong review.
"""
import inspect
import unittest

from ecentric_workspace.shell import nav as shell_nav
from ecentric_workspace.sla import nav as sla_nav


class TestSlaNavItem(unittest.TestCase):
    def test_passes_the_registry_contract(self):
        # Cung ham validate() ma shell dung luc dung sidebar that.
        shell_nav.validate(sla_nav.items())

    def test_one_item_only(self):
        # Bon tab la bon cach nhin cung mot bang diem, khong phai bon diem den.
        self.assertEqual(len(sla_nav.items()), 1)

    def test_lands_in_the_hr_group(self):
        it = sla_nav.items()[0]
        self.assertEqual(it["group"], "Nhân sự")
        self.assertEqual(it["route"], "/sla")
        self.assertIn("Nhân sự", shell_nav.GROUP_ORDER)

    def test_items_returns_a_fresh_list(self):
        # Hop dong giong het moi provider khac trong repo (`list(ITEMS)`): ham
        # tra ve mot LIST moi, con tung dict thi shell tu chep nong truoc khi
        # sua (`_compose_owners`: `it = dict(it)`). Test nay khoa dung ve nua
        # ma tep nay chiu trach nhiem - them/bot muc o mot lan compose khong
        # duoc lam thay doi hang so module.
        first = sla_nav.items()
        first.append({"key": "rac"})
        first.pop(0)
        self.assertEqual([it["key"] for it in sla_nav.items()], ["sla.scoreboard"])


class TestRegisteredWithTheShell(unittest.TestCase):
    def test_provider_is_registered(self):
        src = inspect.getsource(shell_nav._providers)
        self.assertIn("sla_nav.items", src)

    def test_hr_context_composes_sla(self):
        # Day moi la cai lam muc hien ra tren sidebar cua trang /sla. Thieu dong
        # nay thi muc duoc dang ky nhung khong ngu canh nao ve no.
        self.assertIn("sla", shell_nav.CONTEXTS["hr"]["providers"])

    def test_route_resolves_to_the_hr_context(self):
        # Neu /sla khong thuoc ngu canh nao thi resolve_context tra ve
        # DEFAULT_CONTEXT va trang se ve sidebar Phe duyet.
        self.assertEqual(shell_nav.resolve_context("/sla"), "hr")


class TestPortalAlias(unittest.TestCase):
    def test_portal_has_an_alias_row(self):
        rows = [it for it in shell_nav.HOME_PORTAL_ITEMS if it["route"] == "/sla"]
        self.assertEqual(len(rows), 1, "trang chu phai co mot dong tro toi /sla")
        self.assertTrue(rows[0].get("alias"),
                        "dong tren trang chu phai la alias - route thuoc ngu canh hr")

    def test_alias_does_not_steal_the_route(self):
        # alias bi bo qua khi cham diem ngu canh; neu quen co `alias` thi /sla se
        # roi vao ngu canh `home` va ve sidebar cong thay vi sidebar Nhan su.
        self.assertEqual(shell_nav.resolve_context("/sla"), "hr")


if __name__ == "__main__":
    unittest.main()
