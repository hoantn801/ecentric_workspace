# Copyright (c) 2026, eCentric and contributors
"""Tep KY do nghiep vu khai (PR-G 23/11/2026, gop y chat Hop dong muc 3).

Hop dong voi nghiep vu (hooks.py cua app):
    ec_esign_signing_files = {"<business doctype>": "<duong.dan.ham>"}
    ham(business_name) -> [file_url, ...]   # DUY NHAT cac tep nay la tai lieu ky

  * Loai phieu KHONG khai hook (DNTT): khong doi gi - moi PDF dinh kem mac dinh "can ky", nguoi
    lap tu phan loai "Bo chung tu" nhu cu.
  * Loai phieu DA khai: tep trong danh sach = can ky; moi tep khac = bo chung tu (KHONG bao gio
    vao goi ky voi requires_signature=1). Nguoi lap khong doi phan loai duoc (nghiep vu quyet).
  * Ham loi / tra sai kieu -> FAIL-CLOSED: coi nhu KHONG co tep ky nao (preflight chan voi cau ro
    rang), khong roi ve "moi PDF deu ky".
Mot cho duy nhat quyet dinh tep nao duoc ky: moi duong them tep vao goi (dat o ky, phan loai,
goi cua nguoi lap ky, tao ban sua) deu hoi qua day.
"""
import frappe

HOOK = "ec_esign_signing_files"


def hook_path(business_doctype):
    try:
        hooks = frappe.get_hooks(HOOK) or {}
    except Exception:
        return None
    path = hooks.get(business_doctype) if isinstance(hooks, dict) else None
    if isinstance(path, (list, tuple)):
        path = path[-1] if path else None
    return path or None


def declared(business_doctype, business_name):
    """None khi loai phieu khong khai hook. Nguoc lai: {"urls": frozenset, "error": str|None}.
    Loi -> urls rong + error (fail-closed)."""
    path = hook_path(business_doctype)
    if not path:
        return None
    try:
        rows = frappe.get_attr(path)(business_name)
        if rows is None:
            rows = []
        if isinstance(rows, str) or not isinstance(rows, (list, tuple, set, frozenset)):
            raise TypeError("ham tep ky phai tra danh sach file_url")
        urls = frozenset(str(u).strip() for u in rows if u and str(u).strip())
        _mark_first_seen(business_doctype)
        return {"urls": urls, "error": None}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "esign signing files hook %s" % path)
        return {"urls": frozenset(), "error": type(e).__name__}


FIRST_SEEN_KEY = "ec_esign_signing_files_since:%s"


def first_seen(business_doctype):
    """Lan dau he thong goi thanh cong hook tep ky cua loai phieu nay (chuoi datetime) hoac None."""
    try:
        return frappe.db.get_default(FIRST_SEEN_KEY % business_doctype) or None
    except Exception:
        return None


def _mark_first_seen(business_doctype):
    """Ghi moc lan dau (mot lan, khong ghi de). Loi -> bo qua (moc chi dung de so goi cu)."""
    try:
        key = FIRST_SEEN_KEY % business_doctype
        if not frappe.db.get_default(key):
            from frappe.utils import now_datetime
            frappe.db.set_default(key, str(now_datetime()))
    except Exception:
        pass


def declared_shas(decl):
    """sha256 noi dung cua cac tep khai (tinh mot lan cho moi `decl`). Cung mot noi dung co the
    nam o nhieu dong File / nhieu duong dan (Frappe tao dong thu hai cho truong Attach; tai lai
    cung tep) - so theo NOI DUNG giong man thiet lap (nhom theo ma bam), khong chi theo URL."""
    if decl is None:
        return frozenset()
    if "_shas" in decl:
        return decl["_shas"]
    out = set()
    try:
        from ecentric_workspace.platform.esign import hashing
        from ecentric_workspace.platform.esign import package as pkgsvc
    except Exception:
        decl["_shas"] = frozenset()
        return decl["_shas"]             # khong doc duoc -> chi con so theo URL
    for url in decl.get("urls") or ():
        try:
            fid = frappe.db.get_value("File", {"file_url": url}, "name")
            if fid:
                out.add(hashing.sha256_bytes(pkgsvc.raw_file_bytes(fid)))
        except Exception:
            continue                     # khong doc duoc -> chi con so theo URL
    decl["_shas"] = frozenset(out)
    return decl["_shas"]


def is_signing_file(business_doctype, business_name, file_url, decl=None, sha=None):
    """True/False theo khai bao; None khi loai phieu khong khai (nguoi goi giu luat cu).
    Khop theo URL, hoac theo noi dung (sha256) khi nguoi goi dua `sha`."""
    d = decl if decl is not None else declared(business_doctype, business_name)
    if d is None:
        return None
    if file_url and str(file_url).strip() in d["urls"]:
        return True
    return bool(sha) and sha in declared_shas(d)


