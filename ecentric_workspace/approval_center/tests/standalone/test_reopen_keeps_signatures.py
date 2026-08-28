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


def _load(pkg_files, attached_hashes, raise_pkg=False, raise_files=False):
    body = re.search(r"(?m)^def _signable_content_changed\(.*?(?=\ndef )", _LC, re.S).group(0)

    class _Pkgsvc(object):
        @staticmethod
        def package_files(_n):
            if raise_pkg:
                raise RuntimeError("db down")
            return pkg_files

    class _Frappe(object):
        @staticmethod
        def get_all(dt, **kw):
            if raise_files:
                raise RuntimeError("db down")
            return [{"content_hash": h} for h in attached_hashes]

    g = {"pkgsvc": _Pkgsvc(), "frappe": _Frappe()}
    exec(compile(body, "sc", "exec"), g)
    return g["_signable_content_changed"]


def _f(sha, signable=True):
    return {"sha256": sha, "requires_signature": 1 if signable else 0}


class TestAddingEvidenceKeepsSignatures(unittest.TestCase):
    def test_adding_a_receipt_changes_nothing(self):
        fn = _load([_f("aaa")], {"aaa", "bbb-hoa-don-moi"})
        self.assertFalse(fn(_Pkg()), "them bang chung ma bat ky lai het = sai")

    def test_several_extra_attachments_still_change_nothing(self):
        fn = _load([_f("aaa"), _f("bbb")], {"aaa", "bbb", "c1", "c2", "c3"})
        self.assertFalse(fn(_Pkg()))

    def test_supporting_files_in_the_package_are_not_counted(self):
        # tep phu nam trong goi nhung khong can ky -> khong tinh la noi dung da ky
        fn = _load([_f("aaa"), _f("phu", signable=False)], {"aaa"})
        self.assertFalse(fn(_Pkg()))


class TestChangingTheRequestForcesResigning(unittest.TestCase):
    def test_a_replaced_signed_file_is_a_change(self):
        fn = _load([_f("aaa")], {"aaa-DA-SUA", "bbb"})
        self.assertTrue(fn(_Pkg()), "to trinh da khac ma giu chu ky cu = nguy tao bang chung")

    def test_a_removed_signed_file_is_a_change(self):
        fn = _load([_f("aaa"), _f("bbb")], {"aaa"})
        self.assertTrue(fn(_Pkg()))


class TestUncertaintyMeansResign(unittest.TestCase):
    """Khong doc duoc thi phai lam lai - phien toai con hon giu chu ky cu tren noi dung la."""

    def test_unreadable_package_forces_a_new_version(self):
        self.assertTrue(_load([_f("aaa")], {"aaa"}, raise_pkg=True)(_Pkg()))

    def test_unreadable_attachments_force_a_new_version(self):
        self.assertTrue(_load([_f("aaa")], {"aaa"}, raise_files=True)(_Pkg()))

    def test_a_signed_file_without_a_hash_forces_a_new_version(self):
        fn = _load([_f("aaa"), _f(None)], {"aaa"})
        self.assertTrue(fn(_Pkg()), "thieu ma bam thi khong so duoc -> khong duoc doan la giong")

    def test_no_signable_file_at_all_forces_a_new_version(self):
        self.assertTrue(_load([], set())(_Pkg()))


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
