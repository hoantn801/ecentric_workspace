# Copyright (c) 2026, eCentric and contributors
"""Lenh ky khong duoc xep chung hang voi cron, va nhip doi soat phai theo so do that.

03/09 00:00, EC-DSR-2026-00033: nguoi duyet bam xong, chan ky nam trong hang 49,7 giay
truoc khi worker cham toi - worker `default` dang ban chay cron lay PDF. Gui + ky + xac nhan
sau do chi 12 giay. Chan lien truoc khong vuong cron: 0,7 giay.

Va nhip doi soat FAST_VERIFY_DELAYS bat dau bang 8s - so do thoi con di duong pool. Tu khi
di targeted, SCTS ky trong 2-5 giay; lan hoi dau +0,8s luon truot, roi phai doi 8s nua.
"""
import io
import os
import re
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


def _src(rel):
    return io.open(os.path.join(_ROOT, "platform", "esign", rel), encoding="utf-8").read()


def _code_only(s):
    s = re.sub(r'"""[\s\S]*?"""', "", s)
    return re.sub(r"(?m)^\s*#.*$", "", s)


class TestLenhKyDiHangRieng(unittest.TestCase):
    def _enqueues_cua_process_signing_request(self, src):
        """Moi doan `frappe.enqueue(` ma doi so dau la process_signing_request."""
        out = []
        for m in re.finditer(r"frappe\.enqueue\(\s*\n?\s*\"([^\"]+)\"([\s\S]*?)\)", _code_only(src)):
            if m.group(1).endswith("tasks.process_signing_request"):
                out.append(m.group(2))
        return out

    def test_bon_noi_enqueue_deu_dung_SIGNING_QUEUE(self):
        tong = 0
        for f in ("service.py", "requester.py"):
            for args in self._enqueues_cua_process_signing_request(_src(f)):
                tong += 1
                self.assertIn("queue=sm.SIGNING_QUEUE", args,
                              "%s: lenh ky enqueue khong qua sm.SIGNING_QUEUE -> lai chung "
                              "hang voi cron, lai cho 50 giay" % f)
                self.assertNotIn('queue="default"', args, f)
        self.assertEqual(tong, 4, "mong 4 noi enqueue lenh ky (service x3, requester x1); "
                                  "thay %d - co noi nao doi ten/bo qua?" % tong)

    def test_SIGNING_QUEUE_khong_phai_default(self):
        st = _src("state.py")
        m = re.search(r'^SIGNING_QUEUE\s*=\s*"(\w+)"', st, re.M)
        self.assertIsNotNone(m, "state.py thieu SIGNING_QUEUE")
        self.assertNotEqual(m.group(1), "default",
                            "default la hang cua cron lay PDF - dat lenh ky vao do la quay ve "
                            "cho 50 giay")

    def test_cron_lay_PDF_van_o_default(self):
        """Doi xung: khong duoc 'tien tay' keo cron sang short - no se chan lenh ky y het."""
        t = _code_only(_src("tasks.py"))
        m = re.search(r"retrieve_and_store_for_package\"[\s\S]*?queue=\"(\w+)\"", t)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "default")


class TestNhipDoiSoatTheoSoDoThat(unittest.TestCase):
    def _delays(self):
        m = re.search(r"^FAST_VERIFY_DELAYS\s*=\s*\(([^)]*)\)", _src("tasks.py"), re.M)
        self.assertIsNotNone(m)
        return [int(x) for x in re.findall(r"\d+", m.group(1))]

    def test_lan_hoi_thu_hai_khong_qua_3_giay(self):
        d = self._delays()
        self.assertLessEqual(d[0], 3,
                             "SCTS ky trong 2-5s; doi %ds truoc khi hoi lai la nguoi dung nhin "
                             "man hinh thua %ds" % (d[0], d[0] - 3))

    def test_tang_dan(self):
        d = self._delays()
        self.assertEqual(d, sorted(d), "nhip phai gian dan, khong hoi don dap")

    def test_khong_giu_worker_qua_30_giay(self):
        """fast_verify NGU trong worker `short` - cung hang voi lenh ky tu 03/09. Giu lau la
        chan chinh lenh ky ke tiep."""
        self.assertLessEqual(sum(self._delays()), 30)


if __name__ == "__main__":
    unittest.main()
