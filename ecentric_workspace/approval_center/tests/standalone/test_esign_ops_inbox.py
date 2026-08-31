# Copyright (c) 2026, eCentric and contributors
"""Trang "Chân ký cần can thiệp" — mọi lối thoát hiểm phải có tay nắm.

Rà soát 29/08: khi một chân ký hỏng, hệ thống đẩy nó vào trạng thái chờ người xử lý, và các
hàm cứu hộ đã được viết đúng từ lâu — `retry_signature_request`,
`reconcile_signature_request`, `reconcile_document_creation`, `retrieve_signed_files`,
`resolve_signed_file_review`. Không một hàm nào được giao diện gọi. Chúng chỉ chạy nếu ai đó
gõ tay một lệnh API.

Hậu quả: `Permanent Failure` và `Cancelled` không có cạnh ra trong máy trạng thái, khoá chống
trùng lại là `unique` nên không tạo lại chân ký mới được. Phiếu nằm chết vĩnh viễn.

Bốn điều bộ test này giữ:
  1. danh sách nút suy ra TỪ MÁY TRẠNG THÁI, không gõ tay — máy đổi thì nút đổi theo;
  2. ngõ cụt thật phải được gọi là ngõ cụt, không vẽ một hàng nút bấm không được;
  3. "đang chờ SCTS ký xong" KHÁC "đã hỏng" — hai cái trông giống hệt nhau trước đây;
  4. `Retryable Failure` không bị lôi vào danh sách: cron tự xử lý nó, báo lên đây là báo
     động giả cho một việc đang chạy bình thường.
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


_OPS = _read("platform", "esign", "ops.py")
_API = _read("platform", "esign", "api.py")
_TASKS = _read("platform", "esign", "tasks.py")
_UI = _read("platform", "esign", "ui", "ops_page.html")
_STATE = _read("platform", "esign", "state.py")


class _D(dict):
    """Giong `frappe._dict`: doc duoc bang ca `r["x"]` lan `r.x`.

    Ban gia tra `dict` tran thi `r.name` nem AttributeError va test do o cho ma ma nguon
    hoan toan dung - mot ban gia lech voi that thi no do o cho no nen xanh.
    """

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


def _fn(src, name):
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError("khong tim thay ham %s" % name)


#: So luot cron ma ban gia signed_files se tra ve. Dat trong mot o thay vi truyen thang, vi
#: ops.py nhap signed_files LUC CHAY HAM - tuc la sau khi _load_ops da tra ve va da khoi phuc
#: sys.modules. Cai ban gia ben trong _load_ops thi den luc test goi ham no khong con o do
#: nua, va Python di nhap module that -> ModuleNotFoundError: frappe.
_ROUNDS = {"value": 0}
_SAVED_SF = {}


def setUpModule():
    import sys
    _SAVED_SF["mod"] = sys.modules.get("ecentric_workspace.platform.esign.signed_files")
    sf = types.ModuleType("ecentric_workspace.platform.esign.signed_files")
    sf.retrieval_rounds = lambda package_name: _ROUNDS["value"]
    sys.modules["ecentric_workspace.platform.esign.signed_files"] = sf


def tearDownModule():
    import sys
    if _SAVED_SF.get("mod") is None:
        sys.modules.pop("ecentric_workspace.platform.esign.signed_files", None)
    else:
        sys.modules["ecentric_workspace.platform.esign.signed_files"] = _SAVED_SF["mod"]


def _load_ops(dsr_rows=(), pkg_rows=(), event_counts=None, events=(), rounds=0):
    """Chay stuck_legs / unretrieved_bundles THAT voi may trang thai THAT."""
    state_mod = types.ModuleType("state")
    exec(compile(_STATE, "state.py", "exec"), state_mod.__dict__)

    esign_pkg = types.ModuleType("ecentric_workspace.platform.esign")
    esign_pkg.state = state_mod
    import sys
    saved = {k: sys.modules.get(k) for k in
             ("ecentric_workspace.platform.esign",
              "ecentric_workspace.platform.esign.state")}
    sys.modules["ecentric_workspace.platform.esign"] = esign_pkg
    sys.modules["ecentric_workspace.platform.esign.state"] = state_mod

    class _Frappe(object):
        class db(object):
            @staticmethod
            def count(dt, filters=None):
                return (event_counts or {}).get((filters or {}).get("event_type"), 0)

            @staticmethod
            def get_value(dt, name, fields=None, **kw):
                return None

        @staticmethod
        def get_all(dt, filters=None, fields=None, **kw):
            if dt == "EC Digital Signature Request":
                return [_D(r) for r in dsr_rows]
            if dt == "EC Digital Signature Package":
                return [_D(r) for r in pkg_rows]
            if dt == "EC Digital Signature Event":
                return [_D(e) for e in events]
            return []

    # ops.py co `import frappe` o dau file - dat vao globals thoi KHONG du, phai co trong
    # sys.modules luc exec.
    _ROUNDS["value"] = rounds        # xem setUpModule - ban gia song ngoai pham vi ham nay

    frappe_mod = types.ModuleType("frappe")
    frappe_mod.db = _Frappe.db
    frappe_mod.get_all = _Frappe.get_all
    saved["frappe"] = sys.modules.get("frappe")
    sys.modules["frappe"] = frappe_mod
    env = {}
    try:
        exec(compile(_OPS, "ops.py", "exec"), env)
        return env
    finally:
        for k, v in saved.items():           # KHONG de lai module gia cho bo test khac
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _leg(status, **kw):
    base = {"name": "DSR-1", "status": status, "actor_type": "Approval Level",
            "actor_user": "a@x.vn", "approver": None, "package": "PKG-1",
            "business_doctype": "EC Payment Request", "business_name": "PR-1",
            "request_attempt": 1, "modified": "2026-08-31 10:00:00"}
    base.update(kw)
    return base


class TestActionsComeFromTheStateMachine(unittest.TestCase):
    def test_manual_review_doi_soat_duoc(self):
        env = _load_ops(dsr_rows=[_leg("Manual Review")])
        row = env["stuck_legs"]()[0]
        self.assertIn("reconcile", row["actions"],
                      "Manual Review co canh sang Approval Completed - phai doi soat duoc")
        self.assertFalse(row["dead_end"])

    def test_permanent_failure_la_NGO_CUT(self):
        env = _load_ops(dsr_rows=[_leg("Permanent Failure")])
        row = env["stuck_legs"]()[0]
        self.assertEqual(row["actions"], [],
                         "trang thai nay khong co canh ra - khong duoc ve nut nao")
        self.assertTrue(row["dead_end"], "phai goi thang la ngo cut")

    def test_verification_mismatch_chi_sang_duoc_manual_review(self):
        env = _load_ops(dsr_rows=[_leg("Verification Mismatch")])
        row = env["stuck_legs"]()[0]
        # Canh ra duy nhat la Manual Review - khong phai mot hanh dong nguoi dung bam.
        self.assertEqual(row["actions"], [])

    def test_khong_go_tay_danh_sach_nut(self):
        # Neu may trang thai doi thi danh sach nut phai doi theo. Doc cay cu phap de chac
        # rang ham that su TRA CUU DSR_TRANSITIONS chu khong cam mot bang cung.
        body = _fn(_OPS, "stuck_legs")
        self.assertIn("DSR_TRANSITIONS", body,
                      "phai suy ra tu may trang thai, khong go tay")


class TestRetryableFailureIsNotAnAlarm(unittest.TestCase):
    def test_khong_liet_ke_retryable_failure(self):
        # poll_pending tu day no ve Queued cho toi khi het luot. Bao len day la bao dong gia.
        env = _load_ops()
        self.assertNotIn("Retryable Failure", env["_NEEDS_HUMAN"])

    def test_cac_trang_thai_dang_chay_cung_khong_liet_ke(self):
        env = _load_ops()
        for s in ("Queued", "Provider Accepted", "Verifying", "Prepared", "Signed"):
            self.assertNotIn(s, env["_NEEDS_HUMAN"], s + " dang chay, khong phai viec cua nguoi")


class TestWaitingIsNotBroken(unittest.TestCase):
    """Truoc day mot goi dang cho va mot goi da hong trong y het nhau."""

    def _pkg(self, **kw):
        base = {"name": "PKG-1", "business_doctype": "EC Payment Request",
                "business_name": "PR-1", "scts_document_id": "doc-1",
                # `status` co trong ban chieu tu 31/08: trang ops liet ke ca goi da
                # `Completed` ma chua tai xong PDF. Gia lap thieu truong nay tung lam
                # ba test o day no AttributeError chu khong phai loi cua nguon.
                "status": "Active",
                "modified": "2026-08-31 10:00:00"}
        base.update(kw)
        return base

    def test_chua_thu_lan_nao_va_khong_loi_la_DANG_CHO(self):
        env = _load_ops(pkg_rows=[self._pkg()], rounds=0)
        row = env["unretrieved_bundles"]()[0]
        self.assertTrue(row["waiting_on_provider"])
        self.assertFalse(row["stalled"])

    def test_thu_qua_nguong_la_DA_HONG(self):
        env = _load_ops(pkg_rows=[self._pkg()], rounds=30,
                        events=[{"error_summary": "SCTS document not found (HTTP 404)",
                                 "creation": "2026-08-31 09:00:00"}])
        row = env["unretrieved_bundles"]()[0]
        self.assertTrue(row["stalled"], "30 lan thu ma van goi la binh thuong thi vo nghia")
        self.assertFalse(row["waiting_on_provider"])
        self.assertIn("404", row["last_error"])

    def test_co_loi_thi_khong_con_la_dang_cho(self):
        env = _load_ops(pkg_rows=[self._pkg()], rounds=0,
                        events=[{"error_summary": "settings_missing",
                                 "creation": "2026-08-31 09:00:00"}])
        self.assertFalse(env["unretrieved_bundles"]()[0]["waiting_on_provider"])


class TestTheCronNowEscalates(unittest.TestCase):
    """Truoc day cron thu lai VO HAN, khong dem, khong bao ai."""

    def test_co_nguong_bao_dong(self):
        self.assertIn("RETRIEVAL_ALERT_AFTER", _TASKS)
        self.assertIn("_flag_stalled_retrieval", _TASKS)

    def test_bao_dong_DUNG_MOT_LAN(self):
        body = _fn(_TASKS, "_flag_stalled_retrieval")
        self.assertIn("SignedRetrievalStalled", body)
        self.assertIn("frappe.db.exists", body,
                      "keu moi 30 phut thi ba ngay la khong ai doc nua")

    def test_bao_dong_hong_khong_lam_gay_viec_chinh(self):
        body = _fn(_TASKS, "_flag_stalled_retrieval")
        self.assertIn("except Exception", body,
                      "tai file quan trong hon bao dong - bao dong hong khong duoc lam gay no")

    def test_loai_su_kien_da_khai_bao_trong_doctype(self):
        # Emit mot loai chua khai bao trong Select thi Frappe luu sai - loi chi lo ra khi chay.
        j = _read("approval_center", "doctype", "ec_digital_signature_event",
                  "ec_digital_signature_event.json")
        self.assertIn("SignedRetrievalStalled", j)


class TestTheInboxIsReadOnly(unittest.TestCase):
    def test_ops_khong_ghi_gi(self):
        tree = ast.parse(_OPS)
        writes = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                  and getattr(n.func, "attr", "") in
                  ("set_value", "delete_doc", "insert", "save", "emit")]
        self.assertEqual(writes, [], "trang nay chi la mot danh sach")

    def test_endpoint_yeu_cau_system_manager(self):
        body = _fn(_API, "ops_inbox")
        self.assertIn("assert_system_manager", body)


class TestTheScreenNeverResendsASigningCommand(unittest.TestCase):
    def test_khong_co_nut_nao_goi_approve_and_sign(self):
        for forbidden in ("approve_and_sign", "requester_submit_and_sign",
                          "multi_select_sequential_sign"):
            self.assertNotIn(forbidden, _UI,
                             "gui lai lenh ky tu day se tao chu ky THU HAI")

    def test_moi_hanh_dong_deu_hoi_truoc(self):
        self.assertIn("window.confirm", _UI)
        self.assertIn("ACTION_WHY", _UI,
                      "hop xac nhan phai noi ro no lam gi tren mot ho so chi tien")

    def test_ket_qua_khong_bao_xong_bua(self):
        body = _UI.split("function run(")[1][:2500]
        self.assertIn("Chưa xử lý được", body,
                      "nhieu endpoint tra ve dict trang thai chu khong nem loi - bao 'xong' "
                      "cho moi truong hop la dung cai loi im lang ma trang nay sinh ra de xoa")

    def test_lien_ket_phieu_khong_tro_vao_desk(self):
        # BO CHU THICH TRUOC KHI GREP. Chu thich cua chinh ban sua nay co nhac "/app/" de
        # giai thich vi sao khong duoc dung no - de nguyen thi phep kiem khop voi loi van
        # cua chinh no. Lan thu ba trong hai ngay dinh dung cai bay nay.
        import re
        code = re.sub(r"/\*[\s\S]*?\*/", " ", _UI)
        code = re.sub(r"(?m)^\s*//.*$", " ", code)
        self.assertNotIn("/app/", code, "nhac viec/lien ket phai tro vao trang duyet")


if __name__ == "__main__":
    unittest.main()
