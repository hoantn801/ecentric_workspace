# Copyright (c) 2026, eCentric and contributors
"""E2E vong doi: tu choi -> "Tao phieu moi tu phieu nay" (command_service.clone_request).

Duong "tu choi -> lam lai" gio la duong CHINH (da chot: doi tai lieu can ky thi Tu choi
chu khong "Yeu cau bo sung"). Nhung dieu bo test nay giu, tren HAM THAT:

  1. Chi clone duoc tu trang thai KET THUC (Rejected/Cancelled); dang Pending thi chan,
     phieu nhap (chua co request) cung chan.
  2. Ban sao la NHAP doc lap: khong validator nao chay (definition stub KHONG CO thuoc
     tinh validator - neu code dong toi la AttributeError no ngay), khong approval_request.
  3. Tep he thong sinh ra (SIGNED-*, REVIEW-*) KHONG duoc chep sang - chep mot ban PDF
     DA KY sang phieu moi la bat nguoi ta dat o ky len tai lieu da mang chu ky cua phieu
     truoc.
  4. O cam ket ca nhan (clone_exclude_fields) khong duoc chep.
  5. Tep trung noi dung (cung file_url) chi chep MOT lan; tep chep hong phai duoc BAO RA
     (failed list), khong nuot.
  6. Chi chinh chu (requested_by) hoac System Manager duoc clone.

frappe gia lap qua sys.modules; chay clone_request THAT (exec command_service.py).
"""
import io
import os
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "platform", "esign")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()


def _read(*parts):
    return io.open(os.path.join(_ROOT, *parts), encoding="utf-8").read()


class _D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


class _Throw(Exception):
    pass


class _PermissionError(_Throw):
    pass


class _NewDoc(object):
    """frappe.new_doc gia lap - ghi lai moi truong duoc set."""

    def __init__(self):
        self.__dict__["fields"] = {}
        self.__dict__["inserted"] = False

    def set(self, k, v):
        self.fields[k] = v

    def get(self, k, default=None):
        return self.fields.get(k, default)

    def __setattr__(self, k, v):
        self.fields[k] = v

    def __getattr__(self, k):
        # frappe.new_doc tra document co san moi truong (None) - khong AttributeError
        if k.startswith("_"):
            raise AttributeError(k)
        return self.fields.get(k)

    def insert(self, **kw):
        self.__dict__["inserted"] = True
        self.fields["name"] = "EC-PAYR-2026-00099"
        return self


class _SourceDoc(object):
    def __init__(self, fields):
        self._fields = dict(fields)
        self.doctype = "EC Payment Request"
        self.name = fields.get("name", "EC-PAYR-2026-00001")

    def get(self, k, default=None):
        return self._fields.get(k, default)

    @property
    def requested_by(self):
        return self._fields.get("requested_by")


#: bo truong sua duoc - lay theo dinh nghia Payment Request that (rut gon nhung du dai
#: dien: co ca truong bi loai va truong binh thuong)
_EDITABLE = ("request_title", "reason", "payment_amount", "payee_full_name",
             "bank_account_number", "details_and_attachments_correct", "request_attachment")


def _definition():
    """CO Y dung SimpleNamespace KHONG co thuoc tinh `validator`/`submitter`: neu
    clone_request dong toi validator (chay kiem tra hop le tren ban nhap) thi test no
    AttributeError ngay tai cho."""
    return types.SimpleNamespace(
        business_doctype="EC Payment Request",
        editable_fields=_EDITABLE,
        clone_exclude_fields=("details_and_attachments_correct",),
        draft_preparer=None,
        title_builder=lambda d: "Thanh toan (lam lai)",
        status_label_map={"Pending": "Đang duyệt", "Rejected": "Đã từ chối",
                          "Cancelled": "Đã hủy"},
    )


