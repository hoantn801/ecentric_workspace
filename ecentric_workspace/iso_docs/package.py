# Copyright (c) 2026, eCentric and contributors
"""Goi quy trinh tu chat Claude -> du lieu tai lieu (THUAN, khong frappe).

Dinh dang goi: NHIEU_LOP/iso/HUONG_DAN_DONG_GOI_QUY_TRINH.md (goi.json + noi_dung.pdf/.docx +
bieu_mau/). Cung luat voi kiem_goi_quy_trinh.py ma chat dong goi tu chay truoc khi gui.
Goi KHONG BAO GIO tu ban hanh: nhap goi chi tao / ghi de ban NHAP.
"""
import json
import re

from ecentric_workspace.iso_docs import constants as C
from ecentric_workspace.iso_docs import domain as D

TYPES = tuple(n for _p, n in C.DOC_TYPES)
STEP_ID_RE = re.compile(r"^S\w{1,6}$")
NODE_RE = re.compile(r"^\s*(S\w{1,6})\s*[\[\{\(]")
EDGE_RE = re.compile(r"(S\w{1,6})\s*(?:--+>|-\.->|==+>|--\s*\"[^\"]*\"\s*-->)\s*(S\w{1,6})")
MERMAID_FORBIDDEN = ("click ", "style ", "classdef", "class ", "href", "javascript:", "linkstyle", "%%{",
                     "<script", "<iframe", "onerror", "onload")
PLACEHOLDERS = ("ABC/", "Trưởng phòng ABC", "……", "...........", "[ĐIỀN", "TODO")
KIND_MAP = {"lon": C.KIND_MAJOR, "nho": C.KIND_MINOR}
MAX_STEPS = 30


def _txt(v):
    return (v or "").strip() if isinstance(v, str) else ""


def mermaid_nodes(src):
    return [m.group(1) for m in (NODE_RE.match(l) for l in (src or "").splitlines()) if m]


def errors(pkg, departments, code=""):
    """-> [loi]. departments: ten Department hop le tren site. code: ma Ban ISO nhap cho goi moi."""
    e = []
    if not isinstance(pkg, dict):
        return ["goi.json không phải một đối tượng JSON."]
    if pkg.get("phien_ban_goi") != 1:
        e.append("phien_ban_goi phải là 1.")
    kind = pkg.get("loai_goi")
    if kind not in ("moi", "sua_doi"):
        e.append("loai_goi phải là 'moi' hoặc 'sua_doi'.")
    if pkg.get("loai") not in TYPES:
        e.append("loai không hợp lệ: %r." % pkg.get("loai"))
    if _txt(pkg.get("ten")) == "":
        e.append("Thiếu tên tài liệu (ten).")
    if pkg.get("phong_ban") not in departments:
        e.append("phong_ban phải đúng tên phòng ban trên ERP: %r." % pkg.get("phong_ban"))
    target = code or (pkg.get("ma_tai_lieu") if kind == "sua_doi" else pkg.get("ma_de_xuat")) or ""
    ce = D.code_error(target, pkg.get("loai"))
    if ce:
        e.append(ce if target else "Chưa có mã tài liệu: gói mới cần Ban ISO nhập mã.")
    if kind == "sua_doi":
        if pkg.get("kieu_sua") not in KIND_MAP:
            e.append("Gói sửa đổi phải có kieu_sua 'lon' hoặc 'nho'.")
        if not _txt(pkg.get("tom_tat_thay_doi")):
            e.append("Gói sửa đổi phải có tom_tat_thay_doi.")
    pv = pkg.get("pham_vi_doc") or {}
    if not isinstance(pv, dict):
        e.append("pham_vi_doc không hợp lệ.")
        pv = {}
    if not pv.get("ca_cong_ty"):
        if not pv.get("phong_ban"):
            e.append("pham_vi_doc: không phải cả công ty thì phải liệt kê phong_ban.")
        for d in pv.get("phong_ban") or []:
            if d not in departments:
                e.append("pham_vi_doc.phong_ban sai tên: %r." % d)
        if pkg.get("thong_bao_trang_chu"):
            e.append("Chỉ tài liệu cả công ty mới được thông báo lên trang chủ.")
    tt = pkg.get("tom_tat") or {}
    for k in ("dung_khi", "chuan_bi", "ket_qua"):
        if not _txt(tt.get(k) if isinstance(tt, dict) else ""):
            e.append("tom_tat thiếu %s." % k)
    roles = pkg.get("vai_tro") or []
    codes = {r.get("ma") for r in roles if isinstance(r, dict)}
    if not roles or any(not isinstance(r, dict) or not r.get("ma") or not r.get("ten") for r in roles):
        e.append("vai_tro: cần ít nhất một vai trò, mỗi dòng có ma và ten.")
    steps = pkg.get("buoc") or []
    if not steps:
        e.append("Thiếu các bước (buoc).")
    if len(steps) > MAX_STEPS:
        e.append("Quá %d bước: tách thành quy trình con." % MAX_STEPS)
    forms = {f.get("ma") for f in pkg.get("bieu_mau") or [] if isinstance(f, dict)}
    ids = []
    for b in steps:
        if not isinstance(b, dict):
            e.append("Một bước không hợp lệ.")
            continue
        bid = b.get("id") or ""
        if not STEP_ID_RE.match(bid):
            e.append("buoc.id phải dạng S1, S2, S7a…: %r." % bid)
        ids.append(bid)
        for k in ("stt", "ten", "A", "R", "dien_giai"):
            if not b.get(k):
                e.append("Bước %s thiếu %s." % (bid, k))
        for r in [b.get("A")] + list(b.get("R") or []) + list(b.get("CI") or []):
            if r and r not in codes:
                e.append("Bước %s nhắc vai trò %r không có trong vai_tro." % (bid, r))
        for m in b.get("bieu_mau") or []:
            if m not in forms:
                e.append("Bước %s nhắc biểu mẫu %r không có trong bieu_mau." % (bid, m))
        fe = _txt(b.get("form_erp"))
        if fe and not fe.startswith("/"):
            e.append("Bước %s: form_erp phải là đường dẫn trên ERP, bắt đầu bằng /." % bid)
    if len(ids) != len(set(ids)):
        e.append("buoc.id bị trùng.")
    src = pkg.get("so_do_mermaid") or ""
    if not isinstance(src, str) or not src.strip().startswith("flowchart TD"):
        e.append("so_do_mermaid phải bắt đầu bằng 'flowchart TD'.")
    else:
        low = src.lower()
        for bad in MERMAID_FORBIDDEN:
            if bad in low:
                e.append("so_do_mermaid có từ khoá không cho phép: %r." % bad.strip())
        nodes = mermaid_nodes(src)
        missing = [i for i in ids if i and i not in nodes]
        extra = [n for n in nodes if n not in ids]
        if missing:
            e.append("Sơ đồ thiếu nút cho bước: %s." % ", ".join(missing))
        if extra:
            e.append("Sơ đồ có nút không ứng với bước nào: %s." % ", ".join(extra))
    blob = json.dumps(pkg, ensure_ascii=False)
    for ph in PLACEHOLDERS:
        if ph in blob:
            e.append("Gói còn chữ giữ chỗ %r: điền nội dung thật." % ph)
    return e


