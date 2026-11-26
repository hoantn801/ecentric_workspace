# Copyright (c) 2026, eCentric and contributors
"""Hop dong KOL vao THU MUC HAN CHE tren SharePoint (26/11/2026, PO Hoan, "huong 2").

Giu nhung dieu de lo CCCD / STK creator neu sai:
  1. Chua cau hinh `ec_sp_kol_folder` -> KOL KHONG len (hanh vi 17/11), khong goi Graph.
  2. Cau hinh + thu muc chi co quyen RIENG -> len dung `<thu muc>/<ma phieu>/<tep>`.
  3. Thu muc con ke thua / khong ton tai / Graph loi / mo ca cong ty -> KHONG tai, log cho IT
     (mot lan / gio), khong tu tao thu muc, khong tu cap quyen thu muc.
  4. Hop dong lao dong: KHONG BAO GIO len, ke ca khi thu muc KOL an toan.
  5. Ham dong bo lai: chi System Manager, mac dinh chay thu (khong ghi), ghi that phai POST.

    python3 -m pytest -q ecentric_workspace/approval_center/tests/standalone/test_sp_kol_thu_muc_han_che.py
"""
import ast
import importlib.util
import io
import pathlib
import sys
import types
import unittest
from urllib.parse import quote

APP = pathlib.Path(__file__).resolve().parents[2].parent
MIRROR = APP / "approval_center/shared/integrations/sharepoint_mirror.py"
PROBE = APP / "approval_center/features/contract_review/infrastructure/sharepoint_probe.py"
QUERY = APP / "approval_center/shared/requests/query_service.py"
SERVICE = APP / "approval_center/features/contract_review/application/service.py"
ADD_FILE = APP / "approval_center/shared/requests/add_file.py"
SNAPSHOT = APP / "approval_center/shared/integrations/sharepoint_snapshot.py"

CTR = "EC Contract Review Request"
KOL = "KOL/KOC / Creator (EC)"
LABOR = "Labor / Hợp đồng lao động (EC)"
SALES = "Sales / Bán ra (EC)"
THU_MUC = "Contract Review - KOL (Hạn chế)"
G = "https://graph"


def _doan(path, *ten):
    src = io.open(str(path), encoding="utf-8").read()
    tree = ast.parse(src)
    ra, con = [], set(ten)
    for node in tree.body:
        nn = getattr(node, "name", None)
        if nn is None and isinstance(node, ast.Assign):
            nn = getattr(node.targets[0], "id", None)
        if nn in con:
            ra.append(ast.get_source_segment(src, node))
            con.discard(nn)
    assert not con, con
    return "\n\n".join(ra)


class _Resp(object):
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body
        self.text = str(body)

    def json(self):
        return self._b


class Graph(object):
    """Graph gia: thu muc + quyen cua no, va upload session."""

    def __init__(self, ton_tai=True, la_thu_muc=True, quyen=None, ma_quyen=200, boom=False):
        self.ton_tai, self.la_thu_muc, self.ma_quyen, self.boom = ton_tai, la_thu_muc, ma_quyen, boom
        self.quyen = quyen if quyen is not None else [
            {"roles": ["write"], "grantedToV2": {"siteGroup": {"displayName": "ERP - Hợp đồng KOL"}}},
            {"roles": ["owner"], "grantedToV2": {"siteGroup": {"displayName": "Operation Owners"}}}]
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url))
        if self.boom:
            raise RuntimeError("mat mang")
        if url == "%s/sites/site/drive/root:/%s" % (G, quote(THU_MUC)):
            if not self.ton_tai:
                return _Resp(404, {"error": "itemNotFound"})
            item = {"id": "FOLDER-1", "name": THU_MUC}
            if self.la_thu_muc:
                item["folder"] = {"childCount": 0}
            return _Resp(200, item)
        if url == "%s/sites/site/drive/items/FOLDER-1/permissions" % G:
            return _Resp(self.ma_quyen, {"value": self.quyen})
        raise AssertionError("GET la: " + url)

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append(("POST", url))
        if url.endswith(":/createUploadSession"):
            return _Resp(200, {"uploadUrl": "https://up/" + url})
        raise AssertionError("POST la: " + url)

    def put(self, url, headers=None, data=None, timeout=None):
        self.calls.append(("PUT", url))
        return _Resp(201, {"id": "ITEM-NEW", "webUrl": "https://sp/x",
                           "lastModifiedDateTime": "2026-11-26T02:00:00Z"})

    def uploads(self):
        return [u for m, u in self.calls if m == "POST" and u.endswith(":/createUploadSession")]

    def doc_quyen(self):
        return [u for m, u in self.calls if m == "GET" and u.endswith("/permissions")]


