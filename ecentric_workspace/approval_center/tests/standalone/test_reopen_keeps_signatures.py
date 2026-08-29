# Copyright (c) 2026, eCentric and contributors
"""Attaching an extra invoice must not throw away everyone's signature.

Finance sends a request back for supporting documents far more often than for a change to
the request itself. Until 2026-08-28 every resubmit created a new package version, so all
signatures were discarded and the whole chain signed again - for a receipt that nobody signs
in the first place.

The rule agreed that day:

  * only files that REQUIRE a signature count as "the signed content";
  * add supporting evidence -> signatures stand, Finance simply continues;
  * change the request itself -> everyone signs again, no exception.

The second half is not negotiable. A digital signature attests to a specific content; keeping
old signatures on an amended request would show approvers as having signed something they
never read.
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


_LC = _src("platform", "esign", "lifecycle.py")


class _Pkg(object):
    name = "PKG-1"
    business_doctype = "EC Payment Request"
    business_name = "PR-1"


def _sha(content):
    import hashlib
    return hashlib.sha256(content).hexdigest()


def _load(pkg_files, attached, raise_pkg=False, raise_files=False, unreadable=False):
    """`attached` = danh sach NOI DUNG THAT cua cac tep dang dinh kem (bytes).

    Ban dau ham nay nhan thang mot tap MA BAM va gan vao `File.content_hash`. Chinh cho do
    la diem mu: no gia dinh `content_hash` cua Frappe la sha256 - dieu khong ai bao dam - nen
    du hai ben do bang hai thuoc do khac nhau, test van xanh. Gio harness dua NOI DUNG vao va
    de ma nguon that tu tinh ma bam; sai thuat toan la do ngay.
    """
    body = "\n\n".join(re.search(r"(?m)^def %s\(.*?(?=\ndef |\Z)" % n, _LC, re.S).group(0)
                       for n in ("_signable_content_changed", "_attached_signable_shas"))

    class _Pkgsvc(object):
        @staticmethod
        def package_files(_n):
            if raise_pkg:
                raise RuntimeError("db down")
            return pkg_files

    store = {"F%d" % i: c for i, c in enumerate(attached)}

    class _Doc(object):
        def __init__(self, name):
            self.name = name

        def get_content(self):
            if unreadable:
                raise RuntimeError("file missing on disk")
            return store[self.name]

    class _Frappe(object):
        @staticmethod
        def get_all(dt, **kw):
            if raise_files:
                raise RuntimeError("db down")
            return [{"name": n, "file_name": "%s.pdf" % n, "file_url": "/private/%s.pdf" % n,
                     "is_private": 1} for n in store]

        @staticmethod
        def get_doc(dt, name):
            return _Doc(name)

    # `hashing` la module THAT, khong phai ban gia: neu ma nguon doi thuat toan bam thi test
    # nay phai do, chu khong duoc trung khop voi mot ban sao trong test.
    import types
    hashing = types.ModuleType("hashing")
    exec(compile(_src("platform", "esign", "hashing.py"), "hashing.py", "exec"),
         hashing.__dict__)
    g = {"pkgsvc": _Pkgsvc(), "frappe": _Frappe(), "hashing": hashing}
    exec(compile(body, "sc", "exec"), g)
    return g["_signable_content_changed"]


#: TO_TRINH / HOA_DON... la NOI DUNG that cua tep, khong phai ten ma bam. Ma bam do chinh
#: ma nguon san pham tinh ra, nen doi thuat toan la test do.
TO_TRINH = b"%PDF-1.4 to trinh so tien 10.000.000"
TO_TRINH_DA_SUA = b"%PDF-1.4 to trinh so tien 999.000.000"
HOA_DON = b"%PDF-1.4 hoa don ban le"
PHU_LUC = b"%PDF-1.4 phu luc"


def _f(content, signable=True):
    return {"sha256": (_sha(content) if content is not None else None),
            "requires_signature": 1 if signable else 0}


class TestAddingEvidenceKeepsSignatures(unittest.TestCase):
    def test_adding_a_receipt_changes_nothing(self):
        fn = _load([_f(TO_TRINH)], [TO_TRINH, HOA_DON])
        self.assertFalse(fn(_Pkg()), "them bang chung ma bat ky lai het = sai")

    def test_several_extra_attachments_still_change_nothing(self):
        fn = _load([_f(TO_TRINH), _f(PHU_LUC)], [TO_TRINH, PHU_LUC, HOA_DON])
        self.assertFalse(fn(_Pkg()))

    def test_supporting_files_in_the_package_are_not_counted(self):
        # tep phu nam trong goi nhung khong can ky -> khong tinh la noi dung da ky
        fn = _load([_f(TO_TRINH), _f(PHU_LUC, signable=False)], [TO_TRINH])
        self.assertFalse(fn(_Pkg()))


class TestChangingTheRequestForcesResigning(unittest.TestCase):
    def test_a_replaced_signed_file_is_a_change(self):
        fn = _load([_f(TO_TRINH)], [TO_TRINH_DA_SUA, HOA_DON])
        self.assertTrue(fn(_Pkg()), "to trinh da khac ma giu chu ky cu = nguy tao bang chung")

    def test_a_removed_signed_file_is_a_change(self):
        fn = _load([_f(TO_TRINH), _f(PHU_LUC)], [TO_TRINH])
        self.assertTrue(fn(_Pkg()))


class TestUncertaintyMeansResign(unittest.TestCase):
    """Khong doc duoc thi phai lam lai - phien toai con hon giu chu ky cu tren noi dung la."""

    def test_unreadable_package_forces_a_new_version(self):
        self.assertTrue(_load([_f(TO_TRINH)], [TO_TRINH], raise_pkg=True)(_Pkg()))

    def test_unreadable_attachments_force_a_new_version(self):
        self.assertTrue(_load([_f(TO_TRINH)], [TO_TRINH], raise_files=True)(_Pkg()))

    def test_a_signed_file_without_a_hash_forces_a_new_version(self):
        fn = _load([_f(TO_TRINH), _f(None)], [TO_TRINH])
        self.assertTrue(fn(_Pkg()), "thieu ma bam thi khong so duoc -> khong duoc doan la giong")

    def test_no_signable_file_at_all_forces_a_new_version(self):
        self.assertTrue(_load([], [])(_Pkg()))


class TestItIsWiredBeforeTheRevision(unittest.TestCase):
    def test_the_check_runs_before_create_revision(self):
        body = re.search(r"(?m)^def on_request_reopened\(.*?(?=\ndef |\Z)", _LC, re.S).group(0)
        self.assertLess(body.index("_signable_content_changed(pkg)"),
                        body.index("pkgsvc.create_revision"),
                        "phai kiem TRUOC khi tao phien ban moi")
        m = re.search(r"if not _signable_content_changed\(pkg\):(.*?)\n\n", body, re.S)
        self.assertIsNotNone(m, "phep chan phai that su chan, khong chi co mat")
        self.assertIn("return out", m.group(1))


if __name__ == "__main__":
    unittest.main()
