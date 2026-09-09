# Copyright (c) 2026, eCentric and contributors
"""Go co "khong ro da tao tai lieu chua" - va CHI khi da xac minh la chua tao.

BOI CANH THAT (09/09/2026). Ba goi DSP-00058/59/60 (phieu EC-PAYR-2026-00071/72/73) gap
AddDocument tra HTTP 500. 500 = KHONG BIET: co the SCTS da tao tai lieu, co the chua. Ve an
toan cua he la dat co `create_outcome_unknown` len goi, va tu do moi lan chay deu tu choi tao
lai - vi tao lai mot tai lieu da ton tai la nhan doi ho so ky ben nha cung cap.

Nhung ve an toan do chi co MOT loi ra: `reconcile_document_creation`, ma ham do doi BANG DUOC
ma tai lieu. Khi nha cung cap that su khong tao gi thi khong co ma nao de nhap -> goi ket
vinh vien. (Docstring cua API tung hua co duong "clears the unknown marker" - duong do chua
he ton tai.) Ham `clear_create_ambiguity` la ban vien cai lo do.

Ham nay dang so: no THAO mot cai chot an toan. Nen bo test giu bon rang buoc:
  1. Chi go duoc dung mot loai co (`create_outcome_unknown`), khong go bua trang thai khac.
  2. Goi DA CO ma tai lieu thi TU CHOI - va khong duoc dong vao gi (go luc do = cho phep tao
     tai lieu THU HAI, dung cai tham hoa ma co nay sinh ra de chan).
  3. Doi mot ly do CO NOI DUNG. Khong phai thu tuc: no buoc nguoi bam viet ra minh da nhin
     thay gi ben cong. Va ly do do phai di vao su kien bat bien de sau con doi chung.
  4. KHONG tu tao tai lieu, KHONG tu thu lai. Hai buoc tach roi: loi khai, roi hanh dong.
Va: doc phai CO KHOA (for_update) - hai nguoi cung bam thi khong duoc go hai lan.
"""
import ast
import io
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


class _Throw(Exception):
    pass


class _Dict(dict):
    """`as_dict=True` cua Frappe tra ve frappe._dict - truy cap duoc bang thuoc tinh.
    Dung dict thuong o day thi test do vi ly do SAI (AttributeError), khong phai vi logic."""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


class _Recorder(object):
    """frappe gia: ghi lai MOI lan doc/ghi de con khang dinh tren chinh chung."""

    def __init__(self, row):
        self.row = dict(row) if row else None
        self.sets = []
        self.get_kwargs = None
        self.enqueued = []
        self.db = self
        self.events = []

    # --- frappe.db ---
    def get_value(self, doctype, name, fields, as_dict=False, for_update=False):
        self.get_kwargs = {"doctype": doctype, "name": name, "fields": tuple(fields),
                           "as_dict": as_dict, "for_update": for_update}
        if self.row is None:
            return None
        return _Dict(self.row)

    def set_value(self, doctype, name, values):
        self.sets.append((doctype, name, dict(values)))
        self.row.update(values)

    # --- frappe ---
    def throw(self, msg):
        raise _Throw(msg)

    def enqueue(self, *a, **kw):
        self.enqueued.append((a, kw))


def _load():
    """Nap RIENG ham can thu + hang so cua no, chay THAT.

    exec(compile(...)) chu khong import: service.py keo theo ca chuc module esign, va
    __pycache__ tung lam moi phep dot bien song sot (bai hoc 31/08)."""
    src = _read("platform", "esign", "service.py")
    tree = ast.parse(src)
    wanted = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name == "clear_create_ambiguity":
            wanted.append(n)
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "MIN_CLEAR_REASON_LEN" for t in n.targets):
            wanted.append(n)
    assert len(wanted) == 2, "khong tim thay ham hoac hang so trong service.py"
    wanted.sort(key=lambda n: n.lineno)

    def build(row, sm_ok=True):
        fk = _Recorder(row)
        calls = {"assert_sm": 0}

        class _Perms(object):
            @staticmethod
            def assert_system_manager():
                calls["assert_sm"] += 1
                if not sm_ok:
                    raise _Throw("khong phai System Manager")

        class _Events(object):
            @staticmethod
            def set_package_status(pkg, to_status, **kw):
                fk.events.append(("set_package_status", pkg, to_status, kw))

            @staticmethod
            def emit(event_type, **kw):
                fk.events.append(("emit", event_type, None, kw))

        ns = {"frappe": fk, "_": lambda s: s, "perms": _Perms, "events": _Events}
        exec(compile(ast.Module(body=wanted, type_ignores=[]), "service.py", "exec"), ns)
        return ns["clear_create_ambiguity"], fk, ns["MIN_CLEAR_REASON_LEN"], calls

    return build


