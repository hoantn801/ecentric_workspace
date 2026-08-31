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
#: Dem theo LUOT CRON (xem _retrieval_rounds), khong theo so tep - cron chay moi 30 phut
#: nen 10 luot ~ 5 tieng. Nham hai thu nay thi nguong that su ngan hon nhan ghi nhieu lan.
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


def _signable_file_count(package_name):
    """So tep CAN KY cua goi - mau so de doi so lan tai TEP thanh so LUOT cron."""
    return frappe.db.count(DSF, {"package": package_name, "requires_signature": 1}) or 1


def _retrieval_rounds(package_name):
    """So LUOT cron da cham vao goi nay, xap xi.

    `SignedFileRetrievalStarted` duoc phat ra MOT LAN CHO MOI TEP (signed_files._retrieve_one),
    khong phai mot lan cho moi luot cron. Nen voi goi 3 tep, "10 lan thu" that ra la ~3,3
    luot ~ 1,7 tieng chu khong phai 5 tieng nhu nhan ghi. Chia cho so tep can ky de con so
    tren man hinh dung voi cai nguoi doc tuong.

    Xap xi chu khong chinh xac: tep da lay duoc se di vao nhanh `SignedFileDuplicateSkipped`
    va khong phat `Started` nua, nen mau so tut dan khi mot phan goi da xong. Chap nhan
    duoc - viec can biet la "dang cho" hay "quay mai", khong phai con so tuyet doi.
    """
    return _attempts(package_name, "SignedFileRetrievalStarted") // _signable_file_count(package_name)


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
    # Loc KHOP VOI CRON, khong chat hon. Cron quet `scts_document_id da co` + `chua tai
    # xong`, khong xet trang thai goi. Truoc day trang nay chi liet ke goi `Active`, nen mot
    # goi da `Completed` ma chua tai xong PDF van bi cron thu lai moi 30 phut trong khi
    # KHONG hien o dau ca - dung loai an so ma trang nay sinh ra de xoa bo.
    rows = frappe.get_all(
        PKG, filters={"scts_document_id": ["is", "set"], "signed_bundle_complete": 0,
                      "status": ["not in", ("Cancelled", "Superseded")]},
        fields=["name", "status", "business_doctype", "business_name", "scts_document_id",
                "modified"],
        order_by="modified desc", limit_page_length=limit)
    out = []
    for r in rows:
        tries = _retrieval_rounds(r.name)
        fails = frappe.get_all(EVT, filters={"package": r.name,
                                             "event_type": "SignedFileRetrievalFailed"},
                               fields=["error_summary", "creation"],
                               order_by="creation desc", limit_page_length=1)
        out.append({
            "name": r.name, "business_doctype": r.business_doctype,
            "business_name": r.business_name, "package_status": r.status,
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


def signature_debts(limit=100):
    """Cap duyet da hoan tat MA CHUA CO chu ky so - ghi khi cong ky so dang tat.

    Da chot 31/08: phieu van di tiep va hoan tat duoc du con no. Doi lai, mon no phai HIEN
    RA - mot mon no khong ai nhin thay la mot mon no khong bao gio duoc tra.
    """
    rows = frappe.get_all(
        "EC Approval Request Level",
        filters={"signature_deferred": 1, "signature_settled_at": ["is", "not set"]},
        fields=["name", "approval_request", "level_no", "level_name",
                "signature_deferred_by", "signature_deferred_at"],
        order_by="signature_deferred_at asc", limit_page_length=limit)
    out = []
    for r in rows:
        req = frappe.db.get_value(AR, r.approval_request,
                                  ["reference_doctype", "reference_name", "approval_status"],
                                  as_dict=True) if r.approval_request else None
        out.append({
            "name": r.name, "approval_request": r.approval_request,
            "level_no": r.level_no, "level_name": r.level_name,
            "who": r.signature_deferred_by,
            "since": str(r.signature_deferred_at or ""),
            "business_doctype": req.reference_doctype if req else None,
            "business_name": req.reference_name if req else None,
            # Phieu da duyet xong ma van no = mon no de bi bo quen nhat.
            "request_status": req.approval_status if req else None,
            # Dong mon no = GHI NHAN, khong phai ky ho. Hai ket cuc trung thuc, ca hai deu
            # bat buoc ly do - xem guard.settle_signature_debt.
            "actions": ["debt_signed", "debt_waived"],
        })
    return out


def summary(legs=None, bundles=None, mismatches=None, debts=None):
    """Con so cho the dau trang. Dem rieng cai DA CHET voi cai dang cho.

    Nhan san danh sach de KHONG truy van lai. Ban dau `inbox()` goi `summary()` roi goi LAI
    ca bon ham - moi thu chay hai lan, va ba trong bon ham co N+1 ben trong (moi dong mot
    truy van phu). Voi 50 goi dang cho la hon 200 truy van cho MOT lan mo trang.
    """
    legs = stuck_legs(limit=500) if legs is None else legs
    bundles = unretrieved_bundles(limit=500) if bundles is None else bundles
    mismatches = hash_mismatch_reviews(limit=500) if mismatches is None else mismatches
    debts = signature_debts(limit=500) if debts is None else debts
    return {
        "stuck_legs": len(legs),
        "dead_end_legs": len([x for x in legs if x["dead_end"]]),
        "unretrieved": len(bundles),
        "stalled_retrievals": len([x for x in bundles if x["stalled"]]),
        "waiting_on_provider": len([x for x in bundles if x["waiting_on_provider"]]),
        "hash_mismatch": len(mismatches),
        "signature_debts": len(debts),
    }


def inbox():
    """Tat ca trong MOT lan goi - trang nay mo ra la thay het, khong bam tung tab.

    Moi ham chay dung mot lan; `summary` dem tren chinh ket qua do.
    """
    legs = stuck_legs()
    bundles = unretrieved_bundles()
    mismatches = hash_mismatch_reviews()
    debts = signature_debts()
    return {"summary": summary(legs, bundles, mismatches, debts),
            "stuck_legs": legs, "unretrieved": bundles, "hash_mismatch": mismatches,
            "signature_debts": debts,
            "retrieval_alert_after": RETRIEVAL_ALERT_AFTER}
