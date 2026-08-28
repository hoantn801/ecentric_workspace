# Copyright (c) 2026, eCentric and contributors
"""Three ways the signature could land off the box, all of them silent.

Reported 2026-08-28: "nhin hinh chu ky dang bi lech kia".

Our geometry is TOP-left-origin points; SCTS wants PDF coordinates (BOTTOM-left). The flip
needs the page height, and every way of getting that height wrong shifts the signature by a
fixed amount - which reads as "slightly off" rather than "broken", so nobody can say why.

  1. Guessing 792 (Letter) when the height could not be read. An A4 page is 842pt, so every
     signature on an A4 document sat 50pt too low. A guessed number placing a signature on a
     real financial document is not a fallback, it is a wrong answer - now it refuses.
  2. Reading mediabox while the viewer (and our own placement editor) renders the CROPBOX.
     Common in PDFs exported from Word or produced by scanners.
  3. Ignoring /Rotate. A page rotated 90 or 270 swaps displayed width and height; using the
     unrotated height is off by most of a sheet of paper.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _src(*parts):
    root, tried = _HERE, []
    for _i in range(8):
        path = os.path.join(root, *parts)
        tried.append(path)
        if os.path.exists(path):
            return io.open(path, encoding="utf-8").read()
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay %s" % parts[-1])


_PKG = _src("platform", "esign", "package.py")
_SCTS = _src("platform", "esign", "providers", "scts.py")


def _page_sizes():
    """Chay THAT ham, khong duc source.

    Ban dau minh cat may dong `from pypdf import ...` ra khoi source truoc khi exec - cach
    do vo ngay khi thut le doi. Cap mot module pypdf gia vao sys.modules thi ham chay
    nguyen ven, va cai duoc nghiem thu la CHINH doan code se chay tren may that.
    """
    import sys as _sys
    import types as _types

    class _Reader(object):
        PAGES = []

        def __init__(self, _b):
            self.pages = _Reader.PAGES

    mod = _types.ModuleType("pypdf")
    mod.PdfReader = _Reader
    _sys.modules["pypdf"] = mod

    body = re.search(r"(?m)^def _page_sizes\(.*?(?=\ndef )", _PKG, re.S).group(0)
    g = {"io": io}
    exec(compile(body, "ps", "exec"), g)
    return g["_page_sizes"], _Reader


class _Box(object):
    def __init__(self, w, h):
        self.width, self.height = w, h


class _Page(dict):
    def __init__(self, media, crop=None, rotate=0):
        super().__init__()
        self.mediabox = media
        self.cropbox = crop
        if rotate:
            self["/Rotate"] = rotate


class TestPageHeightIsWhatTheViewerShows(unittest.TestCase):
    def setUp(self):
        self.fn, self.Reader = _page_sizes()

    def test_cropbox_wins_over_mediabox(self):
        self.Reader.PAGES = [_Page(_Box(612, 792), crop=_Box(595, 842))]
        self.assertEqual(self.fn(b"x"), [(595.0, 842.0)],
                         "trinh xem ve theo cropbox; dung mediabox la lech dung phan chenh")

    def test_mediabox_is_used_when_there_is_no_cropbox(self):
        self.Reader.PAGES = [_Page(_Box(595, 842), crop=None)]
        self.assertEqual(self.fn(b"x"), [(595.0, 842.0)])

    def test_a_rotated_page_swaps_width_and_height(self):
        self.Reader.PAGES = [_Page(_Box(595, 842), rotate=90)]
        self.assertEqual(self.fn(b"x"), [(842.0, 595.0)],
                         "trang xoay 90 thi chieu cao hien thi la 595, khong phai 842")

    def test_rotation_180_changes_nothing(self):
        self.Reader.PAGES = [_Page(_Box(595, 842), rotate=180)]
        self.assertEqual(self.fn(b"x"), [(595.0, 842.0)])


class TestItRefusesToGuessTheHeight(unittest.TestCase):
    def test_the_letter_fallback_is_gone(self):
        body = re.search(r"(?m)^    def create_document\(.*?(?=\n    @|\n    def )",
                         _SCTS, re.S).group(0)
        self.assertNotIn('pl.get("page_height") or 792', body,
                         "doan 792 = moi chu ky tren giay A4 bi day xuong 50 diem")
        # Kiem CA DIEU KIEN, khong chi su co mat cua chuoi: `if False:` van de lai
        # "scts_page_height_unknown" trong source ma khong bao gio chan gi (phep dot bien
        # BA lot dung vi vay).
        self.assertRegex(
            body,
            r'if not pl\.get\("page_height"\):\s*\n\s*raise ProviderError\(\s*\n?\s*'
            r'"scts_page_height_unknown"',
            "khong doc duoc chieu cao thi phai TU CHOI, va phep chan phai that su chan")

    def test_the_refusal_names_the_file_and_page(self):
        body = re.search(r"(?m)^    def create_document\(.*?(?=\n    @|\n    def )",
                         _SCTS, re.S).group(0)
        m = re.search(r'scts_page_height_unknown",\s*\n\s*"([^"]+)"', body)
        self.assertIsNotNone(m)
        self.assertIn("%s", m.group(1))

    def test_the_flip_still_uses_lower_left(self):
        body = re.search(r"(?m)^    def create_document\(.*?(?=\n    @|\n    def )",
                         _SCTS, re.S).group(0)
        self.assertIn("y_pdf = max(0.0, page_h - float(pl.get(\"y\") or 0) - h)", body,
                      "goc duoi-trai: y_pdf = chieu cao trang - y_tren - chieu cao o")


if __name__ == "__main__":
    unittest.main()
