# Copyright (c) 2026, eCentric and contributors
"""Nhap ma MISA hang loat tu tep (PO 24/11/2026) - chay khong can bench.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_creators_misa_import.py

Kiem:
  1. Quyen: nguoi khong phai EC Finance khong xem truoc / ap dung duoc (ca hai buoc).
  2. Doc tep: CSV tu nut Xuat CSV (BOM, dau ' chong cong thuc, ; cua Excel VN), .xlsx; thieu cot -> loi ro.
  3. Trang thai tung dong: Khop / Ma trong / Sai dinh dang / Khong tim thay / Creator lap / Ma trung trong
     file / Ma da gan creator khac / Creator da co ma khac / Da co dung ma.
  4. Ap dung: server KIEM LAI (client gui trang thai gia khong lot), ghi qua set_misa_code (ghi vet), dong
     loi khong lam hong dong khac, chay lai lan hai khong ghi gi (idempotent), toi da 500 dong.
"""
import base64
import io
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "..", "..")))

from test_creators_service import FakeRepo  # noqa: E402

from ecentric_workspace.approval_center.shared.creators import misa_import  # noqa: E402
from ecentric_workspace.approval_center.shared.creators.repository import InsertError  # noqa: E402
from ecentric_workspace.approval_center.shared.creators.service import (  # noqa: E402
    CreatorError, CreatorPermissionError, CreatorService)

FIN = "ketoan@ec"
ROLES = {FIN: ["EC Finance"], "sale@ec": ["Employee"]}
HEAD = "ma_erp,ten,loai,mst,cccd,sdt,email,dia_chi,ma_misa"


def world():
    rows = [{"name": "SUP-001", "supplier_name": "Nguyễn Thị Hảo", "ec_cr_misa_code": "KH0001", "owner": "an@ec"},
            {"name": "SUP-002", "supplier_name": "Trần Văn B", "ec_cr_misa_code": None, "owner": "an@ec"},
            {"name": "SUP-003", "supplier_name": "Lê C", "ec_cr_misa_code": "", "owner": "an@ec"},
            {"name": "Phạm Thị Dung", "supplier_name": "Phạm Thị Dung", "ec_cr_misa_code": None, "owner": "an@ec"}]
    repo = FakeRepo(rows, ROLES)
    repo.notes = []
    return CreatorService(repo)


def b64(text, enc="utf-8-sig"):
    return base64.b64encode(text.encode(enc)).decode()


def csv_text(*lines):
    return "\n".join((HEAD,) + lines) + "\n"


def by_line(out):
    return {r["line"]: r for r in out["rows"]}


class PermissionTests(unittest.TestCase):
    def test_khong_phai_ke_toan_bi_chan_ca_hai_buoc(self):
        s = world()
        with self.assertRaises(CreatorPermissionError):
            misa_import.preview("sale@ec", "a.csv", b64(csv_text('SUP-002,B,,,,,,,KH0002')), service=s)
        with self.assertRaises(CreatorPermissionError):
            misa_import.apply("sale@ec", [{"line": 2, "name": "SUP-002", "code": "KH0002"}], service=s)
        self.assertEqual(s.repo.updated, [])