class _Cache(object):
    def __init__(self):
        self.d = {}

    def get_value(self, k):
        return self.d.get(k)

    def set_value(self, k, v, expires_in_sec=None):
        self.d[k] = v


def _nap(loai_hd, conf=None, graph=None):
    """sharepoint_mirror THAT tren frappe gia. `loai_hd`: {ten phieu: contract_type}."""
    log, cache = [], _Cache()
    fr = types.ModuleType("frappe")
    fr.conf = dict(conf or {})
    fr.cache = lambda: cache

    def get_value(dt, filters, field=None, *a, **k):
        if dt == CTR and field == "contract_type":
            n = filters.get("name") if isinstance(filters, dict) else filters
            v = loai_hd.get(n)
            if isinstance(v, Exception):
                raise v
            return v
        if dt == "File":
            return "F-1"
        return None
    fr.db = types.SimpleNamespace(get_value=get_value, has_column=lambda *a: True)

    class _F(object):
        def get_content(self):
            return b"noi dung"
    fr.get_doc = lambda dt, name=None: _F()
    fr.get_all = lambda *a, **k: []
    fr.log_error = lambda *a, **k: log.append(a)
    fr.get_traceback = lambda: "tb"
    fu = types.ModuleType("frappe.utils")
    fu.now_datetime = lambda: None
    wr = types.ModuleType("ecentric_workspace.weekly_report.sharepoint")
    wr.safe_filename = lambda n: (n or "").replace(":", "_")
    wr.get_app_token = lambda: "TOKEN"
    wr.GRAPH, wr.SITE_ID = G, "site"
    gia = {"frappe": fr, "frappe.utils": fu, "ecentric_workspace.weekly_report.sharepoint": wr}
    for p in ("ecentric_workspace", "ecentric_workspace.weekly_report"):
        gia.setdefault(p, sys.modules.get(p) or types.ModuleType(p))
    gia["ecentric_workspace.weekly_report"].sharepoint = wr
    cu = {k: sys.modules.get(k) for k in gia}
    sys.modules.update(gia)
    try:
        spec = importlib.util.spec_from_file_location("sp_kol_han_che", str(MIRROR))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        for k, v in cu.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    g = graph or Graph()
    mod._requests = lambda: g
    return mod, g, log, fr


CAU_HINH = {"ec_sp_kol_folder": THU_MUC}
PHIEU = {"CTR-K": KOL, "CTR-L": LABOR, "CTR-S": SALES}


def _co_log_it(log):
    return [a for a in log if "IT cần cấu hình" in str(a[0])]


# --------------------------------------------------------------------------- 1. chua cau hinh
class ChuaCauHinh(unittest.TestCase):
    def test_kol_khong_len_va_khong_goi_graph(self):
        m, g, log, _f = _nap(PHIEU)
        self.assertEqual(m.phan_loai_phieu(CTR, "CTR-K"), ("chua_cau_hinh", None))
        self.assertFalse(m.duoc_soi_guong_phieu(CTR, "CTR-K"))
        self.assertFalse(m.duoc_soi_guong_phieu(CTR, "CTR-K", kiem_quyen=False))
        self.assertIn("bo_qua", m.dong_bo_phieu(CTR, "CTR-K"))
        with self.assertRaises(m.SharePointChuaSan):
            m.tai_len(CTR, "/private/files/hd.docx", "hd.docx", "CTR-K", token="T")
        self.assertEqual(g.calls, [])
        self.assertEqual(log, [], "chua cau hinh = hanh vi cu, khong canh bao")

    def test_cau_hinh_rong_hoac_chi_dau_gach_van_la_chua_cau_hinh(self):
        for v in ("", "  ", "/", None):
            m, g, _l, _f = _nap(PHIEU, {"ec_sp_kol_folder": v})
            self.assertFalse(m.duoc_soi_guong_phieu(CTR, "CTR-K"), repr(v))
            self.assertEqual(g.calls, [])


