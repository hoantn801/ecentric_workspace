# Copyright (c) 2026, eCentric and contributors
"""Buoc 6 (Finance xu ly UNC): nhan viec phai khai HAI ngay, va hoan tat chi hien SAU do.

Y Hoan 09/09 sau khi nhin man hinh that (EC-PAYR-2026-...):

  1. Khoi "Hoan tat - dinh kem UNC" hien ra ngay ca khi phieu con "Cho Finance nhan xu ly".
     Vi no chi gac bang QUYEN (`cap.can_complete`) chu khong gac bang TRANG THAI, ma
     Finance/SM thi luon co quyen. Hau qua khong chi la xau: nhay thang qua buoc nhan viec
     nghia la phieu KHONG CO han xu ly nao, vi han duoc khai o dung buoc do.

  2. Nhan viec phai hoi hai ngay KHAC NHAU:
       * ngay thanh toan -> dung de NHAC VIEC;
       * ngay co UNC     -> dung de tinh QUA HAN, vi buoc nay hoan tat bang viec dinh kem
                            UNC chu khong phai bang viec chuyen tien.

  3. Hai ngay do la TRUONG RIENG. KHONG ghi de `payment_date` cua nguoi de nghi - con so do
     da di qua ca bon cap duyet; ghi de la xoa mat thu moi nguoi da dong y ma khong ai biet
     no tung la gi. Giu ca hai thi con so duoc cam ket voi thuc te.
"""
import ast
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_SVC = ("approval_center", "features", "payment_request", "application", "service.py")
_REM = ("approval_center", "features", "payment_request", "application", "reminders.py")
_UI = ("approval_center", "features", "payment_request", "ui", "main_section.html")


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


def _fn(name, rel=_SVC):
    return next(n for n in ast.parse(_read(*rel)).body
                if isinstance(n, ast.FunctionDef) and n.name == name)


class _Throw(Exception):
    pass


class TestBatBuocHaiNgay(unittest.TestCase):
    """Chay THAT `_claim_dates`."""

    def _f(self):
        ns = {"frappe": types.SimpleNamespace(
                  throw=lambda m, *a, **k: (_ for _ in ()).throw(_Throw(str(m)))),
              "_": lambda s: s,
              "getdate": lambda d: ("NGAY:%s" % d) if d else None}
        exec(compile(ast.Module(body=[_fn("_claim_dates")], type_ignores=[]),
                     "service.py", "exec"), ns)
        return ns["_claim_dates"]

    def test_du_ca_hai_thi_qua(self):
        self.assertEqual(self._f()("2026-09-10", "2026-09-12"),
                         ("NGAY:2026-09-10", "NGAY:2026-09-12"))

    def test_thieu_MOT_ngay_cung_TU_CHOI(self):
        f = self._f()
        for a, b in (("2026-09-10", None), (None, "2026-09-12"), (None, None), ("", "")):
            with self.assertRaises(_Throw, msg=repr((a, b))):
                f(a, b)

    def test_cau_bao_loi_NOI_RO_thieu_ngay_nao(self):
        f = self._f()
        with self.assertRaises(_Throw) as e:
            f(None, "2026-09-12")
        self.assertIn("ngày thanh toán", str(e.exception))
        with self.assertRaises(_Throw) as e2:
            f("2026-09-10", None)
        self.assertIn("ngày có UNC", str(e2.exception))

    def test_KHONG_ep_thu_tu_hai_ngay(self):
        """Nghe thi hop ly la UNC phai sau thanh toan, nhung chua ai xac nhan khong bao gio
        co ca nguoc lai. Dat mot rang buoc SAI vao cho chan nguoi dung thi phien hon la
        thieu no."""
        self.assertIsNotNone(self._f()("2026-09-12", "2026-09-10"))


