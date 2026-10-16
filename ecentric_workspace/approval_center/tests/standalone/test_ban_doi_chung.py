# Copyright (c) 2026, eCentric and contributors
"""Ban doi chung hop dong (16/10/2026): chup tep tren SharePoint tai MOI quyet dinh duyet.

Nhung dieu mat tien neu sai, va test nao giu chung:
  1. Chup dung: tai .docx goc + PDF, luu RIENG TU gan vao phieu, ban ghi du metadata (cap,
     nguoi, hanh dong, sha256, eTag, phien ban) va ten tep doc duoc.            -> ChupTep
  2. Idempotent: cung mot quyet dinh chay lai khong tai lai, khong sinh ban trung; noi dung
     trung byte voi ban truoc thi dung lai tep.                                 -> ChupTep
  3. Graph hong KHONG nem ra ngoai va khong de lai tep mo coi (tep khong dau moc se bi
     soi guong nguoc len SharePoint).                                           -> GraphHong
  4. Ban doi chung KHONG BAO GIO bi day len SharePoint / chep sang phieu moi / dem la dinh
     kem - loai theo DAU MOC (ten ban ghi File), ke ca khi trung file_url.     -> LoaiTru
  5. Engine chi goi nguoi nghe cho QUYET DINH, cua loai phieu da dang ky, va loi cua nguoi
     nghe khong lam hong lan duyet; Contract Review chi xep viec SAU commit.    -> Hook
  6. Quyen: danh sach chi nam trong `detail` SAU cong can_view; tep khong xoa duoc.  -> Quyen
Graph luon gia lap - khong co loi goi mang that nao.
"""
import ast
import datetime as _dt
import hashlib
import io
import json
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "patches")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()
_AC = os.path.join(_ROOT, "approval_center")
_SNAP = os.path.join(_AC, "shared", "integrations", "sharepoint_snapshot.py")
_MIRROR = os.path.join(_AC, "shared", "integrations", "sharepoint_mirror.py")
_ENGINE = os.path.join(_AC, "shared", "workflow", "transitions.py")
_SERVICE = os.path.join(_AC, "features", "contract_review", "application", "service.py")
_QUERY = os.path.join(_AC, "shared", "requests", "query_service.py")
_COMMAND = os.path.join(_AC, "shared", "requests", "command_service.py")
_DT_JSON = os.path.join(_AC, "doctype", "ec_sharepoint_snapshot", "ec_sharepoint_snapshot.json")

DT = "EC Contract Review Request"
SNAP_DT = "EC SharePoint Snapshot"


def _read(p):
    return io.open(p, encoding="utf-8").read()


def _doan(path, *ten):
    src = _read(path)
    tree = ast.parse(src)
    ra, con_lai = [], set(ten)
    for node in tree.body:
        nn = getattr(node, "name", None)
        if nn is None and isinstance(node, ast.Assign):
            nn = getattr(node.targets[0], "id", None)
        if nn in con_lai:
            ra.append(ast.get_source_segment(src, node))
            con_lai.discard(nn)
    if con_lai:
        raise AssertionError("khong thay %s trong %s" % (", ".join(sorted(con_lai)), path))
    return "\n\n".join(ra)


class _Row(dict):
    __getattr__ = dict.get


class _Throw(Exception):
    pass


class _Dup(Exception):
    pass


def _khop(row, filters):
    for k, v in (filters or {}).items():
        if isinstance(v, (list, tuple)) and len(v) == 2 and v[0] == "is":
            if bool(row.get(k)) != (v[1] == "set"):
                return False
        elif isinstance(v, (list, tuple)) and len(v) == 2 and v[0] == "in":
            if row.get(k) not in v[1]:
                return False
        elif row.get(k) != v:
            return False
    return True


class _Db(object):
    """CSDL gia co giao dich: ghi vao `staged`, commit moi chot, rollback thi bo."""

    def __init__(self, w):
        self.w = w

    def get_value(self, dt, name, fields=None, as_dict=False, **kw):
        row = self.w.rows(dt).get(name) if isinstance(name, str) else None
        if row is None:
            return None
        if isinstance(fields, (list, tuple)):
            return _Row({f: row.get(f) for f in fields}) if as_dict else [row.get(f) for f in fields]
        return row.get(fields)

    def exists(self, dt, filters=None):
        if isinstance(filters, str):
            return filters if filters in self.w.rows(dt) else None
        for n, r in self.w.rows(dt).items():
            if _khop(r, filters):
                return n
        return None

    def commit(self):
        self.w.staged = []

    def rollback(self):
        for dt, name in self.w.staged:
            self.w.tables[dt].pop(name, None)
        self.w.staged = []