# --------------------------------------------------------------------------- 2. an toan -> len
class ThuMucAnToan(unittest.TestCase):
    def test_len_dung_duong_dan_thu_muc_han_che(self):
        m, g, log, _f = _nap(PHIEU, CAU_HINH)
        self.assertTrue(m.duoc_soi_guong_phieu(CTR, "CTR-K"))
        kq = m.tai_len(CTR, "/private/files/hd.docx", "hd.docx", "CTR-K", token="T")
        self.assertEqual(kq["item_id"], "ITEM-NEW")
        self.assertEqual(g.uploads(), ["%s/sites/site/drive/root:/%s:/createUploadSession"
                                       % (G, quote("%s/CTR-K/hd.docx" % THU_MUC))])
        self.assertEqual(_co_log_it(log), [])

    def test_dau_gach_hai_dau_trong_cau_hinh_duoc_bo(self):
        m, _g, _l, _f = _nap(PHIEU, {"ec_sp_kol_folder": "/%s/" % THU_MUC})
        self.assertEqual(m.phan_loai_phieu(CTR, "CTR-K"), ("han_che", THU_MUC))

    def test_ket_qua_kiem_quyen_duoc_nho_khong_hoi_graph_moi_tep(self):
        m, g, _l, _f = _nap(PHIEU, CAU_HINH)
        for i in range(3):
            m.tai_len(CTR, "/f/%d.docx" % i, "%d.docx" % i, "CTR-K", token="T")
        self.assertEqual(len(g.doc_quyen()), 1, "cache 10 phut: moi tep khong goi lai Graph")
        self.assertEqual(len(g.uploads()), 3)
        self.assertEqual(m.CACHE_AN_TOAN_GIAY, 600)

    def test_hop_dong_thuong_van_vao_thu_muc_chung_khong_kiem_quyen(self):
        m, g, _l, _f = _nap(PHIEU, CAU_HINH)
        m.tai_len(CTR, "/f/a.docx", "a.docx", "CTR-S", token="T")
        self.assertEqual(g.uploads(), ["%s/sites/site/drive/root:/%s:/createUploadSession"
                                       % (G, quote("Contract Review/CTR-S/a.docx"))])
        self.assertEqual(g.doc_quyen(), [])

    def test_khong_bao_gio_tao_thu_muc_hay_cap_quyen_thu_muc(self):
        src = _doan(MIRROR, "kiem_quyen_thu_muc", "thu_muc_an_toan", "_chot_truoc_khi_tai", "canh_bao_it")
        for cam in ("requests.post", "requests.patch", "requests.delete", "/invite", "createLink",
                    "/children", "cap_quyen("):
            self.assertNotIn(cam, src, "chot an toan chi DOC - quan quyen o mot cho (IT)")