class ReadFileTests(unittest.TestCase):
    def test_csv_tu_nut_xuat_csv_bom_va_dau_nhay_chong_cong_thuc(self):
        text = csv_text('"SUP-002","Trần Văn B","Cá nhân","","\'+84123","","","","KH0002"',
                        '"Phạm Thị Dung","Phạm Thị Dung","","","","","","","\'-KH9"')
        out = misa_import.preview(FIN, "creator_chua_co_ma_misa.csv", "data:text/csv;base64," + b64(text), service=world())
        rows = by_line(out)
        self.assertEqual((rows[2]["status"], rows[2]["code"], rows[2]["supplier_name"]), ("khop", "KH0002", "Trần Văn B"))
        # dau ' do nut Xuat CSV them bi bo; "-KH9" bat dau bang '-' -> sai dinh dang (khong lot thanh cong thuc)
        self.assertEqual((rows[3]["code"], rows[3]["status"]), ("-KH9", "sai_dinh_dang"))
        self.assertEqual(out["rows"][0]["line"], 2)

    def test_csv_excel_vn_dau_cham_phay_va_ansi(self):
        text = "ma_erp;ten;ma_misa\nPhạm Thị Dung;Phạm Thị Dung;KH0100\n"
        out = misa_import.preview(FIN, "a.csv", b64(text, "utf-8"), service=world())
        self.assertEqual(out["rows"][0]["status"], "khop")
        # Excel "CSV (Comma delimited)" tren may tieng Anh: mat dau -> khong tim thay + goi y luu UTF-8
        out = misa_import.preview(FIN, "a.csv", b64("ma_erp,ma_misa\nPh?m Th? Dung,KH0100\n", "cp1252"), service=world())
        self.assertEqual(out["rows"][0]["status"], "khong_tim_thay")
        self.assertIn("UTF-8", out["rows"][0]["message"])

    def test_xlsx(self):
        try:
            from openpyxl import Workbook
        except ImportError:
            self.skipTest("khong co openpyxl")
        wb = Workbook()
        ws = wb.active
        ws.append(["Mã ERP", "Tên", "Mã MISA"])     # tieu de go tay co dau van nhan
        ws.append(["SUP-002", "Trần Văn B", "KH0002"])
        ws.append([None, None, None])               # dong trong bi bo qua
        ws.append(["SUP-003", "Lê C", 12345])        # o so -> "12345", khong "12345.0"
        buf = io.BytesIO()
        wb.save(buf)
        out = misa_import.preview(FIN, "ma.xlsx", base64.b64encode(buf.getvalue()).decode(), service=world())
        rows = by_line(out)
        self.assertEqual(rows[2]["status"], "khop")
        self.assertEqual((rows[4]["code"], rows[4]["status"]), ("12345", "khop"))
        self.assertEqual(out["valid"], 2)

    def test_thieu_cot_ma_misa_hoac_ma_erp(self):
        with self.assertRaises(CreatorError) as cm:
            misa_import.preview(FIN, "a.csv", b64("ma_erp,ten\nSUP-002,B\n"), service=world())
        self.assertIn("ma_misa", str(cm.exception))
        with self.assertRaises(CreatorError) as cm:
            misa_import.preview(FIN, "a.csv", b64("ten,ma_misa\nB,KH1\n"), service=world())
        self.assertIn("ma_erp", str(cm.exception))

    def test_tep_rong_xls_cu_va_qua_lon(self):
        for content, name in (("", "a.csv"), (b64(HEAD + "\n"), "a.csv"), (b64("x"), "a.xls")):
            with self.assertRaises(CreatorError):
                misa_import.preview(FIN, name, content, service=world())
        with self.assertRaises(CreatorError):
            misa_import.read_table("a.csv", b"x" * (misa_import.MAX_BYTES + 1))

    def test_qua_500_dong_bi_chan(self):
        lines = ["SUP-%04d,,,,,,,,KH%04d" % (i, i) for i in range(misa_import.MAX_ROWS + 1)]
        with self.assertRaises(CreatorError) as cm:
            misa_import.preview(FIN, "a.csv", b64(csv_text(*lines)), service=world())
        self.assertIn("500", str(cm.exception))
        ok = misa_import.preview(FIN, "a.csv", b64(csv_text(*lines[:500])), service=world())
        self.assertEqual(ok["total"], 500)


class ClassifyTests(unittest.TestCase):
    def test_moi_trang_thai(self):
        text = csv_text(
            "SUP-002,,,,,,,,KH0002",        # 2 khop
            "SUP-003,,,,,,,,",              # 3 ma trong
            "SUP-003,,,,,,,,KH 03",         # 4 sai dinh dang (dau cach)
            "SUP-999,,,,,,,,KH0999",        # 5 khong tim thay
            "SUP-001,,,,,,,,KH0001",        # 6 da co dung ma
            "SUP-001,,,,,,,,KH7777",        # 7 creator lap (SUP-001 hai dong co ma)
            "Phạm Thị Dung,,,,,,,,KH0001",  # 8 ma da gan creator khac (SUP-001)
            ",,,,,,,,KH0555",               # 9 thieu ma ERP
        )
        out = misa_import.preview(FIN, "a.csv", b64(text), service=world())
        st = {line: r["status"] for line, r in by_line(out).items()}
        self.assertEqual(st, {2: "khop", 3: "ma_trong", 4: "sai_dinh_dang", 5: "khong_tim_thay",
                              6: "creator_lap", 7: "creator_lap", 8: "trung_creator_khac", 9: "khong_tim_thay"})
        self.assertEqual(out["valid"], 1)
        self.assertEqual(out["counts"]["creator_lap"], 2)
        self.assertTrue(all(r["label"] for r in out["rows"]))

    def test_da_co_ma_khac_va_da_co_dung_ma(self):
        out = misa_import.preview(FIN, "a.csv", b64(csv_text("SUP-001,,,,,,,,KH9999")), service=world())
        self.assertEqual(out["rows"][0]["status"], "da_co_ma")
        out = misa_import.preview(FIN, "a.csv", b64(csv_text("SUP-001,,,,,,,,kh0001")), service=world())
        self.assertEqual(out["rows"][0]["status"], "da_co_cung_ma")   # so khong phan biet hoa thuong nhu DB

    def test_ma_trung_trong_file_khong_phan_biet_hoa_thuong(self):
        out = misa_import.preview(FIN, "a.csv", b64(csv_text("SUP-002,,,,,,,,KH0500", "SUP-003,,,,,,,,kh0500")),
                                  service=world())
        self.assertEqual([r["status"] for r in out["rows"]], ["trung_trong_file", "trung_trong_file"])

    def test_xem_truoc_khong_ghi_gi(self):
        s = world()
        misa_import.preview(FIN, "a.csv", b64(csv_text("SUP-002,,,,,,,,KH0002")), service=s)
        self.assertEqual(s.repo.updated, [])


