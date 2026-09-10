# Copyright (c) 2026, eCentric and contributors
"""Cong SCTS da ky ma ERP chua biet -> ERP nghe theo va dong bo ve.

BOI CANH THAT (09/09/2026, EC-PAYR-2026-00051). HOF ky tren cong luc 08:20, CEO luc 13:08;
tai lieu ben SCTS "Da ket thuc" - ca 5 chu ky. Nhung ho khong bam gi tren ERP, nen ERP KHONG
co chan ky nao cho hai cap do va van treo o "HOF Review".

Loai su co nay VO HINH: trang van hanh chi liet ke CHAN KY bi ket, ma o day chua bao gio co
chan ky nao duoc tao. Toi da quet "con phieu nao ket khong" va bao "chi con 00053" - cau do
chi dung voi nhung phieu CO chan ky.

Duong toi de xuat luc dau: bao HOF/CEO vao ERP bam "Duyet & Ky" mot lan nua. Hoan bac, va
dung: bat nguoi duyet ky hai lan la bat nguoi dung ganh cai sai cua he thong.

Bo test nay giu cac phep chan van con nguyen sau khi doi huong:
  1. Danh tinh: chi chap nhan chu ky khop `scts_user_id` trong ANH XA DA XAC MINH cua chinh
     nguoi duyet. Khong anh xa -> bo qua, khong doan theo email.
  2. Thu tu (`prior_signatures`): chan thu N cua mot nguoi phai la chu ky thu N cua ho -
     chan viec dong mot cap bang chu ky cua chan KHAC (loi 28/08).
  3. CHI cap dang cho va CHI nguoi duyet dang Pending o cap do. Khong nhay cap.
  4. KHONG gui gi sang nha cung cap. Day la duong DOC + CONG NHAN.
  5. Cai DUY NHAT duoc bo la moc thoi gian `signed_after` - vi dinh nghia cua tinh huong nay
     la ho ky TRUOC khi ERP hoi.
  6. Ket qua vao LICH SU PHIEU noi ro la dong bo tu cong, khong lan voi mot lan bam that.
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_SVC = ("platform", "esign", "service.py")
_BASE_MOD = "ecentric_workspace.platform.esign.providers.base"


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


def _fn_src(name, rel=_SVC):
    return next(n for n in ast.parse(_read(*rel)).body
                if isinstance(n, ast.FunctionDef) and n.name == name)


class _Throw(Exception):
    pass


class _D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


_DOC = "454f48ce-1473-409b-9d03-9ed91c856e9b"
_HOF = "phuong.nguyen1@ecentric.vn"
_UID = "uid-hof"


def _run(pending=(_HOF,), mapping=True, vr_ok=True, vr_reason="verified", status="Pending",
         level=3, doc_id=_DOC, reason="Da mo cong SCTS: HOF ky luc 09/09 08:20.",
         mapping_aliases=(), uid=_UID):
    """`mapping_aliases`: cac email KHAC cung tro toi mot `scts_user_id` (tai khoan SCTS
    dung chung). Mac dinh rong = moi nguoi dung tai khoan cua rieng minh."""
    seen = {"adopt": [], "expected": None, "polled": None}

    class _FK(object):
        session = types.SimpleNamespace(user="hoan.tran@ec.vn")

        @staticmethod
        def throw(msg, *a, **kw):
            raise _Throw(str(msg))

        @staticmethod
        def get_all(dt, filters=None, fields=None, **kw):
            # PHAN BIET THEO DocType. Ban dau ban gia nay tra ve danh sach nguoi duyet cho
            # MOI lan goi va ghi de `rows_filter` - nen khi `_emails_cua_cung_danh_tinh`
            # them mot lan goi (bang "EC SCTS User Mapping"), bo loc ghi lai thanh cua lan
            # goi SAU, va test "chi cap hien tai" do vi mot ly do khong lien quan gi den
            # cai no dinh kiem.
            if dt == "EC SCTS User Mapping":
                # `pluck` tra ve DANH SACH GIA TRI, khong phai danh sach dong. Ban gia
                # khong ho tro `pluck` thi lot ra mot dict giua danh sach email.
                seen["mapping_filter"] = dict(filters or {})
                cung = [u for u in mapping_aliases]
                return cung if kw.get("pluck") else [_D({"frappe_user": u}) for u in cung]
            seen["rows_filter"] = dict(filters or {})
            return [_D({"name": "row-%s" % u, "approver": u}) for u in pending]

        class db(object):
            @staticmethod
            def get_value(dt, name, field, **kw):
                return doc_id

            @staticmethod
            def count(dt, filters=None):
                seen["count_filter"] = dict(filters or {})
                return 0

    class _Perms(object):
        @staticmethod
        def assert_system_manager():
            seen["sm"] = True

        @staticmethod
        def verified_mapping(user, env):
            return _D({"name": "EC-DSM-1", "modified": "m", "scts_user_id": uid,
                       "signature_id": "sig-1"}) if mapping else None

    class _Adapter(object):
        @staticmethod
        def poll_status(d):
            seen["polled"] = d
            return "DOC_STATE"

    class _SPA(object):
        @staticmethod
        def verify_signed_result(state, expected):
            seen["expected"] = dict(expected)
            return types.SimpleNamespace(ok=vr_ok, reason=vr_reason)

    fake_base = types.ModuleType(_BASE_MOD)
    fake_base.SignatureProviderAdapter = _SPA

    ns = {
        "frappe": _FK, "_": lambda s: s, "perms": _Perms,
        "MIN_CLEAR_REASON_LEN": 10, "DSR": "EC Digital Signature Request",
        "_req_for_business": lambda dt, n: _D({"name": "EC-APR-1", "approval_status": status,
                                               "current_level": level,
                                               "approval_type": "PAYMENT_REQUEST"}),
        "_profile_doc": lambda dt, at: _D({"provider": "SCTS", "environment": "UAT"}),
        "_settings_for": lambda p: _D({"environment": "UAT"}),
        "pkgsvc": types.SimpleNamespace(active_package_for_request=lambda r: "EC-DSP-1"),
        "get_adapter": lambda s: _Adapter,
        "_adopt_provider_signature": (lambda req, prof, pkg, row, who, m, vr, ly_do:
                                      seen["adopt"].append(who) or
                                      {"completed": True, "signature_request": "EC-DSR-9"}),
    }
    saved = sys.modules.get(_BASE_MOD)
    sys.modules[_BASE_MOD] = fake_base
    try:
        # Nap KEM `_emails_cua_cung_danh_tinh`: `sync_signatures_from_provider` goi no de
        # dung danh sach email cua CUNG mot danh tinh SCTS. Nap thieu thi test do vi
        # NameError - mot ly do thuoc ve phep do, khong phai ve code.
        exec(compile(ast.Module(body=[_fn_src("_emails_cua_cung_danh_tinh"),
                                      _fn_src("sync_signatures_from_provider")],
                                type_ignores=[]), "service.py", "exec"), ns)
        try:
            out = ns["sync_signatures_from_provider"]("EC Payment Request",
                                                      "EC-PAYR-2026-00051", reason)
            return seen, out, None
        except _Throw as e:
            return seen, None, str(e)
    finally:
        if saved is None:
            sys.modules.pop(_BASE_MOD, None)
        else:
            sys.modules[_BASE_MOD] = saved


class TestChapNhanChuKyDaCo(unittest.TestCase):
    def test_ky_dung_nguoi_thi_dong_bo(self):
        seen, out, err = _run()
        self.assertIsNone(err, err)
        self.assertEqual(seen["adopt"], [_HOF])
        self.assertEqual([s["approver"] for s in out["synced"]], [_HOF])
        self.assertEqual(out["skipped"], [])

    def test_hoi_dung_tai_lieu_cua_goi(self):
        seen, _o, _e = _run()
        self.assertEqual(seen["polled"], _DOC)


class TestBoQUA_MOC_THOI_GIAN_va_chi_the_thoi(unittest.TestCase):
    """Cai duy nhat duoc bo. Moi phep chan khac phai con nguyen trong `expected`."""

    def test_KHONG_dat_signed_after(self):
        seen, _o, _e = _run()
        self.assertNotIn("signed_after", seen["expected"],
                         "dat moc thoi gian thi chinh tinh huong nay khong bao gio qua duoc")

    def test_van_gui_du_danh_tinh_va_thu_tu(self):
        seen, _o, _e = _run()
        e = seen["expected"]
        self.assertEqual(e["document_id"], _DOC)
        self.assertEqual(e["user_id"], _UID, "phai khop scts_user_id cua ANH XA")
        self.assertEqual(e["email"], [_HOF],
                         "email la DANH SACH: mot nguoi co the ky bang tai khoan dung chung")
        self.assertEqual(e["signature_id"], "sig-1")
        self.assertIn("prior_signatures", e, "thieu phep dem = dong cap bang chu ky chan khac")

    def test_TAI_KHOAN_DUNG_CHUNG_van_nhan_ra_chu_ky(self):
        """EC-PAYR-2026-00087 (10/09): chi Huong gui phieu, nhung tai lieu duoc ky bang tai
        khoan CnB dung chung. eContract chi dinh danh nguoi ky bang EMAIL, nen so voi mot
        email duy nhat cua ERP thi truot - `poll_pending` quay
        `expected_signer_absent:.../of5` 9 lan lien tiep va phieu dung im o current_level=0.

        Email cua tai khoan dung chung phai co trong danh sach doi soat, VA no chi duoc vao
        do khi ANH XA tro cung mot `scts_user_id`."""
        seen, _o, _e = _run(mapping_aliases=(_HOF, "cnb.ecentric@ec.vn"))
        self.assertEqual(seen["expected"]["email"], [_HOF, "cnb.ecentric@ec.vn"])
        self.assertEqual(seen["mapping_filter"].get("scts_user_id"), _UID,
                         "chi lay email cua CUNG mot danh tinh SCTS")
        self.assertEqual(seen["mapping_filter"].get("active"), 1)
        self.assertEqual(seen["mapping_filter"].get("mapping_status"), "Verified",
                         "ban nhap / ban da go KHONG duoc tinh")

    def test_KHONG_nhet_email_la_vao_danh_sach(self):
        """Danh sach nay la cho noi long DUY NHAT cua phep doi soat, nen no phai chat: chi
        email cua anh xa cung danh tinh, khong phai email nao khac trong he thong."""
        seen, _o, _e = _run(mapping_aliases=())
        self.assertEqual(seen["expected"]["email"], [_HOF])

    def test_MOI_email_trong_danh_sach_deu_duoc_thu(self):
        """Dung con dot bien "chi lay phan tu dau": neu chi thu email dau tien thi ca tinh
        nang nay vo dung - email cua tai khoan dung chung LUON dung sau email nguoi dung
        ERP, tuc chinh cai can khop lai la cai bi bo qua."""
        from ecentric_workspace.platform.esign.providers.base import NormalizedDocState
        st = NormalizedDocState("doc-1", "processing", signers=[
            {"user_id": None, "email": "cnb.ecentric@ec.vn", "status": "signed"}])
        self.assertEqual(len(st.signers_for("uid-khong-khop",
                                            [_HOF, "cnb.ecentric@ec.vn"])), 1,
                         "phai thu HET danh sach, khong dung o email dau")
        self.assertEqual(st.signers_for("uid-khong-khop", [_HOF]), [])

    def test_khong_co_uid_thi_KHONG_tra_cuu_anh_xa(self):
        """Chan ky chua co `effective_scts_user_id` thi khong co danh tinh nao de gom quanh.
        Van di tra cuu voi uid rong la hoi "anh xa nao co scts_user_id = ''" - mot cau hoi
        vo nghia, va neu du lieu co dong rong thi no keo email la vao danh sach doi soat."""
        seen, _o, _e = _run(uid="", mapping_aliases=("ai.do@ec.vn",))
        self.assertEqual(seen.get("mapping_filter"), None,
                         "khong duoc goi anh xa khi chua co danh tinh SCTS")

    def test_phep_dem_dem_dung_nguoi_dung_goi(self):
        seen, _o, _e = _run()
        f = seen["count_filter"]
        self.assertEqual(f.get("package"), "EC-DSP-1")
        self.assertEqual(f.get("effective_scts_user_id"), _UID)
        self.assertEqual(f.get("status"), ["in", ("Signed", "Approval Completed")])


class TestCacTruongHopBI_TU_CHOI(unittest.TestCase):
    def test_khong_co_anh_xa_thi_BO_QUA_chu_khong_doan_theo_email(self):
        seen, out, err = _run(mapping=False)
        self.assertEqual(seen["adopt"], [])
        self.assertEqual(out["skipped"][0]["reason"], "no_verified_mapping")

    def test_nha_cung_cap_noi_chua_ky_thi_bo_qua(self):
        for r in ("expected_signer_absent:x/of5", "not_enough_signatures:0<1",
                  "signature_id_mismatch"):
            seen, out, _e = _run(vr_ok=False, vr_reason=r)
            self.assertEqual(seen["adopt"], [], r)
            self.assertEqual(out["skipped"][0]["reason"], r)

    def test_phieu_khong_con_cho_duyet_thi_khong_lam_gi(self):
        for st in ("Approved", "Rejected", "Cancelled"):
            seen, out, _e = _run(status=st)
            self.assertEqual(seen["adopt"], [])
            self.assertTrue(out["reason"].startswith("not_pending:"))
            self.assertIsNone(seen["polled"], "chua ca hoi nha cung cap")

    def test_goi_chua_co_tai_lieu_thi_khong_lam_gi(self):
        seen, out, _e = _run(doc_id=None)
        self.assertEqual(out["reason"], "no_provider_document")
        self.assertEqual(seen["adopt"], [])

    def test_BAT_BUOC_ly_do(self):
        for bad in (None, "", "   ", "ok", "ngan"):
            seen, out, err = _run(reason=bad)
            self.assertIsNotNone(err, repr(bad))
            self.assertEqual(seen["adopt"], [])
            self.assertIsNone(seen.get("polled"), "chua khai gi ma da hoi nha cung cap")

    def test_kiem_quyen_chay_TRUOC_moi_thu(self):
        seen, _o, err = _run(reason="")
        self.assertIsNotNone(err)
        self.assertTrue(seen.get("sm"))


class TestChiCapHIEN_TAI_va_nguoi_dang_CHO(unittest.TestCase):
    def test_loc_dung_cap_va_dung_trang_thai(self):
        seen, _o, _e = _run(level=3)
        f = seen["rows_filter"]
        self.assertEqual(f.get("level_no"), 3, "chi cap hien tai - khong nhay cap")
        self.assertEqual(f.get("status"), "Pending", "chi nguoi duyet CHUA quyet dinh")
        self.assertEqual(f.get("approval_request"), "EC-APR-1")

    def test_nhieu_nguoi_cho_o_cung_cap_thi_xet_tung_nguoi(self):
        seen, out, _e = _run(pending=(_HOF, "ai.do@ec.vn"))
        self.assertEqual(len(seen["adopt"]), 2)
        self.assertEqual(len(out["synced"]), 2)


class TestKHONG_GUI_GI_VA_GHI_LAI(unittest.TestCase):
    def test_duong_nay_khong_he_gui_lenh_ky(self):
        src = ast.unparse(_fn_src("sync_signatures_from_provider"))
        for cam in ("enqueue", "approve_and_sign", "bulk_process", "transition"):
            self.assertNotIn(cam, src, cam)

    def test_chan_ky_tao_ra_KHONG_duoc_enqueue(self):
        """`_adopt_provider_signature` di qua Queued (canh hop le duy nhat toi Signed) nhung
        TUYET DOI khong xep mot job gui lenh - khong co gi de gui."""
        src = ast.unparse(_fn_src("_adopt_provider_signature"))
        self.assertNotIn("enqueue", src)
        self.assertIn('"Queued"', src.replace("'", '"'))
        self.assertIn("mark_verified", src)

    def test_binh_luan_di_vao_lich_su_phieu_noi_ro_la_DONG_BO(self):
        """Nguoi doc lich su phieu phai phan biet duoc voi mot lan bam "Duyet & Ky" that."""
        src = ast.unparse(_fn_src("_adopt_provider_signature"))
        self.assertIn("Đồng bộ chữ ký từ cổng SCTS", src)
        self.assertIn("comment=", src)

    def test_KHONG_tao_them_khi_da_co_chan_dang_song(self):
        src = ast.unparse(_fn_src("_adopt_provider_signature"))
        self.assertIn("idempotency_key", src)
        self.assertIn("LIVE_OR_DONE", src)

    def test_verify_and_complete_nhan_comment_tu_nguoi_goi(self):
        src = _read(*_SVC)
        self.assertIn("def verify_and_complete(dsr_name, comment=None)", src)
        fn = ast.unparse(_fn_src("verify_and_complete"))
        self.assertIn("comment or", fn, "khong truyen thi giu nguyen cau cu")


class TestQuyenKySo(unittest.TestCase):
    """Chot cu la mot danh sach go tay tren Provider Settings; gio la ANH XA DA XAC MINH."""

    def _fn(self, has_mapping):
        node = _fn_src("assert_allowed_signer", ("platform", "esign", "permissions.py"))
        seen = {}

        class _FK(object):
            session = types.SimpleNamespace(user="ai@ec.vn")
            PermissionError = _Throw      # frappe that co thuoc tinh nay; thieu thi test do
                                          # vi ly do SAI (AttributeError), khong phai logic
            @staticmethod
            def throw(msg, *a, **kw):
                raise _Throw(str(msg))
        ns = {"frappe": _FK, "_": lambda s: s,
              "verified_mapping": lambda u, e: (seen.update({"u": u, "e": e}) or
                                                ({"name": "m"} if has_mapping else None))}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "permissions.py", "exec"), ns)
        return ns["assert_allowed_signer"], seen

    def test_co_anh_xa_xac_minh_thi_duoc_ky(self):
        fn, seen = self._fn(True)
        fn({"environment": "UAT", "allowed_signing_users": ""}, "tam.nguyen@ec.vn")
        self.assertEqual(seen["u"], "tam.nguyen@ec.vn")
        self.assertEqual(seen["e"], "UAT", "phai hoi dung moi truong cua cau hinh")

    def test_khong_co_anh_xa_thi_TU_CHOI(self):
        fn, _s = self._fn(False)
        with self.assertRaises(_Throw):
            fn({"environment": "UAT", "allowed_signing_users": "ai@ec.vn"}, "ai@ec.vn")

    def test_KHONG_con_doc_danh_sach_go_tay(self):
        """Danh sach rong tung = khong ai ky duoc; moi nguoi moi phai them tay va khong co
        cho nao nhac. Tam (09/09) co anh xa da xac minh van bi chan.

        Kiem tren THAN HAM, khong ke docstring: docstring CO Y nhac ten truong cu de nguoi
        doc sau biet chuyen gi da xay ra. Kiem ca ham thi phep do bat nham chinh phan ghi
        chu lich su - va cach "sua" de test xanh se la xoa mat ghi chu do.
        """
        node = _fn_src("assert_allowed_signer", ("platform", "esign", "permissions.py"))
        body = [n for n in node.body
                if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                        and isinstance(n.value.value, str))]
        src = "\n".join(ast.unparse(n) for n in body)
        self.assertNotIn("allowed_signing_users", src, "than ham khong duoc doc truong do nua")
        self.assertIn("verified_mapping", src)

    def test_van_con_chot_nguoi_duyet_dung_luot(self):
        """Danh sach nay CHUA BAO GIO chan nguoi khong phai nguoi duyet - viec do do
        `assert_pending_approver` lam. Bo danh sach KHONG duoc dong nghia bo chot do."""
        src = _read("platform", "esign", "service.py")
        fn = ast.unparse(_fn_src("approve_and_sign"))
        self.assertIn("assert_pending_approver", fn)
        self.assertIn("assert_allowed_signer", fn)


if __name__ == "__main__":
    unittest.main()