class _Doc(_Row):
    def __init__(self, w, doctype, **kw):
        super(_Doc, self).__init__(doctype=doctype, **kw)
        self.__dict__["_w"] = w

    def __setattr__(self, k, v):
        self[k] = v

    def update(self, d):
        dict.update(self, d)

    def insert(self, ignore_permissions=False):
        w = self._w
        if self.get("doctype") == "File":
            w.n += 1
            self["name"] = "FILE-%d" % w.n
            self.setdefault("file_url", "/private/files/" + self["file_name"])
            w.file_bytes[self["name"]] = self.pop("content", None)
        else:
            if any(r.get("khoa") == self.get("khoa") for r in w.rows(self["doctype"]).values()):
                raise _Dup("Duplicate khoa")
            w.n += 1
            self["name"] = "%s-%d" % (self["doctype"], w.n)
            self["creation"] = w.n
        w.rows(self["doctype"])[self["name"]] = _Row(self)
        w.staged.append((self["doctype"], self["name"]))
        return self


class _World(object):
    def __init__(self):
        self.tables = {}
        self.staged = []
        self.n = 0
        self.file_bytes = {}
        self.logs = []
        self.enqueued = []

    def rows(self, dt):
        return self.tables.setdefault(dt, {})

    def put(self, dt, name, **kw):
        kw["name"] = name
        self.n += 1
        kw.setdefault("creation", self.n)
        self.rows(dt)[name] = _Row(kw)


def _frappe(w):
    f = types.ModuleType("frappe")
    f.db = _Db(w)
    f._dict = _Row
    f.flags = types.SimpleNamespace()
    f.session = types.SimpleNamespace(user="thu.trinh@ec.vn")
    f.DuplicateEntryError = _Dup
    f.PermissionError = _Throw

    def get_all(dt, filters=None, fields=None, order_by=None, limit_page_length=None, pluck=None, **kw):
        rows = [r for r in w.rows(dt).values() if _khop(r, filters)]
        rows.sort(key=lambda r: r.get("creation") or 0, reverse=bool(order_by and "desc" in order_by))
        if limit_page_length:
            rows = rows[:limit_page_length]
        if pluck:
            return [r.get(pluck) for r in rows]
        return [_Row({k: r.get(k) for k in fields}) if fields else _Row(r) for r in rows]

    f.get_all = get_all
    f.new_doc = lambda dt: _Doc(w, dt)
    f.get_doc = lambda d, name=None: _Doc(w, d["doctype"], **{k: v for k, v in d.items() if k != "doctype"})
    f.log_error = lambda *a, **k: w.logs.append(a)
    f.get_traceback = lambda: "tb"

    def throw(msg, exc=None):
        raise (exc or _Throw)(msg)

    f.throw = throw
    f._ = lambda s: s
    f.enqueue = lambda method, **kw: w.enqueued.append((method, kw))
    return f


def _get_datetime(v):
    if isinstance(v, _dt.datetime):
        return v
    return _dt.datetime.strptime(str(v)[:19], "%Y-%m-%d %H:%M:%S")


class _Resp(object):
    def __init__(self, code, js=None, content=b""):
        self.status_code = code
        self._js = js
        self.content = content
        self.text = "" if js is None else json.dumps(js)

    def json(self):
        return self._js