def dsf_file_url(dsf):
    """file_url cua File ma dong DSF tro vao (dong co `file`)."""
    fid = dsf.get("file") if isinstance(dsf, dict) else getattr(dsf, "file", None)
    if not fid:
        return None
    return frappe.db.get_value("File", fid, "file_url")


def package_errors(pkg_name, business_doctype, business_name, files):
    """Loi preflight theo khai bao tep ky (loai phieu da khai). `files` = package_files(pkg).
    Ma loi: signing_files_unavailable | signing_file_not_declared:<ten> |
    signing_file_missing:<n>. Loai phieu khong khai -> []."""
    d = declared(business_doctype, business_name)
    if d is None:
        return []
    if d["error"] or not d["urls"]:
        return ["signing_files_unavailable"]
    errs = []
    have = set()
    shas = None
    for f in files:
        if not f.get("requires_signature"):
            continue
        url = dsf_file_url(f)
        if url in d["urls"]:
            have.add(url)
            continue
        if shas is None:
            shas = declared_shas(d)
        if f.get("sha256") and f.get("sha256") in shas:
            have.add(("sha", f.get("sha256")))
            continue
        errs.append("signing_file_not_declared:%s" % f.get("file_name"))
    covered_urls = {h for h in have if isinstance(h, str)}
    covered_shas = {h[1] for h in have if isinstance(h, tuple)}
    if covered_shas:
        # Tep khai khop theo noi dung (khac duong dan) cung tinh la co mat.
        for url in d["urls"] - covered_urls:
            try:
                from ecentric_workspace.platform.esign import hashing
                from ecentric_workspace.platform.esign import package as pkgsvc
                fid = frappe.db.get_value("File", {"file_url": url}, "name")
                if fid and hashing.sha256_bytes(pkgsvc.raw_file_bytes(fid)) in covered_shas:
                    covered_urls.add(url)
            except Exception:
                continue
    missing = len(d["urls"] - covered_urls)
    if missing:
        errs.append("signing_file_missing:%d" % missing)
    return errs


def signable_declared(business_doctype, business_name, files, decl=None):
    """Loc `files` (package_files) con DUNG cac tep ky dang khai (khop URL / noi dung). Loai phieu
    khong khai -> tra nguyen `files`. Dung cho preflight goi Draft: tep ky cu khong con khai (ban
    PDF cu sau khi mo lai) se bi go luc khoa (reconcile_draft) - khong bao loi o day (QC PR-G
    vong 2 B-1)."""
    d = decl if decl is not None else declared(business_doctype, business_name)
    if d is None or d.get("error"):
        return list(files)
    out = []
    for f in files:
        if not f.get("requires_signature"):
            out.append(f)
            continue
        if is_signing_file(business_doctype, business_name, dsf_file_url(f), d,
                           sha=f.get("sha256")):
            out.append(f)
    return out


def reconcile_draft(pkg_name, business_doctype, business_name, decl=None):
    """Dua goi DRAFT ve dung khai bao tep ky: go (dong goi + o ky) moi tep `requires_signature`
    KHONG con la tep ky khai (vd ban PDF cu con lai sau "Thay ban PDF" -> mo lai -> tai ban moi).
    Chi goi Draft; loai phieu khong khai / ham khai loi -> khong lam gi (preflight se chan). Goi
    tu: dat o ky (auto_place, save_placement) va khoa goi (package.lock_package). Ghi vet.
    Tra danh sach ten tep da go. QC PR-G vong 2 B-1."""
    d = decl if decl is not None else declared(business_doctype, business_name)
    if d is None or d.get("error") or not d.get("urls") or not pkg_name:
        return []
    from ecentric_workspace.platform.esign import package as pkgsvc
    if frappe.db.get_value("EC Digital Signature Package", pkg_name, "status") != "Draft":
        return []
    dropped = []
    for f in pkgsvc.package_files(pkg_name):
        if not f.get("requires_signature"):
            continue
        if is_signing_file(business_doctype, business_name, dsf_file_url(f), d,
                           sha=f.get("sha256")):
            continue
        dropped.append(f.get("file_name"))
        pkgsvc.remove_file(f.get("name"))
    if dropped:
        from ecentric_workspace.platform.esign import events
        events.emit("PollTick", package=pkg_name, erp_actor=frappe.session.user,
                    verification_result="signing_files_reconciled",
                    request_meta={"dropped_files": dropped})
    return dropped
