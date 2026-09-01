# Copyright (c) 2026, eCentric and contributors
"""Ngung tai PDF da ky: NGUOI quyet dinh, he thong chi ghi lai.

Vong lap tai lai chay VO HAN. Khi tai lieu ben nha cung cap khong con (404), lan thu mot
nghin giong het lan thu nhat, nhung cron van goi mang moi 30 phut. 31/08: hai goi da quay
nhu vay lien tuc tu 23/08.

Bo test nay giu bon dieu, va ca bon deu la dieu de mat neu ai do "don dep" cho gon:

  1. BAT BUOC ly do. Mot chung tu da ky bi tuyen bo thoi khong lay ve nua ma khong ai biet
     vi sao la thu khong duoc phep ton tai trong ho so duyet chi.
  2. Chi System Manager. Va khong co duong nao TU DONG ngung - viec bo mot chung tu da ky
     khong phai viec mot cron tu quyet.
  3. Cron phai THAT SU bo qua goi da ngung. Neu khong, nut chi la trang tri: nguoi bam xong
     van thay he thong goi SCTS moi 30 phut.
  4. MO LAI DUOC. Neu ngung la vinh vien thi khong ai dam bam, va vong lap vo han cu chay.
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


_SF = _read("platform", "esign", "signed_files.py")
_TASKS = _read("platform", "esign", "tasks.py")
_OPS = _read("platform", "esign", "ops.py")
_API = _read("platform", "esign", "api.py")
_UI = _read("platform", "esign", "ui", "ops_page.html")


def _fn(src, name):
    """Than mot ham, lay tu CAY CU PHAP - khong cat theo do dai, khong grep chu."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError("khong tim thay ham %s" % name)