# --------------------------------------------------------------------------- 3. khong an toan
class ThuMucKhongAnToan(unittest.TestCase):
    def _khong_len(self, graph, ly_do_chua):
        m, g, log, _f = _nap(PHIEU, CAU_HINH, graph)
        self.assertFalse(m.duoc_soi_guong_phieu(CTR, "CTR-K"))
        with self.assertRaises(m.SharePointChuaSan):
            m.tai_len(CTR, "/f/hd.docx", "hd.docx", "CTR-K", token="T")
        self.assertEqual(g.uploads(), [], "khong an toan thi khong tai")
        self.assertEqual(m.dong_bo_phieu(CTR, "CTR-K")["so_tep"], 0)
        it = _co_log_it(log)
        self.assertEqual(len(it), 1, "canh bao IT dung MOT lan (mot lan/gio)")
        self.assertIn(ly_do_chua, it[0][0])
        self.assertIn(THU_MUC, it[0][0])
        return m, g, log

    def test_con_quyen_ke_thua(self):
        q = [{"roles": ["write"], "inheritedFrom": {"path": "/drive/root:"},
              "grantedToV2": {"siteGroup": {"displayName": "Operation Members"}}}]
        self._khong_len(Graph(quyen=q), "kế thừa")

    def test_inheritedFrom_rong_van_tinh_la_ke_thua(self):
        q = [{"roles": ["read"], "inheritedFrom": {},
              "grantedToV2": {"siteGroup": {"displayName": "ERP - Hợp đồng KOL"}}}]
        self._khong_len(Graph(quyen=q), "kế thừa")

    def test_thu_muc_chua_ton_tai(self):
        self._khong_len(Graph(ton_tai=False), "chưa tồn tại")

    def test_duong_dan_la_tep_khong_phai_thu_muc(self):
        self._khong_len(Graph(la_thu_muc=False), "không phải thư mục")

    def test_graph_loi_mang(self):
        self._khong_len(Graph(boom=True), "không gọi được Graph")

    def test_graph_tu_choi_doc_quyen(self):
        self._khong_len(Graph(ma_quyen=403), "403")

    def test_khong_doc_duoc_quyen_nao(self):
        self._khong_len(Graph(quyen=[]), "không xác minh")

    def test_link_ca_cong_ty(self):
        q = [{"roles": ["read"], "link": {"scope": "organization", "type": "view"}}]
        self._khong_len(Graph(quyen=q), "organization")

    def test_ngat_ke_thua_nhung_con_chep_nhom_members(self):
        q = [{"roles": ["write"], "grantedToV2": {"siteGroup": {"displayName": "Operation Members"}}},
             {"roles": ["write"], "grantedToV2": {"siteGroup": {"displayName": "ERP - Hợp đồng KOL"}}}]
        self._khong_len(Graph(quyen=q), "Operation Members")

    def test_canh_bao_khong_spam_va_ket_qua_duoc_nho(self):
        q = [{"roles": ["write"], "inheritedFrom": {"id": "ROOT"}}]
        m, g, log = self._khong_len(Graph(quyen=q), "kế thừa")
        so_goi = len(g.calls)
        for _i in range(5):
            m.duoc_soi_guong_phieu(CTR, "CTR-K")
        self.assertEqual(len(_co_log_it(log)), 1)
        self.assertEqual(len(g.calls), so_goi, "ket qua 'chua an toan' cung duoc nho 10 phut")
        self.assertEqual(m.CANH_BAO_GIAY, 3600)

    def test_hoi_db_loi_thi_khong_len(self):
        m, g, log, _f = _nap({"CTR-X": RuntimeError("db")}, CAU_HINH)
        self.assertFalse(m.duoc_soi_guong_phieu(CTR, "CTR-X"))
        self.assertEqual(g.calls, [])
        self.assertTrue(log)


# --------------------------------------------------------------------------- 4. lao dong
class LaoDongKhongBaoGio(unittest.TestCase):
    def test_lao_dong_khong_len_ke_ca_thu_muc_kol_an_toan(self):
        m, g, _l, _f = _nap(PHIEU, CAU_HINH)
        self.assertEqual(m.phan_loai_phieu(CTR, "CTR-L")[0], "bo_qua")
        self.assertFalse(m.duoc_soi_guong_phieu(CTR, "CTR-L"))
        self.assertFalse(m.duoc_soi_guong_phieu(CTR, "CTR-L", kiem_quyen=False))
        with self.assertRaises(m.SharePointChuaSan):
            m.tai_len(CTR, "/f/hd.docx", "hd.docx", "CTR-L", token="T")
        with self.assertRaises(m.SharePointChuaSan):
            m.tai_len(CTR, "/f/hd.docx", "hd.docx", "CTR-L", token="T", item_id="ITEM-CU")
        with self.assertRaises(m.SharePointChuaSan):
            m.duong_dan(CTR, "CTR-L", "hd.docx")
        self.assertIn("bo_qua", m.dong_bo_mot_tep(CTR, "CTR-L", "/f/hd.docx"))
        self.assertEqual(g.calls, [])

    def test_service_lao_dong_khong_hoi_cong_chung(self):
        hoi = []
        ns = {"frappe": types.SimpleNamespace(
                  db=types.SimpleNamespace(get_value=lambda dt, n, f: {"L": LABOR, "K": KOL, "S": SALES}[n]),
                  log_error=lambda *a, **k: hoi.append("log"), get_traceback=lambda: ""),
              "BUSINESS_DT": CTR,
              "esign_flow": types.SimpleNamespace(LABOR_CONTRACT_TYPE=LABOR, KOL_CONTRACT_TYPE=KOL)}
        exec(compile(_doan(SERVICE, "_KHONG_LEN_SHAREPOINT", "_is_labor"), "<s>", "exec"), ns)
        cho_phep = {"K": False, "S": True}

        def _cong(dt, n, kiem_quyen=True):
            hoi.append((n, kiem_quyen))
            return cho_phep[n]
        ns["_mirror"] = lambda: types.SimpleNamespace(duoc_soi_guong_phieu=_cong)
        self.assertTrue(ns["_is_labor"]("L"))
        self.assertEqual(hoi, [], "lao dong chot ngay o feature")
        self.assertTrue(ns["_is_labor"]("K"), "KOL chua cau hinh -> khong xep viec")
        cho_phep["K"] = True
        self.assertFalse(ns["_is_labor"]("K"), "KOL da cau hinh -> xep viec, job chot quyen")
        self.assertFalse(ns["_is_labor"]("S"))
        self.assertTrue(all(k is False for _n, k in [h for h in hoi if isinstance(h, tuple)]),
                        "service chi xet cau hinh, khong goi Graph trong giao dich gui")

        def _no(*a, **k):
            raise RuntimeError("x")
        ns["_mirror"] = lambda: types.SimpleNamespace(duoc_soi_guong_phieu=_no)
        self.assertTrue(ns["_is_labor"]("S"), "loi -> fail-closed")