_build = _load()
_LY_DO = "Da mo cong eContract, tim EC-PAYR-2026-00071: khong co tai lieu nao."


def _pkg(**kw):
    base = {"name": "EC-DSP-2026-00058", "status": "Provider Creating",
            "error_code": "create_outcome_unknown", "scts_document_id": None}
    base.update(kw)
    return base


class TestChiGoDungMotLoaiCo(unittest.TestCase):
    def test_go_duoc_khi_dung_co(self):
        fn, fk, _n, _c = _build(_pkg())
        out = fn("EC-DSP-2026-00058", _LY_DO)
        self.assertTrue(out["cleared"])
        self.assertEqual(fk.row["error_code"], None)
        self.assertEqual(fk.row["error_message"], None)

    def test_TU_CHOI_khi_co_khac(self):
        for ec in (None, "", "document_creation_gated", "bulk_outcome_unknown"):
            fn, fk, _n, _c = _build(_pkg(error_code=ec))
            with self.assertRaises(_Throw):
                fn("EC-DSP-2026-00058", _LY_DO)
            self.assertEqual(fk.sets, [], "tu choi thi khong duoc ghi gi: %r" % (ec,))

    def test_TU_CHOI_khi_khong_tim_thay_goi(self):
        fn, fk, _n, _c = _build(None)
        with self.assertRaises(_Throw):
            fn("khong-co", _LY_DO)
        self.assertEqual(fk.sets, [])


class TestGoiDaCoTaiLieuThiTuyetDoiKhongGo(unittest.TestCase):
    """Rang buoc quan trong nhat. Go co tren mot goi DA co tai lieu = cho phep tao tai lieu
    THU HAI ben nha cung cap - dung cai tham hoa ma co nay sinh ra de chan."""

    def test_tu_choi_va_KHONG_dong_vao_gi(self):
        fn, fk, _n, _c = _build(_pkg(scts_document_id="27a787d8-5be5-4999-9fcc-830bb2448f79"))
        with self.assertRaises(_Throw):
            fn("EC-DSP-2026-00058", _LY_DO)
        self.assertEqual(fk.sets, [], "khong duoc xoa co")
        self.assertEqual(fk.events, [], "khong duoc ghi su kien nhu da xu ly")

    def test_ma_tai_lieu_chi_co_khoang_trang_thi_van_coi_la_chua_co(self):
        fn, fk, _n, _c = _build(_pkg(scts_document_id="   "))
        out = fn("EC-DSP-2026-00058", _LY_DO)
        self.assertTrue(out["cleared"])


class TestDoiLyDoCoNoiDung(unittest.TestCase):
    def test_ly_do_rong_hoac_qua_ngan_thi_TU_CHOI(self):
        fn0, _fk0, nmin, _c = _build(_pkg())
        for bad in (None, "", "   ", "ok", "x" * (nmin - 1), " " * 50):
            fn, fk, _n, _c2 = _build(_pkg())
            with self.assertRaises(_Throw, msg=repr(bad)):
                fn("EC-DSP-2026-00058", bad)
            self.assertEqual(fk.sets, [], "ly do khong dat thi khong duoc ghi gi: %r" % (bad,))

    def test_do_dai_do_dung_hang_so_quyet_dinh(self):
        """Neu ai do doi hang so, test van phai dung. Va ly do DUNG bang nguong phai QUA."""
        fn, _fk, nmin, _c = _build(_pkg())
        self.assertGreaterEqual(nmin, 10, "nguong qua thap thi 'ok...' cung lot")
        out = fn("EC-DSP-2026-00058", "y" * nmin)
        self.assertTrue(out["cleared"])

    def test_ly_do_di_vao_su_kien_BAT_BIEN(self):
        fn, fk, _n, _c = _build(_pkg())
        fn("EC-DSP-2026-00058", "  " + _LY_DO + "  ")
        kinds = [e[0] for e in fk.events]
        self.assertIn("set_package_status", kinds)
        meta = fk.events[0][3].get("request_meta") or {}
        self.assertEqual(meta.get("reason"), _LY_DO, "phai cat khoang trang va giu nguyen van")


