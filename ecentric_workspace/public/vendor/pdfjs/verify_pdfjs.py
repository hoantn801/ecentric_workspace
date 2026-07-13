#!/usr/bin/env python3
# Copyright (c) 2026, eCentric and contributors
"""Verify the vendored PDF.js build against PINNED.sha256 (provenance + integrity + CVE
floor). Run at build/CI time and by tests/test_pdfjs_assets.py. Exit non-zero on any problem.

    python3 ecentric_workspace/public/vendor/pdfjs/verify_pdfjs.py
"""
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_MIN_SAFE = (4, 2, 67)   # CVE-2024-4367 first patched version
_SHA_RE = re.compile(r"^([0-9a-f]{64})\s+(\S+)$")


def parse_manifest(path):
    """Returns (meta_dict, {asset_name: sha256}). Metadata lines are `key: value`; asset
    lines are `<64-hex-sha>  <filename>`. Comment lines start with #."""
    meta, shas = {}, {}
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _SHA_RE.match(line.strip())
        if m:
            shas[m.group(2)] = m.group(1)
        elif ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, shas


def _ver_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def verify(base=HERE):
    problems = []
    meta, shas = parse_manifest(os.path.join(base, "PINNED.sha256"))
    # version floor (CVE-2024-4367)
    ver = meta.get("version", "")
    if _ver_tuple(ver) < _MIN_SAFE:
        problems.append("version_below_min_safe:%s" % ver)
    # license present
    lic = meta.get("license_file", "LICENSE")
    if not os.path.exists(os.path.join(base, lic)):
        problems.append("missing_license:%s" % lic)
    # every vendored asset present + sha match; no legacy 3.11.174 filenames
    if not shas:
        problems.append("no_asset_shas")
    for name, want in shas.items():
        if name in ("pdf.min.js", "pdf.worker.min.js"):
            problems.append("legacy_asset_present:%s" % name)
        fp = os.path.join(base, name)
        if not os.path.exists(fp):
            problems.append("missing:%s" % name)
            continue
        got = hashlib.sha256(open(fp, "rb").read()).hexdigest()
        if got != want:
            problems.append("sha_mismatch:%s" % name)
    # no residual vulnerable dist files on disk
    for legacy in ("pdf.min.js", "pdf.worker.min.js"):
        if os.path.exists(os.path.join(base, legacy)):
            problems.append("residual_legacy_file:%s" % legacy)
    return problems


if __name__ == "__main__":
    probs = verify()
    if probs:
        print("PDF.js vendor verification FAILED:", probs)
        sys.exit(1)
    print("PDF.js vendor verification OK")
