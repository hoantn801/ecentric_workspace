# Copyright (c) 2026, eCentric and contributors
"""06/10/2026: quan ly bam Duyet buoc 1 don hieu/hi/thai san bi 403 "Ban can dang nhap lai"
(sang.bui, HR-LAP-2026-00085). Nguyen nhan: doi leave_approver TRUOC save -> HRMS
share_doc_with_approver goi frappe.share.remove chia se cua nguoi cu bang quyen nguoi bam.
Sua (ec-lv-lead-share-v1): save truoc, ghi nguoi duyet tiep bang db.set_value sau.
Kiem tren nguon fixtures/server_script.json - KHONG can bench."""
import ast
import io
import json
import os
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _decide():
    with io.open(os.path.join(APP, "fixtures", "server_script.json"), encoding="utf-8") as fh:
        return [r for r in json.load(fh) if r["name"] == "ec_hr_leave_decide"][0]["script"]


def _lead_block(src):
    i = src.index("if stage == 'lead':")
    return src[i:src.index("elif stage == 'hr':", i)]


class LeadShare(unittest.TestCase):
    def setUp(self):
        self.src = _decide()
        self.lead = _lead_block(self.src)

    def test_script_hop_le_va_co_marker(self):
        ast.parse(self.src)
        self.assertIn("ec-lv-lead-share-v1", self.src)

    def test_khong_gan_leave_approver_tren_doc_truoc_khi_save(self):
        self.assertNotIn("la.leave_approver = nxt", self.src)
        self.assertNotIn("la.leave_approver=nxt", self.src)

    def test_ghi_nguoi_duyet_tiep_sau_khi_save(self):
        i_save = self.lead.index("la.save(ignore_permissions=True)")
        i_set = self.lead.index("frappe.db.set_value('Leave Application', nm, 'leave_approver', nxt)")
        self.assertLess(i_save, i_set)
        self.assertLess(self.lead.index("la.ec_approval_stage = 'hr'"), i_save)

    def test_buoc_hr_va_ceo_khong_doi_nguoi_duyet(self):
        rest = self.src[self.src.index("elif stage == 'hr':"):]
        self.assertNotIn("leave_approver =", rest.split("for ar in att_rows:")[0])

    def test_todo_buoc_cuoi_doc_lai_don_tu_db(self):
        # la2 doc lai sau set_value -> ToDo giao cho nguoi duyet moi (HR), khong phai quan ly
        self.assertIn("la2 = frappe.get_doc('Leave Application', nm)", self.src)
        self.assertIn("nxt_user = la2.leave_approver or CEO_USER", self.src)


if __name__ == "__main__":
    unittest.main()
