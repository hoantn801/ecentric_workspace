# Copyright (c) 2026, eCentric and contributors
"""Chu ky phai roi DUNG cho nguoi dat o.

Do dac 02/09/2026 tren tai lieu that (EC-DSP-2026-00028, A4 595x842). Doc thang `/Rect` cua
annotation chu ky trong PDF do SCTS tra ve, so voi con so ERP gui di:

    chan ky          ERP GUI (llx, lly, w, h)   SCTS DAT THUC (llx, lly, w, h)
    Nguoi de nghi    355.0  721.0  240  120     286.2  588.8  180   90
    Direct Manager   263.0  606.0  240  120     217.2  502.5  180   90

Bon phep do doc lap deu ra 0.75 = 72/96, tuc ty le point/pixel o 96 DPI: SCTS doc con so
minh gui nhu PIXEL roi quy ra point, con minh gui POINT. Moi o ky vi vay bi co con 3/4 va
dich cho - deu dan tren moi chung tu, nen suot may thang chi thay "no lech" ma khong ai chi
ra duoc lech bao nhieu.

Hai gia thuyet canh tranh da bi loai bang do dac, khong bang suy doan:
  * "SCTS bo qua toa do minh gui, dat theo vung cua sign-template" -> neu vay phan du cua hai
    chu ky da khac nhau; thuc te chung trung khit den hai chu so thap phan, trong khi x cua
    hai chu ky lech nhau 92 diem.
  * "SCTS co ca trang lai 0.75" -> doc lai PDF da ky thi dong tieu de van o dung (60, 760),
    co chu van 14, MediaBox van 595x842. Trang khong bi dung toi.

Bo test nay giu ba dieu:
  1. Phep bu la NGHICH DAO that su cua phep do: gui qua `to_provider_box` roi ap dung chinh
     phep bien doi cua SCTS thi phai ve dung o ban dau. Day la phep kiem chinh.
  2. Hang so hieu chinh phai TAI TAO duoc so lieu do dac goc. Doi con so ma quen so lieu thi
     do.
  3. Cho xay payload PHAI goi `to_provider_box`. Mot phep bu khong ai goi la mot phep bu
     khong ton tai.

[TEMP-WORKAROUND] Day la hieu chinh tu do dac, CHUA co xac nhan cua SCTS. Neu ho sua phia ho
thi phep bu nay lam lech nguoc lai. Xem BACKLOG_ESIGN.md muc "Toa do chu ky".
"""
import ast
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "platform", "esign")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()
_SCTS = os.path.join(_ROOT, "platform", "esign", "providers", "scts.py")
_SRC = io.open(_SCTS, encoding="utf-8").read()
_TREE = ast.parse(_SRC)


def _phan_thuan():
    """Nap RIENG hang so + hai ham thuan tu scts.py (khong keo theo frappe).

    exec(compile(<van ban>)) chu khong phai loader theo duong dan: loader dung lai
    `__pycache__`, va mot dot bien giu nguyen kich thuoc file se duoc cham tren ban .pyc cu.
    """
    giu = []
    for node in _TREE.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "").startswith("SCTS_"):
            giu.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in ("to_provider_box",
                                                                 "from_provider_box"):
            giu.append(node)
    assert len(giu) >= 5, "thieu hang so hoac ham hieu chinh trong scts.py: %d" % len(giu)
    mod = types.ModuleType("scts_calib")
    exec(compile(ast.Module(body=giu, type_ignores=[]), "scts_calib", "exec"),  # noqa: S102
         mod.__dict__)
    return mod


#: So lieu DO DUOC 02/09 - (llx, lly, w, h) ERP gui  ->  (llx, lly, w, h) SCTS dat thuc te.
DO_DAC = [
    ("Nguoi de nghi",  (355.0, 721.0, 240.0, 120.0), (286.2, 588.8, 180.0, 90.0)),
    ("Direct Manager", (263.0, 606.0, 240.0, 120.0), (217.2, 502.5, 180.0, 90.0)),
]