class TestKhongTuTaoVaKhongTuThuLai(unittest.TestCase):
    """Hai buoc tach roi: ham nay chi la LOI KHAI, retry moi la hanh dong."""

    def test_khong_enqueue_gi(self):
        fn, fk, _n, _c = _build(_pkg())
        fn("EC-DSP-2026-00058", _LY_DO)
        self.assertEqual(fk.enqueued, [], "go co ma tu chay lai = mat buoc nguoi kiem")

    def test_bao_ro_la_van_CAN_retry(self):
        fn, _fk, _n, _c = _build(_pkg())
        self.assertTrue(fn("EC-DSP-2026-00058", _LY_DO)["retry_required"])

    def test_ham_khong_he_nhac_toi_viec_tao_tai_lieu(self):
        src = _read("platform", "esign", "service.py")
        fn = next(ast.unparse(n) for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "clear_create_ambiguity")
        for cam in ("create_document", "enqueue", "process_signing_request", "get_adapter"):
            self.assertNotIn(cam, fn, cam)


class TestTrangThaiGoi(unittest.TestCase):
    def test_Provider_Creating_thi_di_ve_Provider_Create_Failed(self):
        """Canh hop le cua may trang thai, va la trang thai DUNG NGHIA: lan tao truoc da hong.
        Tu do `Provider Create Failed -> Provider Creating` moi la duong tao lai binh thuong."""
        fn, fk, _n, _c = _build(_pkg(status="Provider Creating"))
        fn("EC-DSP-2026-00058", _LY_DO)
        self.assertEqual(fk.events[0][:3],
                         ("set_package_status", "EC-DSP-2026-00058", "Provider Create Failed"))

    def test_trang_thai_khac_thi_CHI_ghi_su_kien_khong_doi_trang_thai(self):
        """Che lazy: goi da Active roi van co the vuong co nay. Ha Active xuong
        'Provider Create Failed' la mot buoc LUI trai phep - may trang thai khong co canh do."""
        fn, fk, _n, _c = _build(_pkg(status="Active"))
        fn("EC-DSP-2026-00058", _LY_DO)
        self.assertEqual([e[0] for e in fk.events], ["emit"])
        self.assertEqual(fk.events[0][1], "CreateAmbiguityCleared")
        self.assertEqual((fk.events[0][3].get("request_meta") or {}).get("package_status"),
                         "Active")


class TestQuyenVaKhoa(unittest.TestCase):
    def test_chi_System_Manager(self):
        fn, fk, _n, calls = _build(_pkg(), sm_ok=False)
        with self.assertRaises(_Throw):
            fn("EC-DSP-2026-00058", _LY_DO)
        self.assertEqual(calls["assert_sm"], 1)
        self.assertEqual(fk.sets, [])

    def test_kiem_quyen_chay_TRUOC_khi_doc_du_lieu(self):
        fn, fk, _n, _c = _build(_pkg(), sm_ok=False)
        with self.assertRaises(_Throw):
            fn("EC-DSP-2026-00058", _LY_DO)
        self.assertIsNone(fk.get_kwargs, "chua duoc phep ma da doc ho so")

    def test_doc_phai_CO_KHOA(self):
        """Hai nguoi cung bam: doc khong khoa thi ca hai cung thay co, ca hai cung go, va
        goi duoc tao lai HAI lan. Day dung la kieu loi da dinh 08/09 (khoa `name` roi doc
        thuong -> gui lenh ky hai lan)."""
        fn, fk, _n, _c = _build(_pkg())
        fn("EC-DSP-2026-00058", _LY_DO)
        self.assertTrue(fk.get_kwargs["for_update"], "phai doc voi for_update=True")
        self.assertIn("scts_document_id", fk.get_kwargs["fields"],
                      "phai nap ma tai lieu, khong thi phep kiem o tren la mu")
        self.assertIn("error_code", fk.get_kwargs["fields"])


class TestDuongGoiTuAPI(unittest.TestCase):
    def test_api_co_diem_vao_va_chi_POST(self):
        src = _read("platform", "esign", "api.py")
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "clear_create_ambiguity")
        deco = " ".join(ast.unparse(d) for d in fn.decorator_list)
        self.assertIn("whitelist", deco)
        self.assertIn("POST", deco, "GET tu dong rollback trong Frappe - phai la POST")
        body = ast.unparse(fn)
        self.assertIn("assert_system_manager", body)
        # phai CHUYEN TIEP ca ly do. Chi kiem "co goi svc..." thi bo tham so `reason` di van
        # xanh - luc do bat ky ai cung go duoc co ma khong phai khai gi.
        self.assertIn("svc.clear_create_ambiguity(package, reason)", body)

    def test_docstring_cu_gay_hieu_nham_da_duoc_sua(self):
        """Chinh cai docstring nay lam mat mot vong chan doan: no hua mot duong khong ton
        tai. Neu ai do chep lai cau cu vao `reconcile_document_creation` thi test do."""
        src = _read("platform", "esign", "api.py")
        fn = next(ast.unparse(n) for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "reconcile_document_creation")
        self.assertNotIn("clears the unknown marker", fn)


if __name__ == "__main__":
    unittest.main()