class TestGhiHaiNgayVaHanXuLy(unittest.TestCase):
    def setUp(self):
        self.src = ast.unparse(_fn("claim_fulfillment"))

    def test_nhan_hai_tham_so_ngay(self):
        self.assertIn("def claim_fulfillment(name, user=None, payment_date=None, unc_date=None)",
                      _read(*_SVC))

    def test_ghi_hai_ngay_TRONG_CUNG_lenh_UPDATE_co_dieu_kien(self):
        """Ghi rieng mot lenh khac thi co mot khoanh khac 'da nhan ma chua co han', va hai
        nguoi bam cung luc co the ghi de ngay cua nhau."""
        i = self.src.index("update `tabEC Payment Request`")
        j = self.src.index("where name=%s and fulfillment_status='Assigned'", i)
        cau = self.src[i:j]
        for f in ("fulfillment_owner", "fulfillment_status", "fulfillment_payment_date",
                  "fulfillment_unc_date", "fulfillment_due_at"):
            self.assertIn(f, cau, f)

    def test_han_xu_ly_tinh_theo_ngay_co_UNC(self):
        self.assertIn("unc_due_at(ngay_unc)", self.src)
        self.assertNotIn("unc_due_at(ngay_tt)", self.src)

    def test_nhac_viec_theo_ngay_THANH_TOAN(self):
        """ToDo.date la moc NHAC, khac moc qua han."""
        self.assertIn("ensure_sole_todo", self.src)
        i = self.src.index("ensure_sole_todo")
        self.assertIn("date=ngay_tt", self.src[i:i + 220])

    def test_KHONG_ghi_de_payment_date_cua_nguoi_de_nghi(self):
        """Con so do da di qua bon cap duyet."""
        i = self.src.index("update `tabEC Payment Request`")
        j = self.src.index("where name=%s and fulfillment_status='Assigned'", i)
        self.assertNotIn("payment_date=%s", self.src[i:j].replace("fulfillment_payment_date=%s", ""))

    def test_duong_dung_chung_khong_lot_qua_khi_thieu_ngay(self):
        """`bind_fulfillment` van sinh ra `claim_fulfillment(name)` cho 8 form. Voi De nghi
        thanh toan, goi no ma khong co ngay PHAI bi tu choi - khong duoc lang le nhan viec
        roi de phieu khong co han."""
        self.assertIn("_claim_dates(payment_date, unc_date)", self.src)
        i = self.src.index("_claim_dates(payment_date, unc_date)")
        j = self.src.index("update `tabEC Payment Request`")
        self.assertLess(i, j, "phai kiem ngay TRUOC khi ghi trang thai")


class TestDiemVaoRieng(unittest.TestCase):
    def test_endpoint_rieng_POST_va_chuyen_du_hai_ngay(self):
        src = _read("approval_center", "features", "payment_request", "controllers", "api.py")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "claim_fulfillment_unc")
        deco = " ".join(ast.unparse(d) for d in fn.decorator_list)
        self.assertIn("POST", deco)
        body = ast.unparse(fn)
        self.assertIn("payment_date=payment_date", body)
        self.assertIn("unc_date=unc_date", body)

    def test_tra_ve_dung_hinh_dang_nhu_duong_chung(self):
        """Giao dien khong phai biet minh vua goi duong nao."""
        src = _read("approval_center", "features", "payment_request", "controllers", "api.py")
        fn = ast.unparse(next(n for n in ast.walk(ast.parse(src))
                              if isinstance(n, ast.FunctionDef)
                              and n.name == "claim_fulfillment_unc"))
        for k in ("'claimed'", "'owner'", "'detail'"):
            self.assertIn(k, fn.replace('"', "'"), k)


class TestNhacViecBamNgayFinanceKhai(unittest.TestCase):
    def _f(self):
        # Nap ca `_truong`: `moc_nhac` goi no. Nap thieu thi test do vi NameError - mot ly do
        # SAI, khong phai logic.
        ns = {"frappe": None, "_": lambda s: s}
        exec(compile(ast.Module(body=[_fn("moc_nhac", _REM), _fn("_truong", _REM)],
                                type_ignores=[]), "reminders.py", "exec"), ns)
        return ns["moc_nhac"]

    def test_uu_tien_ngay_Finance_cam_ket(self):
        self.assertEqual(self._f()({"fulfillment_payment_date": "2026-09-15",
                                    "payment_date": "2026-09-10"}), "2026-09-15")

    def test_chua_co_ai_nhan_thi_lui_ve_ngay_da_duyet(self):
        self.assertEqual(self._f()({"payment_date": "2026-09-10"}), "2026-09-10")

    def test_khong_co_ngay_nao_thi_None_chu_khong_no(self):
        self.assertIsNone(self._f()({}))

    def test_doc_duoc_CA_dict_LAN_doi_tuong(self):
        """`frappe.get_all` tra `frappe._dict` (dict), `frappe.get_doc` tra Document (thuoc
        tinh). Ban dau ham nay chi doc duoc `.get` va tra None IM LANG voi kieu con lai -
        tuc "phieu khong co ngay nao" thay vi "toi khong doc duoc"."""
        import types as _t
        f = self._f()
        self.assertEqual(f(_t.SimpleNamespace(fulfillment_payment_date="2026-09-15",
                                              payment_date="2026-09-10")), "2026-09-15")
        self.assertEqual(f(_t.SimpleNamespace(payment_date="2026-09-10")), "2026-09-10")

    def test_loc_moc_nhac_o_PYTHON_khong_o_SQL(self):
        """`COALESCE` trong `fields`/`filters` bi Frappe 16 chan (bai hoc dashboard PnL).

        Kiem tren THAN HAM, khong ke docstring: docstring CO Y nhac chu "coalesce" de noi vi
        sao KHONG dung no. Kiem ca ham thi phep do bat nham chinh phan giai thich - va cach
        "sua" de test xanh se la xoa mat loi giai thich do."""
        node = _fn("due_candidates", _REM)
        body = [n for n in node.body
                if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                        and isinstance(n.value.value, str))]
        src = "\n".join(ast.unparse(n) for n in body)
        self.assertIn("moc_nhac(r)", src)
        self.assertNotIn("coalesce", src.lower(), "than ham khong duoc dung COALESCE")
        self.assertIn("fulfillment_payment_date", src, "phai NAP truong moi ve moi loc duoc")