class ApplyTests(unittest.TestCase):
    def test_ghi_dong_khop_qua_set_misa_code_co_ghi_vet(self):
        s = world()
        calls = []
        real = s.set_misa_code
        s.set_misa_code = lambda *a, **k: (calls.append((a, k)), real(*a, **k))[1]
        out = misa_import.apply(FIN, [{"line": 2, "name": "SUP-002", "code": " KH0002 "},
                                      {"line": 3, "name": "SUP-003", "code": "KH0003"}],
                                filename="ma.csv", service=s)
        self.assertEqual((out["saved"], out["errors"], out["skipped"]), (2, 0, 0))
        self.assertEqual(s.repo.rows["SUP-002"]["ec_cr_misa_code"], "KH0002")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1].get("overwrite"), False)
        self.assertTrue(any("KH0002" in n and "ma.csv" in n and FIN in n for n in s.repo.notes))
        self.assertEqual([r["status"] for r in out["rows"]], ["da_luu", "da_luu"])

    def test_server_kiem_lai_khong_tin_client(self):
        s = world()
        out = misa_import.apply(FIN, [
            {"line": 2, "name": "SUP-001", "code": "KH0002", "status": "khop"},   # da co ma khac: khong de len
            {"line": 3, "name": "SUP-002", "code": "KH0001", "status": "khop"},   # ma cua SUP-001
            {"line": 4, "name": "SUP-003", "code": "x y", "status": "khop"},      # sai dinh dang
            {"line": 5, "name": "SUP-404", "code": "KH0404", "status": "khop"},   # khong co
            {"line": 6, "name": "Phạm Thị Dung", "code": "KH0600"},               # hop le
        ], service=s)
        st = [r["status"] for r in out["rows"]]
        self.assertEqual(st, ["da_co_ma", "trung_creator_khac", "sai_dinh_dang", "khong_tim_thay", "da_luu"])
        self.assertEqual((out["saved"], out["errors"]), (1, 4))
        self.assertEqual(s.repo.rows["SUP-001"]["ec_cr_misa_code"], "KH0001")
        self.assertIsNone(s.repo.rows["SUP-002"]["ec_cr_misa_code"])
        self.assertEqual([u[0] for u in s.repo.updated], ["Phạm Thị Dung"])

    def test_ma_trung_trong_lo_gui_len_khong_ghi_dong_nao(self):
        s = world()
        out = misa_import.apply(FIN, [{"line": 2, "name": "SUP-002", "code": "KH0700"},
                                      {"line": 3, "name": "SUP-003", "code": "KH0700"}], service=s)
        self.assertEqual(out["saved"], 0)
        self.assertEqual(s.repo.updated, [])

    def test_chay_lai_lan_hai_khong_ghi_gi(self):
        s = world()
        rows = [{"line": 2, "name": "SUP-002", "code": "KH0002"}]
        misa_import.apply(FIN, rows, service=s)
        n = len(s.repo.updated)
        again = misa_import.apply(FIN, rows, service=s)
        self.assertEqual(len(s.repo.updated), n)
        self.assertEqual((again["saved"], again["skipped"], again["errors"]), (0, 1, 0))
        self.assertEqual(again["rows"][0]["status"], "da_co_cung_ma")

    def test_loi_ghi_mot_dong_khong_hong_dong_khac(self):
        s = world()
        real = s.repo.update

        def flaky(name, values, note=None, isolate=False):
            if name == "SUP-002":
                self.assertTrue(isolate)   # duong ghi ma MISA luon co lap tung dong
                raise InsertError("Supplier bị khoá")
            return real(name, values, note=note, isolate=isolate)
        s.repo.update = flaky
        out = misa_import.apply(FIN, [{"line": 2, "name": "SUP-002", "code": "KH0002"},
                                      {"line": 3, "name": "SUP-003", "code": "KH0003"}], service=s)
        self.assertEqual([r["status"] for r in out["rows"]], ["loi", "da_luu"])
        self.assertIn("Supplier bị khoá", out["rows"][0]["message"])
        self.assertEqual((out["saved"], out["errors"]), (1, 1))

    def test_gioi_han_va_du_lieu_sai(self):
        many = [{"line": i, "name": "SUP-002", "code": "KH%d" % i} for i in range(misa_import.MAX_ROWS + 1)]
        for bad in (many, [], "SUP-002", ["SUP-002"]):
            with self.assertRaises(CreatorError):
                misa_import.apply(FIN, bad, service=world())