class _Graph(object):
    """Graph gia. `etags` = day eTag tra ve lan luot cho moi lan doc metadata."""

    def __init__(self, docx=b"PK\x03\x04 hop dong v1", pdf=b"%PDF-1.7 ban doc", pdf_code=200,
                 etags=None, boom=False):
        self.docx, self.pdf, self.pdf_code = docx, pdf, pdf_code
        self.etags = list(etags or [])
        self.boom = boom
        self.calls = []

    def get(self, url, headers=None, timeout=None, allow_redirects=True, **kw):
        self.calls.append((url, timeout))
        assert timeout, "moi loi goi Graph phai co timeout"
        assert (headers or {}).get("Authorization") == "Bearer TOKEN"
        if self.boom:
            raise IOError("mat mang")
        if "?$select=" in url:
            et = self.etags.pop(0) if self.etags else '"{E1},3"'
            return _Resp(200, {"id": "IT1", "eTag": et, "size": len(self.docx),
                               "lastModifiedDateTime": "2026-10-14T03:19:00Z",
                               "lastModifiedBy": {"user": {"email": "lien.vu@ec.vn"}}})
        if url.endswith("/versions"):
            return _Resp(200, {"value": [{"id": "2.0", "lastModifiedDateTime": "2026-10-13T01:00:00Z"},
                                         {"id": "3.0", "lastModifiedDateTime": "2026-10-14T03:19:00Z"}]})
        if url.endswith("/content?format=pdf"):
            return _Resp(self.pdf_code, {"error": "x"} if self.pdf_code != 200 else None, self.pdf)
        if url.endswith("/content"):
            return _Resp(200, None, self.docx)
        raise AssertionError("URL la: " + url)

    def downloads(self):
        return [u for u, _t in self.calls if u.endswith("/content")]


def _mirror_ns(w, f):
    """sharepoint_mirror THAT (phan can dung) tren frappe gia."""
    ns = {"frappe": f}
    exec(compile(_doan(_MIRROR, "THU_MUC_THEO_PHIEU", "LINK_DT", "SNAP_DT", "SharePointChuaSan",
                       "duoc_soi_guong", "tep_doi_chung", "_dinh_kem", "gio_he_thong"),
                 "<mirror>", "exec"), ns)
    # gio_he_thong goi frappe.utils - thay bang ban rut gon UTC+7.
    ns["gio_he_thong"] = lambda iso: (_get_datetime(str(iso).replace("T", " ").rstrip("Z"))
                                      + _dt.timedelta(hours=7)) if iso else None
    return types.SimpleNamespace(**ns)