class TestGiaoDien(unittest.TestCase):
    def setUp(self):
        self.h = _read(*_UI)

    def test_khoi_hoan_tat_gac_bang_CA_quyen_VA_trang_thai(self):
        self.assertIn('cap.can_complete && ff.status==="In Progress"', self.h)
        self.assertNotIn("if(cap.can_complete){", self.h,
                         "gac bang mot minh quyen la cai loi dang sua")

    def test_nhan_xu_ly_hoi_hai_ngay_va_chan_khi_thieu(self):
        i = self.h.index("function doUncClaim")
        block = self.h[i:i + 2200]
        self.assertIn('data-claim="pay"', block)
        self.assertIn('data-claim="unc"', block)
        self.assertIn("claim_fulfillment_unc", block)
        self.assertIn("Phải khai cả hai ngày", block)

    def test_nhan_han_xu_ly_goi_dung_ten(self):
        """Truoc day ghi '(ngay thanh toan)' trong khi han tinh theo ngay co UNC."""
        self.assertIn("Hạn xử lý (ngày có UNC)", self.h)
        self.assertNotIn("Hạn xử lý (ngày thanh toán)", self.h)

    def test_chua_ai_nhan_thi_goi_la_han_TAM_TINH(self):
        self.assertIn("Hạn tạm tính", self.h)

    def test_hien_hai_ngay_da_cam_ket(self):
        self.assertIn("fulfillment_payment_date", self.h)
        self.assertIn("fulfillment_unc_date", self.h)

    def test_nut_thay_UNC_chi_hien_khi_server_cho_phep(self):
        """Gac bang co do SERVER tinh (`extra.unc_fix.can_replace`), khong tu suy o trinh
        duyet. Man hinh khong biet chac ai la chu viec: `ff.owner` la nguoi dang xu ly, ma
        phieu da Hoan tat thi khai niem do khong con dung nua."""
        i = self.h.index('data-act="unc-fix"')
        self.assertIn("fx.can_replace", self.h[max(0, i - 400):i])

    def test_modal_thay_UNC_doi_ca_TEP_lan_LY_DO(self):
        i = self.h.index("function doUncFix")
        block = self.h[i:i + 2600]
        self.assertIn('data-fix="file"', block)
        self.assertIn('data-fix="reason"', block)
        self.assertIn("replace_unc_attachment", block)
        self.assertIn("min_reason_len", block)

    def test_khong_dung_chung_state_unc_voi_khoi_hoan_tat(self):
        """Hai luong tai tep khac nhau. Dung chung `state.unc` thi bam Huy o modal van de lai
        mot tep 'da tai' cho khoi Hoan tat - va lan sau bam Hoan tat se gui di tep do."""
        i = self.h.index("function doUncFix")
        self.assertNotIn("state.unc", self.h[i:i + 2600])

    def test_liet_ke_file_da_thay(self):
        self.assertIn("File UNC đã bị thay", self.h)
        self.assertIn("fx.superseded", self.h)


def _compose_dang_ship():
    """Dung lai DUNG thu ma `page_sync._html()` tra ve: main + 3 panel esign.

    Chep thu tu ghep tu `page_sync._html()`. Neu ai do doi thu tu / them panel ben do ma
    khong sua o day thi test se do - dung y: hai cho phai di cung nhau.
    """
    def doc(*p):
        return io.open(os.path.join(_APP, *p), encoding="utf-8").read()

    def panel(f):
        p = os.path.join(_APP, "platform", "esign", "ui", f)
        return doc("platform", "esign", "ui", f) if os.path.exists(p) else ""
    return (doc(*_UI) + "\n"
            + panel("requester_signing_panel.html") + "\n"
            + '<div id="ec-approver-wrap" style="display:none">\n'
            + panel("payment_request_signing.html")
            + '\n</div>\n'
            + panel("document_signing_section.html"))


