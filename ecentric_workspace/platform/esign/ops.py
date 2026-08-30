# Copyright (c) 2026, eCentric and contributors
"""Nhung viec ky so dang CHO NGUOI CAN THIEP - va cho biet ai lam duoc gi.

Vi sao co file nay. Khi mot chan ky hong, he thong day no vao mot trang thai cho nguoi xu
ly, va cac ham cuu ho da duoc viet dung tu lau: retry_signature_request,
reconcile_signature_request, reconcile_document_creation, retrieve_signed_files,
resolve_signed_file_review. Nhung KHONG GIAO DIEN NAO GOI CHUNG. Chung chi chay duoc neu co
ai do go tay mot lenh API.

Hau qua thuc te (ra soat 29/08): `Permanent Failure` va `Cancelled` khong co canh ra trong
may trang thai, khoa chong trung lai la `unique` nen khong tao lai chan ky moi duoc. Phieu
nam chet o do vinh vien. Moi su co ky so deu phai goi nguoi viet he thong.

Doc-only. Khong ghi gi. Moi hanh dong deu di qua endpoint rieng cua no, moi cai tu kiem
quyen lay - trang nay chi la mot danh sach.
"""
import frappe

DSR = "EC Digital Signature Request"
DSF = "EC Digital Signature File"
PKG = "EC Digital Signature Package"
EVT = "EC Digital Signature Event"
AR = "EC Approval Request"

#: Chan ky khong tu thoat duoc: cron khong dua no di dau ca, phai co nguoi quyet dinh.
#:
#: `Retryable Failure` KHONG nam day - poll_pending tu day no ve Queued cho toi khi het luot
#: roi moi chuyen sang Manual Review. Liet ke no o day la bao dong gia mot viec dang tu chay.
_NEEDS_HUMAN = ("Manual Review", "Verification Mismatch", "Permanent Failure")

#: Qua nguong nay ma van chua tai duoc PDF da ky thi khong con la "cham" nua.
#: cron chay moi 30 phut -> 10 lan ~ 5 tieng.
RETRIEVAL_ALERT_AFTER = 10


def _label(dsr):
    who = dsr.get("actor_user") or dsr.get("approver") or ""
    return "%s%s" % (dsr.get("actor_type") or "?", (" - " + who) if who else "")


def _last_error(dsr_name):
    """Su kien loi gan nhat cua mot chan ky. Chi lay MA loi, khong lay payload."""
    rows = frappe.get_all(EVT, filters={"signature_request": dsr_name,
                                        "error_summary": ["is", "set"]},
                          fields=["event_type", "error_summary", "creation"],
                          order_by="creation desc", limit_page_length=1)
    if not rows:
        return None
    r = rows[0]
    summary = (r.get("error_summary") or "")[:200]
    return {"event": r.get("event_type"), "error": summary, "at": str(r.get("creation") or "")}


def _attempts(package_name, event_type):
    return frappe.db.count(EVT, {"package": package_name, "event_type": event_type})


def stuck_legs(limit=100):
    """Chan ky dang cho nguoi quyet dinh, kem VIEC LAM DUOC voi tung cai.

    `actions` la hop dong voi giao dien: no chi ve nut nao duoc ve. Suy ra tu may trang thai
    chu khong go tay, de khi may trang thai doi thi danh sach nut doi theo.
    """
    from ecentric_workspace.platform.esign import state as sm
    rows = frappe.get_all(
        DSR, filters={"status": ["in", _NEEDS_HUMAN]},
        fields=["name", "status", "actor_type", "actor_user", "approver", "package",
                "business_doctype", "business_name", "request_attempt", "modified"],
        order_by="modified desc", limit_page_length=limit)
    out = []
    for r in rows:
        exits = sm.DSR_TRANSITIONS.get(r.status, ())
        actions = []
        # Doi soat = DOC LAI trang thai ben nha cung cap roi xac minh. Khong bao gio gui lai
        # lenh ky (se tao chu ky thu hai) - xem api.reconcile_signature_request.
        if "Approval Completed" in exits or "Signed" in exits:
            actions.append("reconcile")
        if "Queued" in exits:
            actions.append("retry")
        if "Cancelled" in exits:
            actions.append("cancel")
        out.append({
            "name": r.name, "status": r.status, "who": _label(r),
            "business_doctype": r.business_doctype, "business_name": r.business_name,
            "package": r.package, "attempt": r.request_attempt or 1,
            "since": str(r.modified or ""), "actions": actions,
            "last_error": _last_error(r.name),
            # Khong co canh ra nao = ngo cut that su. Giao dien phai noi thang thay vi ve mot
            # hang nut khong bam duoc.
            "dead_end": not actions,
        })
    return out


