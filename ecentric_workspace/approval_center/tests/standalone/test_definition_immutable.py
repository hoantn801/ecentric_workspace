# -*- coding: utf-8 -*-
"""`validate_definition` - hop dong ADR: KHONG truong nao cua dinh nghia duoc phep mutable.

SU CO PRODUCTION 17/09. Toi them truong `ai_hints` va truyen thang mot **dict** vao. Guard
nay tu choi, va vi no chay luc NAP REGISTRY nen no ha ca nhung endpoint chang lien quan gi
toi AI: `list_all_requests` (hub "Tat ca yeu cau") tra 417 y het duong AI. Mot truong moi
sai kieu = ca Approval Center khong nap duoc.

Bai hoc: them mot truong vao contract CO validator thi phai CHAY validator do. Repo da co
san guard; toi chi la khong bao gio goi no. Bo test nay chay duoc KHONG CAN frappe, nen
khong con co de bo qua.
"""
import dataclasses
import io
import os
import sys
import types
import unittest
from types import MappingProxyType

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(
    _HERE, "..", "..", "shared", "requests", "contracts.py"))


def _load():
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    saved = sys.modules.get("frappe")
    sys.modules["frappe"] = fk
    try:
        m = types.ModuleType("_contracts_under_test")
        with io.open(_SRC, encoding="utf-8") as fh:
            exec(compile(fh.read(), "contracts.py", "exec"), m.__dict__)
        return m
    finally:
        if saved is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = saved


def _dinh_nghia(m, **ghi_de):
    """Mot dinh nghia toi gian DU HOP LE, de phep kiem chi noi ve truong dang xet."""
    kw = {}
    for f in dataclasses.fields(m.ApprovalDefinition):
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            kw[f.name] = ()
    kw.update(
        code="X", business_doctype="EC Payment Request",
        options_provider=lambda *a, **k: {},
        submitter=lambda *a, **k: None,
        resubmitter=lambda *a, **k: None,
        title_builder=None, draft_preparer=None, detail_extender=None,
    )
    kw.update(ghi_de)
    return m.ApprovalDefinition(**kw)


class TestKhongTruongNaoDuocMutable(unittest.TestCase):
    def setUp(self):
        self.m = _load()

    def test_nen_tang_khong_khai_gi_them_thi_hop_le(self):
        self.m.validate_definition(_dinh_nghia(self.m))   # khong duoc nem

    def test_ai_hints_la_DICT_THUONG_thi_bi_tu_choi(self):
        # Chinh la loi 17/09. Neu phep kiem nay xanh voi mot dict thuong thi no vo dung.
        with self.assertRaises(ValueError) as e:
            self.m.validate_definition(_dinh_nghia(self.m, ai_hints={"a": "b"}))
        self.assertIn("ai_hints", str(e.exception))

    def test_ai_hints_boc_MappingProxyType_thi_qua(self):
        self.m.validate_definition(
            _dinh_nghia(self.m, ai_hints=MappingProxyType({"request_title": "mau"})))

    def test_mac_dinh_cua_ai_hints_tu_no_da_hop_le(self):
        d = _dinh_nghia(self.m)
        self.assertNotIsInstance(d.ai_hints, dict)
        self.assertEqual(dict(d.ai_hints), {})

    def test_luat_ap_cho_MOI_truong_chu_khong_rieng_ai_hints(self):
        # Guard duyet toan bo `fields()`. Giu phep kiem nay de lan sau ai them truong moi
        # cung dam vao day chu khong dam vao production.
        for ten, gia_tri in (("ai_exclude_fields", ["a"]),
                             ("editable_fields", {"a"}),
                             ("status_labels", {"a": "b"})):
            with self.assertRaises(ValueError, msg=ten) as e:
                self.m.validate_definition(_dinh_nghia(self.m, **{ten: gia_tri}))
            self.assertIn(ten, str(e.exception))


class TestDinhNghiaTHAT(unittest.TestCase):
    """Doc thang file dinh nghia cua payment_request de chac chan no BOC ai_hints.

    Khong import duoc module do o day (no keo theo frappe), nen doc nguon - va phep kiem
    duoc viet sao cho doi ten bien cung khong lam no xanh gia."""

    def test_payment_request_boc_ai_hints(self):
        src = io.open(os.path.abspath(os.path.join(
            _HERE, "..", "..", "features", "payment_request", "domain", "definition.py")),
            encoding="utf-8").read()
        self.assertIn("ai_hints=MappingProxyType(", src)
        self.assertNotIn("ai_hints=ai_hints or {}", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
