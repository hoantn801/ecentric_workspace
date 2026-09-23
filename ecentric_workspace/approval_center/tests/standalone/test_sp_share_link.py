# Copyright (c) 2026, eCentric and contributors
"""Nut "Mo online" phai dung LINK CHIA SE, khong phai URL goc cua tep (23/09).

Hoan bao: huong.pham gui EC-CTR-2026-00019 nhung khong mo duoc tep online. Do tren production:
ban ghi lien ket dong bo thanh cong luc 10:53:00, `sp_granted_to` CO ten chi. Quyen cap bang
createLink(scope=users) gan vao LINK, nhung ham goi chi luu `da_cap` va vut link - nut "Mo
online" tro vao URL goc cua tep. Ai co quyen san trong thu vien mo duoc; nguoi gui thi khong.

Bo test giu bon dieu:
  1. Link chia se DUOC LUU va DUOC DUNG - o ca form Contract Review lan ngan xem nhanh cua hub.
  2. Ban ghi cu chua co link van mo duoc nhu truoc (roi ve URL goc) - khong lam mat duong nao.
  3. Cap bu link TUYET DOI KHONG tai tep len lai: ban tren SharePoint la ban SONG, nguoi duyet
     sua truc tiep tren do; tai de la xoa sach chinh sua cua ho. Day la dieu de mat nhat.
  4. Patch cap bu bat duoc NULL: cot vua them bang migrate thi moi dong deu NULL.

Cat ham bang AST roi chay trong khong gian ten rieng, dung khuon test_sharepoint_mirror -
khong dung sys.modules, nen khong phu thuoc thu tu chay (bai hoc 16/09).
"""
import ast
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_AC = os.path.normpath(os.path.join(_HERE, "..", ".."))
_MIRROR = os.path.join(_AC, "shared", "integrations", "sharepoint_mirror.py")
_QUERY = os.path.join(_AC, "shared", "requests", "query_service.py")
_P204 = os.path.join(_AC, "patches", "p204_backfill_sp_share_url.py")
_UI_CTR = os.path.join(_AC, "features", "contract_review", "ui", "main_section.html")
_UI_HUB = os.path.join(_AC, "ui", "all_requests", "main_section.html")


def _doan(path, *ten):
    src = io.open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    ra, con = [], set(ten)
    for node in tree.body:
        if getattr(node, "name", None) in con:
            ra.append(ast.get_source_segment(src, node))
            con.discard(node.name)
    if con:
        raise AssertionError("khong thay %s" % ", ".join(sorted(con)))
    return "\n\n".join(ra)


class _Doc(object):
    def __init__(self, **kw):
        self.name = "BAN_GHI"
        self.__dict__.update(kw)
        self.da_luu = 0

    def save(self, **kw):
        self.da_luu += 1


class _Row(dict):
    __getattr__ = dict.get


def _moi_truong(ghi, docs=None, loi_tai=None, loi_cap=None, link="https://sp/share/abc"):
    """Khong gian ten gia cho cac ham cua sharepoint_mirror."""
    docs = docs if docs is not None else {}

    fr = types.SimpleNamespace()
    fr.db = types.SimpleNamespace(
        get_value=lambda dt, flt, f=None, **k: next(
            (n for n, d in docs.items() if d.file_url == (flt or {}).get("file_url")), None),
        commit=lambda: ghi["commit"].append(1),
        rollback=lambda: ghi["rollback"].append(1))
    fr.get_doc = lambda dt, ten=None: docs[ten]
    fr.new_doc = lambda dt: docs.setdefault("MOI", _Doc(file_url=None, sp_share_url=None))
    fr.get_all = lambda dt, **k: list(docs.keys())
    fr.log_error = lambda *a, **k: ghi["log"].append(a)
    fr.get_traceback = lambda: "tb"

    def tai_len(*a, **k):
        ghi["tai_len"].append(a)
        if loi_tai:
            raise RuntimeError(loi_tai)
        return {"item_id": "IT1", "web_url": "https://sp/goc/tep.docx",
                "last_modified": "2026-09-23T03:00:00Z"}

    def cap_quyen(item_id, nguoi, token=None, **k):
        ghi["cap_quyen"].append((item_id, tuple(nguoi)))
        if loi_cap and item_id in loi_cap:
            raise RuntimeError("graph hong")
        return {"da_cap": list(nguoi), "bo_qua": [], "link": link}

    ns = {
        "frappe": fr, "LINK_DT": "EC SharePoint File Link",
        "tai_len": tai_len, "cap_quyen": cap_quyen,
        "nguoi_trong_luong": lambda dt, n: ["huong.pham@e.c", "duyet@e.c"],
        "_dinh_kem": lambda dt, n: [_Row(file_url="/private/files/hd.docx", file_name="hd.docx")],
        "duoc_soi_guong": lambda dt: True,
        "gio_he_thong": lambda x: x,
        "now_datetime": lambda: "2026-09-23 10:00:00",
        "wr_sp": types.SimpleNamespace(get_app_token=lambda: "TOKEN"),
    }
    return ns


