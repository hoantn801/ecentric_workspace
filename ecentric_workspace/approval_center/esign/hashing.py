# Copyright (c) 2026, eCentric and contributors
"""Pure hashing helpers for the digital-signature layer (NO frappe import - unit-testable
anywhere). Canonical-JSON + sha256, package-hash and idempotency-key derivation.

Package hash pins the EXACT signed context: version, ordered file hashes + flags,
placement geometry, profile identity. Any change => different hash => new package
version required (no silent mutation after signing starts).
"""
import hashlib
import json

HEX_LEN = 64


def sha256_bytes(content):
    """sha256 hex digest of raw bytes."""
    if not isinstance(content, (bytes, bytearray)):
        raise TypeError("sha256_bytes expects bytes")
    return hashlib.sha256(bytes(content)).hexdigest()


def canonical(obj):
    """Deterministic JSON: sorted keys, tight separators, no NaN."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False, default=str)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def package_hash(package_version, profile_key, files, placements):
    """files: ordered list of dicts {order, sha256, requires_signature,
    is_supporting_document, share_with_partner}; placements: list of dicts
    {file_order, page_index, x, y, width, height, level_no, signature_type}.
    Order-sensitive for files (list order = package order); placements are
    sorted canonically so save order never matters."""
    payload = {
        "v": int(package_version),
        "profile": str(profile_key),
        "files": [
            {"o": int(f.get("order") or 0), "h": str(f.get("sha256") or ""),
             "s": 1 if f.get("requires_signature") else 0,
             "b": 1 if f.get("is_supporting_document") else 0,
             "p": 1 if f.get("share_with_partner") else 0}
            for f in files
        ],
        "pl": sorted(
            [{"fo": int(p.get("file_order") or 0), "pg": int(p.get("page_index") or 0),
              "x": round(float(p.get("x") or 0), 2), "y": round(float(p.get("y") or 0), 2),
              "w": round(float(p.get("width") or 0), 2), "h": round(float(p.get("height") or 0), 2),
              "l": int(p.get("level_no") or 0), "t": str(p.get("signature_type") or "")}
             for p in placements],
            key=lambda r: (r["fo"], r["l"], r["pg"], r["x"], r["y"]),
        ),
    }
    return sha256_text(canonical(payload))


def idempotency_key(provider, environment, approval_request, request_level, approver_row,
                    action, pkg_hash, mapping_key):
    """Immutable business context only. Same key while a request is live/completed =>
    no second provider submission (ERP-side idempotency regardless of provider behavior)."""
    parts = [provider, environment, approval_request, request_level, approver_row,
             action, pkg_hash, mapping_key]
    if not all(isinstance(p, str) and p for p in parts):
        raise ValueError("idempotency_key: every component must be a non-empty string")
    return sha256_text("|".join(parts))
