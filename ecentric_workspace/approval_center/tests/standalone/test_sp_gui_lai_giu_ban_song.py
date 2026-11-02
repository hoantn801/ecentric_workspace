# Copyright (c) 2026, eCentric and contributors
"""Gui lai Contract Review KHONG duoc de len ban song tren SharePoint (03/11/2026, QA t3).

LOI (🔴 mat du lieu). `resubmit` -> `_soi_guong_sharepoint` -> `dong_bo_phieu` tai lai MOI dinh
kem tu Frappe voi conflictBehavior=replace. Ban tren SharePoint la ban SONG - nguoi duyet sua
track changes + comment truc tiep tren do. Gui lai = ban Frappe (cu) de len, cong cua ho mat sach.

Chay module THAT (`sharepoint_mirror.py`) voi frappe gia + Graph gia (ghi lai moi lenh HTTP):

    python3 -m pytest -q ecentric_workspace/approval_center/tests/standalone/test_sp_gui_lai_giu_ban_song.py
"""
import datetime as _dt
import hashlib
import importlib.util
import pathlib
import sys
import types

APP = pathlib.Path(__file__).resolve().parents[2].parent
CTR = "EC Contract Review Request"
LINK = "EC SharePoint File Link"
URL = "/private/files/HopDong.docx"
NOI_DUNG = b"PK hop dong ban 1"


def _bam(b):
    return hashlib.sha256(b).hexdigest()