def _ghi():
    return {"tai_len": [], "cap_quyen": [], "commit": [], "rollback": [], "log": []}


class TestLuuVaDungLink(unittest.TestCase):
    def test_dong_bo_LUU_link_chia_se(self):
        ghi, docs = _ghi(), {}
        ns = _moi_truong(ghi, docs)
        exec(_doan(_MIRROR, "ghi_lien_ket", "dong_bo_phieu"), ns)
        kq = ns["dong_bo_phieu"]("EC Contract Review Request", "EC-CTR-1")
        self.assertEqual(kq["hong"], [], "dong_bo_phieu nuot loi cua tung tep - phai kiem ro khong tep nao hong")
        self.assertEqual(docs["MOI"].sp_share_url, "https://sp/share/abc",
                         "link createLink tra ve bi vut - dung loi cua huong.pham")
        self.assertEqual(docs["MOI"].sp_web_url, "https://sp/goc/tep.docx",
                         "van phai giu URL goc lam duong du phong")

    def test_lan_cap_quyen_KHONG_co_link_thi_GIU_link_cu(self):
        ghi = _ghi()
        docs = {"L1": _Doc(file_url="/private/files/hd.docx", sp_share_url="https://sp/share/CU")}
        ns = _moi_truong(ghi, docs)
        exec(_doan(_MIRROR, "ghi_lien_ket"), ns)
        ns["ghi_lien_ket"]("EC Contract Review Request", "/private/files/hd.docx", "EC-CTR-1",
                           {"item_id": "IT1", "web_url": "u"}, ["a@e.c"], share_url=None)
        self.assertEqual(docs["L1"].sp_share_url, "https://sp/share/CU",
                         "mot lan cap quyen khong tra link da XOA link dang dung duoc")

    def test_gan_sharepoint_tra_link_ra_client(self):
        src = _doan(_QUERY, "gan_sharepoint")
        self.assertIn('"sp_share_url"', src.split("fields=")[1].split(")")[0],
                      "khong doc sp_share_url tu DB")
        self.assertIn('a["sp_share_url"]', src, "doc ra nhung khong dua cho client")


