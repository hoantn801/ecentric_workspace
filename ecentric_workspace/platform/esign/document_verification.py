# Copyright (c) 2026, eCentric and contributors
"""Doi chieu NOI DUNG tep ky voi phieu (chot 18/11/2026 giua chat Hop dong va chat Ky so).

Vi sao. Tep ky cua hop dong / BBNT KOL do NGUOI LAP tu xuat tu Word (phuong an b), khong con la
tep ERP sinh ra - nguoi lap co the sua noi dung truoc khi xuat. Phia nghiep vu (chat Hop dong) doi
chieu so hop dong / so tien trong lop chu cua PDF voi phieu; phia Ky so chi doc lop chu va GOI ham
cua ho, roi chan khi khong khop.

Hop dong goi (hooks.py cua app):
    ec_esign_document_verifiers = {"EC Contract Review Request": "<duong.dan.ham>"}
    ham(business_doctype, business_name, file_name, pages_text)
        -> {"status": "match" | "mismatch" | "no_text", "reason": "<cau tieng Viet>"}

  * Loai phieu KHONG khai hook: khong anh huong gi ("not_required").
  * Loai phieu DA khai: PDF khong co lop chu -> chan ("no_text", bao xuat lai bang Word); ham
    tra khac "match", nem loi, hoac khong nap duoc -> chan. Khong doan.
  * Ket qua gan voi sha256 cua tep (cache ngan) - tep doi thi doi chieu lai.
"""
import frappe

from ecentric_workspace.platform.esign import hashing
from ecentric_workspace.platform.esign import pdf_markers

HOOK = "ec_esign_document_verifiers"
CACHE_SECONDS = 600
ERROR_CACHE_SECONDS = 30
NO_TEXT_MSG = ("Tệp PDF không có lớp chữ (bản scan / in ra ảnh) - không đối chiếu được. "
               "Mở tệp trong Word → Lưu thành PDF rồi tải lên lại.")


def verifier_path(business_doctype):
    """Duong dan ham doi chieu khai trong hooks, hoac None."""
    try:
        hooks = frappe.get_hooks(HOOK) or {}
    except Exception:
        return None
    paths = hooks.get(business_doctype) if isinstance(hooks, dict) else None
    if isinstance(paths, (list, tuple)):
        paths = paths[-1] if paths else None
    return paths or None


def _key(business_doctype, business_name, sha):
    """Khoa cache gom ca `modified` cua PHIEU: ham doi chieu so tep voi truong tren phieu - sua
    phieu thi phai doi chieu lai (QC 22/11)."""
    try:
        mod = frappe.db.get_value(business_doctype, business_name, "modified")
    except Exception:
        mod = None
    return "esign:docverify:%s:%s:%s:%s" % (business_doctype, business_name, mod, sha)


def _cached(key):
    try:
        return frappe.cache().get_value(key) or frappe.cache().get_value(key + ":err")
    except Exception:
        return None


def verify(business_doctype, business_name, file_name, content, analysis=None, sha=None):
    """{"status", "reason", "sha256"}. status: not_required | match | mismatch | no_text | error."""
    path = verifier_path(business_doctype)
    if not path:
        return {"status": "not_required", "reason": None, "sha256": None}
    sha = sha or hashing.sha256_bytes(bytes(content or b""))
    key = _key(business_doctype, business_name, sha)
    cached = _cached(key)
    if cached:
        return cached
    analysis = analysis or pdf_markers.analyze(content)
    if not analysis.get("ok") or not analysis.get("has_text_layer"):
        out = {"status": "no_text", "reason": NO_TEXT_MSG, "sha256": sha}
    else:
        try:
            res = frappe.get_attr(path)(business_doctype, business_name, file_name,
                                        list(analysis.get("pages_text") or []))
            status = str((res or {}).get("status") or "")
            if status not in ("match", "mismatch", "no_text"):
                status, reason = "error", "Hàm đối chiếu trả kết quả lạ: %r" % status
            else:
                reason = (res or {}).get("reason")
                if status == "no_text" and not reason:
                    reason = NO_TEXT_MSG
            out = {"status": status, "reason": reason, "sha256": sha}
        except Exception:
            frappe.log_error(frappe.get_traceback(), "esign document verifier %s" % path)
            out = {"status": "error", "reason": "Không đối chiếu được nội dung tệp với phiếu "
                                                "(lỗi hệ thống) - liên hệ quản trị.", "sha256": sha}
    try:
        if out["status"] in ("match", "mismatch", "no_text"):
            frappe.cache().set_value(key, out, expires_in_sec=CACHE_SECONDS)
        else:                     # loi: cache NGAN (khong ghi Error Log moi lan mo trang)
            frappe.cache().set_value(key + ":err", out, expires_in_sec=ERROR_CACHE_SECONDS)
    except Exception:
        pass
    return out


def package_errors(pkg_name, business_doctype, business_name, signable_files, read_bytes):
    """Loi doi chieu cho preflight khoa goi: ["document_verify:<tep>:<status>"]. Loai phieu khong
    khai hook -> []. `read_bytes(dsf)` tra bytes cua tep (de test khong can File that)."""
    if not verifier_path(business_doctype):
        return []
    errs = []
    for f in signable_files:
        r = None
        sha = getattr(f, "sha256", None)
        if sha:                                   # trung cache: khong doc tep (QC 22/11)
            r = _cached(_key(business_doctype, business_name, sha))
        if not r:
            try:
                content = read_bytes(f)
            except Exception:
                errs.append("document_verify:%s:unreadable" % f.file_name)
                continue
            r = verify(business_doctype, business_name, f.file_name, content)
        if r["status"] != "match":
            errs.append("document_verify:%s:%s" % (f.file_name, r["status"]))
    return errs
