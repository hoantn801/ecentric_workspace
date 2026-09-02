# Copyright (c) 2026, eCentric and contributors
"""Hai loi Hoan ghi nhan 02/09 tren trang Payment Request, va cong QC de chung khong quay lai.

(a) "Loi khi o ngoai form": p123 chi noi cac duong TRONG form sang extractServerMsg. Ngoai
    form - tab danh sach, tab can toi duyet, nap chi tiet, gui lai, boot - van doc `e.message`
    (luon rong voi frappe.throw) hoac vut hang loi di (`.catch(function(){...})`), nen nguoi
    dung chi thay "Khong tai duoc" trong khi may chu da noi ro vi sao. Cong nay di qua TUNG
    `.catch(` trong template: handler nao khong di qua mapErr / friendlyErr /
    applyBackendError / resubmitErr / extractServerMsg thi do, tru ba cho co y im lang va
    duoc ghi ly do o NGOAI_LE.

(b) "Bam Duyet xong phai F5 moi thay": refreshDetail() van doc lai tu API - khong phai loi.
    Loi nam o hai cho quanh no: loadSignReady khoa readiness theo id ho so nen sau khi cap
    chuyen, khu Hanh dong van dung readiness cua cap cu; va renderDetail khong co gi chan phan
    hoi cu ve muon de len phan hoi moi. Cong nay ghim: moi hanh dong duyet goi refreshDetail(),
    refreshDetail -> renderDetail -> call("get_detail") (khong doc state.detail), phan hoi mang
    so thu tu, va khoa readiness co current_level.

Kiem CHINH CAI CONG truoc: phep do (a) duoc cho mot mau chac chan sai va mot mau chac chan
dung truoc khi quet file that. Mot cong xanh vinh vien thi khong ai biet no mu.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "patches")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()
_TEMPLATE = os.path.join(_ROOT, "approval_center", "features", "payment_request", "ui",
                         "main_section.html")


def _page():
    return io.open(_TEMPLATE, encoding="utf-8").read()


# --- doc cau truc JS bang dem ngoac, khong bang thut le ----------------------------------

def _skip_string(src, i):
    """i tro vao dau nhay mo; tra ve vi tri SAU dau nhay dong."""
    q, n = src[i], len(src)
    i += 1
    while i < n and src[i] != q:
        i += 2 if src[i] == "\\" else 1
    return i + 1


def _balanced(src, i):
    """i tro vao mot dau ngoac mo `(` hoac `{`; tra ve (noi_dung_ben_trong, vi_tri_sau_dong)."""
    opener = src[i]
    closer = {"(": ")", "{": "}"}[opener]
    depth, j, n = 0, i, len(src)
    while j < n:
        c = src[j]
        if c in "\"'`":
            j = _skip_string(src, j)
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return src[i + 1:j], j + 1
        j += 1
    raise AssertionError("ngoac khong dong tu vi tri %d" % i)


def _catch_handlers(src):
    """[(dong, dau_handler, than_handler)] cho moi `.catch(` trong src."""
    out = []
    for m in re.finditer(r"\.catch\(", src):
        head_start = m.end()
        brace = src.find("{", head_start)
        if brace == -1:
            raise AssertionError(".catch( khong co handler inline o vi tri %d" % m.start())
        head = src[head_start:brace].strip()
        body, _end = _balanced(src, brace)
        line = src.count("\n", 0, m.start()) + 1
        out.append((line, head, body))
    return out


def _function_body(src, name):
    m = re.search(r"function\s+%s\s*\(" % re.escape(name), src)
    if not m:
        raise AssertionError("khong thay `function %s(`" % name)
    brace = src.find("{", m.end())
    body, _end = _balanced(src, brace)
    return body


#: Handler di qua mot trong cac ham nay la "da boc thong diep may chu".
_HELPERS = ("mapErr(", "friendlyErr(", "applyBackendError(", "resubmitErr(", "extractServerMsg(")


def _bad_handlers(src, exempt=()):
    bad = []
    for line, head, body in _catch_handlers(src):
        if any(h in body for h in _HELPERS):
            continue
        if any(marker in body for marker in exempt):
            continue
        bad.append((line, head, body.strip()[:80]))
    return bad


class TestPhepDoTruocKhiTin(unittest.TestCase):
    """Cho cong mot mau TRUOT va mot mau DAT truoc khi quet file that."""

    def test_bat_duoc_handler_doc_e_message(self):
        mau = 'call("x").then(f).catch(function(e){ toast((e&&e.message)||"Loi"); });'
        self.assertEqual([b[0] for b in _bad_handlers(mau)], [1],
                         "handler doc e.message truc tiep ma cong khong bao -> cong mu")

    def test_bat_duoc_handler_vut_loi(self):
        mau = 'call("x").then(f).catch(function(){ host.innerHTML="Khong tai duoc"; });'
        self.assertEqual(len(_bad_handlers(mau)), 1)

    def test_khong_bao_dong_gia(self):
        mau = ('call("x").then(f).catch(function(e){ toast(mapErr(e),true); });\n'
               'call("y").catch(function(e){ if(!applyBackendError(e)){ toast(friendlyErr(e),true); } });\n'
               'call("z").catch(function(e){ d.textContent=extractServerMsg(e)||"Loi"; });')
        self.assertEqual(_bad_handlers(mau), [])

    def test_ngoai_le_duoc_ton_trong_va_chi_khi_khop_dau_moc(self):
        mau = 'p.then(close).catch(function(){ ok.disabled=false; });'
        self.assertEqual(len(_bad_handlers(mau)), 1)
        self.assertEqual(_bad_handlers(mau, exempt=("ok.disabled=false",)), [])

    def test_dem_ngoac_bo_qua_chuoi_co_ngoac(self):
        mau = '.catch(function(e){ x="}"; toast(mapErr(e)); }); .catch(function(){ y=1; });'
        handlers = _catch_handlers(mau)
        self.assertEqual(len(handlers), 2)
        self.assertIn("mapErr(e)", handlers[0][2])
        self.assertNotIn("mapErr", handlers[1][2])


class TestMoiNhanhLoiDeuBocThongDiepMayChu(unittest.TestCase):
    #: Ba handler co y im lang. Moi muc = (dau moc trong than handler, ly do). Go mot muc khi
    #: cho do khong con im lang nua - test_ngoai_le_van_ton_tai se nhac.
    NGOAI_LE = (
        ("da co so tam tu picker", "funding_source_summary: doc lai so du o nen; da co so tam tu "
                                   "picker, loi thi giu so tam, khong lam phien nguoi dung"),
        ("ok.disabled=false", "modal: onConfirm da toast loi cua chinh no; day chi mo lai nut OK"),
        ("state._signReady=null", "loadSignReady: tham do readiness o nen; loi thi actionPanelHTML "
                                  "hien CA HAI nut, nguoi duyet khong bi ket"),
    )

    def setUp(self):
        self.page = _page()
        self.handlers = _catch_handlers(self.page)
        self.assertGreater(len(self.handlers), 15,
                           "chi thay %d `.catch(` - cach doc da lac hau, cong dang mu"
                           % len(self.handlers))

    def test_ngoai_le_van_ton_tai(self):
        bodies = [b for _l, _h, b in self.handlers]
        for marker, _reason in self.NGOAI_LE:
            hits = [b for b in bodies if marker in b]
            self.assertEqual(len(hits), 1,
                             "dau moc ngoai le '%s' khop %d handler (phai dung 1) - go hoac "
                             "sua danh sach NGOAI_LE" % (marker, len(hits)))
            self.assertFalse(any(h in hits[0] for h in _HELPERS),
                             "handler '%s' da di qua helper roi - ngoai le thua, go di" % marker)

    def test_khong_handler_nao_vut_thong_diep_may_chu(self):
        bad = _bad_handlers(self.page, exempt=[m for m, _r in self.NGOAI_LE])
        self.assertEqual(bad, [],
                         "`.catch(` khong di qua mapErr/friendlyErr/applyBackendError/resubmitErr/"
                         "extractServerMsg -> nguoi dung thay cau chung chung trong khi may chu "
                         "da noi ro vi sao:\n  " + "\n  ".join("dong %d: .catch(%s{ %s" % b for b in bad))

    def test_cac_ham_boc_loi_deu_doc_qua_extractServerMsg(self):
        for name in ("mapErr", "friendlyErr", "applyBackendError", "resubmitErr"):
            with self.subTest(fn=name):
                self.assertIn("extractServerMsg(e)", _function_body(self.page, name),
                              "%s khong doc qua extractServerMsg -> e.message luon rong voi "
                              "frappe.throw" % name)

    def test_khong_ai_doc_e_message_ngoai_extractServerMsg(self):
        """resubmitErr (02/09) va renderDetail (02/09) deu tung doc `e.message` truc tiep."""
        no_comments = re.sub(r"(?m)^\s*//.*$", "", self.page)
        body = _function_body(no_comments, "extractServerMsg")
        outside = no_comments.replace(body, "")
        hits = [m.start() for m in re.finditer(r"\be\.message\b|\be\s*&&\s*e\.message\b", outside)]
        lines = [outside.count("\n", 0, h) + 1 for h in hits]
        self.assertEqual(lines, [],
                         "doc e.message truc tiep ngoai extractServerMsg o dong (tinh sau khi bo "
                         "chu thich): %s" % lines)

    def test_tab_danh_sach_hien_thong_diep_may_chu(self):
        """Chinh cai 'loi khi o ngoai form': danh sach + can-toi-duyet + boot."""
        for fn in ("loadList", "loadApprovals", "boot"):
            with self.subTest(fn=fn):
                self.assertIn("mapErr(e)", _function_body(self.page, fn),
                              "%s bat loi ma khong hien cau cua may chu" % fn)


class TestSauKhiDuyetChiTietDuocNapLaiTuAPI(unittest.TestCase):
    ACTIONS = ("doApprove", "doReject", "doRequestInfo", "doAdminApprove", "doCancel")

    def setUp(self):
        self.page = _page()

    def test_moi_hanh_dong_deu_goi_refreshDetail_khi_thanh_cong(self):
        for name in self.ACTIONS:
            with self.subTest(fn=name):
                body = _function_body(self.page, name)
                then_at = body.find(".then(")
                catch_at = body.find(".catch(", then_at)
                self.assertGreater(then_at, -1, "%s khong co .then(" % name)
                self.assertGreater(catch_at, then_at, "%s khong co .catch( sau .then(" % name)
                self.assertIn("refreshDetail()", body[then_at:catch_at],
                              "%s thanh cong ma khong nap lai chi tiet" % name)

    def test_refreshDetail_di_qua_renderDetail(self):
        self.assertIn("renderDetail(", _function_body(self.page, "refreshDetail"))

    def test_renderDetail_doc_tu_API_khong_tu_state(self):
        body = _function_body(self.page, "renderDetail")
        self.assertIn('call("get_detail"', body, "renderDetail khong goi API")
        self.assertNotIn("state.detail", body,
                         "renderDetail doc state.detail = ve lai trang thai cu")
        self.assertIn("drawDetail(b,det)", body, "phan hoi API phai la thu duoc ve")

    def test_phan_hoi_cu_ve_muon_bi_bo(self):
        """Nhieu get_detail bay cung luc (readiness, poll SIGNWAIT, sau hanh dong): cai ve SAU
        thang, ke ca khi no duoc gui TRUOC hanh dong. Phai co so thu tu."""
        body = _function_body(self.page, "renderDetail")
        self.assertRegex(body, r"var seq\s*=\s*\+\+state\._detailSeq",
                         "moi lan nap phai lay mot so thu tu moi")
        then_body = body[body.find(".then("):]
        self.assertRegex(then_body, r"if\s*\(\s*seq\s*!==\s*state\._detailSeq\s*\)\s*return;",
                         "phan hoi khong phai lan nap moi nhat van duoc ve -> trang thai cu de len")
        self.assertIn("_detailSeq:0", self.page, "state phai khoi tao _detailSeq")

    def test_readiness_khoa_theo_cap_khong_chi_theo_id(self):
        """Cai lam nut Duyet/Duyet & Ky sai sau khi cap chuyen: khoa `_signReadyFor===id`."""
        key = _function_body(self.page, "signReadyKey")
        self.assertIn("current_level", key, "khoa readiness phai doi khi cap doi")
        self.assertIn("approval_status", key)
        body = _function_body(self.page, "loadSignReady")
        self.assertIn("signReadyKey()", body)
        self.assertNotRegex(body, r"_signReadyFor\s*===\s*id\b",
                            "van khoa theo id -> sau Duyet readiness cua cap cu duoc dung tiep")
        self.assertRegex(body, r"if\s*\(\s*state\._signReadyFor\s*!==\s*key\s*\)\s*return;",
                         "readiness cua cap cu ve muon phai bi bo")

    def test_drawDetail_dat_state_detail_truoc_khi_hoi_readiness(self):
        """signReadyKey doc state.detail - phai la ban ghi VUA nap, khong phai ban cu."""
        body = _function_body(self.page, "drawDetail")
        self.assertLess(body.find("state.detail=det"), body.find("loadSignReady()"),
                        "loadSignReady() chay truoc khi state.detail duoc gan ban ghi moi")


class TestPatchResyncDiKem(unittest.TestCase):
    """Sua HTML ma khong co patch resync thi trinh duyet van chay ma cu (31/08, 29/08)."""

    def test_p130_ton_tai_va_duoc_khai(self):
        patch = os.path.join(_ROOT, "approval_center", "patches",
                             "p130_resync_payment_request_list_errors_and_stale_detail.py")
        self.assertTrue(os.path.exists(patch))
        src = io.open(patch, encoding="utf-8").read()
        self.assertIn("payment_request", src)
        self.assertIn("page_sync.sync()", src)
        listed = io.open(os.path.join(_ROOT, "patches.txt"), encoding="utf-8").read()
        self.assertIn("p130_resync_payment_request_list_errors_and_stale_detail", listed)


if __name__ == "__main__":
    unittest.main()