# --------------------------------------------------------------------------- CC
class KhongCapQuyenChoCC(unittest.TestCase):
    def _nguoi(self, ten):
        m, _g, _l, fr = _nap(PHIEU, CAU_HINH)
        fr.get_meta = lambda dt: types.SimpleNamespace(has_field=lambda f: f == "cc_to")
        goc = fr.db.get_value

        def get_value(dt, filters, field=None, *a, **k):
            if dt == CTR and isinstance(field, list):
                return {"requested_by": "lap@ec.vn", "approval_request": None, "cc_to": "cc@ec.vn"}
            if dt == "User":
                return 1
            return goc(dt, filters, field, *a, **k)
        fr.db.get_value = get_value
        m._phieu_duyet_theo_tham_chieu = lambda *a: None
        return m.nguoi_trong_luong(CTR, ten)

    def test_kol_khong_gom_cc_hop_dong_thuong_van_gom(self):
        self.assertEqual(self._nguoi("CTR-K"), ["lap@ec.vn"])
        self.assertEqual(self._nguoi("CTR-S"), ["lap@ec.vn", "cc@ec.vn"])


# --------------------------------------------------------------------------- nhat quan
class NhatQuanMoiCho(unittest.TestCase):
    def test_them_tep_o_buoc_duyet_chot_theo_phieu(self):
        src = _doan(ADD_FILE, "_mirror_new_file")
        self.assertIn("sp.duoc_soi_guong_phieu(doctype, name, kiem_quyen=False)", src)

    def test_ban_doi_chung_chot_theo_phieu(self):
        src = _doan(SNAPSHOT, "chup_quyet_dinh")
        self.assertIn("mirror.duoc_soi_guong_phieu(ref.reference_doctype, ref.reference_name, "
                      "kiem_quyen=False)", src)

    def _gan(self, cong):
        sp = types.ModuleType("ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror")
        sp.duoc_soi_guong = lambda dt: dt == CTR
        sp.duoc_soi_guong_phieu = cong
        pkg = types.ModuleType("ecentric_workspace.approval_center.shared.integrations")
        pkg.sharepoint_mirror = sp
        gia = {pkg.__name__: pkg, sp.__name__: sp}
        for p in ("ecentric_workspace", "ecentric_workspace.approval_center",
                  "ecentric_workspace.approval_center.shared"):
            gia.setdefault(p, sys.modules.get(p) or types.ModuleType(p))
        log = []
        ns = {"frappe": types.SimpleNamespace(log_error=lambda *a, **k: log.append(a),
                                              get_traceback=lambda: ""),
              "gan_sharepoint": lambda att, appr: [dict(a, sp_web_url="https://sp") for a in att]}
        exec(compile(_doan(QUERY, "_gan_sharepoint_cua_phieu"), "<q>", "exec"), ns)
        cu = {k: sys.modules.get(k) for k in gia}
        sys.modules.update(gia)
        try:
            return {n: ns["_gan_sharepoint_cua_phieu"](dt, n, [{"file_url": "/f"}], [])
                    for dt, n in ((CTR, "CTR-K"), (CTR, "CTR-L"), (CTR, "CTR-S"), ("EC Leave", "LV-1"))}
        finally:
            for k, v in cu.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_link_mo_online_theo_cung_cong(self):
        cho = {"CTR-K": False, "CTR-L": False, "CTR-S": True}
        kq = self._gan(lambda dt, n, kiem_quyen=True: (kiem_quyen is False) and cho[n])
        self.assertNotIn("sp_web_url", kq["CTR-K"][0], "KOL chua cau hinh: khong hien link")
        self.assertNotIn("sp_web_url", kq["CTR-L"][0], "lao dong: khong bao gio hien link")
        self.assertIn("sp_web_url", kq["CTR-S"][0])
        self.assertIn("sp_web_url", kq["LV-1"][0], "loai phieu ngoai danh sach: giu hanh vi cu")
        cho["CTR-K"] = True
        self.assertIn("sp_web_url", self._gan(lambda dt, n, kiem_quyen=True: cho[n])["CTR-K"][0])

    def test_link_loi_thi_khong_gan(self):
        def _no(*a, **k):
            raise RuntimeError("x")
        self.assertNotIn("sp_web_url", self._gan(_no)["CTR-S"][0])

    def test_detail_goi_qua_cong(self):
        src = io.open(str(QUERY), encoding="utf-8").read()
        self.assertIn("attachments = _gan_sharepoint_cua_phieu(definition.business_doctype, name,", src)
        self.assertNotIn("attachments = gan_sharepoint(", src)