def _load_cs(source_fields, request_status, files=(), user="hoan.tran@ec.vn",
             is_sm=False, fail_urls=()):
    import sys

    rec = {"file_inserts": [], "new_docs": []}
    source = _SourceDoc(source_fields)

    frappe_mod = types.ModuleType("frappe")
    frappe_mod._ = lambda s: s
    frappe_mod._dict = _D
    frappe_mod.session = types.SimpleNamespace(user=user)
    frappe_mod.PermissionError = _PermissionError

    def _throw(msg, exc=None):
        raise (exc or _Throw)(msg)

    frappe_mod.throw = _throw

    def get_doc(dt, name=None):
        if isinstance(dt, dict):
            if dt.get("doctype") == "File":
                if dt.get("file_url") in fail_urls:
                    raise ValueError("khong gan duoc tep")
                rec["file_inserts"].append(dict(dt))
                return types.SimpleNamespace(insert=lambda **kw: None)
            raise AssertionError("insert dict la cho File thoi: %r" % dt)
        return source

    frappe_mod.get_doc = get_doc

    def new_doc(dt):
        d = _NewDoc()
        rec["new_docs"].append(d)
        return d

    frappe_mod.new_doc = new_doc

    def get_all(dt, filters=None, fields=None, limit_page_length=None, pluck=None, **kw):
        assert dt == "File"
        return [_D(f) for f in files]

    frappe_mod.get_all = get_all
    frappe_mod.parse_json = lambda s: s
    frappe_mod.db = types.SimpleNamespace(
        exists=lambda *a, **kw: None, get_value=lambda *a, **kw: None,
        set_value=lambda *a, **kw: None)
    frappe_mod.logger = lambda *a, **kw: types.SimpleNamespace(warning=lambda *x: None)
    frappe_mod.flags = types.SimpleNamespace(mute_messages=False)
    frappe_mod.local = types.SimpleNamespace(message_log=[])

    caps_mod = types.ModuleType("capabilities")
    caps_mod.approval_request_for = lambda definition, name: (
        _D({"name": "AR-1", "approval_status": request_status}) if request_status else None)
    caps_mod.is_system_manager = lambda u=None: is_sm
    caps_mod.derive = lambda *a, **kw: {"can_cancel": True}

    qs_mod = types.ModuleType("query_service")
    qs_mod.employee_context = lambda u: {"employee": "EMP-1", "department": "Ops",
                                         "company": "eCentric"}
    qs_mod.detail = lambda *a, **kw: {}

    req_pkg = types.ModuleType("ecentric_workspace.approval_center.shared.requests")
    req_pkg.capabilities = caps_mod
    req_pkg.query_service = qs_mod

    mods = {
        "frappe": frappe_mod,
        "ecentric_workspace.approval_center.shared.requests": req_pkg,
        "ecentric_workspace.approval_center.shared.requests.capabilities": caps_mod,
        "ecentric_workspace.approval_center.shared.requests.query_service": qs_mod,
    }
    saved = {k: sys.modules.get(k) for k in mods}
    for k, v in mods.items():
        sys.modules[k] = v
    env = {}
    try:
        exec(compile(_read("approval_center", "shared", "requests", "command_service.py"),
                     "command_service.py", "exec"), env)
        return env, rec
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _src_fields(**over):
    base = {"name": "EC-PAYR-2026-00001", "requested_by": "hoan.tran@ec.vn",
            "request_title": "Thanh toan NCC A", "reason": "mua hang",
            "payment_amount": 12345678.0, "payee_full_name": "Cong ty A",
            "bank_account_number": "0123456789",
            "details_and_attachments_correct": 1,
            "request_attachment": "/private/files/to-trinh.pdf"}
    base.update(over)
    return base


def _file(fname, url=None, private=1):
    return {"file_url": url or ("/private/files/" + fname), "file_name": fname,
            "is_private": private}


