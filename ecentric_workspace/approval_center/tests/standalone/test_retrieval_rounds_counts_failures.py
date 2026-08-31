# Copyright (c) 2026, eCentric and contributors
"""Dem luot tai PDF phai dem CA nhung luot that bai ngay tu dau.

31/08/2026, mo trang ops tren du lieu that lan dau: EC-DSP-2026-00016 that bai moi 30 phut
lien tuc tu 23/08 - hon 50 su kien `SignedFileRetrievalFailed`, khong mot su kien `Started`
nao - va ca trang lan bao dong deu ghi "da thu 0 luot". Bao dong `SignedRetrievalStalled`
KHONG THE keu, vi nguong 10 dat tren mot con so vinh vien bang 0.

Nguyen nhan: `SignedFileRetrievalStarted` chi phat ra sau khi da do trang thai ben nha cung
cap thanh cong. Goi hong ngay o buoc do - 404, mat mang, sai cau hinh - khong bao gio di toi
cho phat su kien do. Tuc la phep dem chi thay duoc nhung luot ITHONG, va mu hoan toan voi
nhung luot HONG, dung loai ma no sinh ra de canh.

Ca bo test truoc do khong thay gi: chung dua thang so `event_counts` vao ban gia lap, tuc la
tu tra loi cho chinh cau hoi minh dat. Phep kiem duoi day khong dem su kien - no dung lai
DONG SU KIEN nhu that (chi co Failed, khong co Started) roi hoi ham that.
"""
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


class _D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


def _load_signed_files(events):
    """Nap signed_files voi mot `frappe` gia chi tra ve dong su kien duoc dua vao.

    Ban gia LOC theo `event_type` giong that, de mot phep dem sai loai su kien se lo ra chu
    khong duoc ban gia am tham chieu long.
    """
    seen = {}

    def get_all(doctype, filters=None, fields=None, limit_page_length=None, **kw):
        seen["doctype"] = doctype
        seen["filters"] = filters or {}
        want = (filters or {}).get("event_type")
        types_wanted = set(want[1]) if isinstance(want, (list, tuple)) else (
            {want} if want else None)
        out = []
        for e in events:
            if types_wanted is not None and e["event_type"] not in types_wanted:
                continue
            out.append(_D({"creation": e["creation"]}))
        return out

    fake = types.ModuleType("frappe")
    fake.get_all = get_all
    fake.db = types.SimpleNamespace(count=lambda *a, **k: 0, get_value=lambda *a, **k: None)
    fake._dict = _D
    fake.utils = types.SimpleNamespace(now_datetime=lambda: None)

    src = io.open(os.path.join(_ROOT, "platform", "esign", "signed_files.py"),
                  encoding="utf-8").read()
    # Chi lay ham can do - nap ca module keo theo nhieu phu thuoc khong lien quan.
    start = src.index("_RETRIEVAL_EVENTS")
    end = src.index("def retrieve_and_store_for_package")
    mod = types.ModuleType("sf_slice")
    mod.frappe = fake
    exec(compile(src[start:end], "signed_files.py", "exec"), mod.__dict__)
    return mod, seen


def _ev(t, when):
    return {"event_type": t, "creation": when}


class TestRetrievalRoundsSeesFailures(unittest.TestCase):
    def test_goi_chi_co_Failed_van_phai_dem_ra_so_luot(self):
        """Chinh ca EC-DSP-2026-00016: that bai moi 30 phut, khong mot Started nao."""
        events = [_ev("SignedFileRetrievalFailed", "2026-08-31 %02d:00:00" % h)
                  for h in range(12)]
        mod, _seen = _load_signed_files(events)
        self.assertEqual(mod.retrieval_rounds("PKG-1"), 12,
                         "goi that bai ngay o buoc do van phai dem duoc so luot - neu khong "
                         "thi bao dong khong bao gio keu cho dung loai goi can canh")

    def test_nhieu_su_kien_cung_mot_luot_chi_tinh_MOT(self):
        """Mot luot cron de lai nhieu su kien (moi tep mot cai) - do la LY DO dem theo moc."""
        events = [_ev("SignedFileRetrievalStarted", "2026-08-31 10:00:0%d" % i)
                  for i in range(3)]
        events += [_ev("SignedFileRetrievalFailed", "2026-08-31 10:00:04")]
        events += [_ev("SignedFileRetrievalStarted", "2026-08-31 10:30:00")]
        mod, _seen = _load_signed_files(events)
        self.assertEqual(mod.retrieval_rounds("PKG-1"), 2,
                         "bon su kien luc 10:00 va mot luc 10:30 la HAI luot cron")

    def test_goi_chua_thu_lan_nao_van_la_0(self):
        mod, _seen = _load_signed_files([])
        self.assertEqual(mod.retrieval_rounds("PKG-1"), 0)

    def test_hoi_dung_CA_HAI_loai_su_kien(self):
        mod, seen = _load_signed_files([_ev("SignedFileRetrievalFailed", "2026-08-31 10:00:00")])
        mod.retrieval_rounds("PKG-1")
        want = seen["filters"].get("event_type")
        self.assertIsInstance(want, (list, tuple),
                             "phai loc theo mot DANH SACH loai su kien, khong phai mot loai")
        got = set(want[1])
        self.assertIn("SignedFileRetrievalFailed", got,
                     "bo qua Failed la tai lap dung lo hong 31/08")
        self.assertIn("SignedFileRetrievalStarted", got)

    def test_khong_dem_su_kien_khong_lien_quan(self):
        events = [_ev("SignedFileRetrievalFailed", "2026-08-31 10:00:00"),
                  _ev("Locked", "2026-08-31 11:00:00"),
                  _ev("ProviderSubmitted", "2026-08-31 12:00:00")]
        mod, _seen = _load_signed_files(events)
        self.assertEqual(mod.retrieval_rounds("PKG-1"), 1,
                         "su kien vong doi khac khong phai luot tai PDF")


class TestAlarmAndScreenCountTheSameWay(unittest.TestCase):
    """Hai ben tung dem hai kieu, nen man hinh va bao dong khong bao gio khop nhau."""

    def _src(self, *parts):
        return io.open(os.path.join(_ROOT, *parts), encoding="utf-8").read()

    def test_bao_dong_khong_con_tu_dem_Started(self):
        tasks = self._src("platform", "esign", "tasks.py")
        i = tasks.index("def _flag_stalled_retrieval")
        body = tasks[i:i + 1600]
        self.assertIn("retrieval_rounds", body,
                      "bao dong phai dung chung cach dem voi man hinh")
        self.assertNotIn('"event_type": "SignedFileRetrievalStarted"', body,
                         "dem thang Started la lo hong da lam bao dong cam trong 8 ngay")

    def test_man_hinh_khong_con_tu_dem(self):
        ops = self._src("platform", "esign", "ops.py")
        i = ops.index("def _retrieval_rounds")
        body = ops[i:i + 1400]
        self.assertIn("signed_files.retrieval_rounds", body)
        self.assertNotIn("//", body.split('"""')[-1],
                         "khong con phep chia cho so tep - do la cach dem cu")


if __name__ == "__main__":
    unittest.main()