# --------------------------------------------------------------------------- 5. dong bo lai
def _nap_probe(sp, method="GET", roles=("System Manager",), phieu=None):
    w = types.SimpleNamespace(enqueued=[])
    fr = types.ModuleType("frappe")
    fr.local = types.SimpleNamespace(request=types.SimpleNamespace(method=method))
    fr.session = types.SimpleNamespace(user="sm@e.c")
    fr.get_roles = lambda u: list(roles)
    fr._ = lambda s: s
    fr.whitelist = lambda *a, **k: (lambda f: f)
    fr.PermissionError = PermissionError

    def throw(msg, exc=Exception):
        raise exc(msg)
    fr.throw = throw
    phieu = phieu if phieu is not None else [
        {"name": "EC-CTR-2026-00130", "approval_request": "AR-130", "st": "Pending",
         "tep": [("hd.docx", "/f/130.docx")], "co": []},
        {"name": "CTR-DA-CO", "approval_request": "AR-2", "st": "Pending",
         "tep": [("a.docx", "/f/a.docx")], "co": ["/f/a.docx"]},
        {"name": "CTR-XONG", "approval_request": "AR-3", "st": "Approved",
         "tep": [("b.docx", "/f/b.docx")], "co": []}]
    theo = {p["name"]: p for p in phieu}

    def get_all(dt, filters=None, fields=None, pluck=None, **k):
        if dt == CTR:
            assert filters["contract_type"] == KOL
            return [{"name": p["name"], "approval_request": p["approval_request"]} for p in phieu]
        if dt == sp.LINK_DT:
            return list(theo[filters["business_name"]]["co"])
        return []
    fr.get_all = get_all
    fr.db = types.SimpleNamespace(
        get_value=lambda dt, n, f: next(p["st"] for p in phieu if p["approval_request"] == n),
        exists=lambda *a, **k: True)
    fr.enqueue = lambda method, **kw: w.enqueued.append((method, kw))
    sp._dinh_kem = lambda dt, n: [{"file_name": a, "file_url": b} for a, b in theo[n]["tep"]]
    kol = types.ModuleType("ecentric_workspace.approval_center.features.contract_review.domain.kol")
    kol.KOL_CONTRACT_TYPE = KOL
    dom = types.ModuleType("ecentric_workspace.approval_center.features.contract_review.domain")
    dom.kol = kol
    integ = types.ModuleType("ecentric_workspace.approval_center.shared.integrations")
    integ.sharepoint_mirror = sp
    gia = {"frappe": fr, dom.__name__: dom, kol.__name__: kol, integ.__name__: integ,
           "ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror": sp}
    for p in ("ecentric_workspace", "ecentric_workspace.approval_center",
              "ecentric_workspace.approval_center.shared", "ecentric_workspace.approval_center.features",
              "ecentric_workspace.approval_center.features.contract_review"):
        gia.setdefault(p, sys.modules.get(p) or types.ModuleType(p))
    cu = {k: sys.modules.get(k) for k in gia}
    sys.modules.update(gia)
    try:
        spec = importlib.util.spec_from_file_location("probe_kol", str(PROBE))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    finally:
        for k, v in cu.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return m, w


