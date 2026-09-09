# Copyright (c) 2026, eCentric and contributors
"""Popup hub: trang thai dung thuc te, tien trinh du buoc, va khung trao doi (09/09, Hoan).

Bon loi that, deu thay tren production 09/09:
  1. Phieu dang o buoc Operation van hien "Hoan tat" - `statusCell` chi ghep buoc xu ly vao
     KHI dang o tab "Cho toi xu ly"; tab khac hien trang thai duyet, ma duyet xong = Approved
     -> "Hoan tat".
  2. Cot "Cap hien tai" in ra so 0 - duyet xong thi current_level ve 0.
  3. Tien trinh trong popup thieu "Da gui" / buoc xu ly / "Hoan tat" so voi trang day du.
  4. Ba nguoi da duyet ma moi cap hien nhu chua ai xu ly: chot cu la
     `level_status==="Completed"`, MA GIA TRI DO KHONG TON TAI (options that: Pending /
     In Progress / Approved / Rejected / Skipped / Information Requested). Ve dau luon sai;
     ve con lai `level_no < cur` cung tat khi cur = 0. Popup chua bao gio ve dung cho phieu
     da duyet.

Va phan trao doi: dung Frappe Comment gan vao ho so, gac bang `can_view_request` - khong tu
che luat quyen thu hai.
"""
import ast
import io
import json
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "reporting")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()
_HUB = os.path.join(_ROOT, "approval_center", "ui", "all_requests", "main_section.html")
_ACTIONS = os.path.join(_ROOT, "approval_center", "reporting", "actions.py")
_LEVEL_JSON = os.path.join(_ROOT, "approval_center", "doctype", "ec_approval_request_level",
                           "ec_approval_request_level.json")


def _read(p):
    return io.open(p, encoding="utf-8").read()


class TestTrangThaiVaCapHienTai(unittest.TestCase):
    def test_buoc_xu_ly_duoc_ghep_o_MOI_tab(self):
        src = _read(_HUB)
        self.assertIn("function ffActive(r)", src)
        self.assertNotIn('if(state.box==="fulfil" && r.fulfillment_status)', src,
                         "khong duoc chi ghep buoc xu ly rieng tab 'Cho toi xu ly'")

    def test_cot_cap_hien_tai_khong_in_so_0(self):
        src = _read(_HUB)
        self.assertIn("function levelCell(r)", src)
        self.assertNotIn("cell(r.current_level_name||r.current_level)", src,
                         "in thang current_level thi phieu da duyet hien so 0")


class TestTienTrinhPopup(unittest.TestCase):
    def test_khong_con_chot_theo_gia_tri_KHONG_TON_TAI(self):
        """`Completed` khong nam trong options cua level_status - chot theo no la chot chet."""
        opts = None
        for f in json.loads(_read(_LEVEL_JSON))["fields"]:
            if f.get("fieldname") == "level_status":
                opts = set((f.get("options") or "").split("\n"))
        self.assertTrue(opts)
        self.assertNotIn("Completed", opts, "neu Frappe them 'Completed' thi doc lai test nay")
        src = _read(_HUB)
        blk = src[src.index("function stepperHtml("):]
        blk = blk[:blk.index("function isLong(")]
        self.assertNotIn('l.level_status==="Completed"', blk,
                         "chot theo gia tri khong ton tai -> luon sai")
        for st in ("Approved", "Skipped"):
            self.assertIn('"%s"' % st, blk, "phai xet trang thai %s" % st)

    def test_co_du_buoc_da_gui_xu_ly_hoan_tat(self):
        src = _read(_HUB)
        blk = src[src.index("function stepperHtml("):]
        blk = blk[:blk.index("function isLong(")]
        for lb in ("Đã gửi", "Xử lý", "Hoàn tất"):
            self.assertIn(lb, blk, "tien trinh thieu buoc %r" % lb)

    def test_phieu_da_duyet_thi_moi_cap_deu_xong(self):
        src = _read(_HUB)
        blk = src[src.index("function stepperHtml("):]
        blk = blk[:blk.index("function isLong(")]
        self.assertIn("approved", blk,
                      "phai xet overall=Approved, vi luc do cur=0 nen moi chot theo cur deu tat")


class TestBamRaNgoaiDeDong(unittest.TestCase):
    def test_bam_vao_khung_bao_cung_dong(self):
        src = _read(_HUB)
        blk = src[src.index('ov.addEventListener("click"'):]
        blk = blk[:blk.index("document.addEventListener")]
        self.assertIn("ec-apl-wrap", blk,
                      "khoang trong giua/duoi hai the la .ec-apl-wrap, khong phai lop phu")