class TestCloneOnlyFromTerminalStates(unittest.TestCase):
    def test_dang_duyet_thi_khong_clone_duoc(self):
        env, _rec = _load_cs(_src_fields(), "Pending")
        with self.assertRaises(_Throw) as ctx:
            env["clone_request"](_definition(), "EC-PAYR-2026-00001")
        self.assertIn("từ chối", str(ctx.exception))

    def test_phieu_nhap_chua_gui_cung_khong_clone(self):
        env, _rec = _load_cs(_src_fields(), None)
        with self.assertRaises(_Throw):
            env["clone_request"](_definition(), "EC-PAYR-2026-00001")

    def test_da_tu_choi_thi_clone_duoc(self):
        env, rec = _load_cs(_src_fields(), "Rejected")
        out = env["clone_request"](_definition(), "EC-PAYR-2026-00001")
        self.assertEqual(out["name"], "EC-PAYR-2026-00099")
        self.assertTrue(rec["new_docs"][0].inserted)

    def test_da_huy_cung_clone_duoc(self):
        # _CLONEABLE gom ca Cancelled: trang thai ket thuc, khong the ra hai ho so song song
        env, rec = _load_cs(_src_fields(), "Cancelled")
        out = env["clone_request"](_definition(), "EC-PAYR-2026-00001")
        self.assertEqual(out["name"], "EC-PAYR-2026-00099")

    def test_khong_phai_chu_phieu_thi_chan(self):
        env, _rec = _load_cs(_src_fields(), "Rejected", user="ke.toan@ec.vn", is_sm=False)
        with self.assertRaises(_PermissionError):
            env["clone_request"](_definition(), "EC-PAYR-2026-00001")


class TestCloneIsAnIndependentDraft(unittest.TestCase):
    def test_ban_sao_khong_chay_validator_va_khong_mang_approval_request(self):
        # definition stub KHONG co .validator - neu clone dong toi thi AttributeError o day
        env, rec = _load_cs(_src_fields(), "Rejected")
        env["clone_request"](_definition(), "EC-PAYR-2026-00001")
        clone = rec["new_docs"][0]
        self.assertNotIn("approval_request", clone.fields,
                         "ban sao phai la nhap doc lap, khong bam vao request cu")
        self.assertEqual(clone.fields["requested_by"], "hoan.tran@ec.vn")

    def test_o_cam_ket_ca_nhan_khong_duoc_chep(self):
        env, rec = _load_cs(_src_fields(), "Rejected")
        env["clone_request"](_definition(), "EC-PAYR-2026-00001")
        clone = rec["new_docs"][0]
        self.assertNotIn("details_and_attachments_correct", clone.fields,
                         "tich ho o xac nhan la ky thay nguoi dung cho bo ho so ho chua doc")
        # con noi dung binh thuong thi phai sang du
        self.assertEqual(clone.fields["payment_amount"], 12345678.0)
        self.assertEqual(clone.fields["bank_account_number"], "0123456789")


class TestCloneAttachmentPolicy(unittest.TestCase):
    def test_loai_tep_he_thong_SIGNED_va_REVIEW(self):
        env, rec = _load_cs(_src_fields(), "Rejected", files=[
            _file("to-trinh.pdf"),
            _file("SIGNED-to-trinh.pdf"),
            _file("REVIEW-ab12cd34-to-trinh.pdf"),
            _file("hoa-don.pdf"),
        ])
        out = env["clone_request"](_definition(), "EC-PAYR-2026-00001")
        copied_names = {f["file_name"] for f in rec["file_inserts"]}
        self.assertEqual(copied_names, {"to-trinh.pdf", "hoa-don.pdf"},
                         "PDF DA KY cua phieu cu chep sang la phieu moi doi dat o ky len "
                         "tai lieu da mang chu ky cua phieu truoc")
        self.assertEqual(out["attachments_copied"], 2)
        self.assertEqual(out["attachments_failed"], [])

    def test_tep_trung_url_chi_chep_mot_lan(self):
        env, rec = _load_cs(_src_fields(), "Rejected", files=[
            _file("to-trinh.pdf"), _file("to-trinh.pdf"),   # hai dong File cung url
        ])
        out = env["clone_request"](_definition(), "EC-PAYR-2026-00001")
        self.assertEqual(out["attachments_copied"], 1)
        self.assertEqual(len(rec["file_inserts"]), 1)

    def test_tep_chep_hong_phai_duoc_bao_ra_khong_nuot(self):
        env, rec = _load_cs(_src_fields(), "Rejected", files=[
            _file("to-trinh.pdf"), _file("hoa-don.pdf"),
        ], fail_urls=("/private/files/hoa-don.pdf",))
        out = env["clone_request"](_definition(), "EC-PAYR-2026-00001")
        self.assertEqual(out["attachments_copied"], 1)
        self.assertEqual(out["attachments_failed"], ["hoa-don.pdf"],
                         "tep khong gan duoc ma im lang thi nguoi dung tuong ho so day du")


if __name__ == "__main__":
    unittest.main()