def _nap_snapshot(w, graph):
    """Nap NGUYEN module sharepoint_snapshot.py voi frappe/wr_sp/mirror gia trong sys.modules."""
    f = _frappe(w)
    utils = types.ModuleType("frappe.utils")
    utils.get_datetime = _get_datetime
    utils.now_datetime = lambda: _dt.datetime(2026, 10, 14, 10, 21, 5)
    f.utils = utils
    mirror = _mirror_ns(w, f)
    wr = types.ModuleType("ecentric_workspace.weekly_report.sharepoint")
    wr.get_app_token = lambda: "TOKEN"
    wr.GRAPH = "https://graph.microsoft.com/v1.0"
    wr.SITE_ID = "SITE"
    wrpkg = types.ModuleType("ecentric_workspace.weekly_report")
    wrpkg.sharepoint = wr
    integ = types.ModuleType("ecentric_workspace.approval_center.shared.integrations")
    integ.sharepoint_mirror = mirror
    mods = {"frappe": f, "frappe.utils": utils,
            "ecentric_workspace.weekly_report": wrpkg,
            "ecentric_workspace.weekly_report.sharepoint": wr,
            "ecentric_workspace.approval_center.shared.integrations": integ,
            "ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror": mirror}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        mod = types.ModuleType("sharepoint_snapshot")
        exec(compile(_read(_SNAP), "sharepoint_snapshot.py", "exec"), mod.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    mod._requests = lambda: graph
    return mod, f


def _the_gioi(action="Approved", level_no=2, actor="thu.trinh@ec.vn", act="ACT-1",
              business_dt=DT):
    w = _World()
    w.put("EC Approval Request", "AR-1", reference_doctype=business_dt, reference_name="CTR-1")
    w.put("EC Approval Action", act, approval_request="AR-1", level_no=level_no, actor=actor,
          action=action, action_time=_dt.datetime(2026, 10, 14, 10, 20, 0))
    w.put("User", "thu.trinh@ec.vn", full_name="Nguyễn Thu Trinh")
    w.put("File", "F-DOCX", file_name="Hop dong ABC.docx", file_url="/private/files/Hop dong ABC.docx",
          attached_to_doctype=business_dt, attached_to_name="CTR-1")
    w.put("File", "F-PDF", file_name="phu luc.pdf", file_url="/private/files/phu luc.pdf",
          attached_to_doctype=business_dt, attached_to_name="CTR-1")
    w.put("EC SharePoint File Link", "L1", file_url="/private/files/Hop dong ABC.docx",
          business_doctype=business_dt, business_name="CTR-1", sp_item_id="IT1")
    w.put("EC SharePoint File Link", "L2", file_url="/private/files/phu luc.pdf",
          business_doctype=business_dt, business_name="CTR-1", sp_item_id="IT2")
    return w


def _snaps(w):
    return list(w.rows(SNAP_DT).values())


def _files_moi(w):
    return [r for n, r in w.rows("File").items() if n.startswith("FILE-")]


class ChupTep(unittest.TestCase):
    def test_chup_docx_va_pdf_dung_ten_dung_metadata(self):
        w, g = _the_gioi(), _Graph()
        mod, _f = _nap_snapshot(w, g)
        kq = mod.chup_quyet_dinh("ACT-1")
        self.assertEqual(kq["xong"], ["Hop dong ABC.docx"], "chi tep Office duoc chup, PDF bo qua")
        files = _files_moi(w)
        self.assertEqual(sorted(f["file_name"] for f in files), [
            "[Đối chứng] Hop dong ABC – sau duyệt cấp 2 – Thu Trinh – 14-10-2026 10h20.docx",
            "[Đối chứng] Hop dong ABC – sau duyệt cấp 2 – Thu Trinh – 14-10-2026 10h20.pdf"])
        for f in files:
            self.assertEqual(f["is_private"], 1, "ban doi chung phai RIENG TU")
            self.assertEqual((f["attached_to_doctype"], f["attached_to_name"]), (DT, "CTR-1"),
                             "gan vao phieu nghiep vu -> di dung luat quyen cua dinh kem")
        (s,) = _snaps(w)
        self.assertEqual(s["khoa"], "ACT-1|IT1")
        self.assertEqual((s["level_no"], s["actor"], s["action"], s["approval_request"]),
                         (2, "thu.trinh@ec.vn", "Approved", "AR-1"))
        self.assertEqual(s["sha256"], hashlib.sha256(g.docx).hexdigest())
        self.assertEqual(w.file_bytes[s["docx_file"]], g.docx, "ban goc phai la bytes Graph tra ve")
        self.assertEqual(w.file_bytes[s["pdf_file"]], g.pdf)
        self.assertEqual((s["sp_etag"], s["sp_version_id"], s["sp_on_dinh"]), ('"{E1},3"', "3.0", 1))
        self.assertEqual(s["sp_last_modified"], _dt.datetime(2026, 10, 14, 10, 19, 0), "UTC -> gio he thong")
        self.assertEqual(s["sp_last_modified_by"], "lien.vu@ec.vn")
        self.assertTrue(any(u.endswith("/items/IT1/content?format=pdf") for u, _t in g.calls))
        self.assertFalse(any("/IT2/" in u for u, _t in g.calls), "khong goi Graph cho tep PDF")

    def test_chay_lai_khong_tai_lai_khong_sinh_ban_trung(self):
        w, g = _the_gioi(), _Graph()
        mod, _f = _nap_snapshot(w, g)
        mod.chup_quyet_dinh("ACT-1")
        goi = len(g.calls)
        kq = mod.chup_quyet_dinh("ACT-1")
        self.assertEqual(kq["da_co"], ["Hop dong ABC.docx"])
        self.assertEqual(len(_snaps(w)), 1)
        self.assertEqual(len(_files_moi(w)), 2)
        self.assertEqual(len(g.calls), goi, "da chup roi thi KHONG goi Graph nua")

    def test_hoan_tat_trung_noi_dung_dung_lai_tep(self):
        w, g = _the_gioi(action="Approved", level_no=4), _Graph()
        w.put("EC Approval Action", "ACT-2", approval_request="AR-1", level_no=None,
              actor="Administrator", action="Approved", action_time=_dt.datetime(2026, 10, 14, 10, 20, 1))
        mod, _f = _nap_snapshot(w, g)
        mod.chup_quyet_dinh("ACT-1")
        mod.chup_quyet_dinh("ACT-2")
        a, b = sorted(_snaps(w), key=lambda r: r["creation"])
        self.assertEqual(b["reused_from"], a["name"])
        self.assertEqual((b["docx_file"], b["pdf_file"]), (a["docx_file"], a["pdf_file"]))
        self.assertEqual(len(_files_moi(w)), 2, "noi dung trung byte -> khong luu them tep")
        self.assertEqual((b["action_label"], b["level_no"]), ("hoàn tất duyệt", 0))

    def test_pdf_hong_van_luu_ban_goc(self):
        w, g = _the_gioi(action="Information Requested", level_no=1), _Graph(pdf_code=406)
        mod, _f = _nap_snapshot(w, g)
        kq = mod.chup_quyet_dinh("ACT-1")
        self.assertEqual(kq["xong"], ["Hop dong ABC.docx"])
        (s,) = _snaps(w)
        self.assertTrue(s.get("docx_file") and not s.get("pdf_file"))
        self.assertIn("406", s["pdf_error"])
        self.assertIn("khi trả lại cấp 1", _files_moi(w)[0]["file_name"])

    def test_etag_lech_thi_tai_lai_va_ghi_trung_thuc(self):
        w, g = _the_gioi(), _Graph(etags=['"A"', '"B"', '"B"', '"B"'])
        mod, _f = _nap_snapshot(w, g)
        mod.chup_quyet_dinh("ACT-1")
        (s,) = _snaps(w)
        self.assertEqual((s["sp_etag"], s["sp_on_dinh"]), ('"B"', 1))
        self.assertEqual(len([u for u in g.downloads() if not u.endswith("pdf")]), 2)

        w2, g2 = _the_gioi(), _Graph(etags=['"A"', '"B"', '"C"', '"D"'])
        mod2, _f = _nap_snapshot(w2, g2)
        mod2.chup_quyet_dinh("ACT-1")
        self.assertEqual(_snaps(w2)[0]["sp_on_dinh"], 0, "khong on dinh thi phai noi ra, khong gia vo")

    def test_khong_phai_quyet_dinh_hoac_khong_soi_guong_thi_bo_qua(self):
        for w in (_the_gioi(action="Skipped"), _the_gioi(business_dt="EC Payment Request")):
            g = _Graph()
            mod, _f = _nap_snapshot(w, g)
            self.assertIn("bo_qua", mod.chup_quyet_dinh("ACT-1"))
            self.assertEqual(g.calls, [])
            self.assertEqual(_snaps(w), [])


class GraphHong(unittest.TestCase):
    def test_mat_mang_khong_nem_va_khong_de_tep_mo_coi(self):
        w, g = _the_gioi(), _Graph(boom=True)
        mod, _f = _nap_snapshot(w, g)
        kq = mod.chup_nen("ACT-1")
        self.assertEqual(kq["hong"], ["Hop dong ABC.docx"])
        self.assertEqual(_snaps(w), [])
        self.assertTrue(w.logs, "hong thi phai ghi log de sua")

    def test_hong_giua_chung_thi_rollback_tep_da_tao(self):
        w, g = _the_gioi(), _Graph()
        mod, _f = _nap_snapshot(w, g)
        mod.doc_phien_ban = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no"))
        mod.chup_nen("ACT-1")
        self.assertEqual(_files_moi(w), [], "File khong co ban ghi doi chung = tep KHONG dau moc "
                                            "-> se bi soi guong nhu tep nguoi dung")

    def test_chup_nen_nuot_moi_loi(self):
        w, g = _the_gioi(), _Graph()
        mod, _f = _nap_snapshot(w, g)
        mod.chup_quyet_dinh = lambda *a: 1 / 0
        self.assertIsNone(mod.chup_nen("ACT-1"))
        self.assertTrue(w.logs)


class TenTep(unittest.TestCase):
    def setUp(self):
        self.mod, _f = _nap_snapshot(_World(), _Graph())

    def test_nhan(self):
        n = self.mod.nhan_hanh_dong
        self.assertEqual(n("Approved", 2), "sau duyệt cấp 2")
        self.assertEqual(n("Approved", None), "hoàn tất duyệt")
        self.assertEqual(n("Rejected", 3), "khi từ chối cấp 3")
        self.assertEqual(n("Information Requested", 1), "khi trả lại cấp 1")

    def test_ten_ngan(self):
        t = self.mod.ten_ngan
        self.assertEqual(t("a@x.vn", "Nguyễn Thu  Trinh"), "Thu Trinh")
        self.assertEqual(t("Administrator", "Administrator"), "Hệ thống")
        self.assertEqual(t("lan@x.vn", ""), "lan")

    def test_ten_dai_va_ky_tu_cam(self):
        ten = self.mod.ten_tep("HĐ: dịch vụ/khung #1? " + "rất dài " * 40 + ".DOCX",
                               "sau duyệt cấp 2", "Thu Trinh", _dt.datetime(2026, 10, 14, 9, 5), ".DOCX")
        self.assertLessEqual(len(ten), 140, "File.file_name la Data(140)")
        self.assertTrue(ten.startswith("[Đối chứng] HĐ dịch vụ khung 1 "))
        self.assertTrue(ten.endswith("– sau duyệt cấp 2 – Thu Trinh – 14-10-2026 09h05.docx"))
        for c in ':/#?%\\*"<>|':
            self.assertNotIn(c, ten)


class LoaiTru(unittest.TestCase):
    def _w(self):
        w = _the_gioi()
        # Ban doi chung TRUNG file_url voi tep nguoi dung (Frappe gop theo content_hash).
        w.put("File", "F-SNAP", file_name="[Đối chứng] x.docx", file_url="/private/files/Hop dong ABC.docx",
              attached_to_doctype=DT, attached_to_name="CTR-1")
        w.put("File", "F-SNAP-PDF", file_name="[Đối chứng] x.pdf", file_url="/private/files/snap.pdf",
              attached_to_doctype=DT, attached_to_name="CTR-1")
        w.put(SNAP_DT, "S1", business_doctype=DT, business_name="CTR-1", khoa="A|IT1",
              docx_file="F-SNAP", pdf_file="F-SNAP-PDF", action="Approved", level_no=1,
              actor="thu.trinh@ec.vn", action_time=_dt.datetime(2026, 10, 14, 10, 20),
              sp_last_modified=_dt.datetime(2026, 10, 14, 10, 20, 30), docx_file_url="/u.docx",
              pdf_file_url="/u.pdf", sha256="ab" * 32)
        return w

    def test_soi_guong_khong_bao_gio_day_ban_doi_chung_len(self):
        w = self._w()
        f = _frappe(w)
        m = _mirror_ns(w, f)
        ten = [t.get("name") for t in m._dinh_kem(DT, "CTR-1")]
        self.assertEqual(sorted(ten), ["F-DOCX", "F-PDF"],
                         "loai theo TEN ban ghi File: tep nguoi dung trung URL van phai con")
        tai = []
        ns = {"frappe": f, "wr_sp": types.SimpleNamespace(get_app_token=lambda: "T"),
              "tai_len": lambda dt, url, name, bn, token=None: tai.append(name) or {"item_id": "I"},
              "cap_quyen": lambda *a, **k: {"da_cap": [], "link": None},
              "ghi_lien_ket": lambda *a, **k: None, "nguoi_trong_luong": lambda *a: []}
        ns.update({k: getattr(m, k) for k in ("duoc_soi_guong", "_dinh_kem")})
        exec(compile(_doan(_MIRROR, "dong_bo_phieu"), "<m>", "exec"), ns)
        ns["dong_bo_phieu"](DT, "CTR-1")
        self.assertEqual(sorted(tai), ["Hop dong ABC.docx", "phu luc.pdf"])

    def test_chi_tiet_tach_rieng_va_moi_nhat_truoc(self):
        w = self._w()
        w.put(SNAP_DT, "S2", business_doctype=DT, business_name="CTR-1", khoa="B|IT1",
              docx_file="F-SNAP", action="Rejected", level_no=2, actor="Administrator",
              action_time=_dt.datetime(2026, 10, 15, 8, 0), docx_file_url="/u.docx")
        mod, f = _nap_snapshot(w, _Graph())
        rows = f.get_all("File", filters={"attached_to_doctype": DT, "attached_to_name": "CTR-1"},
                         fields=["name", "file_name", "file_url"])
        con, ds = mod.tach_ban_doi_chung(DT, "CTR-1", rows)
        self.assertEqual(sorted(r["name"] for r in con), ["F-DOCX", "F-PDF"])
        self.assertEqual([x["action"] for x in ds], ["Rejected", "Approved"], "moi nhat truoc")
        self.assertEqual(ds[0]["actor_name"], "Hệ thống")
        self.assertEqual(ds[1]["actor_name"], "Nguyễn Thu Trinh")
        self.assertTrue(ds[1]["sua_sau_quyet_dinh"], "sua 30s sau quyet dinh -> phai bao")
        self.assertFalse(ds[0]["sua_sau_quyet_dinh"])

    def test_tep_can_chup_bo_qua_ban_doi_chung_va_tep_da_go(self):
        w = self._w()
        w.put("EC SharePoint File Link", "L3", file_url="/private/files/cu.docx",
              business_doctype=DT, business_name="CTR-1", sp_item_id="IT3")   # tep da go khoi phieu
        mod, _f = _nap_snapshot(w, _Graph())
        self.assertEqual([n.sp_item_id for n in mod.tep_can_chup(DT, "CTR-1")], ["IT1"])

    def test_chep_phieu_moi_khong_mang_ban_doi_chung(self):
        w = self._w()
        f = _frappe(w)
        m = _mirror_ns(w, f)
        mods = {"frappe": f,
                "ecentric_workspace.approval_center.shared.integrations": types.SimpleNamespace(
                    sharepoint_mirror=m),
                "ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror": m}
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            ns = {"frappe": f, "_SYSTEM_FILE_PREFIXES": ("SIGNED-", "REVIEW-")}
            exec(compile(_doan(_COMMAND, "_is_system_artefact", "_tep_doi_chung", "_copy_attachments"),
                         "<c>", "exec"), ns)
            src = types.SimpleNamespace(doctype=DT, name="CTR-1")
            dst = types.SimpleNamespace(doctype=DT, name="CTR-2")
            ns["_copy_attachments"](src, dst)
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        moi = [r for r in w.rows("File").values() if r.get("attached_to_name") == "CTR-2"]
        self.assertEqual(sorted(r["file_name"] for r in moi), ["Hop dong ABC.docx", "phu luc.pdf"])


class Hook(unittest.TestCase):
    def _engine(self, ref_dt=DT, handler_boom=False):
        goi, logs = [], []

        def handler(*a):
            if handler_boom:
                raise RuntimeError("boom")
            goi.append(a)

        class _Ins(object):
            def __init__(self, d):
                self.d = d

            def insert(self, **kw):
                return types.SimpleNamespace(name="ACT-9")

        f = types.SimpleNamespace(
            db=types.SimpleNamespace(
                count=lambda *a, **k: 0,
                get_value=lambda dt, n, fields=None, as_dict=False: _Row(
                    reference_doctype=ref_dt, reference_name="CTR-1")),
            get_doc=lambda d: _Ins(d), session=types.SimpleNamespace(user="u"),
            get_attr=lambda path: handler, log_error=lambda *a, **k: logs.append(a),
            get_traceback=lambda: "tb")
        ns = {"frappe": f, "now_datetime": lambda: None}
        exec(compile(_doan(_ENGINE, "log_action", "_DECISION_ACTIONS", "_DECISION_OBSERVERS",
                           "_notify_decision_observers"), "<e>", "exec"), ns)
        return ns, goi, logs

    def test_chi_quyet_dinh_moi_goi_nguoi_nghe(self):
        ns, goi, _l = self._engine()
        for a in ("Approved", "Rejected", "Information Requested"):
            ns["log_action"]("AR-1", a, "x@e.vn", 2)
        for a in ("Submitted", "Skipped", "Resubmitted", "Cancelled", "Restarted"):
            ns["log_action"]("AR-1", a, "x@e.vn", 2)
        self.assertEqual([g[3] for g in goi], ["Approved", "Rejected", "Information Requested"])
        self.assertEqual(goi[0][:3], ("CTR-1", "AR-1", "ACT-9"))

    def test_loai_phieu_chua_dang_ky_thi_khong_goi(self):
        ns, goi, _l = self._engine(ref_dt="EC Payment Request")
        ns["log_action"]("AR-1", "Approved", "x@e.vn", 1)
        self.assertEqual(goi, [])

    def test_loi_nguoi_nghe_khong_lam_hong_lan_duyet(self):
        ns, _g, logs = self._engine(handler_boom=True)
        ns["log_action"]("AR-1", "Approved", "x@e.vn", 1)
        self.assertTrue(logs)

    def test_dang_ky_tro_dung_ham_on_decision(self):
        ns, _g, _l = self._engine()
        path = ns["_DECISION_OBSERVERS"][DT]
        self.assertTrue(path.endswith("features.contract_review.application.service.on_decision"))
        self.assertIn("\ndef on_decision(", _read(_SERVICE))

    def test_contract_review_chi_xep_viec_sau_commit(self):
        w = _World()
        f = _frappe(w)
        ns = {"frappe": f}
        exec(compile(_doan(_SERVICE, "on_decision"), "<s>", "exec"), ns)
        ns["on_decision"]("CTR-1", "AR-1", "ACT-9", "Approved")
        ((method, kw),) = w.enqueued
        self.assertEqual(method, "ecentric_workspace.approval_center.shared.integrations."
                                 "sharepoint_snapshot.chup_nen")
        self.assertIs(kw.get("enqueue_after_commit"), True,
                      "chay truoc commit thi dong EC Approval Action chua ton tai")
        self.assertEqual((kw.get("queue"), kw.get("approval_action")), ("long", "ACT-9"))
        self.assertIn("\ndef chup_nen(approval_action):", _read(_SNAP))
        f.enqueue = lambda *a, **k: 1 / 0
        ns["on_decision"]("CTR-1", "AR-1", "ACT-9", "Approved")   # khong nem
        self.assertTrue(w.logs)


class Quyen(unittest.TestCase):
    def test_danh_sach_chi_sau_cong_can_view(self):
        src = _read(_QUERY)
        tree = ast.parse(src)
        fn = [n for n in tree.body if getattr(n, "name", None) == "detail"][0]
        body = ast.get_source_segment(src, fn)
        self.assertLess(body.index("capabilities.can_view("), body.index("_tach_doi_chung("))
        self.assertIn('"doi_chung": doi_chung', body)
        # Tach TRUOC khi gop trung theo file_url.
        self.assertLess(body.index("_tach_doi_chung("), body.index("dedupe_attachments("))

    def test_khong_xoa_duoc_tep_doi_chung(self):
        w = LoaiTru()._w()
        mod, f = _nap_snapshot(w, _Graph())
        tep = lambda n: types.SimpleNamespace(name=n, get=lambda k: n)
        with self.assertRaises(_Throw):
            mod.chan_xoa_tep_doi_chung(tep("F-SNAP"))
        with self.assertRaises(_Throw):
            mod.chan_xoa_tep_doi_chung(tep("F-SNAP-PDF"))
        mod.chan_xoa_tep_doi_chung(tep("F-DOCX"))       # tep nguoi dung: xoa binh thuong
        f.flags.ec_allow_snapshot_file_delete = True
        mod.chan_xoa_tep_doi_chung(tep("F-SNAP"))       # co quan tri: cho qua nhung ghi vet
        self.assertTrue(w.logs)

    def test_hook_xoa_da_dang_ky(self):
        h = _read(os.path.join(_ROOT, "hooks.py"))
        i = h.index('"File": {')
        self.assertIn("sharepoint_snapshot.chan_xoa_tep_doi_chung", h[i:i + 700])

    def test_doctype_chi_system_manager_va_moi_truong_chi_doc(self):
        d = json.load(io.open(_DT_JSON, encoding="utf-8"))
        self.assertEqual([p["role"] for p in d["permissions"]], ["System Manager"])
        self.assertFalse(d["permissions"][0].get("create"))
        f = {x["fieldname"]: x for x in d["fields"]}
        self.assertEqual(f["khoa"].get("unique"), 1, "khoa unique = chot idempotent o CSDL")
        for x in d["fields"]:
            if x["fieldtype"] not in ("Section Break", "Column Break"):
                self.assertEqual(x.get("read_only"), 1, x["fieldname"])
        # Moi truong ma code ghi/doc phai co that trong DocType.
        for k in ("docx_file", "pdf_file", "sha256", "sp_etag", "sp_version_id", "approval_action",
                  "level_no", "actor", "action", "action_time", "captured_at", "reused_from",
                  "sp_on_dinh", "pdf_error", "business_doctype", "business_name"):
            self.assertIn(k, f)


if __name__ == "__main__":
    unittest.main()
