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


_SRC = io.open(os.path.join(_root(), "platform", "esign", "tasks.py"),
               encoding="utf-8").read()
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
        """Neu ai do lam nghe `may_have_sent` thi chot o tren rong ruot ma van 'dung ten'."""
        fn = _func("process_signing_request")
        assign = None
        for node in ast.walk(fn):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == "may_have_sent"):
                assign = node
        self.assertIsNotNone(assign, "khong tim thay noi gan `may_have_sent`")
        # Ten truong o day di qua `dsr.get("...")` nen la HANG CHUOI, khong phai thuoc tinh -
        # gom ca hai, neu khong phep kiem se do trong khi nguon hoan toan dung.
        used = _names(assign.value) | {c.value for c in ast.walk(assign.value)
                                       if isinstance(c, ast.Constant)
                                       and isinstance(c.value, str)}
        for f in ("accepted_at", "bulk_job_transaction_id", "request_attempt"):
            self.assertIn(f, used, "may_have_sent phai xet %s" % f)

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
