# Copyright (c) 2026, eCentric and contributors
"""Multi-page PDFs, and a viewer that stays inside its card.

Two defects reported 2026-08-28, both in the placement drawer.

Page navigation. The backend has stored `page_index` from the start, but the viewer only
ever showed page 1 and drew EVERY placement on it - so a box belonging to page 2 appeared
over page 1, where it could also be dragged by mistake. Signatures on any page but the first
were unreachable.

Overflow. `.ecd-viewer` was a centring flex container with no scrolling. A page wider or
taller than the frame could not scroll, so it spilled out over the surrounding card - the
"PDF tran ca card" complaint, raised more than once.
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


_UI = _src("platform", "esign", "ui", "document_signing_section.html")


class TestTheViewerCanScroll(unittest.TestCase):
    def setUp(self):
        m = re.search(r"\.ecd-viewer\{([^}]*)\}", _UI)
        self.assertIsNotNone(m, "khong tim thay style cua khung xem")
        self.rule = m.group(1)

    def test_it_scrolls_instead_of_spilling(self):
        self.assertIn("overflow:auto", self.rule,
                      "khong cuon duoc thi trang PDF lon se tran ra ngoai the")

    def test_it_is_allowed_to_shrink(self):
        # Mot flex item mac dinh khong nho hon noi dung cua no; thieu min-width/min-height
        # thi `overflow:auto` khong cuu duoc gi.
        self.assertIn("min-width:0", self.rule)
        self.assertIn("min-height:0", self.rule)

    def test_centring_no_longer_relies_on_flex(self):
        self.assertNotIn("display:flex", self.rule,
                         "flex + align-items:center khong cuon duoc")
        self.assertRegex(_UI, r"\.ecd-viewer > #ecdStage\{[^}]*margin:auto",
                         "van phai canh giua khi trang nho hon khung")


class TestOnlyTheCurrentPageIsDrawn(unittest.TestCase):
    def test_boxes_of_other_pages_are_skipped(self):
        body = re.search(r"function hydrateBoxes\(\)\s*\{(.*?)\n  \}", _UI, re.S).group(1)
        self.assertRegex(
            body,
            r"if \(Number\(p\.page_index \|\| 1\) !== Number\(DRW\.page \|\| 1\)\) return;",
            "ve het moi trang len mot trang = nhin sai va keo nham o cua trang khac")

    def test_a_placement_still_records_the_page_it_was_made_on(self):
        self.assertIn("page_index: DRW.page", _UI)


class TestThePagerExistsAndIsWiredOnce(unittest.TestCase):
    def test_there_are_previous_and_next_controls(self):
        self.assertIn('data-page="prev"', _UI)
        self.assertIn('data-page="next"', _UI)

    def test_it_hides_itself_for_a_single_page_document(self):
        body = re.search(r"function _syncPager\(\)\s*\{(.*?)\n  \}", _UI, re.S).group(1)
        self.assertIn('n > 1 ? "flex" : "none"', body,
                      "mot trang ma van bay thanh dieu huong thi chi lam roi mat")

    def test_the_ends_are_disabled_rather_than_wrapping(self):
        body = re.search(r"function _syncPager\(\)\s*\{(.*?)\n  \}", _UI, re.S).group(1)
        self.assertIn("prev.disabled", body)
        self.assertIn("next.disabled", body)

    def test_the_page_is_clamped_to_the_document(self):
        body = re.search(r"function gotoPage\(n\)\s*\{(.*?)\n  \}", _UI, re.S).group(1)
        self.assertIn("Math.max(1, Math.min(total,", body,
                      "khong duoc nhay ra ngoai so trang that")
        self.assertIn("if (n === DRW.page) return;", body,
                      "cung trang thi khong ve lai - ve lai la mat cac o dang keo do")

    def test_the_handler_is_bound_once_outside_renderPdf(self):
        render = re.search(r"function renderPdf\(\)\s*\{(.*?)\n  \}", _UI, re.S).group(1)
        self.assertNotIn("onclick", render,
                         "gan su kien trong renderPdf = moi lan ve lai chong them mot lop")
        self.assertIn('_pg.onclick = function (e)', _UI)


if __name__ == "__main__":
    unittest.main()