def _brace_body(src, marker):
    """Than mot ham JS, cat bang cach dem ngoac nhon - khong phu thuoc do dai."""
    i = src.index(marker)
    start = src.index("{", i)
    depth = 0
    for j in range(start, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    raise AssertionError("khong tim thay ngoac dong cho %r" % marker)


def _calls(src, name):
    """Ten cac ham duoc GOI ben trong mot ham - de khong khop nham chu trong chu thich."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return {getattr(c.func, "attr", None) or getattr(c.func, "id", None)
                    for c in ast.walk(node) if isinstance(c, ast.Call)}
    raise AssertionError("khong tim thay ham %s" % name)


class TestReasonIsMandatory(unittest.TestCase):
    def test_bat_buoc_ly_do(self):
        body = _fn(_SF, "abandon_retrieval")
        self.assertIn('if not (reason or "").strip():', body,
                      "thieu ly do van ngung duoc = mot chung tu da ky bien mat khong dau vet")
        self.assertIn("frappe.throw", body)

    def test_ly_do_duoc_ghi_lai(self):
        body = _fn(_SF, "abandon_retrieval")
        self.assertIn("retrieval_abandoned_reason", body,
                      "ly do phai nam lai tren goi, khong chi thoang qua man hinh")
        self.assertIn("log_action", body,
                      "phai ghi vao lich su phieu - noi nguoi duyet that su doc")

    def test_ghi_ca_ai_va_luc_nao(self):
        body = _fn(_SF, "abandon_retrieval")
        for f in ("retrieval_abandoned_by", "retrieval_abandoned_at"):
            self.assertIn(f, body, "thieu %s thi khong quy trach nhiem duoc" % f)


class TestOnlySystemManagerAndNeverAutomatic(unittest.TestCase):
    def test_chi_system_manager(self):
        self.assertIn("assert_system_manager", _fn(_SF, "abandon_retrieval"))
        self.assertIn("assert_system_manager", _fn(_SF, "resume_retrieval"))

    def test_cron_KHONG_tu_ngung(self):
        """Cai nay de mat thi he thong tu bo chung tu da ky - dung thu can canh nhat."""
        for fname in ("retrieve_signed_bundles", "_flag_stalled_retrieval"):
            called = _calls(_TASKS, fname)
            self.assertNotIn("abandon_retrieval", called,
                             "%s KHONG duoc tu ngung - viec bo mot chung tu da ky phai co "
                             "nguoi ky ten" % fname)

    def test_khong_xoa_gi(self):
        body = _fn(_SF, "abandon_retrieval")
        for forbidden in ("delete_doc", "db.delete", "remove_attach"):
            self.assertNotIn(forbidden, body,
                             "ngung thu lai la bat mot co, khong phai xoa du lieu")


class TestCronActuallySkips(unittest.TestCase):
    """Khong loc o cron thi nut chi la trang tri."""

    def test_bo_loc_cron_co_retrieval_abandoned(self):
        body = _fn(_TASKS, "retrieve_signed_bundles")
        self.assertIn('"retrieval_abandoned": 0', body,
                      "cron van quet goi da ngung = nguoi bam xong van thay he thong goi "
                      "SCTS moi 30 phut, tuc la nut khong lam gi ca")

    def test_trang_ops_van_HIEN_goi_da_ngung(self):
        body = _fn(_OPS, "unretrieved_bundles")
        self.assertIn("retrieval_abandoned", body,
                      "an goi da ngung di thi khong ai kiem lai duoc quyet dinh, cung khong "
                      "mo lai duoc")
        self.assertNotIn('"retrieval_abandoned": 0', body,
                         "trang KHONG duoc loc bo goi da ngung - do la viec cua cron")

    def test_goi_da_ngung_khong_dem_vao_bao_dong(self):
        body = _fn(_OPS, "summary")
        self.assertIn('not x["abandoned"]', body,
                      "mot con so bao dong khong bao gio ve 0 thi khong ai nhin nua")


class TestReversible(unittest.TestCase):
    def test_co_duong_mo_lai(self):
        names = [n.name for n in ast.parse(_SF).body if isinstance(n, ast.FunctionDef)]
        self.assertIn("resume_retrieval", names,
                      "ngung vinh vien thi khong ai dam bam, va vong lap vo han cu chay")

    def test_mo_lai_xoa_co(self):
        body = _fn(_SF, "resume_retrieval")
        self.assertIn('"retrieval_abandoned", 0', body)

    def test_hai_endpoint_deu_duoc_khai(self):
        for m in ("abandon_signed_retrieval", "resume_signed_retrieval"):
            self.assertIn("def %s(" % m, _API, "thieu endpoint %s" % m)
        i = _API.index("def abandon_signed_retrieval")
        self.assertIn("POST", _API[max(0, i - 200):i],
                      "hanh dong ghi phai la POST - GET tu dong rollback trong Frappe")


class TestScreenWiring(unittest.TestCase):
    def test_hai_nut_co_nhan_va_giai_thich(self):
        for act in ("abandon", "resume"):
            self.assertIn(act + ":", _UI, "thieu nhan cho nut %s" % act)

    def test_nut_ngung_hoi_ly_do_truoc(self):
        i = _UI.index('act === "abandon"')
        seg = _UI[i:i + 700]
        self.assertIn("window.prompt", seg, "phai hoi ly do ngay tren man hinh")
        self.assertIn("Bắt buộc nêu lý do", seg)

    def test_goi_da_ngung_trong_KHAC_goi_dang_treo(self):
        # Cat than ham theo DAU NGOAC, khong theo do dai co dinh: them mot khoi vao dau ham
        # la doan can kiem bi day ra ngoai cua so va test do trong khi nguon van dung. Lop
        # loi nay da gap 3 lan - lan nay o test_abandon_retrieval (01/09).
        seg = _brace_body(_UI, "function bundleRow")
        self.assertIn("r.abandoned", seg,
                      "truoc day moi thu trong y het nhau - do chinh la loi trang nay sinh "
                      "ra de xoa bo")
        self.assertIn("abandoned_reason", seg, "phai hien ly do va ai quyet dinh")


if __name__ == "__main__":
    unittest.main()