class TestTraoDoi(unittest.TestCase):
    def test_hai_tab_va_dem_so_tin(self):
        src = _read(_HUB)
        self.assertIn('data-tab="tl"', src)
        self.assertIn('data-tab="cm"', src)
        self.assertIn('class="cnt"', src)

    def test_endpoint_gac_bang_can_view_request(self):
        src = _read(_ACTIONS)
        self.assertIn("def list_comments(", src)
        self.assertIn("def add_comment(", src)
        self.assertIn("def _assert_can_view(", src)
        tree = ast.parse(src)
        for fn in ("list_comments", "add_comment"):
            node = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn]
            self.assertTrue(node, fn)
            called = {c.func.id for c in ast.walk(node[0])
                      if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
            self.assertIn("_assert_can_view", called, "%s khong kiem quyen" % fn)

    def test_goi_dung_khong_gian_ten_reporting_actions(self):
        """09/09: goi bang call() -> tro toi reporting.api, ma hai ham nay nam o
        reporting.actions -> "module has no attribute 'list_comments'" ngay tren production."""
        src = _read(_HUB)
        for fn in ("list_comments", "add_comment"):
            self.assertIn('ACT+"%s"' % fn, src,
                          "%s phai goi qua ACT (reporting.actions), khong phai call()" % fn)
            self.assertNotIn('call("%s"' % fn, src)

    def test_tab_mac_dinh_la_trao_doi(self):
        src = _read(_HUB)
        blk = src[src.index("aside.innerHTML="):]
        blk = blk[:blk.index("box.appendChild(aside)")]
        self.assertIn('data-tab="cm" class="on"', blk, "tab mac dinh phai la Trao doi")
        self.assertNotIn('data-tab="tl" class="on"', blk)
        self.assertIn('data-pane="tl" hidden', blk, "Lich su phai an luc dau")

    def test_nap_binh_luan_ngay_khi_mo(self):
        """Tab mac dinh la Trao doi thi phai nap san, khong doi nguoi dung bam tab."""
        src = _read(_HUB)
        blk = src[src.index("function setAside("):]
        blk = blk[:blk.index("function bindAside(")]
        self.assertIn("loadComments();", blk)

    def test_luu_van_ban_thuan_khong_luu_HTML_tho(self):
        """Comment cua Frappe la truong HTML; do lai HTML tho tu client la mo duong cho script."""
        src = _read(_ACTIONS)
        self.assertIn("def _strip_html(", src)
        blk = src[src.index("def add_comment("):]
        blk = blk[:blk.index("def _notify_participants(")]
        self.assertIn("_strip_html(content)", blk)

    def test_add_comment_la_POST(self):
        src = _read(_ACTIONS)
        m = re.search(r"(@frappe\.whitelist\([^)]*\)\s*\ndef add_comment)", src)
        self.assertTrue(m)
        self.assertIn('methods=["POST"]', m.group(1), "ghi du lieu thi phai POST")

    def test_loi_bao_khong_lam_hong_viec_gui_tin(self):
        src = _read(_ACTIONS)
        blk = src[src.index("def _notify_participants("):]
        self.assertIn("except Exception", blk)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestKhungPhaiCaoBangKhungTrai(unittest.TestCase):
    """09/09, Hoan chi tren anh: the phai ngan hon the trai, va chu "Gui" bi lech.

    Doc CSS that trong file, khong khang dinh "co goi ham" - xem
    feedback_test_asserting_call_exists_proves_nothing.
    """

    def _css(self):
        return io.open(_HUB, encoding="utf-8").read()

    def test_hai_the_cao_bang_nhau(self):
        css = self._css()
        self.assertIn("align-items:stretch", css,
                      "wrap phai stretch thi the phai moi cao bang the trai")
        self.assertNotIn("display:flex; align-items:flex-start; gap:16px", css,
                         "flex-start la nguyen nhan the phai bi ngan")

    def test_khong_dung_center_vi_cat_mat_phan_dau(self):
        """Ly do da ghi san trong file: center cat dau khi the cao hon man hinh."""
        css = self._css()
        self.assertNotIn(".ec-apl-wrap{ display:flex; align-items:center", css)

    def test_aside_la_cot_flex_de_o_nhap_dinh_day(self):
        css = self._css()
        i = css.index(".ec-apl-aside{")
        block = css[i:i + 400]
        self.assertIn("flex-direction:column", block)
        j = css.index(".ec-apl-aside .bd{")
        self.assertIn("flex:1 1 auto", css[j:j + 260])
        self.assertIn("min-height:0", css[j:j + 260])

    def test_nut_gui_can_giua_tuong_minh(self):
        css = self._css()
        i = css.index(".ec-apl-cbox .btn{")
        block = css[i:i + 400]
        for want in ("display:inline-flex", "align-items:center",
                     "justify-content:center", "line-height:1"):
            self.assertIn(want, block, "nut Gui thieu %s -> chu co dau bi lech" % want)

    def test_nut_gui_khong_con_class_approve_thua(self):
        """Rule .btn.approve bi gioi han trong .ec-apl-mf nen khong voi toi khung chat;
        de lai class do chi lam nguoi doc sau hieu nham. Hai nut Duyet THAT phai con."""
        css = self._css()
        self.assertNotIn('class="btn approve" data-send', css)
        self.assertIn('class="btn approve" data-a="approve"', css,
                      "nut Duyet that cua popup khong duoc dong cham")
