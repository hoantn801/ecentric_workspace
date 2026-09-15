# Copyright (c) 2026, eCentric and contributors
"""Chu ky co TRUOC lenh: giao cho nguoi trong vai giay, khong bat cho 24 tieng.

SU CO 15/09/2026 - EC-PAYR-2026-00106, cap 4, anh Lam.

Anh ay mo mail SCTS ky luc 12:00. Den 16:47 moi vao ERP bam "Duyet & Ky". Phep kiem do tuoi
(`signed_after`, them 27/08) doi chu ky phai MOI HON luc ERP ra lenh, nen tu choi mot chu ky
co truoc gan 5 tieng, voi ly do ghi nguyen van:

    signature_predates_request:15/09/2026 12:00

Hang rao lam DUNG viec cua no. Cai sai nam o chuyen sau do: chan ky ket `Verifying` va khong
co duong ra nao trong duoi MOT NGAY.

  * `poll_pending` chi ap `max_poll_attempts` cho `Retryable Failure`. Chan `Verifying` khong
    duoc dem vao dau ca.
  * Nut cuu ho "Doi soat - chap nhan chu ky ky truoc lenh" CHI hien khi chan ky da o
    `Manual Review`.
  * Thu duy nhat dua no toi `Manual Review` la `sweep_stale`, nguong `stale_after_hours` = 24.

Do tren prod: 10 luot PollTick trong 13 phut, tat ca cung mot dong chu, va con 24 tieng nua
moi co nguoi bam duoc nut ba giay.

Bo test nay giu bon dieu:
  1. ly do NAY (chu ky co roi, sai moc thoi gian) thi thoat som - khac han "chua ky";
  2. nhung khong thoat o luot DAU: mot nguoi vua co chu ky cu vua sap ky se cho ra dung ly do
     nay mot lan roi binh thuong tro lai;
  3. moi ly do khac KHONG bi dung vao;
  4. tien to ly do phai khop voi chuoi that trong `providers/base.py` - hai ben roi nhau thi
     ham nay im lang khong chay nua.
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
_TASKS = io.open(os.path.join(_ROOT, "platform", "esign", "tasks.py"), encoding="utf-8").read()
_BASE = io.open(os.path.join(_ROOT, "platform", "esign", "providers", "base.py"),
                encoding="utf-8").read()


def _node(src, name):
    for n in ast.parse(src).body:
        if isinstance(n, (ast.FunctionDef,)) and n.name == name:
            return n
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets):
            return n
    raise AssertionError("khong thay %s" % name)


def _chay(reason, so_lan_da_ghi, trang_thai_hien_tai="Verifying"):
    """Chay THAT `_thoat_som_neu_ky_truoc_lenh` voi ban gia.

    Nap kem HAI hang so tu chinh tasks.py (khong chep tay): chep tay thi doi hang so ben kia
    ma test van xanh - dung loai lo hong "phep do tu enforce luat dang bi kiem".
    """
    ghi = {"status": None, "extra": None, "event": None, "vr": None,
           "todo": 0, "stopped": 0, "dem_filters": None}

    class _FK(object):
        class db(object):
            @staticmethod
            def count(dt, filters=None):
                ghi["dem_filters"] = dict(filters or {})
                return so_lan_da_ghi

    ns = {
        "frappe": _FK,
        "EVT": "EC Digital Signature Event",
        "events": types.SimpleNamespace(
            set_dsr_status=lambda n, s, extra_fields=None, event_type=None, **kw:
                (ghi.__setitem__("status", s), ghi.__setitem__("extra", extra_fields),
                 ghi.__setitem__("event", event_type),
                 ghi.__setitem__("vr", kw.get("verification_result")))),
        "_dead_letter_todo": lambda n: ghi.__setitem__("todo", ghi["todo"] + 1),
        "_leg_stopped": lambda n, d=None: ghi.__setitem__("stopped", ghi["stopped"] + 1),
    }
    exec(compile(ast.Module(body=[_node(_TASKS, "LAN_KY_TRUOC_LENH_TOI_DA"),
                                  _node(_TASKS, "LY_DO_KY_TRUOC_LENH"),
                                  _node(_TASKS, "_thoat_som_neu_ky_truoc_lenh")],
                            type_ignores=[]), "tasks.py", "exec"), ns)
    vr = types.SimpleNamespace(ok=False, reason=reason)
    dsr = types.SimpleNamespace(name="EC-DSR-2026-00256", package="EC-DSP-2026-00091",
                                status=trang_thai_hien_tai)
    ket_qua = ns["_thoat_som_neu_ky_truoc_lenh"]("EC-DSR-2026-00256", dsr, vr)
    return ket_qua, ghi, ns


_LY_DO_THAT = "signature_predates_request:15/09/2026 12:00"


class TestThoatSomKhiKyTruocLenh(unittest.TestCase):
    def test_du_so_luot_thi_giao_cho_nguoi_NGAY(self):
        ok, ghi, _ = _chay(_LY_DO_THAT, 3)
        self.assertTrue(ok)
        self.assertEqual(ghi["status"], "Manual Review")
        self.assertEqual(ghi["event"], "ManualReview")

    def test_ghi_dung_LY_DO_chu_khong_phai_het_luot(self):
        """Nguoi doc so phai phan biet duoc "ky truoc lenh" voi "poll mai khong xong" -
        hai cai can hai hanh dong khac nhau."""
        _ok, ghi, _ = _chay(_LY_DO_THAT, 5)
        self.assertEqual((ghi["extra"] or {}).get("manual_review_reason"),
                         "signature_predates_request")
        self.assertNotIn("max_poll", str(ghi["extra"]))
        self.assertEqual(ghi["vr"], _LY_DO_THAT, "giu ca moc gio de doi chieu voi cong")

    def test_co_giao_viec_va_co_dung_chan_ky(self):
        _ok, ghi, _ = _chay(_LY_DO_THAT, 3)
        self.assertEqual(ghi["todo"], 1, "phai co ToDo, khong thi khong ai biet ma bam")
        self.assertEqual(ghi["stopped"], 1)

    def test_CHUA_du_so_luot_thi_KHONG_thoat(self):
        """Mot nguoi vua co chu ky CU tu goi truoc, vua sap ky goi nay, se cho ra dung ly do
        nay o lan hoi dau roi binh thuong tro lai. Thoat ngay luot dau la doan nham."""
        for n in (0, 1, 2):
            ok, ghi, _ = _chay(_LY_DO_THAT, n)
            self.assertFalse(ok, "luot %s" % n)
            self.assertIsNone(ghi["status"], "luot %s khong duoc doi trang thai" % n)
            self.assertEqual(ghi["todo"], 0)

    def test_ly_do_KHAC_thi_khong_dung_vao(self):
        for ly_do in ("expected_signer_absent:uid/of5", "not_enough_signatures:have=0/need=1",
                      "signature_id_mismatch", "signed_at_unreadable:none",
                      "signer_not_signed:pending", ""):
            ok, ghi, _ = _chay(ly_do, 99)
            self.assertFalse(ok, ly_do)
            self.assertIsNone(ghi["status"], ly_do)

    def test_dem_DUNG_loai_su_kien_va_DUNG_chan_ky(self):
        """Dem nham (moi PollTick, hoac ca chan ky khac) thi nguong 3 vo nghia."""
        _ok, ghi, _ = _chay(_LY_DO_THAT, 3)
        f = ghi["dem_filters"] or {}
        self.assertEqual(f.get("signature_request"), "EC-DSR-2026-00256")
        self.assertEqual(f.get("event_type"), "PollTick")
        self.assertEqual(f.get("verification_result"), ["like", "signature_predates_request%"])

    def test_vr_khong_co_reason_thi_khong_no(self):
        ok, _ghi, _ = _chay(None, 99)
        self.assertFalse(ok)


class TestHaiBenDINH_NHAU(unittest.TestCase):
    """Tien to ly do song o base.py; tasks.py chi so voi mot ban chep. Roi nhau la ham tren
    im lang khong chay nua, va khong co gi bao ca."""

    def test_tien_to_khop_voi_chuoi_that_trong_base(self):
        ns = {}
        exec(compile(ast.Module(body=[_node(_TASKS, "LY_DO_KY_TRUOC_LENH")], type_ignores=[]),
                     "t.py", "exec"), ns)
        self.assertIn('"%s:%%s"' % ns["LY_DO_KY_TRUOC_LENH"], _BASE.replace("'", '"'),
                      "base.py khong con sinh ra ly do nay - cap nhat ca hai ben")

    def test_canh_Verifying_toi_Manual_Review_la_HOP_LE(self):
        """Canh khong hop le thi `assert_transition` nem, va ca lan poll do bi nuot vao
        `except` cua `process_signing_request` - im lang y het truoc khi sua."""
        st = io.open(os.path.join(_ROOT, "platform", "esign", "state.py"),
                     encoding="utf-8").read()
        i = st.index('"Verifying":')
        self.assertIn("Manual Review", st[i:i + 300])


class TestDuocGOI_THAT(unittest.TestCase):
    def test_nhanh_Verifying_co_goi_ham_nay(self):
        """Ham dung ma khong ai goi thi vo nghia - va nhanh `Verifying` la CHO DUY NHAT
        chan ky nay lap lai mai."""
        fn = _node(_TASKS, "process_signing_request")
        src = ast.unparse(fn)
        self.assertIn("_thoat_som_neu_ky_truoc_lenh", src)
        # Phai nam SAU khi da ghi PollTick: thoat truoc thi luot cuoi cung khong de lai dau
        # vet, va nguoi doc so mat dung dong giai thich vi sao no dung lai.
        i_tick = src.replace("'", '"').index('"PollTick"')
        src = src.replace("'", '"')
        i_thoat = src.index("_thoat_som_neu_ky_truoc_lenh")
        self.assertLess(i_tick, i_thoat)


if __name__ == "__main__":
    unittest.main()
