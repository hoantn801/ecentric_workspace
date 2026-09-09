# Copyright (c) 2026, eCentric and contributors
"""Dua mot chan ky len "Signed" thi PHAI dat `verified_at` - khong co ngoai le.

SU CO (09/09/2026, DSR-2026-00080). Duong doi soat THU CONG xac minh THANH CONG chu ky tay
cua Vinh (`verified_predating_manual:08/09/2026 23:48`), dua chan ky len "Signed" - roi engine
tu choi ngay sau do:

    PermissionError: Cap duyet nay yeu cau ky so... [dsr_not_verified]

`guard.validate_completion` doc DUNG mot truong: `verified_at`. Ma `reconcile_manual_review`
(28/08, c6a2ecce) tu viet lai chuyen doi trang thai bang tay va QUEN dat truong do. Hai cho
kia trong tasks.py thi dat dung. Va `service.mark_verified` - ham duy nhat biet luat nay -
KHONG AI GOI: no la code chet tu luc sinh ra.

Nen duong doi soat thu cong chua bao gio hoan tat duoc mot cap duyet nao, tu 28/08 den 09/09.
Loi nam im hai tuan vi lan chay dau roi vao mot yeu cau DA HUY, nen ai cung tuong that bai la
do yeu cau huy.

Bo test nay khong kiem "co goi mark_verified khong" - kiem the thi doi ten ham la mu. No kiem
DIEU BAT BIEN: trong ca package esign, KHONG mot cho nao duoc dat trang thai "Signed" ma
khong kem `verified_at`. Ban sao thu tu xuat hien la test do ngay, du no nam o file nao.
"""
import ast
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_ESIGN = os.path.join(_APP, "platform", "esign")


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


def _py_files():
    for root, dirs, files in os.walk(_ESIGN):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests", "docs")]
        for n in sorted(files):
            if n.endswith(".py"):
                yield os.path.join(root, n)


#: Vi tri cua tham so `to_status` trong tung ham. PHAI theo dung vi tri, khong duoc chi do
#: "co chuoi 'Signed' trong loi goi": `_guarded_dsr_transition(dsr, "Signed", "Manual Review")`
#: la chuyen DI KHOI Signed - bat nham no thi phep do bao dong gia va nguoi doc se sua code
#: dang chay dung. (Da dinh dung cai nay khi viet test nay.)
_TO_STATUS_ARG = {"set_dsr_status": 1, "_guarded_dsr_transition": 2}


def _signed_transitions():
    """Moi loi goi dat trang thai DSR THANH "Signed", kem file/dong va tham so tu khoa."""
    out = []
    for path in _py_files():
        with io.open(path, encoding="utf-8") as fh:
            src = fh.read()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name not in _TO_STATUS_ARG:
                continue
            args = node.args
            idx = _TO_STATUS_ARG[name]
            if len(args) <= idx:
                continue
            to = args[idx]
            if not (isinstance(to, ast.Constant) and to.value == "Signed"):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            out.append({"file": os.path.relpath(path, _APP), "line": node.lineno,
                        "fn": name, "kw": kw})
    return out


def _has_verified_at(kw):
    d = kw.get("extra_fields") or kw.get("extra")
    if not isinstance(d, ast.Dict):
        return False
    return any(isinstance(k, ast.Constant) and k.value == "verified_at" for k in d.keys)


class TestKhongCoDuongNaoLenSignedMaThieuVerifiedAt(unittest.TestCase):
    def test_moi_cho_dat_Signed_deu_kem_verified_at(self):
        rows = _signed_transitions()
        self.assertTrue(rows, "khong quet duoc cho nao dat 'Signed' - phep do hong")
        thieu = ["%s:%d (%s)" % (r["file"], r["line"], r["fn"])
                 for r in rows if not _has_verified_at(r["kw"])]
        self.assertEqual(thieu, [],
                         "dat 'Signed' ma KHONG dat verified_at -> guard.validate_completion "
                         "se tu choi voi dsr_not_verified: %s" % thieu)

    def test_chi_con_DUNG_MOT_cho_dat_Signed(self):
        """Ba ban sao la ly do mot ban thieu mot dong. Gio phai la mot."""
        rows = _signed_transitions()
        self.assertEqual(len(rows), 1,
                         "moi cho dat 'Signed' phai di qua service.mark_verified: %s"
                         % ["%s:%d" % (r["file"], r["line"]) for r in rows])
        self.assertTrue(rows[0]["file"].endswith("service.py"))


class TestMarkVerified(unittest.TestCase):
    """Chay THAT ham do, khong doc suong."""

    def _fn(self):
        src = _read("platform", "esign", "service.py")
        node = next(n for n in ast.parse(src).body
                    if isinstance(n, ast.FunctionDef) and n.name == "mark_verified")
        seen = {}

        class _Events(object):
            @staticmethod
            def set_dsr_status(dsr, to_status, extra_fields=None, **kw):
                seen.update({"dsr": dsr, "to": to_status,
                             "extra": dict(extra_fields or {}), "kw": kw})
        ns = {"events": _Events, "now_datetime": lambda: "2026-09-09 12:00:00"}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "service.py", "exec"), ns)
        return ns["mark_verified"], seen

    def test_dat_verified_at_va_trang_thai_Signed(self):
        fn, seen = self._fn()
        fn("EC-DSR-2026-00080")
        self.assertEqual(seen["to"], "Signed")
        self.assertEqual(seen["extra"].get("verified_at"), "2026-09-09 12:00:00")

    def test_ly_do_di_TU_THAM_SO_chu_khong_phai_hang_so(self):
        """Duong doi soat mang mot ly do RIENG (`verified_predating_manual:...`) de con dem
        duoc. Dong cung thanh "verified" la mat dau vet do."""
        fn, seen = self._fn()
        fn("EC-DSR-2026-00080", "verified_predating_manual:08/09/2026 23:48")
        self.assertEqual(seen["kw"].get("verification_result"),
                         "verified_predating_manual:08/09/2026 23:48")

    def test_mac_dinh_van_la_verified(self):
        fn, seen = self._fn()
        fn("EC-DSR-2026-00080")
        self.assertEqual(seen["kw"].get("verification_result"), "verified")


class TestGuardVanDocDungTruongDo(unittest.TestCase):
    """Neu ai do doi guard sang doc truong khac, phep bat bien o tren thanh vo nghia."""

    def test_guard_tu_choi_dua_tren_verified_at(self):
        src = _read("platform", "esign", "guard.py")
        fn = next(ast.unparse(n) for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "validate_completion")
        self.assertIn("'verified_at'", fn.replace('"', "'"),
                      "guard phai NAP truong nay thi phep kiem moi that")
        self.assertIn("dsr_not_verified", fn)


class TestDuongDoiSoatDungHamChung(unittest.TestCase):
    def test_reconcile_goi_mark_verified_kem_ly_do(self):
        src = _read("platform", "esign", "service.py")
        fn = next(ast.unparse(n) for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "reconcile_manual_review")
        # Kiem ca THAM SO: bo `vr.reason` di van goi ham, van xanh neu chi kiem ten ham -
        # va luc do ly do doi soat thu cong bien mat khoi so.
        self.assertIn("mark_verified(dsr_name, vr.reason)", fn)


if __name__ == "__main__":
    unittest.main()
