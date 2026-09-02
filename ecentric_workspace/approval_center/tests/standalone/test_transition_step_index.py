# Copyright (c) 2026, eCentric and contributors
"""transitionId chay theo THU TU BUOC, khong theo cap duyet ERP va khong theo nguoi.

Chup tay tu cong 02/09 tren MOT tai lieu, bam tuan tu: Trinh ky `-2`, duyet 1 `-9`,
duyet 2 `-10`, duyet 3 `-11`.

Cau hinh cu gan DUNG MOT id `-9` cho moi buoc duyet. Hau qua do duoc tren so lieu that:

    02/09 02:56  DSR-00024  targeted, khong fallback   -> `-2`  dung
    02/09 03:03  DSR-00025  targeted, khong fallback   -> `-9`  dung
    02/09 03:24  DSR-00026  400 -> pool -> Lien KY DUOC        (can `-10`, gui `-9`)
    02/09 03:25  DSR-00027  400 -> pool -> Phuong KHONG        (can `-11`, gui `-9`)

Hai buoc dau chay tot bao lau nay khong phai may. Tu buoc 3, he song bang pool - ma pool chi
ky duoc khi nguoi minh gui TINH CO dung la nguoi eContract dang cho. Lien trung, Phuong trat.

Bo test nay giu ba dieu, va ca ba deu la cho tung mat mot ngay de nhin ra:

  1. Biet vi tri buoc thi phai dung id CUA BUOC DO, khong dung dong mac dinh theo stage.
  2. KHONG dem duoc thi phai la `None`, tuyet doi khong phai 0 - coi la 0 se gui `-2`
     (Trinh ky) vao mot tai lieu dang o giua chung.
  3. Buoc khong co trong day da chup thi KHONG BIA. Voi mau "5 chu ky", buoc do la Ky chinh
     (`signToken=1`) - ky bang OfficeSignTool tren may nguoi ky, ERP khong lam thay duoc.
"""
import ast
import io
import os
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
_NH = os.path.join(_ROOT, "platform", "esign", "next_handler.py")
_SRC = io.open(_NH, encoding="utf-8").read()
_TREE = ast.parse(_SRC)


def _fn(name):
    for n in ast.walk(_TREE):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError("khong tim thay ham %s" % name)


def _than(name):
    return ast.get_source_segment(_SRC, _fn(name)) or ""


class TestChonTheoViTriBuoc(unittest.TestCase):
    def test_resolve_nhan_step_index(self):
        args = [a.arg for a in _fn("resolve_transition_config").args.args]
        self.assertIn("step_index", args,
                      "khong nhan vi tri buoc thi van la mot-id-cho-moi-buoc")

    def test_vi_tri_buoc_THANG_stage(self):
        """Kiem DIEU KIEN cua nhanh, khong kiem thu tu chu trong file.

        Ban dau test nay so vi tri hai chuoi trong than ham. Dot bien
        `if step_index is not None and False:` song sot: chuoi van dung cho, thu tu van dung,
        nhung nhanh KHONG BAO GIO chay - tuc quay ve dung mot-id-cho-moi-buoc ma test khong
        hay biet. Mot cong luon dong cung vo dung y het mot cong khong ton tai.
        """
        fn = _fn("resolve_transition_config")
        nhanh = [n for n in ast.walk(fn)
                 if isinstance(n, ast.If)
                 and "step_index" in {getattr(x, "id", None) for x in ast.walk(n.test)}]
        self.assertTrue(nhanh, "khong co nhanh nao xet step_index")
        dieu_kien = nhanh[0].test
        self.assertIsInstance(
            dieu_kien, ast.Compare,
            "dieu kien phai la DUY NHAT `step_index is not None`; them bat cu ve nao (`and "
            "False`, mot co bi tat...) la mot duong am tham vo hieu hoa ban sua")
        # ...va dung CHIEU. `is None` cung la mot Compare, cung nhac dung bien, nhung dao
        # nguoc y nghia: chi chon theo vi tri buoc khi KHONG biet vi tri buoc.
        self.assertTrue(dieu_kien.ops and isinstance(dieu_kien.ops[0], ast.IsNot),
                        "phai la `is not None` - `is None` nghia la chi dung vi tri buoc khi "
                        "khong dem duoc, tuc dung dung luc khong duoc phep dung")
        than = _than("resolve_transition_config")
        self.assertLess(than.find("step_index is not None"), than.find('(r.get("stage") or "")'),
                        "stage xet truoc thi dong `-9` mac dinh van thang")

    def test_plan_handover_truyen_vi_tri_buoc_xuong(self):
        than = _than("plan_handover")
        self.assertIn("provider_step_index", than,
                      "khong hoi vi tri buoc thi resolve khong bao gio co gi de dung")
        self.assertIn("step_index=", than, "quen truyen xuong resolve_transition_config")