class SingleSaveSharesRules(unittest.TestCase):
    """Nut Luu tung dong dung CUNG luat: sai dinh dang bi chan, va co ghi vet."""

    def test_luu_tung_dong(self):
        s = world()
        with self.assertRaises(CreatorError):
            s.set_misa_code(FIN, "SUP-002", "KH 02")
        s.set_misa_code(FIN, "SUP-002", "KH0002")
        self.assertEqual(s.repo.rows["SUP-002"]["ec_cr_misa_code"], "KH0002")
        self.assertTrue(any("KH0002" in n for n in s.repo.notes))


class TransportTests(unittest.TestCase):
    """kol_misa_preview / kol_misa_apply: POST, nguoi dung lay tu PHIEN (khong nhan user), loi quyen ->
    frappe.PermissionError, rows chuoi JSON duoc doc. Nap kol_api voi frappe gia, tra sys.modules ve cu."""

    def setUp(self):
        import types
        fake = types.ModuleType("frappe")
        fake._ = lambda s: s
        self.whitelisted = {}

        def whitelist(*a, **k):
            def deco(f):
                self.whitelisted[f.__name__] = k.get("methods")
                return f
            return deco
        fake.whitelist = whitelist

        class Thrown(Exception):
            pass
        fake.PermissionError = type("PermissionError", (Thrown,), {})
        fake.Thrown = Thrown

        def throw(msg, exc=None):
            raise (exc or Thrown)(msg)
        fake.throw = throw
        fake.session = types.SimpleNamespace(user="sale@ec")
        self.saved = {k: sys.modules.get(k) for k in ("frappe",)}
        sys.modules["frappe"] = fake
        self.fake = fake
        path = os.path.abspath(os.path.join(_HERE, "..", "..", "features", "contract_review", "controllers", "kol_api.py"))
        mod = types.ModuleType("kol_api_misa_t")
        mod.__file__ = path
        exec(compile(open(path, encoding="utf-8").read(), path, "exec"), mod.__dict__)
        self.api = mod
        self.world = world()
        mod.misa_import = types.SimpleNamespace(
            preview=lambda user, fn, content: misa_import.preview(user, fn, content, service=self.world),
            apply=lambda user, items, fn: misa_import.apply(user, items, fn, service=self.world))

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def test_post_va_quyen_theo_phien(self):
        self.assertEqual(self.whitelisted.get("kol_misa_preview"), ["POST"])
        self.assertEqual(self.whitelisted.get("kol_misa_apply"), ["POST"])
        rows = '[{"line": 2, "name": "SUP-002", "code": "KH0002"}]'
        with self.assertRaises(self.fake.PermissionError):
            self.api.kol_misa_apply(rows)
        self.assertEqual(self.world.repo.updated, [])
        self.fake.session.user = FIN
        out = self.api.kol_misa_apply(rows, "ma.csv")
        self.assertEqual(out["saved"], 1)
        prev = self.api.kol_misa_preview("a.csv", b64(csv_text("SUP-003,,,,,,,,KH0003")))
        self.assertEqual(prev["valid"], 1)
        with self.assertRaises(self.fake.Thrown):
            self.api.kol_misa_apply("{khong phai json")
        import inspect
        for fn in (self.api.kol_misa_preview, self.api.kol_misa_apply):
            self.assertFalse({"user", "actor"} & set(inspect.signature(fn).parameters))


if __name__ == "__main__":
    unittest.main()
