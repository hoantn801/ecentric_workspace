# Copyright (c) 2026, eCentric and contributors
"""Mot chan ky DA TUNG gui lenh ky thi KHONG BAO GIO duoc tu gui lai.

Lenh bulk-process cua nha cung cap KHONG idempotent: gui lan hai co the dat chu ky THU HAI
len cung mot tai lieu. Duong nguy hiem co that trong may trang thai:

    Queued -> (gui) -> Provider Accepted -> loi poll thoang qua -> Retryable Failure
           -> poll_pending dua ve Queued -> nhanh gui chay LAN HAI

POLL-FIRST chi cuu duoc khi chu ky lan mot da kip xuat hien ben nha cung cap; con cua so
giua "da gui" va "chu ky hien ra" thi khong ai cuu duoc ngoai cai chot nay.

Chot phai dua tren `may_have_sent` - tuc accepted_at HOAC bulk_job_transaction_id HOAC
request_attempt > 1 - chu KHONG chi rieng `bulk_job_transaction_id`. Ly do: mot HTTP 200
khong kem transaction id (portal khong tra) van dat `accepted_at`, nen chot chi-nhin-txn de
lot dung truong hop mo ho nhat (BOT vong 3, 01/09).

Phep kiem doc CAY CU PHAP cua nhanh `if dsr.status == "Queued"`, khong grep chu - chu thich
ngay tren no co nhac ca hai ten truong.
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
_SRC = io.open(os.path.join(_ROOT, "platform", "esign", "tasks.py"),
               encoding="utf-8").read()


def _state_module():
    """Nap `state.py` that su (khong import frappe nen nap thang duoc).

    `exec(compile(...))` chu khong phai `spec_from_file_location`: loader theo duong dan
    dung lai `__pycache__`, va bo nho dem do chi bi coi la cu khi mtime HOAC kich thuoc doi -
    nen mot phep dot bien DI CHUYEN khoi lenh se duoc cham tren ban .pyc cu va bao xanh gia.
    Da mat mot vong chan doan vi dung cai bay nay hom 01/09.
    """
    import types
    path = os.path.join(_ROOT, "platform", "esign", "state.py")
    mod = types.ModuleType("esign_state_under_test")
    exec(compile(io.open(path, encoding="utf-8").read(), path, "exec"),  # noqa: S102
         mod.__dict__)
    return mod
_TREE = ast.parse(_SRC)


def _func(name):
    for node in ast.walk(_TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("khong tim thay ham %s" % name)


def _names(node):
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def _queued_branch():
    """Nhanh `if dsr.status == "Queued":` CHUA LENH GUI.

    Trong process_signing_request co HAI nhanh Queued: mot cong kiem rang buoc nguoi ky
    (assert_outbound_binding) chay som, va mot nhanh gui lenh ky. Lay nham cai dau thi phep
    kiem bao "chot bien mat" trong khi chot van con nguyen - dung lop loi do luong da gap
    nhieu lan. Phan biet bang NOI DUNG: nhanh gui la nhanh co goi `_PROVIDER_TRANSITION`
    hoac `next_handler`.
    """
    fn = _func("process_signing_request")
    found = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        t = node.test
        if (isinstance(t, ast.Compare) and isinstance(t.left, ast.Attribute)
                and t.left.attr == "status"
                and any(isinstance(c, ast.Constant) and c.value == "Queued"
                        for c in t.comparators)):
            found.append(node)
    if not found:
        raise AssertionError("khong tim thay nhanh Queued nao - cach doc AST da lac hau")
    for node in found:
        names = _names(node)
        if "_PROVIDER_TRANSITION" in names or "next_handler" in names:
            return node
    raise AssertionError(
        "tim thay %d nhanh Queued nhung khong nhanh nao chua lenh gui (_PROVIDER_TRANSITION "
        "/ next_handler) - hoac cach gui da doi ten, hoac lenh gui da bi go" % len(found))


def _guard_if():
    """Cau `if ...:` DAU TIEN ben trong nhanh Queued - chinh la chot chong gui lan hai."""
    branch = _queued_branch()
    for stmt in branch.body:
        if isinstance(stmt, ast.If):
            return stmt
    raise AssertionError("nhanh Queued KHONG CON cau if nao - chot chong gui lan hai da "
                         "bien mat, day la lo hong chu ky doi")


class TestSecondSubmitIsLatched(unittest.TestCase):
    def test_co_chot_truoc_khi_gui(self):
        guard = _guard_if()
        self.assertTrue(guard.body, "chot rong = khong chot gi")

    def test_chot_dung_tin_hieu_DAY_DU(self):
        """`may_have_sent` gop ca ba dau hieu; chi nhin txn la lot ca HTTP-200-khong-txn."""
        cond = _names(_guard_if().test)
        self.assertIn("may_have_sent", cond,
                      "chot phai dung `may_have_sent` (accepted_at HOAC txn HOAC "
                      "request_attempt>1). Chi nhin bulk_job_transaction_id thi mot HTTP 200 "
                      "khong kem txn van lot -> co the dat chu ky THU HAI.")

    def test_may_have_sent_van_gom_du_ba_dau_hieu(self):
        """Neu ai do lam nghe `may_have_sent` thi chot o tren rong ruot ma van 'dung ten'.

        Phep chan da chuyen ve `state.may_have_sent` (02/09) de trang ops dung CHUNG mot
        dinh nghia voi worker - hai ban sao se lech, va lech o day nghia la mot cai nut hua
        gui lai roi lang le khong gui. Nen kiem HANH VI cua ham do, khong kiem chuoi.
        """
        mod = _state_module()
        self.assertFalse(mod.may_have_sent({"status": "Queued", "request_attempt": 1}),
                         "chan ky chua gui gi ma da bi coi la co the da gui")
        for dau_hieu in ({"accepted_at": "2026-08-28 23:54:00"},
                         {"bulk_job_transaction_id": "abc"},
                         {"request_attempt": 2}):
            row = {"status": "Queued", "request_attempt": 1}
            row.update(dau_hieu)
            self.assertTrue(mod.may_have_sent(row),
                            "may_have_sent phai xet %s - bo qua no thi mot lan gui thanh "
                            "cong van lot va co the dat chu ky THU HAI" % list(dau_hieu))

    def test_du_doan_phai_tinh_ca_buoc_tang_ma_retry_gay_ra(self):
        """Nhan nut phai noi dung viec SE xay ra, khong phai viec dang thay.

        `retry_signature_request` tang `request_attempt` ROI moi xep job. Nen mot chan ky
        dang o attempt 1 va sach tron - nhin vao thi tuong "chua gui gi, bam la gui" - thuc
        te khi worker chay se thay attempt 2, chot dong, va no chuyen sang Manual Review chu
        khong gui. Neu du doan quen mo phong cai +1 do thi trang lai in "Gui lai" va lai hua
        dieu ma chot tu choi: dung cai sai dang duoc sua, chi doi cho.
        """
        mod = _state_module()
        sach = {"status": "Queued", "request_attempt": 1}
        self.assertTrue(mod.may_have_sent(dict(sach, request_attempt=2)),
                        "tien de: attempt 2 la co the da gui")
        self.assertFalse(
            mod.retry_will_resend(sach),
            "chan ky nay nhin thi sach, nhung bam retry se thanh attempt 2 -> chot dong -> "
            "Manual Review. Du doan phai tra False de nhan la 'Doi soat', khong phai 'Gui lai'")

    def test_du_doan_va_chot_khong_bao_gio_mau_thuan(self):
        """Quet moi to hop dau hieu: da hua gui lai thi chot phai that su cho gui."""
        mod = _state_module()
        for status in ("Queued", "Provider Accepted", "Verifying", "Manual Review"):
            for attempt in (1, 2, 5):
                for extra in ({}, {"accepted_at": "2026-08-28 23:54:00"},
                              {"bulk_job_transaction_id": "abc"}):
                    row = dict({"status": status, "request_attempt": attempt}, **extra)
                    if mod.retry_will_resend(row):
                        sau = dict(row, request_attempt=attempt + 1)
                        self.assertFalse(
                            mod.may_have_sent(sau),
                            "hua 'Gui lai' cho %s nhung chot se chan lai" % row)

    def test_worker_va_trang_ops_dung_CHUNG_dinh_nghia(self):
        """Hai ban sao cua luat nay se lech, va lech = nut hua mot dang lam mot neo."""
        import io as _io
        import os as _os
        tasks = _io.open(_os.path.join(_ROOT, "platform", "esign", "tasks.py"),
                         encoding="utf-8").read()
        ops = _io.open(_os.path.join(_ROOT, "platform", "esign", "ops.py"),
                       encoding="utf-8").read()
        self.assertIn("sm.may_have_sent(dsr)", tasks, "worker tu tinh lai phep chan")
        self.assertIn("sm.retry_will_resend(r)", ops,
                      "trang ops phai hoi cung mot module, va phai hoi ban DU DOAN "
                      "(retry lam tang request_attempt truoc khi job chay)")

    def test_chot_KHONG_gui_ma_day_sang_nguoi(self):
        """Fail-closed: gap truong hop mo ho thi dung lai cho NGUOI doi soat, khong doan."""
        guard = _guard_if()
        called = {getattr(c.func, "attr", None) or getattr(c.func, "id", None)
                  for c in ast.walk(guard) if isinstance(c, ast.Call)}
        self.assertIn("set_dsr_status", called, "phai chuyen trang thai, khong im lang")
        consts = {c.value for c in ast.walk(guard)
                  if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        self.assertIn("Manual Review", consts,
                      "truong hop mo ho phai sang Manual Review cho nguoi 'Doi soat'")
        for forbidden in ("bulk_process", "transition", "create_document"):
            self.assertNotIn(forbidden, called,
                             "chot KHONG duoc goi lenh nao toi nha cung cap: %s" % forbidden)

    def test_chot_dung_TRUOC_moi_lenh_gui(self):
        """Chot nam sau lenh gui thi vo nghia."""
        branch = _queued_branch()
        guard = _guard_if()
        idx = branch.body.index(guard)
        self.assertEqual(idx, 0,
                         "chot phai la cau LENH DAU TIEN trong nhanh Queued (hien o vi tri "
                         "%d) - dat sau bat ky lenh gui nao la da muon" % idx)


if __name__ == "__main__":
    unittest.main()