class TestKhongDemDuocThiPhaiLaKhongBiet(unittest.TestCase):
    """`None` va `0` la hai cau tra loi khac han nhau."""

    def test_khong_co_adapter_tra_None(self):
        than = _than("provider_step_index")
        self.assertIn("return None", than)
        self.assertNotIn("return 0", than,
                         "tra 0 khi khong dem duoc = gui `-2` (Trinh ky) vao mot tai lieu "
                         "dang o giua chung")

    def test_danh_sach_chan_ky_RONG_khong_phai_la_chua_ai_ky(self):
        than = _than("provider_step_index")
        i = than.find("if not signers")
        self.assertNotEqual(i, -1, "khong xet truong hop khong doc duoc chan ky")
        sau = than[i:i + 320]
        self.assertIn("return None", sau,
                      "danh sach rong ma tra 0 la doan - dung lop loi 'tai lieu 0 nguoi ky "
                      "duoc coi la da ky xong' cua UAT VOID 5")

    def test_dem_tu_NHA_CUNG_CAP_chu_khong_tu_dem(self):
        """Phai GOI poll_status, khong phai chi nhac ten no.

        Ban dau test nay tim chuoi `poll_status` trong than ham. Dot bien thay
        `doc = adapter.poll_status(instance_id)` bang `doc = None` van xanh - vi dong
        `hasattr(adapter, "poll_status")` o tren giu chuoi do song. Lop nham lan grep-chu
        nay phai sua den lan thu nam trong hai ngay.
        """
        fn = _fn("provider_step_index")
        goi = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
               and getattr(c.func, "attr", None) == "poll_status"]
        self.assertTrue(goi,
                        "khong GOI poll_status = tu dem ben ERP, va se lech ngay khi co nguoi "
                        "ky thang tren cong - ma chan Ky chinh BUOC PHAI ky tay, nen ho so nao "
                        "cung co it nhat mot buoc khong di qua ERP")


class TestKhongBiaBuocChuaChupDuoc(unittest.TestCase):
    def test_khong_co_dong_cau_hinh_thi_khong_gui_bua(self):
        than = _than("plan_handover")
        i = than.find("if not cfg:")
        self.assertNotEqual(i, -1)
        self.assertIn("no_transition_config", than[i:i + 700],
                      "phai noi ro la khong co cau hinh cho buoc nay")

    def test_ly_do_co_kem_so_buoc(self):
        than = _than("plan_handover")
        self.assertIn('buoc=%s', than,
                      "khong ghi so buoc vao ly do thi lan sau lai phai do tay lai tu dau")


class TestPatchKhongSeedCanhTuChoi(unittest.TestCase):
    """`-12` la Tu choi. So duyet va so tu choi xen ke nhau."""

    def setUp(self):
        p = os.path.join(_ROOT, "approval_center", "patches",
                         "p127_seed_transition_step_index.py")
        self.src = io.open(p, encoding="utf-8").read()

    def test_chi_seed_id_da_chup(self):
        cay = ast.parse(self.src)
        ids = set()
        for n in ast.walk(cay):
            if (isinstance(n, ast.Dict)
                    and any(getattr(k, "value", None) == "transition_id" for k in n.keys)):
                for k, v in zip(n.keys, n.values):
                    if getattr(k, "value", None) == "transition_id":
                        ids.add(ast.literal_eval(v))
        self.assertEqual(ids, {-2, -9, -10, -11},
                         "chi duoc seed bon canh da chup tuan tu 02/09")

    def test_TUYET_DOI_khong_seed_canh_tu_choi(self):
        cay = ast.parse(self.src)
        for n in ast.walk(cay):
            if isinstance(n, ast.Dict):
                for k, v in zip(n.keys, n.values):
                    if getattr(k, "value", None) == "transition_id":
                        self.assertNotEqual(
                            ast.literal_eval(v), -12,
                            "`-12` la TU CHOI. Seed no vao day duyet = co ngay tu tu choi "
                            "mot phieu chi tien that")

    def test_co_buoc_danh_so_lien_tuc_tu_0(self):
        cay = ast.parse(self.src)
        buoc = []
        for n in ast.walk(cay):
            if isinstance(n, ast.Dict):
                for k, v in zip(n.keys, n.values):
                    if getattr(k, "value", None) == "step_index":
                        buoc.append(ast.literal_eval(v))
        self.assertEqual(sorted(buoc), [0, 1, 2, 3],
                         "vi tri buoc phai lien tuc tu 0; thung lo mot so la mot buoc khong "
                         "bao gio khop va lai roi ve pool")

    def test_patch_co_verify_doc_lai_tu_DB(self):
        self.assertIn("frappe.get_doc", self.src.split("# VERIFY")[-1],
                      "khong doc lai tu DB thi khong biet ghi co an khong - da bi lua vi "
                      "chuyen nay nhieu lan roi")


if __name__ == "__main__":
    unittest.main()
