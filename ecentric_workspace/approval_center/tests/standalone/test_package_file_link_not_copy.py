# Copyright (c) 2026, eCentric and contributors
"""Dua tep dinh kem cua phieu vao goi ky = LIEN KET, khong sao chep (05/09).

Chi Hien 05/09 01:57: tai 1 PDF, bam "Thiet lap chu ky" -> phieu hien 2 PDF
("..._004.pdf" va "..._004eefe52.pdf"). package.add_file luon insert mot File moi cung noi
dung dinh vao cung phieu. Gio: co `source_file` (File da dinh vao phieu) thi DSF tro thang
vao no (file_is_linked=1); remove_file khong xoa File lien ket.

Chay code THAT cua package.py voi frappe gia.
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")


def _read(rel):
    with io.open(os.path.join(_ESIGN, rel), encoding="utf-8") as fh:
        return fh.read()


class _Doc(dict):
    def __init__(self, d, store):
        super().__init__(d); self.__dict__.update(d); self._store = store

    def insert(self, ignore_permissions=False):
        self.name = "%s-%d" % (self.doctype, len(self._store) + 1)
        self["name"] = self.name
        self._store.append(dict(self, name=self.name))
        return self


def _package(files_by_name, dsf_row=None):
    fk = types.ModuleType("frappe"); fk._ = lambda s: s
    fk.PermissionError = type("PermissionError", (Exception,), {})
    fk.thrown = []; fk.inserted = []; fk.deleted = []

    def throw(msg, exc=None):
        fk.thrown.append(msg); raise (exc or Exception)(msg)
    fk.throw = throw
    fk.get_doc = lambda d, name=None: (_Doc(d, fk.inserted) if isinstance(d, dict)
                                       else types.SimpleNamespace(**dsf_row))

    class _DB(object):
        def get_value(self, dt, name, fields=None, as_dict=False, **k):
            if dt == "File":
                r = files_by_name.get(name)
                return types.SimpleNamespace(**r) if r else None
            if dt == "EC Digital Signature Profile":
                return types.SimpleNamespace(max_files=10, max_file_mb=10, require_signable_pdf=0)
            if dt == "EC Digital Signature File":
                return "PKG-1"
            return None

        def count(self, dt, flt=None):
            return 0

        def exists(self, dt, name):
            return True
    fk.db = _DB()
    fk.get_all = lambda *a, **k: []
    fk.delete_doc = lambda dt, name, ignore_permissions=False: fk.deleted.append((dt, name))
    utils = types.ModuleType("frappe.utils"); utils.now_datetime = lambda: None
    events = types.ModuleType("ecentric_workspace.platform.esign.events"); events.emit = lambda *a, **k: None
    hashing = types.ModuleType("ecentric_workspace.platform.esign.hashing"); hashing.sha256_bytes = lambda b: "sha-x"
    perms = types.ModuleType("ecentric_workspace.platform.esign.permissions")
    perms.assert_requester_draft_package = lambda pkg: None
    mods = {"frappe": fk, "frappe.utils": utils,
            "ecentric_workspace.platform.esign.events": events,
            "ecentric_workspace.platform.esign.hashing": hashing,
            "ecentric_workspace.platform.esign.permissions": perms}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_package_under_test")
        exec(compile(_read("package.py"), "package.py", "exec"), m.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    pkg = types.SimpleNamespace(name="PKG-1", business_doctype="EC Payment Request",
                                business_name="EC-PAYR-2026-00042", profile="P")
    m.get_package = lambda name: pkg
    m._validate_content = lambda *a, **k: True
    m._guess_mime = lambda *a, **k: "application/pdf"
    m._fk = fk; m._mods = mods
    return m


def _run(m, fn):
    saved = {k: sys.modules.get(k) for k in m._mods}
    sys.modules.update(m._mods)
    try:
        return fn()
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


FILES = {"F-orig": {"name": "F-orig", "attached_to_doctype": "EC Payment Request",
                    "attached_to_name": "EC-PAYR-2026-00042"},
         "F-other": {"name": "F-other", "attached_to_doctype": "EC Payment Request",
                     "attached_to_name": "EC-PAYR-2026-00099"}}


class TestLinkNotCopy(unittest.TestCase):
    def test_co_source_file_thi_lien_ket_khong_insert_File(self):
        m = _package(FILES)
        _run(m, lambda: m.add_file("PKG-1", "a.pdf", b"%PDF", requires_signature=1, source_file="F-orig"))
        kinds = [d["doctype"] for d in m._fk.inserted]
        self.assertEqual(kinds, ["EC Digital Signature File"], "khong duoc insert File moi")
        dsf = m._fk.inserted[0]
        self.assertEqual(dsf["file"], "F-orig")
        self.assertEqual(dsf["file_is_linked"], 1)

    def test_khong_source_file_thi_van_sao_chep_nhu_cu(self):
        m = _package(FILES)
        _run(m, lambda: m.add_file("PKG-1", "a.pdf", b"%PDF", requires_signature=1))
        kinds = [d["doctype"] for d in m._fk.inserted]
        self.assertEqual(kinds, ["File", "EC Digital Signature File"])
        self.assertEqual(m._fk.inserted[1]["file_is_linked"], 0)

    def test_source_file_cua_phieu_khac_bi_tu_choi(self):
        m = _package(FILES)
        with self.assertRaises(Exception):
            _run(m, lambda: m.add_file("PKG-1", "a.pdf", b"%PDF", source_file="F-other"))
        self.assertEqual(m._fk.inserted, [])

    def test_remove_file_khong_xoa_File_lien_ket(self):
        m = _package(FILES, dsf_row={"name": "DSF-1", "package": "PKG-1", "file": "F-orig",
                                     "file_is_linked": 1, "get": lambda k, d=None: 1})
        _run(m, lambda: m.remove_file("DSF-1"))
        self.assertIn(("EC Digital Signature File", "DSF-1"), m._fk.deleted)
        self.assertNotIn(("File", "F-orig"), m._fk.deleted, "tep cua phieu phai o lai")

    def test_remove_file_van_xoa_ban_sao(self):
        m = _package(FILES, dsf_row={"name": "DSF-2", "package": "PKG-1", "file": "F-copy",
                                     "file_is_linked": 0, "get": lambda k, d=None: 0})
        _run(m, lambda: m.remove_file("DSF-2"))
        self.assertIn(("File", "F-copy"), m._fk.deleted)


class TestCallersLink(unittest.TestCase):
    def test_requester_va_document_setup_deu_truyen_source_file(self):
        import ast
        for rel in ("requester.py", "document_setup.py"):
            tree = ast.parse(_read(rel))
            calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                     and ast.unparse(n.func).endswith("add_file")]
            self.assertTrue(calls, rel)
            for c in calls:
                self.assertIn("source_file", [k.arg for k in c.keywords], rel)
                self.assertEqual(ast.unparse([k for k in c.keywords if k.arg == "source_file"][0].value),
                                 "f.name", rel)

    def test_dsf_json_co_truong(self):
        import json
        p = os.path.join(_APP, "ecentric_workspace", "approval_center", "doctype",
                         "ec_digital_signature_file", "ec_digital_signature_file.json")
        with io.open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        f = [x for x in d["fields"] if x["fieldname"] == "file_is_linked"]
        self.assertEqual(len(f), 1); self.assertEqual(f[0]["fieldtype"], "Check")


if __name__ == "__main__":
    unittest.main()
