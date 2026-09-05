# Copyright (c) 2026, eCentric and contributors
"""Ban nhap Payment Request: go tep khi dang lap, va huy ban nhap khi da co goi ky (05/09).

Hoan: "them cho de xoa nua chu, khong co cho xoa thi sao xoa duoc file khong dung?"
Hien: bam "Huy yeu cau" tren ban nhap 00043 -> "Cannot delete ... linked with EC Digital
Signature Package EC-DSP-2026-00031".

  1. document_setup.remove_attachment (code THAT, frappe gia): dung cong _assert_setup_editable;
     go dong goi Draft + File (delete_permanently=False); tu choi neu sha nam trong goi da
     chot; xoa con tro request_attachment khi tro vao tep vua go.
  2. lifecycle.on_draft_discarded (code THAT): don placement -> DSF (+ban sao) -> event
     (ignore_on_trash) -> goi, tat ca delete_permanently=False; tu choi khi goi khong Draft /
     da co ma SCTS / da co chan ky.
  3. command_service.cancel (AST): goi hook TRUOC delete_doc; hook chi dung thu ImportError.
  4. api + HTML landmarks + patch p144.
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_PKG = os.path.join(_APP, "ecentric_workspace")


def _read(*parts):
    with io.open(os.path.join(_PKG, *parts), encoding="utf-8") as fh:
        return fh.read()


def _fake_frappe():
    fk = types.ModuleType("frappe"); fk._ = lambda s: s
    fk.PermissionError = type("PermissionError", (Exception,), {})
    fk.ValidationError = type("ValidationError", (Exception,), {})
    fk.session = types.SimpleNamespace(user="hien.nguyen@ecentric.vn")
    fk.deleted = []
    fk.set_values = []

    def throw(msg, exc=None):
        raise (exc or Exception)(msg)
    fk.throw = throw

    def delete_doc(dt, name, **kw):
        fk.deleted.append((dt, name, kw))
    fk.delete_doc = delete_doc
    return fk


def _with(mods, fn):
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        return fn()
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


# --------------------------------------------------------------------------- #
# 1. document_setup.remove_attachment
# --------------------------------------------------------------------------- #
def _document_setup(files, dsf_rows, packages, request_attachment=None, frozen_has_sha=False):
    fk = _fake_frappe()
    calls = {"remove_file": [], "log": []}

    class _DB(object):
        def get_value(self, dt, name=None, fields=None, as_dict=False, **k):
            if dt == "EC Digital Signature File" and isinstance(name, dict):
                for r in dsf_rows:
                    if r["package"] == name.get("package") and r["sha256"] == name.get("sha256"):
                        return types.SimpleNamespace(**r)
                return None
            if dt == "EC Payment Request" and fields == "request_attachment":
                return request_attachment
            if dt == "EC Payment Request" and fields == "owner":
                return "hien.nguyen@ecentric.vn"
            return None

        def has_column(self, dt, col):
            return True

        def exists(self, dt, flt):
            if dt == "EC Digital Signature File":
                return frozen_has_sha
            return dt == "File" and any(f["name"] == flt for f in files)

        def count(self, dt, flt=None):
            return len([r for r in dsf_rows if r["package"] == (flt or {}).get("package")])

        def set_value(self, dt, name, field, value=None):
            fk.set_values.append((dt, name, field, value))
    fk.db = _DB()

    def get_all(dt, filters=None, fields=None, pluck=None, order_by=None, **k):
        filters = filters or {}
        if dt == "File":
            return [dict(f) for f in files]
        if dt == "EC Digital Signature Package":
            st = filters.get("status")
            rows = packages
            if isinstance(st, list) and st[0] == "!=":
                rows = [p for p in packages if p["status"] != st[1]]
            elif isinstance(st, list) and st[0] == "in":
                rows = [p for p in packages if p["status"] in st[1]]
            if pluck:
                return [p[pluck] for p in rows]
            return [types.SimpleNamespace(**p) for p in rows]
        if dt == "EC Digital Signature File":
            rows = [r for r in dsf_rows if r["package"] == filters.get("package")
                    and r["sha256"] == filters.get("sha256")]
            return [r[pluck] for r in rows] if pluck else rows
        return []
    fk.get_all = get_all

    pkgsvc = _stub("ecentric_workspace.platform.esign.package",
                   raw_file_bytes=lambda name: ("bytes-of-" + name).encode(),
                   remove_file=lambda dsf: calls["remove_file"].append(dsf))
    hashing = _stub("ecentric_workspace.platform.esign.hashing",
                    sha256_bytes=lambda b: "sha:" + b.decode())
    perms = _stub("ecentric_workspace.platform.esign.permissions",
                  assert_can_view_business=lambda bd, bn: None,
                  business_approval_request=lambda bd, bn: None)
    engine = _stub("ecentric_workspace.approval_center.shared.workflow.transitions",
                   log_action=lambda *a, **k: calls["log"].append(a))
    mods = {"frappe": fk,
            "ecentric_workspace.platform.esign.events": _stub("e", emit=lambda *a, **k: None),
            "ecentric_workspace.platform.esign.guard": _stub("g"),
            "ecentric_workspace.platform.esign.hashing": hashing,
            "ecentric_workspace.platform.esign.package": pkgsvc,
            "ecentric_workspace.platform.esign.render": _stub("r", delivery_for_name=lambda n, s=False: "as_is"),
            "ecentric_workspace.platform.esign.permissions": perms,
            "ecentric_workspace.platform.esign.signer_plan": _stub("sp"),
            "ecentric_workspace.approval_center.shared.workflow.transitions": engine}
    m = types.ModuleType("_document_setup_under_test")
    _with(mods, lambda: exec(compile(_read("platform", "esign", "document_setup.py"),
                                     "document_setup.py", "exec"), m.__dict__))
    m.get_document_setup_state = lambda bd, bn: {"stub": True}
    m._fk = fk; m._mods = mods; m._calls = calls
    return m


FILES = [{"name": "F-1", "file_name": "bang.xlsx", "file_url": "/private/files/bang.xlsx",
          "content_hash": "h1", "is_private": 1, "creation": "2026-09-05"},
         {"name": "F-2", "file_name": "to-trinh.pdf", "file_url": "/private/files/to-trinh.pdf",
          "content_hash": "h2", "is_private": 1, "creation": "2026-09-05"}]


class TestRemoveAttachment(unittest.TestCase):
    def test_go_tep_trong_goi_draft_xoa_dong_goi_va_file(self):
        m = _document_setup(FILES, [{"name": "DSF-2", "package": "PKG-D", "sha256": "sha:bytes-of-F-2"}],
                            [{"name": "PKG-D", "status": "Draft"}],
                            request_attachment="/private/files/to-trinh.pdf")
        out = _with(m._mods, lambda: m.remove_attachment("EC Payment Request", "PR-1", "F-2"))
        self.assertEqual(m._calls["remove_file"], ["DSF-2"])
        self.assertEqual([(d[0], d[1]) for d in m._fk.deleted], [("File", "F-2")])
        self.assertFalse(m._fk.deleted[0][2].get("delete_permanently", False), "phai vao Deleted Document")
        self.assertIn(("EC Payment Request", "PR-1", "request_attachment", None), m._fk.set_values)
        self.assertEqual(out["removed"], 1); self.assertEqual(out["removed_signing_rows"], 1)

    def test_tep_chua_vao_goi_chi_xoa_file(self):
        m = _document_setup(FILES, [], [], request_attachment="/private/files/to-trinh.pdf")
        _with(m._mods, lambda: m.remove_attachment("EC Payment Request", "PR-1", "F-1"))
        self.assertEqual(m._calls["remove_file"], [])
        self.assertEqual([(d[0], d[1]) for d in m._fk.deleted], [("File", "F-1")])
        self.assertEqual(m._fk.set_values, [], "con tro dai dien tro tep KHAC thi giu nguyen")

    def test_tep_trong_goi_da_chot_bi_tu_choi(self):
        m = _document_setup(FILES, [], [{"name": "PKG-D", "status": "Draft"},
                                        {"name": "PKG-S", "status": "Superseded"}], frozen_has_sha=True)
        m._setup_editable = lambda bd, bn: (True, None)
        with self.assertRaises(Exception) as cm:
            _with(m._mods, lambda: m.remove_attachment("EC Payment Request", "PR-1", "F-2"))
        self.assertIn("đã chốt", str(cm.exception))
        self.assertEqual(m._fk.deleted, [])

    def test_ngoai_cua_so_sua_thi_tu_choi_truoc_khi_dong_gi(self):
        m = _document_setup(FILES, [], [{"name": "PKG-L", "status": "Locked"}])
        with self.assertRaises(Exception):
            _with(m._mods, lambda: m.remove_attachment("EC Payment Request", "PR-1", "F-1"))
        self.assertEqual(m._fk.deleted, [])

    def test_khong_phai_nguoi_de_nghi_bi_tu_choi(self):
        m = _document_setup(FILES, [], [])
        m._fk.session.user = "vinh.vu@ecentric.vn"
        with self.assertRaises(m._fk.PermissionError):
            _with(m._mods, lambda: m.remove_attachment("EC Payment Request", "PR-1", "F-1"))


# --------------------------------------------------------------------------- #
# 2. lifecycle.on_draft_discarded
# --------------------------------------------------------------------------- #
def _lifecycle(packages, dsf_rows=(), placements=(), events=(), legs=0):
    fk = _fake_frappe()

    class _DB(object):
        def count(self, dt, flt=None):
            return legs if dt == "EC Digital Signature Request" else 0

        def exists(self, dt, name):
            return True

        def get_value(self, *a, **k):
            return None
    fk.db = _DB()

    def get_all(dt, filters=None, fields=None, pluck=None, **k):
        if dt == "EC Digital Signature Package":
            return [types.SimpleNamespace(**p) for p in packages]
        if dt == "EC Digital Signature Placement":
            return list(placements)
        if dt == "EC Digital Signature File":
            return [types.SimpleNamespace(**r) for r in dsf_rows]
        if dt == "EC Digital Signature Event":
            return list(events)
        return []
    fk.get_all = get_all
    mods = {"frappe": fk,
            "ecentric_workspace.platform.esign.events": _stub("e"),
            "ecentric_workspace.platform.esign.hashing": _stub("h"),
            "ecentric_workspace.platform.esign.package": _stub("p")}
    m = types.ModuleType("_lifecycle_under_test")
    _with(mods, lambda: exec(compile(_read("platform", "esign", "lifecycle.py"), "lifecycle.py", "exec"),
                             m.__dict__))
    m._fk = fk; m._mods = mods
    return m


class TestDraftDiscard(unittest.TestCase):
    def test_don_goi_draft_theo_thu_tu_va_khong_xoa_vinh_vien(self):
        m = _lifecycle([{"name": "PKG-D", "status": "Draft", "scts_document_id": None}],
                       dsf_rows=[{"name": "DSF-1", "file": "F-copy", "file_is_linked": 0},
                                 {"name": "DSF-2", "file": "F-orig", "file_is_linked": 1}],
                       placements=["PL-1"], events=["EV-1", "EV-2"])
        out = _with(m._mods, lambda: m.on_draft_discarded("EC Payment Request", "PR-1"))
        seq = [(d[0], d[1]) for d in m._fk.deleted]
        self.assertEqual(seq, [("EC Digital Signature Placement", "PL-1"),
                               ("EC Digital Signature File", "DSF-1"), ("File", "F-copy"),
                               ("EC Digital Signature File", "DSF-2"),
                               ("EC Digital Signature Event", "EV-1"),
                               ("EC Digital Signature Event", "EV-2"),
                               ("EC Digital Signature Package", "PKG-D")])
        self.assertNotIn(("File", "F-orig"), seq, "tep lien ket la dinh kem cua phieu - Frappe xoa cung phieu")
        for d in m._fk.deleted:
            self.assertFalse(d[2].get("delete_permanently", False), d)
        ev_kw = [d[2] for d in m._fk.deleted if d[0] == "EC Digital Signature Event"]
        self.assertTrue(all(k.get("ignore_on_trash") for k in ev_kw), "event append-only: phai ignore_on_trash")
        self.assertEqual(out, {"discarded": ["PKG-D"]})

    def test_khong_co_goi_thi_khong_lam_gi(self):
        m = _lifecycle([])
        self.assertEqual(_with(m._mods, lambda: m.on_draft_discarded("EC Payment Request", "PR-1")),
                         {"discarded": []})
        self.assertEqual(m._fk.deleted, [])

    def test_goi_da_khoa_hoac_da_sang_scts_hoac_co_chan_ky_thi_tu_choi_truoc_khi_xoa_gi(self):
        for pkgs, legs in (([{"name": "P", "status": "Locked", "scts_document_id": None}], 0),
                           ([{"name": "P", "status": "Draft", "scts_document_id": "e8fc"}], 0),
                           ([{"name": "P", "status": "Draft", "scts_document_id": None}], 1)):
            m = _lifecycle(pkgs, placements=["PL-1"], legs=legs)
            with self.assertRaises(Exception):
                _with(m._mods, lambda: m.on_draft_discarded("EC Payment Request", "PR-1"))
            self.assertEqual(m._fk.deleted, [], (pkgs, legs))


# --------------------------------------------------------------------------- #
# 3-4. wiring
# --------------------------------------------------------------------------- #
class TestWiring(unittest.TestCase):
    def test_cancel_goi_hook_truoc_delete_doc(self):
        src = _read("approval_center", "shared", "requests", "command_service.py")
        fn = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "cancel"][0]
        body = ast.unparse(fn)
        i_hook = body.index("_esign_on_draft_discarded(definition.business_doctype, name)")
        i_del = body.index("frappe.delete_doc(definition.business_doctype, name")
        self.assertLess(i_hook, i_del)
        helper = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef)
                  and n.name == "_esign_on_draft_discarded"][0]
        hs = ast.unparse(helper)
        self.assertIn("except ImportError", hs)
        self.assertNotIn("except Exception", hs, "loi that phai noi len")
        self.assertIn("esign_lifecycle.on_draft_discarded(business_doctype, name)", hs)

    def test_api_va_html_va_patch(self):
        api = _read("platform", "esign", "api.py")
        i = api.index("def remove_attachment(")
        self.assertIn('@frappe.whitelist(methods=["POST"])', api[i - 60:i])
        self.assertIn("ds.remove_attachment(", api[i:i + 500])
        h = _read("platform", "esign", "ui", "document_signing_section.html")
        self.assertIn('data-remove-any="1"', h)
        self.assertIn('call("remove_attachment", { payment_request_name: name, document_ref: ref }, "POST")', h)
        self.assertIn("STATE._can_remove_any = !!(STATE.editable && STATE.can_classify)", h)
        self.assertIn("Các vị trí ký đã đặt trên tệp này sẽ bị xoá.", h)
        self.assertIn("chỉ lưu trên ERP, không gửi SCTS", h)
        self.assertIn('"payr:attachments-changed"', h)
        pr = _read("approval_center", "features", "payment_request", "ui", "main_section.html")
        self.assertIn('window.addEventListener("payr:attachments-changed"', pr)
        self.assertIn("p144_resync_payment_request_remove_attachment", _read("patches.txt"))
        patch = _read("approval_center", "patches", "p144_resync_payment_request_remove_attachment.py")
        self.assertIn("'data-remove-any=\"1\"'", patch); self.assertIn("payr:attachments-changed", patch)


if __name__ == "__main__":
    unittest.main()