class TestHangSoTaiTaoDuocSoLieuDoDac(unittest.TestCase):
    """Doi hang so ma khong doi so lieu do dac = do."""

    def test_ap_phep_bien_doi_len_so_lieu_goc_ra_dung_ket_qua_do_duoc(self):
        m = _phan_thuan()
        for ten, gui, that in DO_DAC:
            ra = m.from_provider_box(*gui)
            for nhan, duoc, mong in (("llx", ra["x"], that[0]), ("lly", ra["y"], that[1]),
                                     ("w", ra["w"], that[2]), ("h", ra["h"], that[3])):
                self.assertAlmostEqual(
                    duoc, mong, delta=0.6,
                    msg="%s / %s: hang so hieu chinh khong tai tao duoc so lieu do duoc "
                        "(tinh ra %.2f, do duoc %.2f)" % (ten, nhan, duoc, mong))

    def test_ty_le_dung_bang_72_tren_96(self):
        m = _phan_thuan()
        self.assertAlmostEqual(m.SCTS_SCALE, 72.0 / 96.0, places=6,
                               msg="0.75 khong phai con so ngau nhien - do la point/pixel o "
                                   "96 DPI. Lech khoi no thi gia thuyet da doi, va phai do lai")


class TestPhepBuLaNghichDaoThatSu(unittest.TestCase):
    """Phep kiem chinh: dat o cho nao thi chu ky phai roi dung cho do."""

    def test_gui_qua_phep_bu_thi_SCTS_dat_dung_cho_mong_muon(self):
        m = _phan_thuan()
        for mong_muon in ((355.0, 721.0, 240.0, 120.0),   # sat mep tren
                          (263.0, 606.0, 240.0, 120.0),
                          (100.0, 50.0, 240.0, 120.0),    # sat mep duoi
                          (355.0, 172.8, 240.0, 120.0)):  # Finance, chua ky
            gui = m.to_provider_box(*mong_muon)
            ra = m.from_provider_box(gui["x"], gui["y"], gui["w"], gui["h"])
            self.assertAlmostEqual(ra["x"], mong_muon[0], delta=0.6, msg="lech x")
            self.assertAlmostEqual(ra["y"], mong_muon[1], delta=0.6, msg="lech y")
            self.assertAlmostEqual(ra["w"], mong_muon[2], delta=0.6, msg="lech chieu rong")
            self.assertAlmostEqual(ra["h"], mong_muon[3], delta=0.6, msg="lech chieu cao")

    def test_khong_phai_phep_dong_nhat(self):
        """Chan cach: `to_provider_box` tra ve y nguyen dau vao cung lam phep kiem tren xanh
        neu `from_provider_box` cung la dong nhat. Bat buoc no PHAI doi so."""
        m = _phan_thuan()
        gui = m.to_provider_box(355.0, 721.0, 240.0, 120.0)
        self.assertNotAlmostEqual(gui["x"], 355.0, delta=1.0,
                                  msg="khong doi gi = khong bu gi")
        self.assertEqual(gui["w"], 320, "240 point phai thanh 320 (chia 0.75)")
        self.assertEqual(gui["h"], 160, "120 point phai thanh 160 (chia 0.75)")


class TestChoXayPayloadThatSuGoiPhepBu(unittest.TestCase):
    def test_create_document_goi_to_provider_box(self):
        fn = next((n for n in ast.walk(_TREE)
                   if isinstance(n, ast.FunctionDef) and n.name == "create_document"), None)
        self.assertIsNotNone(fn, "khong tim thay create_document")
        goi = {getattr(c.func, "id", None) or getattr(c.func, "attr", None)
               for c in ast.walk(fn) if isinstance(c, ast.Call)}
        self.assertIn("to_provider_box", goi,
                      "create_document khong goi to_provider_box -> toa do van gui thang, "
                      "phep bu chi nam trong file chu khong nam tren duong di")

    def test_toa_do_khong_con_gui_thang_bien_tho(self):
        """Bat gap `\"Llx\": x` la dau hieu ai do da quay ve gui gia tri chua bu."""
        fn = next(n for n in ast.walk(_TREE)
                  if isinstance(n, ast.FunctionDef) and n.name == "create_document")
        than = ast.get_source_segment(_SRC, fn) or ""
        for xau in ('"Llx": x,', '"Lly": y_pdf', '"x": x, "y": y_pdf'):
            self.assertNotIn(xau, than,
                             "con gui toa do chua qua phep bu: %r" % xau)


if __name__ == "__main__":
    unittest.main()