class DongBoLai(unittest.TestCase):
    def _sp(self, conf=CAU_HINH, graph=None):
        m, g, log, _f = _nap(PHIEU, conf, graph)
        return m, g

    def test_chi_system_manager(self):
        sp, _g = self._sp()
        m, w = _nap_probe(sp, roles=("Accounts User",))
        with self.assertRaises(PermissionError):
            m.dong_bo_lai_kol()
        self.assertEqual(w.enqueued, [])

    def test_mac_dinh_chay_thu_khong_ghi_va_liet_ke_dung(self):
        sp, g = self._sp()
        m, w = _nap_probe(sp, method="POST")
        bao = m.dong_bo_lai_kol()
        self.assertEqual(w.enqueued, [])
        self.assertEqual([p["name"] for p in bao["phieu"]], ["EC-CTR-2026-00130"])
        self.assertEqual(bao["phieu"][0]["tep_thieu"], ["hd.docx"])
        self.assertEqual(g.uploads(), [])
        self.assertTrue(bao["buoc"][-1]["ok"])
        self.assertIn("quyen_thu_muc", bao)

    def test_ghi_that_qua_POST_xep_viec_dong_bo_idempotent(self):
        sp, _g = self._sp()
        m, w = _nap_probe(sp, method="POST")
        m.dong_bo_lai_kol(dry_run=0)
        ((method, kw),) = w.enqueued
        self.assertTrue(method.endswith("sharepoint_mirror.dong_bo_nen"))
        self.assertEqual((kw["business_doctype"], kw["business_name"]), (CTR, "EC-CTR-2026-00130"))
        self.assertIs(kw["enqueue_after_commit"], True)

    def test_ghi_that_qua_GET_khong_xep(self):
        sp, _g = self._sp()
        m, w = _nap_probe(sp, method="GET")
        bao = m.dong_bo_lai_kol(dry_run=0)
        self.assertEqual(w.enqueued, [])
        self.assertFalse(bao["buoc"][-1]["ok"])

    def test_thu_muc_chua_an_toan_khong_xep(self):
        sp, _g = self._sp(graph=Graph(quyen=[{"roles": ["read"], "inheritedFrom": {"id": "R"}}]))
        m, w = _nap_probe(sp, method="POST")
        bao = m.dong_bo_lai_kol(dry_run=0)
        self.assertEqual(w.enqueued, [])
        self.assertFalse(bao["buoc"][-1]["ok"])

    def test_chua_cau_hinh_dung_ngay(self):
        sp, g = self._sp(conf={})
        m, w = _nap_probe(sp, method="POST")
        bao = m.dong_bo_lai_kol(dry_run=0)
        self.assertEqual(w.enqueued, [])
        self.assertEqual(g.calls, [])
        self.assertFalse(bao["buoc"][-1]["ok"])

    def test_kiem_tuoi_ghi_de_cache_cu(self):
        """IT vua sua xong: lan kiem tuoi cua ham dong bo lai phai thay ket qua 'chua an toan' cu
        trong cache, neu khong job nen se bo qua het toi 10 phut."""
        sp, g = self._sp()
        sp.ghi_nho_an_toan(THU_MUC, False, "cu")
        m, _w = _nap_probe(sp, method="POST")
        m.dong_bo_lai_kol(dry_run=0)
        self.assertEqual(sp.thu_muc_an_toan(THU_MUC), (True, ""))

    def test_khong_phai_patch_tu_chay(self):
        hooks = io.open(str(APP / "hooks.py"), encoding="utf-8").read()
        patches = io.open(str(APP / "patches.txt"), encoding="utf-8").read()
        self.assertNotIn("dong_bo_lai_kol", hooks + patches)


if __name__ == "__main__":
    unittest.main()
