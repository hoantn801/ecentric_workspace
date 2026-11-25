# Copyright (c) 2026, eCentric and contributors
"""25/11/2026 - sau khi bam "Duyet & Ky", cong CMC mat ~30s moi xac nhan; trang van hien nut nhu chua bam,
Ctrl+Shift+R cung vay (chi Lien, EC-CTR-2026-00135). PO: tai lai trang KHONG duoc hien lai nut.
  * server: esign_gate.in_flight hoi ban ghi yeu cau ky cua nen tang (service.in_flight_leg);
    detail_extra tra extra.esign_wait -> co ngay trong lan tai dau;
  * trang: an Duyet/Tra lai/Tu choi TRUOC khi ve, o "Viec cua ban" chuyen sang dang cho, tu tai lai.
Chay: python -m unittest ecentric_workspace.approval_center.tests.standalone.test_hop_dong_cho_cong_25_11
"""
import importlib
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from test_contract_kol_qc_15_11 import _fresh  # noqa: E402
from test_hop_dong_ky_so_23_11 import P, _read  # noqa: E402

SVC = "ecentric_workspace.platform.esign.service"


class Gate(unittest.TestCase):
    def _gate(self, leg=None, boom=False):
        _fresh("lien@ec")
        self.calls = []
        svc = types.ModuleType(SVC)

        def in_flight_leg(ar, level, user):
            self.calls.append((ar, level, user))
            if boom:
                raise RuntimeError("x")
            return leg
        svc.in_flight_leg = in_flight_leg
        keys = ("ecentric_workspace.platform", "ecentric_workspace.platform.esign", SVC, P + "esign_gate")
        saved = {k: sys.modules.get(k) for k in keys}
        saved_attr = getattr(sys.modules.get("ecentric_workspace.platform.esign"), "service", None)

        def restore():
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
            pkg = sys.modules.get("ecentric_workspace.platform.esign")
            if pkg is not None and saved_attr is not None:
                pkg.service = saved_attr
        self.addCleanup(restore)
        for name in ("ecentric_workspace.platform", "ecentric_workspace.platform.esign"):
            sys.modules.setdefault(name, types.ModuleType(name))
        sys.modules[SVC] = svc
        sys.modules["ecentric_workspace.platform.esign"].service = svc
        sys.modules.pop(P + "esign_gate", None)
        return importlib.import_module(P + "esign_gate")

    REQ = {"name": "EC-APR-1", "approval_status": "Pending", "current_level": 2}

    def test_dang_cho_cong(self):
        g = self._gate({"name": "DSR-1", "status": "Accepted", "accepted_at": "2026-11-25 11:03:23"})
        w = g.in_flight(dict(self.REQ), "lien@ec")
        self.assertEqual(self.calls, [("EC-APR-1", 2, "lien@ec")])
        self.assertEqual(w, {"status": "Accepted", "accepted_at": "2026-11-25 11:03:23", "manual": False})

    def test_manual_review(self):
        g = self._gate({"name": "DSR-1", "status": "Manual Review", "accepted_at": None})
        self.assertTrue(g.in_flight(dict(self.REQ), "lien@ec")["manual"])

    def test_khong_co_chan_ky(self):
        self.assertIsNone(self._gate(None).in_flight(dict(self.REQ), "lien@ec"))

    def test_phieu_khong_pending_khong_hoi(self):
        g = self._gate({"status": "Accepted"})
        self.assertIsNone(g.in_flight(dict(self.REQ, approval_status="Approved"), "lien@ec"))
        self.assertIsNone(g.in_flight(None, "lien@ec"))
        self.assertEqual(self.calls, [])

    def test_loi_nen_tang_khong_lam_vo_trang(self):
        self.assertIsNone(self._gate(boom=True).in_flight(dict(self.REQ), "lien@ec"))


class Detail(unittest.TestCase):
    def test_detail_extra_gop_esign_wait(self):
        src = _read("features/contract_review/application/kol_service.py")
        i = src.index("def detail_extra(")
        seg = src[i:src.index("def _detail_extra(")]
        self.assertIn("esign_gate.in_flight(request, frappe.session.user)", seg)
        self.assertIn('out["esign_wait"] = wait', seg)


class DetailChay(unittest.TestCase):
    def test_hop_dong_thuong_co_esign_wait(self):
        _fresh("lien@ec")
        g = types.ModuleType(P + "esign_gate")
        g.in_flight = lambda req, user: {"status": "Accepted", "accepted_at": "", "manual": False} \
            if user == "lien@ec" else None
        old = sys.modules.get(P + "esign_gate")
        sys.modules[P + "esign_gate"] = g
        self.addCleanup(lambda: sys.modules.__setitem__(P + "esign_gate", old) if old else sys.modules.pop(P + "esign_gate", None))
        sys.modules.pop(P + "kol_service", None)
        svc = importlib.import_module(P + "kol_service")
        out = svc.detail_extra({"contract_type": "Purchase / Mua vào (EC)"}, {"name": "EC-APR-1"})
        self.assertEqual(out, {"esign_wait": {"status": "Accepted", "accepted_at": "", "manual": False}})
        g.in_flight = lambda req, user: None
        self.assertEqual(svc.detail_extra({"contract_type": "Purchase / Mua vào (EC)"}, {"name": "EC-APR-1"}), {})


class Trang(unittest.TestCase):
    def setUp(self):
        self.page = _read("features/contract_review/ui/main_section.html")

    def test_an_nut_truoc_khi_ve(self):
        self.assertIn("function drawDetail(b,det){ applyEsignWait(det); scheduleEsignWait(det); state.detail=det;",
                      self.page)
        i = self.page.index("function applyEsignWait(")
        seg = self.page[i:i + 700]
        for k in ("c.can_approve=false", "c.can_reject=false", "c.can_request_information=false"):
            self.assertIn(k, seg)
        self.assertIn('kind:"watch"', seg)

    def test_khu_hanh_dong_bao_dang_cho(self):
        i = self.page.index("function actionPanelHTML(det)")
        self.assertIn("if(ew) return esignWaitHTML(ew);", self.page[i:i + 300])
        self.assertIn("đang chờ CMC xác nhận", self.page)

    def test_tu_tai_lai_va_cham_lai_khi_lau(self):
        i = self.page.index("function scheduleEsignWait(")
        seg = self.page[i:i + 1200]
        self.assertIn("refreshDetail()", seg)
        self.assertIn("age>180000", seg)
        self.assertIn("30000:5000", seg)
        self.assertIn("clearTimeout(state._esignTimer)", seg)


if __name__ == "__main__":
    unittest.main()