class Obj(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v


def _pkg(name):
    if name not in sys.modules or not isinstance(sys.modules[name], types.ModuleType):
        sys.modules[name] = types.ModuleType(name)
    return sys.modules[name]


class _Resp(object):
    def __init__(self, code, payload=None):
        self.status_code = code
        self._p = payload or {}
        self.text = str(self._p)

    def json(self):
        return self._p


class Graph(object):
    """Graph gia. `co_san` = cac duong dan DA co tep (ten so khong phan biet hoa/thuong nhu
    SharePoint). `moc_sua` = lastModifiedDateTime (UTC) cua tung item."""

    def __init__(self, co_san=(), moc_sua=None, moc_sua_loi=False):
        self.co_san = {p.lower() for p in co_san}
        self.moc_sua = dict(moc_sua or {})
        self.moc_sua_loi = moc_sua_loi
        self.goi = []
        self._phien = {}
        self._dem = 0

    def post(self, url, headers=None, json=None, timeout=None):
        self.goi.append(("POST", url, json))
        if url.endswith("/createUploadSession"):
            self._dem += 1
            up = "https://up/%d" % self._dem
            hv = ((json or {}).get("item") or {}).get("@microsoft.graph.conflictBehavior")
            if "/root:/" in url:
                from urllib.parse import unquote
                rel = unquote(url.split("/root:/", 1)[1].rsplit(":/createUploadSession", 1)[0])
                if rel.lower() in self.co_san and hv != "replace":
                    return _Resp(409, {"error": {"code": "nameAlreadyExists"}})
                self._phien[up] = ("path", rel)
            else:
                item = url.split("/items/", 1)[1].split("/", 1)[0]
                self._phien[up] = ("item", item)
            return _Resp(200, {"uploadUrl": up})
        if url.endswith("/createLink"):
            item = url.split("/items/", 1)[1].split("/", 1)[0]
            return _Resp(200, {"link": {"webUrl": "https://share/" + item}})
        return _Resp(404)

    def put(self, url, headers=None, data=None, timeout=None):
        self.goi.append(("PUT", url, None))
        kieu, gia_tri = self._phien[url]
        if kieu == "path":
            self.co_san.add(gia_tri.lower())
            item = "IT-" + gia_tri.rsplit("/", 1)[-1]
        else:
            item = gia_tri
        return _Resp(201, {"id": item, "webUrl": "https://sp/" + item,
                           "lastModifiedDateTime": "2026-11-03T03:00:00Z"})

    def get(self, url, headers=None, timeout=None):
        self.goi.append(("GET", url, None))
        if "/items/" in url and "lastModifiedDateTime" in url:
            if self.moc_sua_loi:
                return _Resp(503)
            item = url.split("/items/", 1)[1].split("?", 1)[0]
            if item in self.moc_sua:
                return _Resp(200, {"id": item, "lastModifiedDateTime": self.moc_sua[item]})
            return _Resp(404)
        return _Resp(404)

    # ---- tien ich cho test --------------------------------------------------------------
    def tai_len(self):
        return [g for g in self.goi if g[0] == "PUT"]

    def phien(self):
        return [g for g in self.goi if g[1].endswith("/createUploadSession")]

    def cap_link(self):
        return [g[1].split("/items/", 1)[1].split("/", 1)[0] for g in self.goi
                if g[1].endswith("/createLink")]


def _match(row, filters):
    for k, v in (filters or {}).items():
        if row.get(k) != v:
            return False
    return True


def _nap(files, links, graph, noi_dung=None, co_cot_bam=True):
    """files: [dict(name, file_url, file_name, attached_to_*, creation)]; links: {ten: dict}."""
    noi_dung = noi_dung if noi_dung is not None else {URL: NOI_DUNG}
    W = types.SimpleNamespace(log=[], saved=[])

    class _LinkDoc(Obj):
        def save(self, ignore_permissions=False):
            if not self.get("name"):
                self["name"] = "L%d" % (len(links) + 1)
            links[self["name"]] = dict(self)
            W.saved.append(self["name"])

    class _FileDoc(Obj):
        def get_content(self):
            return noi_dung[self["file_url"]]

    def get_value(dt, filters, fields=None, as_dict=False, **k):
        if dt == "File":
            r = next((f for f in files if f["file_url"] == filters.get("file_url")), None)
            return r and r["name"]
        if dt == LINK:
            r = next(((n, l) for n, l in links.items() if _match(l, filters)), None)
            if not r:
                return None
            n, l = r
            if as_dict:
                return Obj({f: (n if f == "name" else l.get(f)) for f in fields})
            if isinstance(fields, str):
                return n if fields == "name" else l.get(fields)
            return n
        return None

    def get_doc(dt, name=None):
        if dt == "File":
            return _FileDoc(next(f for f in files if f["name"] == name))
        if dt == LINK:
            d = _LinkDoc(links[name])
            d["name"] = name
            return d
        raise KeyError(dt)

    def get_all(dt, filters=None, fields=None, order_by=None, **k):
        if dt == "File":
            rows = [Obj(f) for f in files if _match(f, filters)]
            return sorted(rows, key=lambda r: r.get("creation") or _dt.datetime.min)
        return []

    fr = types.ModuleType("frappe")
    fr.db = types.SimpleNamespace(get_value=get_value,
                                  has_column=lambda dt, col: co_cot_bam)
    fr.get_doc = get_doc
    fr.new_doc = lambda dt: _LinkDoc()
    fr.get_all = get_all
    fr.log_error = lambda *a, **k: W.log.append(a)
    fr.get_traceback = lambda: "tb"
    fu = types.ModuleType("frappe.utils")
    fu.now_datetime = lambda: _dt.datetime(2026, 11, 3, 10, 0, 5)

    def _gd(v):
        if isinstance(v, _dt.datetime):
            return v
        return _dt.datetime.strptime(str(v)[:19], "%Y-%m-%d %H:%M:%S")
    fu.get_datetime = _gd
    fu.convert_utc_to_system_timezone = lambda d: d + _dt.timedelta(hours=7)
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = fu
    wr = types.ModuleType("ecentric_workspace.weekly_report.sharepoint")
    wr.safe_filename = lambda n: (n or "").replace(":", "_")
    wr.get_app_token = lambda: "TOKEN"
    wr.GRAPH, wr.SITE_ID = "https://graph", "site"
    wr.create_deck_upload_session = lambda rel, token: graph.post(
        "https://graph/sites/site/drive/root:/%s:/createUploadSession" % rel,
        json={"item": {"@microsoft.graph.conflictBehavior": "replace"}}).json()["uploadUrl"]
    _pkg("ecentric_workspace")
    _pkg("ecentric_workspace.weekly_report").sharepoint = wr
    sys.modules["ecentric_workspace.weekly_report.sharepoint"] = wr
    spec = importlib.util.spec_from_file_location(
        "sp_mirror_gui_lai", APP / "approval_center/shared/integrations/sharepoint_mirror.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._requests = lambda: graph
    mod.nguoi_trong_luong = lambda dt, bn: ["req@ec.vn", "lead@ec.vn", "fin@ec.vn"]
    mod.tep_doi_chung = lambda dt, bn: set()
    return mod, W


def _file(name="F1", url=URL, ten="HopDong.docx", phieu="CTR-1", tao=None):
    return dict(name=name, file_url=url, file_name=ten, attached_to_doctype=CTR,
                attached_to_name=phieu, creation=tao or _dt.datetime(2026, 11, 1, 9, 0))


def _link(phieu="CTR-1", bam=None, item="ITEM-SONG", tai_luc=_dt.datetime(2026, 11, 1, 9, 0, 10)):
    return dict(file_url=URL, business_doctype=CTR, business_name=phieu, sp_item_id=item,
                sp_web_url="https://sp/" + item, sp_share_url="https://share/cu",
                sp_uploaded_at=tai_luc, sp_last_modified=tai_luc, sp_synced_at=tai_luc,
                sp_granted_to="req@ec.vn", sp_content_hash=bam)


# 2026-11-01 09:00:10 gio he thong = 02:00:10Z
MOC_TAI_LEN_UTC = "2026-11-01T02:00:10Z"
MOC_NGUOI_SUA_UTC = "2026-11-02T03:15:00Z"


# ---- 1. Tep KHONG doi -> khong tai, chi cap quyen --------------------------------------
def test_gui_lai_tep_khong_doi_thi_KHONG_tai_len_chi_cap_quyen():
    g = Graph(co_san=["Contract Review/CTR-1/HopDong.docx"],
              moc_sua={"ITEM-SONG": MOC_NGUOI_SUA_UTC})
    links = {"L1": _link(bam=_bam(NOI_DUNG))}
    mod, W = _nap([_file()], links, g)
    kq = mod.dong_bo_phieu(CTR, "CTR-1")
    assert g.tai_len() == [], "gui lai da TAI DE len ban song - xoa track changes cua nguoi duyet"
    assert g.phien() == []
    assert g.cap_link() == ["ITEM-SONG"], "van phai cap quyen cho nguoi trong luong HIEN TAI"
    assert kq["giu_ban_song"] == ["HopDong.docx"] and kq["hong"] == []
    l1 = links["L1"]
    assert l1["sp_share_url"] == "https://share/ITEM-SONG"
    assert "fin@ec.vn" in l1["sp_granted_to"]
    # Moc nen KHONG doi: day khong phai lan tai len - bang canh bao van so dung.
    assert l1["sp_uploaded_at"] == _dt.datetime(2026, 11, 1, 9, 0, 10)


def test_ban_ghi_cu_chua_co_ma_bam_va_tep_khong_bi_thay_thi_KHONG_tai():
    g = Graph(co_san=["Contract Review/CTR-1/HopDong.docx"])
    links = {"L1": _link(bam=None)}
    mod, W = _nap([_file(tao=_dt.datetime(2026, 11, 1, 8, 59))], links, g)
    mod.dong_bo_phieu(CTR, "CTR-1")
    assert g.tai_len() == []
    assert g.cap_link() == ["ITEM-SONG"]


def test_truoc_migrate_chua_co_cot_ma_bam_van_chay():
    g = Graph(co_san=["Contract Review/CTR-1/HopDong.docx"])
    links = {"L1": _link(bam=None)}
    mod, W = _nap([_file(tao=_dt.datetime(2026, 11, 1, 8, 59))], links, g, co_cot_bam=False)
    kq = mod.dong_bo_phieu(CTR, "CTR-1")
    assert kq["hong"] == [] and g.tai_len() == []


# ---- 2. Tep DOI + ban song chua ai sua -> ghi de DUNG item ----------------------------
def test_tep_doi_ban_song_chua_sua_thi_ghi_de_dung_item():
    g = Graph(co_san=["Contract Review/CTR-1/HopDong.docx"],
              moc_sua={"ITEM-SONG": MOC_TAI_LEN_UTC})
    links = {"L1": _link(bam=_bam(b"ban cu"))}
    mod, W = _nap([_file()], links, g)
    kq = mod.dong_bo_phieu(CTR, "CTR-1")
    assert [p[1] for p in g.phien()] == [
        "https://graph/sites/site/drive/items/ITEM-SONG/createUploadSession"]
    assert kq["xong"] == ["HopDong.docx"]
    assert links["L1"]["sp_item_id"] == "ITEM-SONG"
    assert links["L1"]["sp_content_hash"] == _bam(NOI_DUNG)


# ---- 3. Tep DOI + ban song DA bi sua -> tep RIENG, ban song giu nguyen -----------------
def test_tep_doi_nhung_ban_song_da_bi_sua_thi_tai_thanh_tep_rieng():
    g = Graph(co_san=["Contract Review/CTR-1/HopDong.docx"],
              moc_sua={"ITEM-SONG": MOC_NGUOI_SUA_UTC})
    links = {"L1": _link(bam=_bam(b"ban cu"))}
    mod, W = _nap([_file()], links, g)
    kq = mod.dong_bo_phieu(CTR, "CTR-1")
    assert kq["hong"] == []
    assert not any("/items/ITEM-SONG/createUploadSession" in p[1] for p in g.phien()), \
        "ghi de ban song da co nguoi sua"
    assert all(((p[2] or {}).get("item") or {}).get("@microsoft.graph.conflictBehavior") == "fail"
               for p in g.phien())
    assert links["L1"]["sp_item_id"] == "IT-HopDong (2).docx"
    assert any("giu ban song" in str(a) for a in W.log), "phai de lai vet cho quan tri"


def test_khong_doc_duoc_moc_sua_thi_coi_nhu_da_sua_KHONG_ghi_de():
    g = Graph(co_san=["Contract Review/CTR-1/HopDong.docx"], moc_sua_loi=True)
    links = {"L1": _link(bam=_bam(b"ban cu"))}
    mod, W = _nap([_file()], links, g)
    mod.dong_bo_phieu(CTR, "CTR-1")
    assert not any("/items/" in p[1] for p in g.phien())


def test_ban_ghi_cu_tep_bi_go_ra_tai_lai_cung_ten_va_ban_song_da_sua():
    """Ban ghi truoc 03/11 (khong ma bam), nguoi gui go tep roi tai lai cung ten -> File moi
    tao SAU lan dong bo. Ban song da co nguoi sua -> khong duoc de."""
    g = Graph(co_san=["Contract Review/CTR-1/HopDong.docx"],
              moc_sua={"ITEM-SONG": MOC_NGUOI_SUA_UTC})
    links = {"L1": _link(bam=None)}
    mod, W = _nap([_file(tao=_dt.datetime(2026, 11, 3, 8, 0))], links, g)
    mod.dong_bo_phieu(CTR, "CTR-1")
    assert not any("/items/ITEM-SONG/createUploadSession" in p[1] for p in g.phien())
    assert links["L1"]["sp_item_id"] == "IT-HopDong (2).docx"


# ---- 4. Tep MOI -> khong bao gio de tep dang co ---------------------------------------
def test_tep_moi_trung_ten_tep_dang_co_thi_doi_ten_khong_de():
    """Vd tep cu da bi go khoi phieu nhung ban song (co comment) van con tren SharePoint."""
    g = Graph(co_san=["Contract Review/CTR-1/hopdong.docx"])
    mod, W = _nap([_file()], {}, g)
    kq = mod.dong_bo_phieu(CTR, "CTR-1")
    assert kq["xong"] == ["HopDong.docx"]
    hv = [((p[2] or {}).get("item") or {}).get("@microsoft.graph.conflictBehavior") for p in g.phien()]
    assert hv == ["fail", "fail"], hv
    assert "IT-HopDong (2).docx" in g.cap_link()


def test_khong_bao_gio_replace_theo_duong_dan():
    for co_san in ([], ["Contract Review/CTR-1/HopDong.docx"]):
        g = Graph(co_san=co_san, moc_sua={"ITEM-SONG": MOC_NGUOI_SUA_UTC})
        mod, W = _nap([_file()], {"L1": _link(bam=_bam(b"x"))} if co_san else {}, g)
        mod.dong_bo_phieu(CTR, "CTR-1")
        for p in g.phien():
            if "/root:/" in p[1]:
                assert p[2]["item"]["@microsoft.graph.conflictBehavior"] == "fail"


def test_phieu_tao_lai_dung_chung_file_url_KHONG_cap_quyen_vao_ban_song_cua_phieu_cu():
    """clone_request chep File dung CHUNG file_url. Lien ket dang thuoc phieu CU (CTR-1)."""
    g = Graph()
    links = {"L1": _link(phieu="CTR-1", bam=_bam(NOI_DUNG))}
    mod, W = _nap([_file(name="F9", phieu="CTR-2")], links, g)
    kq = mod.dong_bo_phieu(CTR, "CTR-2")
    assert "ITEM-SONG" not in g.cap_link(), "mo ban song cua phieu CU cho luong duyet phieu MOI"
    assert kq["xong"] == ["HopDong.docx"]
    assert any("Contract Review/CTR-2/" in p[1] or "CTR-2" in p[1] for p in g.phien())


def test_hai_ban_ghi_file_cung_url_chi_tai_mot_lan():
    g = Graph()
    files = [_file(name="F1"), _file(name="F2", tao=_dt.datetime(2026, 11, 1, 9, 0, 1))]
    mod, W = _nap(files, {}, g)
    kq = mod.dong_bo_phieu(CTR, "CTR-1")
    assert len(g.tai_len()) == 1 and kq["so_tep"] == 1


def test_ten_thay_the():
    mod, W = _nap([], {}, Graph())
    assert mod.ten_thay_the("HopDong.docx", 1) == "HopDong.docx"
    assert mod.ten_thay_the("HopDong.v2.docx", 3) == "HopDong.v2 (3).docx"
    assert mod.ten_thay_the("README", 2) == "README (2)"


def test_het_ten_thay_the_thi_bao_loi_khong_ghi_de():
    co = ["Contract Review/CTR-1/HopDong.docx"] + [
        "Contract Review/CTR-1/HopDong (%d).docx" % i for i in range(2, 21)]
    g = Graph(co_san=co)
    mod, W = _nap([_file()], {}, g)
    kq = mod.dong_bo_phieu(CTR, "CTR-1")
    assert kq["hong"] == ["HopDong.docx"] and g.tai_len() == []
