# Copyright (c) 2026, eCentric and contributors
"""Khoa chong troi phai khop nguon o MOI form, khong chi 5 form (10/09).

`test_fulfillment_reassign.TestDriftLock` da kiem viec nay tu 08/09 - nhung tren mot danh
sach CUNG gom dung 5 form (asset/data/document/resignation/system), la nhom cua dot reassign
luc do. Thuc te 25/27 form co `BASELINE_SHA256`. Nghia la 20 form khac sua giao dien ma quen
bump thi KHONG CO AI BAO.

Hau qua neu lot: `page_sync` tra `action=refused`, HTML tren production giu nguyen ban cu,
va patch resync (von tu kiem landmark roi `raise`) se lam CHET CA LAN MIGRATE - dung chuoi
p116 va dung ca da xay ra 08/09.

Bo test nay quet DONG - moi feature co page_sync deu bi kiem, khong ai them form moi ma
lot ra ngoai duoc.
"""
import glob
import hashlib
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "features")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()
_SYNCS = sorted(glob.glob(os.path.join(
    _ROOT, "approval_center", "features", "*", "infrastructure", "page_sync.py")))


def _feature(path):
    return path.split(os.sep + "features" + os.sep)[1].split(os.sep)[0]


def _read(p):
    return io.open(p, encoding="utf-8").read()


def _esign_ui(ten):
    p = os.path.join(_ROOT, "platform", "esign", "ui", ten)
    try:
        return _read(p)
    except OSError:
        return ""


def _html_that(feature, sync_src):
    """HTML THAT duoc ghi len Web Page cua form nay.

    Hau het form ghi nguyen main_section.html. Payment Request thi KHONG: `_html()` cua no
    ghep main + 3 panel ky so (xem chu thich 10/09 trong page_sync.py cua form do), nen sha
    cua rieng main_section.html khong bao gio bang sha cua trang. Truoc dot 12/09 phep kiem
    nay so BASELINE voi sha file va bao lech - no bao DUNG mot su that, nhung su that do la
    "test dang do sai thu", chu khong phai "ai do quen bump". Test do lien tuc nen khong ai
    doc nua, va mot lan quen bump that se lan trong do.

    Nhan dien bang `_PLATFORM_ESIGN_UI`: form nao co tham chieu do la form co ghep panel.
    Form moi ghep kieu khac se lam test nay do - dung huong, vi nguoi them form se phai khai
    cach ghep o day thay vi de no truot qua.
    """
    main = _read(os.path.join(_ROOT, "approval_center", "features", feature, "ui",
                              "main_section.html"))
    if "_PLATFORM_ESIGN_UI" not in sync_src:
        return main
    return (main + "\n"
            + _esign_ui("requester_signing_panel.html") + "\n"
            + '<div id="ec-approver-wrap" style="display:none">\n'
            + _esign_ui("payment_request_signing.html")
            + '\n</div>\n'
            + _esign_ui("document_signing_section.html"))


class TestKhoaChongTroiMoiForm(unittest.TestCase):
    def test_co_du_form_de_quet(self):
        """Neu glob hong thi ca bo test thanh vo dung ma van xanh - chan trong luong truoc."""
        self.assertGreaterEqual(len(_SYNCS), 20,
                                "chi tim thay %d page_sync - phep quet co van de" % len(_SYNCS))

    def test_baseline_khop_voi_main_section_o_moi_form(self):
        lech = []
        co_khoa = 0
        for sync in _SYNCS:
            f = _feature(sync)
            m = re.search(r'BASELINE_SHA256 = "([0-9a-f]{64})"', _read(sync))
            if not m:
                continue          # form chua co khoa chong troi - hop le, khong ep
            co_khoa += 1
            real = hashlib.sha256(_html_that(f, _read(sync)).encode("utf-8")).hexdigest()
            if m.group(1) != real:
                lech.append("%s (khoa %s... nguon %s...)" % (f, m.group(1)[:12], real[:12]))
        self.assertGreaterEqual(co_khoa, 20, "chi thay %d form co khoa - nghi phep do" % co_khoa)
        self.assertEqual(
            lech, [],
            "Sua main_section.html thi PHAI bump BASELINE_SHA256 va day sha cu xuong "
            "SUPERSEDES_SHA256 trong CUNG commit. Khong bump thi page_sync tra 'refused', "
            "ban sua khong len production, va patch resync se lam chet migrate. Form lech: "
            + ", ".join(lech))

    def test_sha_cu_van_nam_trong_supersedes(self):
        """Luc deploy, live con giu bytes CU -> phai con trong danh sach chap nhan."""
        thieu = []
        for sync in _SYNCS:
            s = _read(sync)
            if "BASELINE_SHA256" not in s:
                continue
            block = re.search(r"SUPERSEDES_SHA256 = \((.*?)\n\)", s, re.S)
            if not block or not re.findall(r'"[0-9a-f]{64}"', block.group(1)):
                thieu.append(_feature(sync))
        self.assertEqual(thieu, [], "SUPERSEDES rong o: " + ", ".join(thieu))


if __name__ == "__main__":
    unittest.main(verbosity=2)
