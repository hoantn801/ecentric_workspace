# Copyright (c) 2026, eCentric and contributors
"""PURE tests (no frappe): package-hash determinism + per-component sensitivity,
idempotency-key derivation. Runnable anywhere via unittest."""
import unittest

from ecentric_workspace.approval_center.esign import hashing


def _files():
    return [{"order": 0, "sha256": "a" * 64, "requires_signature": 1,
             "is_supporting_document": 0, "share_with_partner": 1},
            {"order": 1, "sha256": "b" * 64, "requires_signature": 0,
             "is_supporting_document": 1, "share_with_partner": 0}]


def _placements():
    return [{"file_order": 0, "page_index": 1, "x": 10, "y": 20, "width": 100,
             "height": 40, "level_no": 1, "signature_type": "digital"},
            {"file_order": 0, "page_index": 2, "x": 10, "y": 20, "width": 100,
             "height": 40, "level_no": 2, "signature_type": "digital"}]


class TestPackageHash(unittest.TestCase):
    def test_deterministic(self):
        h1 = hashing.package_hash(1, "P@2026", _files(), _placements())
        h2 = hashing.package_hash(1, "P@2026", _files(), list(reversed(_placements())))
        self.assertEqual(h1, h2)  # placement save order never matters
        self.assertEqual(len(h1), 64)

    def test_each_component_flips_the_hash(self):
        base = hashing.package_hash(1, "P@2026", _files(), _placements())
        # file bytes
        f = _files(); f[0]["sha256"] = "c" * 64
        self.assertNotEqual(base, hashing.package_hash(1, "P@2026", f, _placements()))
        # file order
        self.assertNotEqual(base, hashing.package_hash(
            1, "P@2026", list(reversed(_files())), _placements()))
        # sign flag
        f = _files(); f[1]["requires_signature"] = 1
        self.assertNotEqual(base, hashing.package_hash(1, "P@2026", f, _placements()))
        # BCT flag
        f = _files(); f[0]["is_supporting_document"] = 1
        self.assertNotEqual(base, hashing.package_hash(1, "P@2026", f, _placements()))
        # partner flag
        f = _files(); f[0]["share_with_partner"] = 0
        self.assertNotEqual(base, hashing.package_hash(1, "P@2026", f, _placements()))
        # placement geometry
        p = _placements(); p[0]["x"] = 11
        self.assertNotEqual(base, hashing.package_hash(1, "P@2026", _files(), p))
        # placement level
        p = _placements(); p[0]["level_no"] = 3
        self.assertNotEqual(base, hashing.package_hash(1, "P@2026", _files(), p))
        # version
        self.assertNotEqual(base, hashing.package_hash(2, "P@2026", _files(), _placements()))
        # profile identity/version
        self.assertNotEqual(base, hashing.package_hash(1, "P@2027", _files(), _placements()))

    def test_sha256_bytes_type_guard(self):
        with self.assertRaises(TypeError):
            hashing.sha256_bytes("not-bytes")


class TestIdempotencyKey(unittest.TestCase):
    ARGS = dict(provider="Mock", environment="UAT", approval_request="EC-APR-1",
                request_level="EC-APRL-1", approver_row="EC-APRA-1", action="Sign",
                pkg_hash="h" * 64, mapping_key="M-1@2026")

    def test_stable(self):
        self.assertEqual(hashing.idempotency_key(**self.ARGS),
                         hashing.idempotency_key(**self.ARGS))

    def test_every_component_changes_key(self):
        base = hashing.idempotency_key(**self.ARGS)
        for k in self.ARGS:
            a = dict(self.ARGS); a[k] = a[k] + "X"
            self.assertNotEqual(base, hashing.idempotency_key(**a), k)

    def test_rejects_empty_components(self):
        a = dict(self.ARGS); a["pkg_hash"] = ""
        with self.assertRaises(ValueError):
            hashing.idempotency_key(**a)


if __name__ == "__main__":
    unittest.main()
