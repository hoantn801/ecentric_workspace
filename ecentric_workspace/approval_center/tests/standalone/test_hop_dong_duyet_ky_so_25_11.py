# Copyright (c) 2026, eCentric and contributors
"""25/11/2026 - chi Lien (EC-CTR-2026-00135, KOL WF09) bam "Duyet & Ky" o form 27 nhung trang goi approve
thuong -> engine chan "[no_completion_marker]". Cap duyet di qua cong ky so phai goi API dung chung cua nen
tang (platform.esign.api.approve_and_sign), giong form DNTT (pr_approve_and_sign).
Chay: python -m unittest ecentric_workspace.approval_center.tests.standalone.test_hop_dong_duyet_ky_so_25_11
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from test_hop_dong_ky_so_23_11 import _read  # noqa: E402


class DuyetKySo(unittest.TestCase):
    def setUp(self):
        self.page = _read("features/contract_review/ui/main_section.html")

    def test_nut_doi_nhan_khi_can_ky(self):
        self.assertIn("(cap.requires_signature?'Duyệt &amp; Ký':'Duyệt')", self.page)

    def test_bam_duyet_cap_ky_so_di_api_nen_tang(self):
        self.assertIn('if(a==="approve") return ((det.capabilities||{}).requires_signature?'
                      'doApproveAndSign(name,det):doApprove(name,det));', self.page)
        i = self.page.index("function doApproveAndSign(")
        seg = self.page[i:i + 1600]
        self.assertIn('callEsign("approve_and_sign",{business_doctype:"EC Contract Review Request",'
                      'business_name:name,comment:cmt})', seg)
        self.assertNotIn('call("approve"', seg)
        self.assertIn("extractServerMsg(e)", seg)

    def test_callesign_dung_namespace_nen_tang_post(self):
        i = self.page.index("function callEsign(")
        seg = self.page[i:i + 400]
        self.assertIn('"ecentric_workspace.platform.esign.api."+method', seg)
        self.assertIn('type:"POST"', seg)

    def test_duyet_thuong_van_giu(self):
        i = self.page.index("function doApprove(")
        self.assertIn('call("approve",{name:name,comment:cmt})', self.page[i:i + 600])

    def test_tieu_de_hop_thoai_khong_escape_hai_lan(self):
        self.assertIn('modal("Duyệt & Ký", summaryRows(det)', self.page)


if __name__ == "__main__":
    unittest.main()