class TestKhoaChongTroiVaPatch(unittest.TestCase):
    def test_BASELINE_bang_sha_cua_COMPOSE_chu_khong_phai_cua_FILE(self):
        """BASELINE duoc so voi `main_section_html` cua trang SONG, ma trang do duoc ghi bang
        `_html()` = main + 3 panel esign - KHONG phai rieng ui/main_section.html.

        Ban dau test nay bam rieng file main (10/09 phat hien): mot cai cong canh sai thu.
        Hai gia tri lech nhau that (128 591 vs 237 816 ky tu), nen BASELINE khong bao gio
        khop live - va vi `upsert_web_page` con chap nhan `ec_page_sync_sha` do
        `record_live_sha` ghi lai nen KHONG co gi hong, chi la luoi du phong vo dung. Mot
        luoi du phong sai thi lan nao can toi no cung khong do duoc.
        """
        import hashlib
        h = hashlib.sha256(_compose_dang_ship().encode("utf-8")).hexdigest()
        ps = _read("approval_center", "features", "payment_request", "infrastructure",
                   "page_sync.py")
        self.assertIn('BASELINE_SHA256 = "%s"' % h, ps,
                      "BASELINE phai la sha cua _html() da compose")

    def test_manifest_bam_FILE_chu_khong_phai_compose(self):
        """Doi lai, `resync_manifest.json` bam DUNG FILE template - do la ban ke "file nao
        da doi ma chua co patch resync". Nham hai thu nay la sua mai khong xanh."""
        import hashlib
        import json
        raw = io.open(os.path.join(_APP, *_UI), "rb").read().replace(b"\r\n", b"\n")
        h = hashlib.sha256(raw).hexdigest()
        man = json.loads(_read("approval_center", "patches", "resync_manifest.json"))
        self.assertEqual(
            man["approval_center/features/payment_request/ui/main_section.html"]["sha256"], h)
        self.assertNotEqual(h, hashlib.sha256(_compose_dang_ship().encode("utf-8")).hexdigest(),
                            "hai gia tri nay PHAI khac nhau - bang nhau la mot cai dang sai")

    def test_ban_cu_nam_trong_SUPERSEDES(self):
        ps = _read("approval_center", "features", "payment_request", "infrastructure",
                   "page_sync.py")
        # ban dang o trong repo truoc dot nay - live co the dang giu chinh no
        self.assertIn("74d10a85d20203ee214212072d944f8fb37599457be4f2fb3e963fd323d6cdda", ps)
        # baseline cu (da lech san)
        self.assertIn("6cd06565ca958bd89a0e33e5c2a6a63484b45d7417d0bee748112d76566e9c59", ps)

    def test_compose_ma_LIVE_dang_giu_phai_duoc_chap_nhan(self):
        """Da do truc tiep 09/09: live tren team.ecentric.vn dang bam ra dung gia tri nay
        (compose sau p170). Bo no khoi SUPERSEDES la tu tay dung mot cai cong tu choi cho
        lan sync toi, neu `ec_page_sync_sha` vi ly do nao do khong con."""
        ps = _read("approval_center", "features", "payment_request", "infrastructure",
                   "page_sync.py")
        self.assertIn("950c56c3d385132623b12f5dc6e61554bf910ea2a6243df06f4109816c5b6d68", ps)

    def test_patch_da_khai_va_KIEM_ket_qua(self):
        self.assertIn("p170_resync_payment_request_unc_claim_dates", _read("patches.txt"))
        src = _read("approval_center", "patches",
                    "p170_resync_payment_request_unc_claim_dates.py")
        self.assertIn('action == "refused"', src, "phai bao khi bi tu choi ghi")
        self.assertIn("_EXPECT", src)
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "execute")
        self.assertFalse([n for n in ast.walk(fn) if isinstance(n, ast.Raise)],
                         "patch chay trong migrate: nem loi = chet ca lan deploy")


class TestDocType(unittest.TestCase):
    def test_hai_truong_moi_ton_tai_va_CHI_MAY_CHU_ghi(self):
        import json
        d = json.loads(_read("approval_center", "doctype", "ec_payment_request",
                             "ec_payment_request.json"))
        by = {f["fieldname"]: f for f in d["fields"]}
        for n in ("fulfillment_payment_date", "fulfillment_unc_date"):
            self.assertIn(n, by, n)
            self.assertEqual(by[n]["fieldtype"], "Date", n)
            self.assertEqual(by[n].get("read_only"), 1,
                             "%s: nguoi dung sua tay tren Desk = mot han khong ai cam ket" % n)
        self.assertIn("payment_date", by, "ngay nguoi de nghi khai PHAI con nguyen")


if __name__ == "__main__":
    unittest.main()