def unretrieved_bundles(limit=100):
    """Goi da ky xong nhung PDF chua ve duoc ERP.

    Cron `retrieve_signed_bundles` chay 30 phut/lan va thu lai VO HAN: khong dem so lan,
    khong leo thang, khong tao nhac viec. Nen mot goi hong quay mai trong im lang, va no
    trong y het mot goi dang cho binh thuong. Cot `attempts` chinh la thu phan biet hai cai
    do - 29/08 co hai goi da quay hon 30 lan voi loi 404 ma khong ai biet.
    """
    rows = frappe.get_all(
        PKG, filters={"status": "Active", "signed_bundle_complete": 0},
        fields=["name", "business_doctype", "business_name", "scts_document_id", "modified"],
        order_by="modified desc", limit_page_length=limit)
    out = []
    for r in rows:
        tries = _attempts(r.name, "SignedFileRetrievalStarted")
        fails = frappe.get_all(EVT, filters={"package": r.name,
                                             "event_type": "SignedFileRetrievalFailed"},
                               fields=["error_summary", "creation"],
                               order_by="creation desc", limit_page_length=1)
        out.append({
            "name": r.name, "business_doctype": r.business_doctype,
            "business_name": r.business_name,
            "has_provider_document": bool(r.scts_document_id),
            "attempts": tries,
            "stalled": tries >= RETRIEVAL_ALERT_AFTER,
            "last_error": ((fails[0].get("error_summary") or "")[:200] if fails else None),
            "since": str(r.modified or ""),
            # Chua thu lan nao + khong co loi = tai lieu ben nha cung cap chua o trang thai
            # da ky hoan tat. Do la CHO, khong phai HONG - noi ro de khong ai di sua nham.
            "waiting_on_provider": tries == 0 and not fails,
            "actions": ["retrieve"],
        })
    return out


def hash_mismatch_reviews(limit=50):
    """PDF da ky ve toi noi nhung ma bam KHAC ban da chap nhan - phai co nguoi doi chieu.

    Khong co DocType rieng cho viec nay: signed_files._store_hash_mismatch danh dau ngay
    tren DONG TEP bang `provider_status = "SignedHashMismatch"`, giu nguyen con tro tep da
    chap nhan, va mo mot nhac viec. Xem review.pending_reviews.
    """
    rows = frappe.get_all(
        DSF, filters={"provider_status": "SignedHashMismatch"},
        fields=["name", "package", "file_name", "signed_file_sha256", "modified"],
        order_by="modified desc", limit_page_length=limit)
    out = []
    for r in rows:
        pkg = frappe.db.get_value(PKG, r.package, ["business_doctype", "business_name"],
                                  as_dict=True) if r.package else None
        out.append({"name": r.name, "package": r.package, "file": r.file_name,
                    "business_doctype": pkg.business_doctype if pkg else None,
                    "business_name": pkg.business_name if pkg else None,
                    "since": str(r.modified or ""), "actions": ["resolve_review"]})
    return out


def summary():
    """Con so cho the dau trang. Dem rieng cai DA CHET voi cai dang cho."""
    legs = stuck_legs(limit=500)
    bundles = unretrieved_bundles(limit=500)
    return {
        "stuck_legs": len(legs),
        "dead_end_legs": len([x for x in legs if x["dead_end"]]),
        "unretrieved": len(bundles),
        "stalled_retrievals": len([x for x in bundles if x["stalled"]]),
        "waiting_on_provider": len([x for x in bundles if x["waiting_on_provider"]]),
        "hash_mismatch": len(hash_mismatch_reviews(limit=500)),
    }


def inbox():
    """Tat ca trong mot lan goi - trang nay mo ra la thay het, khong bam tung tab."""
    return {"summary": summary(), "stuck_legs": stuck_legs(),
            "unretrieved": unretrieved_bundles(), "hash_mismatch": hash_mismatch_reviews(),
            "retrieval_alert_after": RETRIEVAL_ALERT_AFTER}
