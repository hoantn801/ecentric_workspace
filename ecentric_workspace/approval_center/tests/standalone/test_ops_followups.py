# Copyright (c) 2026, eCentric and contributors
"""Năm việc còn lại sau rà soát 31/08 — mỗi cái một lớp.

Không cái nào chặn ai làm việc, nhưng cả năm đều thuộc cùng một họ: **hệ thống nói một đằng,
làm một nẻo**. Một danh sách nợ chỉ tăng mà giao diện hứa sẽ giảm; một con số "10 lần" thật ra
là 3,3 lượt; một bảng bảo "đây là mọi gói chưa tải xong" trong khi cron còn thử những gói nó
không hiện; một nút hiện cho người bấm vào sẽ bị từ chối.

Việc số 5 (clone không chạy kiểm tra hợp lệ) **cố ý không sửa** — xem lớp cuối.
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


def _read(*parts):
    return io.open(os.path.join(_ROOT, *parts), encoding="utf-8").read()


_GUARD = _read("platform", "esign", "guard.py")
_OPS = _read("platform", "esign", "ops.py")
_UI = _read("platform", "esign", "ui", "ops_page.html")
_MAIN = _read("approval_center", "features", "payment_request", "ui", "main_section.html")
_CS = _read("approval_center", "shared", "requests", "command_service.py")
_TASKS = _read("platform", "esign", "tasks.py")


def _fn(src, name):
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError("khong tim thay ham %s" % name)


class _Throw(Exception):
    pass


class _D(dict):
    """Giong `frappe._dict` - doc duoc bang ca `r["x"]` lan `r.x`.

    `get_value(..., as_dict=True)` cua Frappe tra kieu do; ban gia tra dict tran thi ma nguon
    dung van no AttributeError, va test do o cho khong co loi.
    """

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


# ---------------------------------------------------------------------------- #
# 1. Duong xu ly no chu ky
# ---------------------------------------------------------------------------- #
_ENGINE = "ecentric_workspace.approval_center.shared.workflow.transitions"
_SAVED = None
_LOG = []


def setUpModule():
    global _SAVED
    import sys
    _SAVED = sys.modules.get(_ENGINE)
    stub = types.ModuleType("transitions")
    stub.log_action = lambda ar, action, actor, **kw: _LOG.append((action, kw.get("comment")))
    sys.modules[_ENGINE] = stub


def tearDownModule():
    import sys
    if _SAVED is None:
        sys.modules.pop(_ENGINE, None)
    else:
        sys.modules[_ENGINE] = _SAVED


def _load_settle(row=None, is_sm=True):
    del _LOG[:]
    written, emitted = {}, []

    class _Frappe(object):
        session = types.SimpleNamespace(user="admin@x.vn")
        ValidationError = _Throw

        class db(object):
            @staticmethod
            def get_value(dt, name, fields=None, **kw):
                return _D(row) if row else None

            @staticmethod
            def set_value(dt, name, field, value=None):
                written[field] = value

        @staticmethod
        def throw(msg, exc=None):
            raise _Throw(msg)

    def _sm():
        if not is_sm:
            raise _Throw("chi System Manager")

    env = {"frappe": _Frappe, "_": lambda s: s,
           "perms": types.SimpleNamespace(assert_system_manager=_sm),
           "events": types.SimpleNamespace(emit=lambda t, **kw: emitted.append((t, kw))),
           "now_datetime": lambda: "2026-08-31 23:00:00"}
    exec(compile(_fn(_GUARD, "settle_signature_debt"), "guard.py", "exec"), env)
    return env["settle_signature_debt"], written, emitted


def _debt(**kw):
    base = {"name": "ARL-1", "approval_request": "AR-1", "level_no": 2,
            "signature_deferred": 1, "signature_settled_at": None,
            "signature_deferred_by": "lien.vu@x.vn"}
    base.update(kw)
    return base


class TestSettlingADebtIsRecordingNotSigning(unittest.TestCase):
    """He thong nay khong ky thay ai duoc. Hai ket cuc trung thuc, ca hai bat buoc ly do."""

    def test_xac_nhan_da_ky_bu(self):
        fn, written, emitted = _load_settle(_debt())
        out = fn("ARL-1", "signed", "SCTS doc-123, ky luc 10:05 ngay 01/09")
        self.assertTrue(out["ok"])
        self.assertIn("signature_settled_at", written)

    def test_mien_no_co_ly_do(self):
        fn, written, _e = _load_settle(_debt())
        fn("ARL-1", "waived", "Tai lieu ben SCTS da dong, nguoi duyet da nghi viec")
        self.assertIn("signature_settled_at", written)

    def test_KHONG_ly_do_thi_tu_choi(self):
        fn, written, _e = _load_settle(_debt())
        for bad in ("", "   ", None):
            with self.assertRaises(_Throw):
                fn("ARL-1", "waived", bad)
        self.assertEqual(written, {}, "da chan ma van ghi")

    def test_cach_xu_ly_la_hai_gia_tri_dong(self):
        fn, written, _e = _load_settle(_debt())
        with self.assertRaises(_Throw):
            fn("ARL-1", "cleared", "abc")
        self.assertEqual(written, {})

    def test_chi_System_Manager(self):
        fn, written, _e = _load_settle(_debt(), is_sm=False)
        with self.assertRaises(_Throw):
            fn("ARL-1", "waived", "ly do")
        self.assertEqual(written, {})

    def test_khong_co_no_thi_tu_choi(self):
        fn, written, _e = _load_settle(_debt(signature_deferred=0))
        with self.assertRaises(_Throw):
            fn("ARL-1", "waived", "ly do")
        self.assertEqual(written, {})

    def test_dong_hai_lan_khong_ghi_de(self):
        fn, written, _e = _load_settle(_debt(signature_settled_at="2026-08-30 10:00:00"))
        out = fn("ARL-1", "waived", "ly do")
        self.assertTrue(out.get("already"))
        self.assertEqual(written, {}, "idempotent - khong ghi lai")

    def test_ghi_vao_lich_su_phieu_kem_LY_DO(self):
        fn, _w, _e = _load_settle(_debt())
        fn("ARL-1", "waived", "SCTS da dong tai lieu")
        self.assertEqual(len(_LOG), 1)
        action, comment = _LOG[0]
        self.assertEqual(action, "Commented")
        self.assertIn("SCTS da dong tai lieu", comment)
        self.assertIn("lien.vu@x.vn", comment, "phai ghi ai la nguoi no")

    def test_phat_su_kien_co_ca_hai_nguoi(self):
        fn, _w, emitted = _load_settle(_debt())
        fn("ARL-1", "signed", "da doi soat")
        self.assertEqual(len(emitted), 1)
        t, kw = emitted[0]
        self.assertEqual(t, "SignatureDebtSettled")
        meta = kw["request_meta"]
        self.assertEqual(meta["owed_by"], "lien.vu@x.vn")
        self.assertEqual(meta["settled_by"], "admin@x.vn",
                         "ai NO va ai DONG la hai nguoi khac nhau - phai ghi ca hai")

    def test_KHONG_co_duong_nao_ky_ho(self):
        # Doc CAC LOI GOI, khong grep chuoi: chinh ham nay import `transitions as engine` de
        # ghi lich su, nen tim chu "transition" se bat oan mot dong hop le. Lan thu nam trong
        # ba ngay dinh cai bay "grep trung chu cua chinh minh".
        fn = [n for n in ast.parse(_GUARD).body
              if isinstance(n, ast.FunctionDef) and n.name == "settle_signature_debt"][0]
        called = {getattr(c.func, "attr", None) or getattr(c.func, "id", None)
                  for c in ast.walk(fn) if isinstance(c, ast.Call)}
        for forbidden in ("approve_and_sign", "requester_submit_and_sign", "sign_on_submit",
                          "get_adapter", "create_document", "poll_status"):
            self.assertNotIn(forbidden, called,
                             "dong mon no la GHI NHAN, khong duoc cham vao nha cung cap")

    def test_su_kien_da_khai_bao(self):
        j = _read("approval_center", "doctype", "ec_digital_signature_event",
                  "ec_digital_signature_event.json")
        self.assertIn("SignatureDebtSettled", j)

    def test_giao_dien_co_hai_nut_va_bat_buoc_ly_do(self):
        self.assertIn("debt_signed", _UI)
        self.assertIn("debt_waived", _UI)
        body = _UI.split("function run(")[1][:3000]
        self.assertIn("Bắt buộc nêu lý do", body)

    def test_giao_dien_noi_ro_khong_ky_thay(self):
        self.assertIn("Hệ thống không", _UI,
                      "nut 'Da ky bu' phai noi ro no chi GHI NHAN viec da xay ra")


# ---------------------------------------------------------------------------- #
# 2. Bo dem: luot cron, khong phai so tep
# ---------------------------------------------------------------------------- #
class TestTheCounterCountsRounds(unittest.TestCase):
    """`SignedFileRetrievalStarted` phat ra MOT LAN CHO MOI TEP, khong phai moi luot cron.
    Goi 3 tep cham nguong 10 sau ~3,3 luot ~ 1,7 tieng, khong phai 5 tieng nhu nhan ghi."""

    def test_co_ham_doi_sang_luot(self):
        names = [n.name for n in ast.parse(_OPS).body if isinstance(n, ast.FunctionDef)]
        self.assertIn("_retrieval_rounds", names)

    def test_uy_thac_cho_noi_PHAT_su_kien(self):
        """Cach chia cho so tep da bi thay ngay 31/08.

        No dem `SignedFileRetrievalStarted`, ma su kien do chi phat ra khi da qua duoc buoc
        do trang thai - nen goi hong ngay o buoc do luon hien "0 luot". Gio ca man hinh lan
        bao dong deu goi signed_files.retrieval_rounds, xem
        test_retrieval_rounds_counts_failures.py.
        """
        body = _fn(_OPS, "_retrieval_rounds")
        self.assertIn("signed_files.retrieval_rounds", body,
                      "man hinh va bao dong phai dem chung mot cach")

    def test_bang_dung_ham_do_chu_khong_dem_tho(self):
        body = _fn(_OPS, "unretrieved_bundles")
        self.assertIn("_retrieval_rounds(r.name)", body)
        self.assertNotIn('_attempts(r.name, "SignedFileRetrievalStarted")', body)

    def test_nhan_tren_man_hinh_noi_LUOT(self):
        self.assertIn("lượt", _UI)
        self.assertNotIn("Thử ' + r.attempts + ' lần", _UI,
                         "nhan cu noi 'lan' trong khi con so la luot")


# ---------------------------------------------------------------------------- #
# 3. Trang ops loc KHOP voi cron
# ---------------------------------------------------------------------------- #
class TestOpsSeesEverythingTheCronRetries(unittest.TestCase):
    def test_khong_con_loc_cung_moi_Active(self):
        body = _fn(_OPS, "unretrieved_bundles")
        self.assertNotIn('"status": "Active"', body,
                         "goi Completed chua tai xong van bi cron thu - phai hien ra")

    def test_loc_theo_dung_dieu_kien_cron_dung(self):
        body = _fn(_OPS, "unretrieved_bundles")
        self.assertIn('"scts_document_id": ["is", "set"]', body)
        self.assertIn('"signed_bundle_complete": 0', body)

    def test_van_bo_goi_da_huy_va_da_thay_the(self):
        body = _fn(_OPS, "unretrieved_bundles")
        self.assertIn("Cancelled", body)
        self.assertIn("Superseded", body)


# ---------------------------------------------------------------------------- #
# 4. Nut "Tao phieu moi" khop quyen backend
# ---------------------------------------------------------------------------- #
class TestTheCloneButtonMatchesTheBackend(unittest.TestCase):
    def test_ui_chi_xet_requested_by(self):
        body = _MAIN.split("function isMine")[1][:400]
        self.assertIn("b.requested_by===u", body)
        self.assertNotIn("b.owner===u", body,
                         "backend chi nhan requested_by - hien nut cho owner la bay nguoi dung")

    def test_backend_van_la_nguon_su_that(self):
        body = _fn(_CS, "clone_request")
        self.assertIn("source.requested_by != user", body)


# ---------------------------------------------------------------------------- #
# 5. clone KHONG chay validator - co y
# ---------------------------------------------------------------------------- #
class TestCloneDeliberatelySkipsValidation(unittest.TestCase):
    """Ban sao la mot phieu NHAP. Nhap thi duoc phep chua day du."""

    def test_khong_goi_validator(self):
        body = _fn(_CS, "clone_request")
        code = body.split('"""')[2] if body.count('"""') >= 2 else body
        self.assertNotIn("definition.validator", code,
                         "chay kiem tra o day = phieu thieu truong khong tao lai duoc, "
                         "dung cai be tac ma nut nay sinh ra de xoa bo")

    def test_ly_do_duoc_ghi_lai(self):
        body = _fn(_CS, "clone_request")
        self.assertIn("CO Y KHONG chay", body,
                      "bo qua mot buoc ma khong ghi ly do thi lan sau co nguoi them vao")

    def test_van_chuan_bi_du_lieu_nhu_mot_phieu_nhap(self):
        body = _fn(_CS, "clone_request")
        self.assertIn("draft_preparer", body, "chuan hoa du lieu thi van phai chay")


if __name__ == "__main__":
    unittest.main()
