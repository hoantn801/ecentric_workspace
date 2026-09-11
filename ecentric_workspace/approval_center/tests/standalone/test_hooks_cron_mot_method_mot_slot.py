# Copyright (c) 2026, eCentric and contributors
"""Mot `method` chi duoc khai o MOT bieu thuc cron. Khai o hai cho = mat mot luot, im lang.

SU CO (09-10/09/2026). Hoan chot "soi lech chu ky 2 luot/ngay: 08:30 va 14:30". Cach viet
tu nhien nhat - mot vong lap dat CUNG MOT ham vao ca hai bieu thuc - trong hoan toan dung
trong hooks.py, va sai:

    Frappe dinh danh Scheduled Job Type bang `method`, KHONG phai bang (method, cron).

Nen ban ghi thu hai ghi de ban ghi thu nhat. Do tren prod 10/09:
  * `sweep_provider_signature_drift` khai o "30 8" + "30 14"  -> chi ton tai "30 14";
  * `pm.api.schedule.nudge_unconfirmed` khai o "0 9" + "0 18" -> chi ton tai "0 18".
Cai thu hai la loi CO SAN cua module PM, im lang tu truoc, khong ai biet: comment ngay tren
no van ghi "TWICE a day".

Vi sao phai co bo test nay chu khong chi sua hooks.py: cai bay nay khong de lai dau vet nao.
Khong log, khong loi, khong test do - chi la mot luot cron khong bao gio chay. Nguoi viet
tiep theo se lai viet vong lap do, vi no la cach viet dung nhat theo truc giac.

Bo test doc hooks.py THAT (exec ca file, ke ca cac dong `.setdefault().append()` chay sau
khai bao dict) chu khong doc mot ban chep - de no khong bao gio lac hau so voi file that.
"""
import os
import re
import unittest
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))

# `nudge_unconfirmed` thuoc module PM va dang duoc bao cho chat PM xu ly (10/09). De o day
# duoi dang MIEN TRU CO TEN, khong phai lam ngo: khi PM sua xong, dong nay phai duoc xoa.
# Ngu nghia la TAP CON - fix duoc phep, THEM MOI thi khong. Neu de "bang dung tap nay" thi
# ban va cua PM se lam do bo test cua minh, va cai gia do khong dang.
NO_CU_DA_BIET = {
    "ecentric_workspace.pm.api.schedule.nudge_unconfirmed",
}


def _cron_cua_hooks():
    """`scheduler_events['cron']` doc tu hooks.py that, khong can frappe.

    hooks.py chi co DUNG mot import (`from . import __version__`) can ngu canh package;
    thay bang mot hang so roi exec la chay duoc nguyen ven, ke ca phan dung dict bang
    `.setdefault().append()` o cuoi file - phan ma phan tich tinh (ast) se doc sai.
    """
    duong = os.path.join(_APP, "hooks.py")
    with open(duong, encoding="utf-8") as f:
        src = f.read()
    src, n = re.subn(r"^from \. import __version__ as app_version\s*$",
                     'app_version = "0"', src, count=1, flags=re.M)
    assert n == 1, "hooks.py doi cach import __version__ - cap nhat lai bo test nay"
    ns = {}
    exec(compile(src, duong, "exec"), ns)          # noqa: S102 - doc chinh file that
    return ns["scheduler_events"]["cron"]


def _method_theo_cron():
    d = defaultdict(list)
    for bieu_thuc, ds in _cron_cua_hooks().items():
        for m in ds:
            d[m].append(bieu_thuc)
    return d


class TestMoiMethodMotSlotCron(unittest.TestCase):
    def test_khong_method_nao_khai_o_hai_cron(self):
        trung = {m: e for m, e in _method_theo_cron().items() if len(e) > 1}
        moi = set(trung) - NO_CU_DA_BIET
        self.assertFalse(
            moi,
            "Frappe khoa Scheduled Job Type theo `method`: khai mot ham o nhieu cron thi "
            "CHI MOT khung gio song sot, cac khung con lai bien mat khong bao gi. Tach "
            "thanh cac ham vo mong rieng (xem sweep_provider_signature_drift_0830/_1430). "
            "Dang trung: %s" % trung)

    def test_bo_test_nay_chay_that_chu_khong_doc_file_rong(self):
        # Neu `_cron_cua_hooks` im lang tra ve {} (doi duong dan, doi ten bien) thi phep
        # kiem o tren xanh vinh vien ma khong do gi ca. Mot cong khong bao gio do la mot
        # cong khong con canh gi - da dinh dung loi nay ngay 09/09 voi mot cong khac.
        cron = _cron_cua_hooks()
        self.assertGreaterEqual(len(cron), 5, "doc duoc qua it slot cron - nghi phep do")
        self.assertTrue(any("*/1" in k or "*/5" in k for k in cron),
                        "khong thay slot cao tan nao - nghi doc nham bien")


class TestSoiLechChuKyDuHaiLuot(unittest.TestCase):
    """Y dinh cua Hoan la HAI luot/ngay. Kiem dung dieu do, khong kiem "co dang ky la duoc"."""

    GOC = "ecentric_workspace.platform.esign.tasks."

    def test_dung_hai_luot_0830_va_1430(self):
        theo_method = _method_theo_cron()
        for ten, gio in (("sweep_provider_signature_drift_0830", "30 8 * * *"),
                         ("sweep_provider_signature_drift_1430", "30 14 * * *")):
            slots = theo_method.get(self.GOC + ten, [])
            self.assertEqual(slots, [gio], "%s phai khai DUNG mot lan o %r" % (ten, gio))

    def test_ham_goc_KHONG_con_tu_khai_cron(self):
        # Neu ham goc van con nam trong cron, no lai thanh ban ghi thu ba tranh cho voi hai
        # vo mong - va mot trong ba luot lai bien mat.
        self.assertNotIn(self.GOC + "sweep_provider_signature_drift", _method_theo_cron())

    def test_hai_vo_mong_khong_mang_logic_rieng(self):
        """Vo mong phai la CAI TEN, khong phai mot ban sao logic.

        Hai luot ma di theo hai nhanh code khac nhau thi som muon mot nhanh lech - va do la
        cach bien mot ban va thanh hai hanh vi khac nhau tuy gio trong ngay.
        """
        import ast
        with open(os.path.join(_APP, "platform", "esign", "tasks.py"), encoding="utf-8") as f:
            cay = ast.parse(f.read())
        for ten in ("sweep_provider_signature_drift_0830",
                    "sweep_provider_signature_drift_1430"):
            fn = next((n for n in ast.walk(cay)
                       if isinstance(n, ast.FunctionDef) and n.name == ten), None)
            self.assertIsNotNone(fn, "thieu ham %s" % ten)
            than = [n for n in fn.body if not (isinstance(n, ast.Expr)
                                               and isinstance(n.value, ast.Constant))]
            self.assertEqual(len(than), 1, "%s phai chi co MOT lenh (goi ham goc)" % ten)
            self.assertEqual(ast.unparse(than[0]), "return sweep_provider_signature_drift()",
                             "%s phai goi thang ham goc, khong tu xu ly gi" % ten)


if __name__ == "__main__":
    unittest.main()