def doc_code(pkg, code=""):
    return (code or (pkg.get("ma_tai_lieu") if pkg.get("loai_goi") == "sua_doi" else pkg.get("ma_de_xuat"))
            or "").strip().upper()


def steps_payload(pkg, form_urls=None):
    """Phan cua goi luu theo phien ban (ec_steps_json): tom tat, vai tro, buoc, bieu mau, hoi dap."""
    urls = form_urls or {}
    forms = []
    for f in pkg.get("bieu_mau") or []:
        if isinstance(f, dict):
            forms.append({"ma": f.get("ma"), "ten": f.get("ten"), "url": urls.get(f.get("ma")) or ""})
    keep = {"tom_tat": pkg.get("tom_tat") or {}, "vai_tro": pkg.get("vai_tro") or [],
            "buoc": pkg.get("buoc") or [], "bieu_mau": forms,
            "cau_hoi_thuong_gap": pkg.get("cau_hoi_thuong_gap") or [], "nguon": pkg.get("nguon") or ""}
    return json.dumps(keep, ensure_ascii=False, indent=1)


def to_fields(pkg, code, session_user):
    """-> truong Quality Procedure cho ban nhap (khong gom tep, khong gom trang thai)."""
    pv = pkg.get("pham_vi_doc") or {}
    wide = 1 if pv.get("ca_cong_ty") else 0
    sections = pkg.get("muc_thay_doi") or []
    if isinstance(sections, list):
        sections = "\n".join(str(s) for s in sections)
    f = {
        "quality_procedure_name": _txt(pkg.get("ten"))[:140],
        "ec_doc_code": code,
        "ec_doc_type": pkg.get("loai"),
        "ec_department": pkg.get("phong_ban"),
        "ec_change_kind": KIND_MAP.get(pkg.get("kieu_sua"), "") if pkg.get("loai_goi") == "sua_doi" else "",
        "ec_change_summary": _txt(pkg.get("tom_tat_thay_doi")) or ("Ban hành lần đầu trên ERP"
                                                                   if pkg.get("loai_goi") == "moi" else ""),
        "ec_changed_sections": sections or "",
        "ec_drafter": _txt(pkg.get("nguoi_soan_email")) or session_user,
        "ec_source": "Gói từ Claude",
        "ec_company_wide": wide,
        "ec_notify_home": 1 if (wide and pkg.get("thong_bao_trang_chu")) else 0,
        "ec_notify_summary": _txt(pkg.get("tom_tat_thong_bao")),
        "ec_mermaid": (pkg.get("so_do_mermaid") or "").strip(),
        "scope_departments": [] if wide else list(pv.get("phong_ban") or []),
    }
    months = pkg.get("chu_ky_ra_soat_thang")
    if isinstance(months, int) and 1 <= months <= 60:
        f["ec_review_months"] = months
    return f