class TestCapBuKhongTaiLai(unittest.TestCase):
    """Dieu de mat nhat: tai tep len lai la xoa sach chinh sua tren ban song."""

    def test_cap_bu_KHONG_goi_tai_len(self):
        ghi = _ghi()
        docs = {"L1": _Doc(file_url="/f", sp_item_id="IT1", business_doctype="EC Contract Review Request",
                           business_name="EC-CTR-1", sp_share_url=None, sp_granted_to="")}
        ns = _moi_truong(ghi, docs)
        exec(_doan(_MIRROR, "cap_bu_link"), ns)
        ns["cap_bu_link"]("L1", token="T")
        self.assertEqual(ghi["tai_len"], [],
                         "cap bu link da TAI TEP LEN LAI - ghi de ban song tren SharePoint")
        self.assertEqual(docs["L1"].sp_share_url, "https://sp/share/abc")
        self.assertEqual(ghi["cap_quyen"][0][0], "IT1")

    def test_cap_bu_doc_nguoi_tu_luong_HIEN_TAI(self):
        ghi = _ghi()
        docs = {"L1": _Doc(file_url="/f", sp_item_id="IT1", business_doctype="X", business_name="Y",
                           sp_share_url=None, sp_granted_to="cu@e.c")}
        ns = _moi_truong(ghi, docs)
        exec(_doan(_MIRROR, "cap_bu_link"), ns)
        ns["cap_bu_link"]("L1", token="T")
        self.assertIn("huong.pham@e.c", ghi["cap_quyen"][0][1])

    def test_ban_ghi_khong_co_item_id_thi_bo_qua(self):
        ghi = _ghi()
        docs = {"L1": _Doc(file_url="/f", sp_item_id=None, business_doctype="X", business_name="Y")}
        ns = _moi_truong(ghi, docs)
        exec(_doan(_MIRROR, "cap_bu_link"), ns)
        ns["cap_bu_link"]("L1")
        self.assertEqual(ghi["cap_quyen"], [])

    def test_mot_ban_ghi_hong_KHONG_keo_ca_lo(self):
        ghi = _ghi()
        docs = {n: _Doc(file_url="/" + n, sp_item_id=n, business_doctype="X", business_name="Y",
                        sp_share_url=None, sp_granted_to="") for n in ("L1", "L2", "L3")}
        ns = _moi_truong(ghi, docs, loi_cap={"L2"})
        exec(_doan(_MIRROR, "cap_bu_link", "cap_bu_link_nen"), ns)
        ns["cap_bu_link_nen"]()
        self.assertEqual(docs["L1"].sp_share_url, "https://sp/share/abc")
        self.assertEqual(docs["L3"].sp_share_url, "https://sp/share/abc",
                         "L2 hong lam L3 khong duoc cap bu")
        self.assertEqual(len(ghi["commit"]), 2, "phai commit sau MOI ban ghi xong")
        self.assertEqual(len(ghi["rollback"]), 1)


class TestPatch(unittest.TestCase):
    def setUp(self):
        self.src = io.open(_P204, encoding="utf-8").read()

    def test_bo_loc_bat_duoc_NULL(self):
        self.assertIn('"sp_share_url": ["is", "not set"]', self.src,
                      "cot vua them bang migrate thi moi dong deu NULL - loc sai la dem ra 0 roi im lang")

    def test_chi_dat_viec_KHONG_goi_Graph_trong_migrate(self):
        ma = "\n".join(l for l in self.src.splitlines() if not l.strip().startswith("#"))
        self.assertIn("frappe.enqueue(", ma)
        for cam in ("cap_quyen(", "tai_len(", "dong_bo_phieu", "dong_bo_nen"):
            self.assertNotIn(cam, ma.split('"""', 2)[-1], "patch goi thang " + cam)

    def test_khong_bao_gio_nem_loi(self):
        tree = ast.parse(self.src)
        f = next(n for n in tree.body if getattr(n, "name", None) == "execute")
        self.assertIsInstance(f.body[0], ast.Try, "patch nem loi se lam chet ca lan migrate")


class TestGiaoDien(unittest.TestCase):
    def _kiem(self, path, bien):
        s = io.open(path, encoding="utf-8").read()
        self.assertIn("%s.sp_share_url||%s.sp_web_url" % (bien, bien), s,
                      "%s khong uu tien link chia se" % os.path.basename(os.path.dirname(os.path.dirname(path))))
        # khong con cho nao dung THANG sp_web_url lam href
        self.assertNotIn("href=\"'+esc(%s.sp_web_url)" % bien, s)
        self.assertNotIn("esc(online?%s.sp_web_url" % bien, s)

    def test_form_contract_review(self):
        self._kiem(_UI_CTR, "f")

    def test_ngan_xem_nhanh_cua_hub(self):
        self._kiem(_UI_HUB, "a")

    def test_van_giu_ban_ERP_lam_duong_du_phong(self):
        s = io.open(_UI_CTR, encoding="utf-8").read()
        self.assertIn("Bản ERP", s, "mat duong du phong - SharePoint chan ai thi nguoi do mat luon hop dong")


if __name__ == "__main__":
    unittest.main()
