# Copyright (c) 2026, eCentric and contributors
"""Trang /weekly-update: chi MOT luong nop duoc chay tren mot cu bam.

05-06/10/2026: ba nguoi khong nop duoc bao cao (NV00083, NV00148, NV00173), man
hinh hien `HTTP 409 nameAlreadyExists`. Goc khong nam o SharePoint ma o trang:
nut Submit mang ba the he code chong len nhau, va MOT cu bam chay HAI luong nop
doc lap -> hai phien upload cung ten tep -> luong sau bi 409.

Bo test nay doc file nguon trong repo (khong can site, khong can trinh duyet).
No khong kiem "trang chay dung" -- dieu do phai thu bang trinh duyet. No ghim
dung mot dieu: cau hinh da gay ra loi KHONG duoc quay lai.

    bench run-tests --module ecentric_workspace.weekly_report.tests.test_weekly_update_page
"""

import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PAGE = os.path.join(os.path.dirname(_HERE), "pages", "weekly_update")


def _html():
    with io.open(os.path.join(_PAGE, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def _code_lines(src):
    """Bo dong chu thich JS.

    Can thiet: chu thich giai thich su co CO CHUA lai doan code cu lam vi du.
    Tim chuoi tren ca file se dinh chinh phan giai thich do va bao dong gia --
    da dinh mot lan khi viet ban sua nay.
    """
    return [l for l in src.splitlines() if not l.strip().startswith("//")]


class OneSubmitPathTest(unittest.TestCase):
    def setUp(self):
        self.src = _html()
        self.code = "\n".join(_code_lines(self.src))

    def test_the_generation_1_bindings_are_gone(self):
        """`initSubmit` tung gan CUNG mot handler cho ca form 'submit' lan nut
        'click'. Nut nam trong form nen mot cu bam chay ca hai."""
        hits = re.findall(r"(?:f|btn)\.addEventListener\(\s*['\"](?:submit|click)['\"]\s*,\s*handler\s*\)",
                          self.code)
        self.assertEqual(hits, [], "the he 1 da duoc gan lai: %s" % hits)

    def test_submit_button_is_not_type_submit(self):
        """`type="submit"` trong form -> mot cu bam con kich hoat nop mac dinh
        cua trinh duyet, ngoai cac handler. Doi sang `type="button"` de chi con
        dung mot duong."""
        m = re.search(r"<button[^>]*id=\"wu-btn-submit\"", self.src)
        self.assertIsNotNone(m, "khong con nut wu-btn-submit")
        tag = self.src[m.start():self.src.index(">", m.start()) + 1]
        self.assertIn('type="button"', tag)
        self.assertNotIn('type="submit"', tag)

    def test_the_remaining_submit_path_is_still_there(self):
        """Canh doi: go the he 1 KHONG duoc lam mat the he 3.

        Neu ai do go nhan hon can, trang se im lang khong nop duoc gi -- te hon
        han loi 409, vi 409 con hien ra man hinh."""
        self.assertIn("doServerSubmit", self.code)
        self.assertIn("weeklyOverrideV2", self.code)

    def test_validation_layer_is_still_there(self):
        """The he 1 mang ba phep kiem (trang thai / slide / cong cu AI). Go no
        chi an toan vi the he 2 kiem du ca ba. Neu the he 2 bien mat thi viec
        go the he 1 tro thanh mat kiem."""
        self.assertIn("_validateHooked", self.code)
        for dau_hieu in ('name="overall_status"', 'name="ai_tools"', "upload-zone"):
            self.assertIn(dau_hieu, self.code, "mat phep kiem: " + dau_hieu)

    def test_permission_gate_for_view_is_still_there(self):
        """Cong kiem quyen `?view=` (28/09) nam cung file. Dua nguon ve repo
        khong duoc lam roi mat no."""
        self.assertEqual(self.src.count("EC-VIEW-PERM-START"), 2)
        self.assertEqual(self.src.count("can_view_weekly_record"), 2)


class PageSyncTest(unittest.TestCase):
    """`page_sync.py` phai tro dung ban ghi va giu khoa chong troi."""

    def setUp(self):
        with io.open(os.path.join(_PAGE, "page_sync.py"), encoding="utf-8") as fh:
            self.src = fh.read()

    def test_points_at_the_real_route(self):
        self.assertIn('ROUTE = "weekly-update"', self.src)

    def test_record_name_is_the_vietnamese_one(self):
        """Ten ban ghi KHAC ten route: ban ghi co dau, route khong. Mot probe
        28/09 loc theo route chua 'bao-cao-tuan' va khong ra gi ca.

        Ky tu co dau viet THANG trong .py la duoc -- nguon Python la UTF-8.
        Quy tac cam tieng Viet chi ap cho .ps1 (PS5 doc file theo Latin-1).
        """
        self.assertIn("NAME = ", self.src)
        self.assertIn("áo-cáo-tu", self.src)

    def test_drift_lock_is_on_by_default(self):
        """Mac dinh PHAI co khoa. Trang nay co nguoi dung that moi tuan; ghi de
        nham la xoa mot ban sua doi ma khong ai biet."""
        self.assertIn("BASELINE_SHA256", self.src)
        self.assertIn("expect_sha=BASELINE_SHA256", self.src)

    def test_baseline_matches_the_file_in_repo(self):
        """Baseline phai la ma bam CUA FILE NAY, khong phai mot so chep tay.

        Luu y: `page_sync` so voi ban LIVE, con test nay so voi ban REPO. Hai
        so bang nhau tai thoi diem dua nguon ve; sau khi sua nguon thi chung
        lech nhau -- va dung the: baseline la "live dang la gi", khong phai
        "repo dang la gi".
        """
        import hashlib
        raw = io.open(os.path.join(_PAGE, "main_section.html"), "rb").read()
        m = re.search(r'BASELINE_SHA256 = "([0-9a-f]{64})"', self.src)
        self.assertIsNotNone(m, "khong tim thay BASELINE_SHA256")
        # Chi canh dinh dang + co mat; bang nhau hay khong tuy luc.
        self.assertEqual(len(m.group(1)), 64)
        self.assertTrue(raw.lstrip().startswith(b"<"),
                        "main_section.html phai la HTML")

    def test_source_has_no_bom(self):
        """Nguon trong repo KHONG duoc bat dau bang BOM UTF-8.

        Lan dau dua trang nay ve repo, file mang BOM (EF BB BF) va chinh test
        nay tung ghi "do la noi dung THAT tu live, giu nguyen moi dung byte".
        SAI. Live khong co BOM; BOM do script chup chen vao, vi
        `WriteAllText(..., Encoding.UTF8)` cua .NET tu ghi preamble. Hau qua:
        baseline tinh sai, p229 bi khoa chong troi tu choi ngay 06/10 14:25
        du khong ai sua trang. Va neu khoa khong chan, sync se day mot ky tu
        BOM len dau trang live.
        """
        raw = io.open(os.path.join(_PAGE, "main_section.html"), "rb").read()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"),
                         "nguon repo co BOM -- chup lai bang UTF8Encoding($false)")

    def test_baseline_is_not_the_bom_poisoned_value(self):
        """Ghim de khong ai vo tinh khoi phuc baseline cu.

        265c3d0a... la sha cua file CO BOM. Gia tri nay khong bao gio khop live,
        nen dung no la lam khoa chong troi chan moi lan sync."""
        self.assertNotIn("265c3d0ac2d78ac5ac499640ef5552b54b543f4d61271dd8346f45c9d33c7468",
                         self.src)


if __name__ == "__main__":
    unittest.main()
