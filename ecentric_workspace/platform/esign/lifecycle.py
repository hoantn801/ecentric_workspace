# Copyright (c) 2026, eCentric and contributors
"""What has to happen to a signing package when the approval flow reopens a request.

The gap this closes, observed live on 2026-08-27 (EC-PAYR-2026-00027):

    14:07  lien.vu     "Yêu cầu bổ sung"  - Pending -> Information Required
    17:54  hoan.tran   "Gửi lại"

`resubmit()` reset the approval levels and touched nothing else. The signing package stayed
Locked with the file list frozen at lock time, so a document attached after 14:07 was NOT in
it. Every later level would then sign the OLD set of documents while everyone believed they
were looking at the supplemented one. No error, no warning - the kind of wrong answer that
only surfaces during an audit, months later.

`package.create_revision()` was written for exactly this and documented as "used by resubmit
cycles", but nothing ever called it.

## The judgement call, stated plainly

A signature attests to the documents as they stood at the moment of signing. Change the
documents and an earlier signature no longer says what it appears to say. So when digital
signatures have ALREADY been collected and the package is reopened, the approval restarts
from level 1 rather than resuming mid-chain.

That is deliberately the inconvenient option. Re-signing costs people a few minutes;
a payment carrying signatures that attest to a different document set is not recoverable
after the fact. Accounting and legal should confirm the rule, but until they do, the safe
side is the one that asks for the signature again.

When nothing has been signed yet there is nothing to invalidate, so an ordinary resubmit
proceeds - only the package is revised so new attachments can join it.
"""
import frappe
from frappe import _

from ecentric_workspace.platform.esign import events
from ecentric_workspace.platform.esign import hashing
from ecentric_workspace.platform.esign import package as pkgsvc
from ecentric_workspace.platform.esign import state as sm

#: Package states that hold a frozen file list. A Draft package still picks up new
#: attachments by itself, so it needs no revision.
_FROZEN = ("Locked", "Active", "Provider Created", "Provider Create Failed")

#: A leg that reached this state means a real signature exists at the provider.
_SIGNED = ("Approval Completed",)


def _frozen_package(approval_request):
    return frappe.db.get_value("EC Digital Signature Package",
                               {"approval_request": approval_request,
                                "status": ["in", _FROZEN]},
                               ["name", "business_doctype", "business_name"],
                               order_by="creation desc", as_dict=True)


def has_collected_signatures(package_name):
    return bool(frappe.db.count("EC Digital Signature Request",
                                {"package": package_name, "status": ["in", _SIGNED]}))


def _reopened_draft(approval_request):
    """Goi Draft cua phieu do reopen_for_edit tao (co vet `reopened_for_edit`), hoac None."""
    name = frappe.db.get_value("EC Digital Signature Package",
                               {"approval_request": approval_request, "status": "Draft"}, "name")
    if name and frappe.get_all("EC Digital Signature Event",
                               filters={"package": name, "event_type": "PollTick",
                                        "verification_result": "reopened_for_edit"},
                               fields=["name"], limit_page_length=1):
        return name
    return None


def _signing_decl(pkg):
    """Khai bao tep ky cua nghiep vu (signing_files.declared) cho goi, hoac None (PR-G)."""
    from ecentric_workspace.platform.esign import signing_files
    return signing_files.declared(pkg.business_doctype, pkg.business_name)


def _signable_content_verdict(pkg, decl=None):
    """`unchanged` | `changed` | `unreadable` - BA ket qua, khong phai hai.

    Truoc day ham nay tra bool va gop "khong doc duoc" vao "da doi", voi ly le: lam lai goi
    ky la phien toai, con bo qua mot thay doi that su thi de nguyen chu ky cu tren mot to
    trinh da khac. Ly le do dung KHI "da doi" chi ton mot vong ky lai.

    Tu 31/08 "da doi" nghia la TU CHOI HAN duong gui lai. Luc do gop hai thu vao mot nghia
    la: mot tep khong doc duoc tren dia (bi don, mount loi, sai quyen) se chan vinh vien moi
    lan gui lai cua phieu do - va thong bao con noi sai su that ("tai lieu da thay doi").
    Van fail-closed, nhung noi dung cai minh biet.
    """
    if decl is not None and decl.get("error"):
        return "unreadable"             # ham khai tep ky loi -> khong ket luan "da doi" (QC PR-G)
    try:
        signable = [f for f in pkgsvc.package_files(pkg.name) if f.get("requires_signature")]
    except Exception:
        return "unreadable"
    locked = {f.get("sha256") for f in signable if f.get("sha256")}
    if not locked or len(locked) != len(signable):
        return "unreadable"             # thieu ma bam -> khong so duoc, va do la mot su co

    if decl is not None:
        # Nghiep vu khai tep ky (PR-G): so DUNG cac tep dang khai, doc theo file_url (ca tep cong
        # khai - QC vong 2). Bo tep khai phai TRUNG bo da khoa (bot tep cung la "da doi"). Rieng
        # goi khoa TRUOC khi co hook (luat cu: moi PDF deu ky, co the giu them tep) -> chi can
        # tep khai nam trong bo da khoa (an toan cho phieu dang chay).
        present = _declared_shas_strict(decl)
        if present is None:
            return "unreadable"
        if not present:
            return "changed"
        if present == locked:
            return "unchanged"
        if _locked_before_signing_files(pkg) and present.issubset(locked):
            return "unchanged"
        return "changed"
    present = _attached_signable_shas(pkg, decl)
    if present is None:
        return "unreadable"
    # Con nguyen ven tung tep da ky -> chi la dinh kem THEM, khong dung toi noi dung da ky.
    return "unchanged" if locked.issubset(present) else "changed"


def _locked_before_signing_files(pkg):
    """Goi khoa TRUOC lan dau he thong thay hook ec_esign_signing_files cua loai phieu nay (luat
    cu: moi PDF deu ky) -> so "tap con". Moc lay tu signing_files.first_seen (ghi khi declared()
    thanh cong lan dau) - khong ghi cung ngay (QC PR-G vong 3 M3). Chua co moc -> coi la goi cu."""
    from ecentric_workspace.platform.esign import signing_files
    try:
        at = frappe.db.get_value("EC Digital Signature Package", pkg.name, "locked_at")
        since = signing_files.first_seen(pkg.business_doctype)
    except Exception:
        return False
    if not at:
        return False
    return (not since) or str(at) < str(since)


def _declared_shas_strict(decl):
    """sha256 tung tep KHAI (doc theo file_url, ke ca tep cong khai). Mot tep khong doc duoc ->
    None (khong ket luan)."""
    out = set()
    for url in sorted(decl.get("urls") or ()):
        fid = frappe.db.get_value("File", {"file_url": url}, "name")
        if not fid:
            return None
        try:
            content = pkgsvc.raw_file_bytes(fid)
        except Exception:
            return None
        if not content:
            return None
        out.add(hashing.sha256_bytes(content))
    return out


def _attached_signable_shas(pkg, decl=None):
    """sha256 cua cac tep dinh kem CO THE PHAI KY, tinh lai tu noi dung that.

    KHONG dung `File.content_hash`. Ma bam cua goi ky do chinh module nay tinh bang sha256
    (hashing.sha256_bytes, 64 ky tu). `File.content_hash` la truong cua Frappe va duoc sinh
    bang thuat toan RIENG cua framework - khong co gi bao dam no cung la sha256. Neu khac
    thuat toan thi hai tap KHONG BAO GIO giao nhau, `issubset` luon sai, va ham goi se ket
    luan "noi dung da doi" o MOI lan gui lai: ai da ky cung phai ky lai, ke ca khi nguoi de
    nghi chi dinh kem them mot to hoa don - dung cai phien toai ma ban 28/08 dinh bo di.

    So sanh hai dai luong do bang hai thuoc do khac nhau la loi chi lo ra khi chay that;
    bo test cu cam `content_hash` gia bang chinh ma bam cua goi nen khong the bat duoc.

    Chi doc cac tep private co duoi .pdf - dung tieu chi cua _add_requester_pdf_files, la
    noi quyet dinh tep nao vao goi. Doc du thi ton, doc thieu thi ket luan sai.

    Tra ve None khi khong doc duoc: nguoi goi phai coi nhu "da doi" cho chac.
    """
    try:
        rows = frappe.get_all("File",
                              filters={"attached_to_doctype": pkg.business_doctype,
                                       "attached_to_name": pkg.business_name,
                                       "is_private": 1},
                              fields=["name", "file_name", "file_url"], limit_page_length=0)
    except Exception:
        return None
    out, seen_url = set(), set()
    for r in rows:
        name_l = (r.get("file_name") or "").lower()
        url_l = (r.get("file_url") or "").lower()
        if not (name_l.endswith(".pdf") or url_l.endswith(".pdf")):
            continue
        if decl is not None and (r.get("file_url") or "") not in decl["urls"]:
            continue
        # Mot tep vat ly co the co NHIEU dong File tro vao (Frappe tao dong thu hai cho
        # truong Attach; package.add_file luu them mot ban sao). Doc lai cung mot duong dan
        # nhieu lan la I/O thua ngay tren duong nguoi dung dang cho: tran cau hinh la 20 tep
        # x 25 MB, va ham nay chay dong bo trong request "Gui lai".
        if r.get("file_url"):
            if r["file_url"] in seen_url:
                continue
            seen_url.add(r["file_url"])
        try:
            content = pkgsvc.raw_file_bytes(r["name"])
        except Exception:
            return None                 # mot tep khong doc duoc -> khong ket luan gi
        if content:
            out.add(hashing.sha256_bytes(content))
    return out


def on_request_reopened(approval_request):
    """Called by the approval flow BEFORE it resets levels.

    Returns {"revised": bool, "new_package": str|None, "force_restart": bool}.

    Failure is NOT swallowed. If a frozen package exists and cannot be revised, the resubmit
    must stop: carrying on would leave the request open against a stale package, which is the
    precise silent-wrong-result this function exists to prevent.
    """
    out = {"revised": False, "new_package": None, "force_restart": False}
    pkg = _frozen_package(approval_request)
    if not pkg:
        # Nguoi lap da MO LAI thiet lap ky trong luc "Can bo sung" (reopen_for_edit, PR-G): tai
        # lieu tren cong se TAO LAI tu dau -> chuoi duyet phai chay lai tu cap 1 (cac buoc da
        # gui sang cong thuoc tai lieu cu, da huy).
        draft = _reopened_draft(approval_request)
        if draft:
            # Kiem goi Draft TRUOC khi cho phieu ve Pending (QC PR-G vong 2 M-2): thieu o ky / tep
            # ky -> tu choi gui lai, noi ro (khong de phieu Pending ma khong co goi ky de khoa).
            _assert_reopened_draft_ready(draft)
            return {"revised": True, "new_package": draft, "force_restart": True,
                    "reason": "reopened_for_edit"}
        return out

    # Chi lam lai goi ky khi NOI DUNG DA KY thay doi.
    #
    # Truoc 28/08 lan resubmit nao cung tao phien ban moi, nen ai da ky deu phai ky lai -
    # ke ca khi nguoi de nghi chi dinh kem them mot to hoa don theo yeu cau cua Ke toan.
    # Do la truong hop thuong gap nhat va no khong dung: to hoa don la BANG CHUNG kem
    # theo, khong phai to trinh; khong ai ky len no, va viec them no khong lam sai mot chu
    # ky nao da co.
    #
    # Nguoc lai, sua chinh to trinh (so tien, noi dung) thi duong nay DUNG HAN - xem doan
    # duoi. Chu ky so ky len mot noi dung cu the; giu chu ky cu tren to trinh da sua la
    # nguy tao bang chung - cap duyet se "da ky" mot to trinh ho chua tung doc.
    verdict = _signable_content_verdict(pkg, _signing_decl(pkg))
    if verdict == "unchanged":
        # Tep giu nguyen nhung PHIEU co the da sua (so hop dong / so tien) khi "Can bo sung" ->
        # goi Locked di thang sang ky, khong qua preflight Draft. Loai phieu co ham doi chieu
        # (ec_esign_document_verifiers) phai doi chieu lai o day (QC 22/11).
        _assert_documents_still_match(pkg)
        out["unchanged"] = True
        return out

    # Doi TAI LIEU CAN KY thi duong nay KHONG di duoc - tu choi ngay, chua ghi gi.
    #
    # Truoc 31/08 nhanh nay tao mot goi ky moi roi de `sign_on_submit` chay tiep. Chuoi do
    # KHONG BAO GIO ket thuc duoc: create_revision chep tep + o ky cua goi cu, prepare them
    # to trinh MOI voi requires_signature=1 va khong co o ky nao, preflight tu choi va nem
    # loi -> Frappe rollback ca giao dich -> goi Draft vua tao BIEN MAT. Nen cua so dat o ky
    # (document_setup._setup_editable, mo khi goi la Draft va dang cho nguoi de nghi ky)
    # khong bao gio ton tai du mot phan nghin giay ngoai giao dich vua bi huy. Nguoi dung
    # bam "Gui lai" va chi nhan mot thong bao thieu vi tri ky, lan nao cung vay.
    #
    # Quy uoc da chot 31/08: doi tai lieu can ky thi cap duyet TU CHOI, nguoi de nghi bam
    # "Tao phieu moi tu phieu nay". Ly do cung: SCTS chi nhan danh sach tep LUC TAO tai lieu.
    # Nen o day noi thang dieu do thay vi dan nguoi dung vao mot vong lap khong loi ra.
    if verdict == "unreadable":
        frappe.throw(_("Không đọc được nội dung tài liệu đã ký của yêu cầu này, nên không thể "
                       "kiểm tra tài liệu có thay đổi hay không. Vui lòng báo quản trị hệ "
                       "thống trước khi gửi lại."))
    msg = _("Tài liệu cần ký đã thay đổi so với bộ đã ký. Đường “Gửi lại” không xử lý "
            "được trường hợp này: chữ ký số ký lên một nội dung cụ thể, và nhà cung "
            "cấp chỉ nhận danh sách tệp lúc tạo tài liệu.\n\n"
            "Hãy đề nghị cấp duyệt bấm “Từ chối”, rồi dùng “Tạo phiếu mới từ phiếu "
            "này” — nội dung và tệp đính kèm sẽ được chép sang phiếu mới.")
    bd, bn = pkg.business_doctype, pkg.business_name
    if _reopen_check(bd, bn, approval_request, check_user=False, check_portal=False)[0]:
        # Ho so nguoi lap KHONG ky, chua ai ky (PR-G): sua duoc - nhung phai mo lai thiet lap ky
        # TRUOC khi gui (dat o ky cho tep moi), khong lam trong lenh "Gui lai".
        msg = _("Tài liệu cần ký đã thay đổi. Mở lại thiết lập ký trên phiếu trước, tải bản PDF "
                "để ký mới, kiểm tra ô ký rồi bấm Gửi lại.")
    frappe.throw(msg)


def _assert_reopened_draft_ready(draft):
    """Goi Draft mo lai sau "Can bo sung" phai san sang khoa truoc khi "Gui lai" (QC PR-G vong 2
    M-2). Nem loi tieng Viet neu thieu."""
    errs = pkgsvc.preflight_for_lock(draft)
    if errs:
        from ecentric_workspace.platform.esign import requester
        frappe.throw(_("Chưa gửi lại được - bản ký mới chưa sẵn sàng: {0}.").format(
            "; ".join(requester._preflight_vi(e) for e in errs[:6])))


def _assert_documents_still_match(pkg):
    from ecentric_workspace.platform.esign import document_verification as dv
    from ecentric_workspace.platform.esign import package as pkgsvc
    name = pkg.get("name") if isinstance(pkg, dict) else getattr(pkg, "name", pkg)
    row = frappe.db.get_value("EC Digital Signature Package", name,
                              ["business_doctype", "business_name"], as_dict=True) or {}
    if not row.get("business_doctype") or not dv.verifier_path(row.get("business_doctype")):
        return
    files = [f for f in pkgsvc.package_files(name) if f.requires_signature and f.is_pdf]
    errs = dv.package_errors(name, row.get("business_doctype"), row.get("business_name"), files,
                             lambda f: pkgsvc.file_bytes(f.name))
    if errs:
        from ecentric_workspace.platform.esign import requester
        frappe.throw(_("Chưa gửi lại được: {0}.").format(
            "; ".join(requester._preflight_vi(e) for e in errs)))


#: Chan ky dang chay / can nguoi xem - khong mo lai khi con chan nay.
_IN_FLIGHT = ("Prepared", "Queued", "Provider Accepted", "Verifying", "Retryable Failure",
              "Manual Review", "Signed", "Verification Mismatch")


def _lock_rows(business_doctype, business_name, approval_request=None):
    """Khoa hang PHIEU roi hang YEU CAU DUYET - cung thu tu voi auto_place va resubmit (QC PR-G M6)
    - de mo lai va "Gui lai" khong chay chong. Tra ten yeu cau duyet (doc co khoa)."""
    from ecentric_workspace.platform.esign import permissions as perms
    frappe.db.get_value(business_doctype, business_name, "name", for_update=True)
    ar = approval_request or perms.business_approval_request(business_doctype, business_name)
    if ar:
        frappe.db.get_value("EC Approval Request", ar, "name", for_update=True)
    return ar


def portal_signed_signers(pkg_name):
    """(danh sach nguoi DA KY tren cong cua tai lieu cua goi, loi). Khong co tai lieu -> ([], None).
    Khong doc duoc -> (None, "<ly do>"). Goi TRUOC khi khoa hang (khong goi mang khi dang giu
    khoa - QC PR-G vong 2)."""
    row = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["scts_document_id", "provider", "environment"], as_dict=True) or {}
    if not row.get("scts_document_id"):
        return [], None
    try:
        from ecentric_workspace.platform.esign import provider_cancel
        from ecentric_workspace.platform.esign.providers import get_adapter
        settings = provider_cancel._settings(row.get("provider"), row.get("environment"))
        if not settings or not int(settings.get("integration_enabled") or 0):
            return None, "integration_closed"
        state = get_adapter(settings).poll_status(row["scts_document_id"])
        signers = getattr(state, "signers", None) or []
    except Exception as e:
        return None, type(e).__name__
    return [s for s in signers if str((s or {}).get("status") or "").lower() == "signed"], None


def unmatched_signed(pkg_name, signed):
    """Nguoi da ky tren cong KHONG khop danh tinh mot chan ERP da xong cua goi (QC PR-G vong 2
    M-4: so theo DANH TINH, khong dem). Doi tac ngoai (is_external) luon la "khong khop". Khop =
    user_id trung effective_scts_user_id, hoac email thuoc cung danh tinh da xac minh cua chan do."""
    from ecentric_workspace.platform.esign.service import _emails_cua_cung_danh_tinh
    ids, mails = set(), set()
    for r in frappe.get_all("EC Digital Signature Request",
                            filters={"package": pkg_name,
                                     "status": ["in", ("Approval Completed", "Signed")]},
                            fields=["effective_scts_user_id", "actor_user", "approver"]):
        if r.effective_scts_user_id:
            ids.add(str(r.effective_scts_user_id))
        ds = _emails_cua_cung_danh_tinh({"actor_user": r.actor_user or r.approver,
                                         "effective_scts_user_id": r.effective_scts_user_id})
        if isinstance(ds, str):
            ds = [ds]
        mails.update(str(e).strip().lower() for e in (ds or []) if e)
    out = []
    for x in signed or []:
        if bool((x or {}).get("is_external")):
            out.append(x)
            continue
        uid = str((x or {}).get("user_id") or "")
        em = str((x or {}).get("email") or "").strip().lower()
        if (uid and uid in ids) or (em and em in mails):
            continue
        out.append(x)
    return out


def _reopen_check(business_doctype, business_name, approval_request=None, check_user=True,
                  check_portal=True, portal=None):
    """(ok, ly_do, ctx). Dieu kien mo lai thiet lap ky sau "Can bo sung" (PR-G 23/11, gop y chat
    Hop dong muc 2) - CHI ho so nguoi lap KHONG ky:
      * phieu "Information Required"; goi dang khoa (frozen) cua phieu nay;
      * chua co chu ky nao: khong chan Sign da xong, khong co buoc nguoi lap SAU doi tac (WF03 -
        doi tac da ky), tren cong khong co ai ky ngoai cac chan ERP biet, khong doi tac nao da ky
        (doc cong; ho so co doi tac ma khong doc duoc -> tu choi);
      * khong con chan dang chay / cho doi soat; tao tai lieu khong mo ho;
      * tai lieu cu tren cong HUY duoc (tu dong huy dang bat) - khong thi tai lieu cu se con song;
      * ham khai tep ky (neu co) doc duoc.
    ly_do bat dau "refuse:" = du dieu kien nghiep vu nhung KHONG duoc mo (bao nguoi dung).
    Doc trang thai bang lenh CO KHOA khi nguoi goi da khoa hang (_lock_rows)."""
    from ecentric_workspace.platform.esign import permissions as perms
    from ecentric_workspace.platform.esign import signing_files
    # CHI loai phieu chu dong khai tep ky (ec_esign_signing_files) - QC PR-G vong 2 M-3. DNTT va
    # loai khac khong bao gio vao duong nay.
    if not signing_files.hook_path(business_doctype):
        return False, "not_opted_in", None
    ar = approval_request or perms.business_approval_request(business_doctype, business_name)
    if not ar:
        return False, "no_request", None
    if frappe.db.get_value("EC Approval Request", ar, "approval_status",
                           for_update=True) != "Information Required":
        return False, "not_information_required", None
    pkg = frappe.db.get_value("EC Digital Signature Package",
                              {"approval_request": ar, "status": ["in", _FROZEN]},
                              ["name", "business_doctype", "business_name", "profile",
                               "scts_document_id", "error_code"],
                              order_by="creation desc", as_dict=True, for_update=True)
    if not pkg:
        return False, "no_frozen_package", None
    prof = pkg.profile
    if not prof or int(frappe.db.get_value("EC Digital Signature Profile", prof,
                                           "requester_signature_required") or 0):
        return False, "requester_signs", None
    if check_user and frappe.session.user != perms.business_requested_by(business_doctype,
                                                                         business_name):
        return False, "not_requester", None
    if frappe.db.count("EC Digital Signature Request",
                       {"package": pkg.name, "action": "Sign",
                        "status": ["in", ("Signed", "Approval Completed")]}):
        return False, "refuse:signatures_collected", pkg
    if frappe.db.count("EC Digital Signature Request",
                       {"package": pkg.name, "status": ["in", list(_IN_FLIGHT)]}):
        return False, "refuse:leg_in_flight", pkg
    if pkg.error_code == "create_outcome_unknown":
        return False, "refuse:create_outcome_unknown", pkg
    # Buoc nguoi lap SAU doi tac (WF03 -11) da co = doi tac DA KY (QC PR-G B1).
    if frappe.db.count("EC Digital Signature Request",
                       {"package": pkg.name, "actor_type": "Requester",
                        "transition_id": ["is", "set"]}):
        return False, "refuse:partner_signed", pkg
    decl = signing_files.declared(business_doctype, business_name)
    if decl is not None and decl.get("error"):
        return False, "refuse:signing_files_unavailable", pkg
    if pkg.scts_document_id and check_portal:
        # Doc cong TRUOC khi khoa (nguoi goi dua `portal` = (goi, ma tai lieu, signed, loi)); chi
        # doc lai khi goi / tai lieu da doi trong luc cho khoa.
        if portal and portal[0] == pkg.name and portal[1] == pkg.scts_document_id:
            signed, err = portal[2], portal[3]
        else:
            signed, err = portal_signed_signers(pkg.name)
        if err:
            return False, "refuse:portal_unreadable", pkg        # khong doc duoc -> chan
        if unmatched_signed(pkg.name, signed):
            return False, "refuse:partner_signed", pkg
        from ecentric_workspace.platform.esign import provider_cancel
        if not provider_cancel.auto_armed():
            return False, "refuse:cancel_not_armed", pkg
    return True, None, {"pkg": pkg, "ar": ar, "decl": decl}


_REFUSE_VI = {
    "refuse:signatures_collected": "Tài liệu đã có chữ ký số - không sửa lại được. Đề nghị cấp "
                                   "duyệt bấm Từ chối, rồi tạo phiếu mới từ phiếu này.",
    "refuse:leg_in_flight": "Cổng ký số đang xử lý một bước của phiếu này - chờ vài phút rồi thử "
                            "lại. Nếu vẫn báo vậy, liên hệ bộ phận vận hành.",
    "refuse:create_outcome_unknown": "Chưa rõ tài liệu trên cổng ký số đã được tạo hay chưa - bộ "
                                     "phận vận hành cần đối soát trước khi sửa lại.",
    "refuse:partner_signed": "Đối tác (hoặc một người ký) đã ký trên cổng ký số - không sửa lại "
                             "được tài liệu này. Đề nghị cấp duyệt bấm Từ chối, rồi tạo phiếu "
                             "mới từ phiếu này.",
    "refuse:portal_unreadable": "Chưa đọc được tình trạng ký trên cổng ký số nên chưa biết đối tác "
                                "đã ký hay chưa - thử lại sau ít phút. Nếu vẫn báo vậy, liên hệ "
                                "bộ phận vận hành.",
    "refuse:cancel_not_armed": "Tài liệu cũ trên cổng ký số chưa huỷ tự động được (chức năng tự "
                               "huỷ đang tắt) - liên hệ bộ phận vận hành huỷ tài liệu cũ trước "
                               "khi sửa lại.",
    "refuse:signing_files_unavailable": "Chưa xác định được bản PDF để ký của phiếu (lỗi hệ "
                                        "thống) - liên hệ quản trị trước khi sửa lại.",
}


def reopen_for_edit(business_doctype, business_name):
    """Mo lai thiet lap ky (goi Draft moi tu goi da khoa) khi phieu "Can bo sung" va NGUOI LAP
    KHONG KY (hop dong WF09). Chi nguoi lap. Tai lieu cu tren cong (neu da tao) duoc HUY sau
    (provider_cancel quet goi danh dau `superseded_for_edit`), khong chan viec mo lai.
    Tra {"reopened", "new_package", "old_package", "cancel_pending"} hoac nem loi tieng Viet."""
    from ecentric_workspace.platform.esign import permissions as perms
    # Quyen TRUOC khi khoa / doc trang thai (QC PR-G vong 2 minor 2).
    perms.assert_can_view_business(business_doctype, business_name)
    if frappe.session.user != perms.business_requested_by(business_doctype, business_name):
        frappe.throw(_("Chỉ người lập phiếu được mở lại thiết lập ký."), frappe.PermissionError)
    portal = _portal_before_lock(business_doctype, business_name)
    ar = _lock_rows(business_doctype, business_name)
    ok, why, ctx = _reopen_check(business_doctype, business_name, ar, portal=portal)
    if not ok:
        if why == "not_opted_in":
            frappe.throw(_("Loại phiếu này không hỗ trợ mở lại thiết lập ký."))
        if why == "not_requester":
            frappe.throw(_("Chỉ người lập phiếu được mở lại thiết lập ký."), frappe.PermissionError)
        if why in _REFUSE_VI:
            frappe.throw(_(_REFUSE_VI[why]))
        if why == "no_frozen_package" and frappe.db.get_value(
                "EC Digital Signature Package", {"business_doctype": business_doctype,
                                                 "business_name": business_name,
                                                 "status": "Draft"}, "name"):
            return {"reopened": False, "reason": "already_draft"}
        frappe.throw(_("Phiếu chưa ở trạng thái \"Cần bổ sung\" với gói ký đã khoá - không có gì "
                       "để mở lại."))
    return _do_reopen(business_doctype, business_name, ctx)


def locked_signable_shas(business_doctype, business_name):
    """sha256 cac tep KY cua goi dang khoa khi phieu "Can bo sung", hoac None (khong phai truong
    hop mo lai). Dung cho auto_place: tai lai DUNG ban da khoa thi khong mo lai (QC PR-G M2)."""
    from ecentric_workspace.platform.esign import permissions as perms
    ar = perms.business_approval_request(business_doctype, business_name)
    if not ar or frappe.db.get_value("EC Approval Request", ar,
                                     "approval_status") != "Information Required":
        return None
    pkg = _frozen_package(ar)
    if not pkg:
        return None
    return {f.get("sha256") for f in pkgsvc.package_files(pkg.name)
            if f.get("requires_signature") and f.get("sha256")}


_UNSET = object()


def portal_for_possible_reopen(business_doctype, business_name):
    """Doc cong cho auto_place TRUOC khi khoa hang (QC PR-G vong 3 M1). None khi khong the mo
    lai (khong phai "Can bo sung" / khong co goi khoa co tai lieu / loai phieu khong khai)."""
    try:
        return _portal_before_lock(business_doctype, business_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "esign lifecycle.portal_for_possible_reopen")
        return None


def maybe_reopen_for_edit(business_doctype, business_name, portal=_UNSET):
    """Goi tu tu dat o ky (placement_service.auto_place) SAU KHI tep moi da qua moi phep kiem:
    du dieu kien thi mo lai; khong phai truong hop nay thi im lang (None); du dieu kien nghiep vu
    ma bi chan (da ky / dang chay) thi nem loi tieng Viet de nguoi lap biet vi sao.
    `portal`: ket qua doc cong da lam TRUOC khi nguoi goi khoa hang (auto_place) - khong doc
    lai khi dang giu khoa. Khong truyen -> tu doc (truoc khi khoa)."""
    if portal is _UNSET:
        portal = _portal_before_lock(business_doctype, business_name)
    ar = _lock_rows(business_doctype, business_name)
    ok, why, ctx = _reopen_check(business_doctype, business_name, ar, portal=portal)
    if ok:
        return _do_reopen(business_doctype, business_name, ctx)
    if why in _REFUSE_VI:
        frappe.throw(_(_REFUSE_VI[why]))
    return None


def _portal_before_lock(business_doctype, business_name):
    """Doc nguoi da ky tren cong cua goi dang khoa TRUOC khi khoa hang (khong goi mang khi giu
    khoa). (goi, ma tai lieu, signed, loi) hoac None (khong co goi / khong phai truong hop)."""
    from ecentric_workspace.platform.esign import permissions as perms
    from ecentric_workspace.platform.esign import signing_files
    if not signing_files.hook_path(business_doctype):
        return None
    ar = perms.business_approval_request(business_doctype, business_name)
    # Chi khi phieu dang "Can bo sung" (QC PR-G vong 3 minor 4): khong goi CMC vo ich.
    if not ar or frappe.db.get_value("EC Approval Request", ar, "approval_status") != "Information Required":
        return None
    pkg = _frozen_package(ar) if ar else None
    doc_id = frappe.db.get_value("EC Digital Signature Package", pkg.name,
                                 "scts_document_id") if pkg else None
    if not doc_id:
        return None
    signed, err = portal_signed_signers(pkg.name)
    return (pkg.name, doc_id, signed, err)


def _do_reopen(business_doctype, business_name, ctx):
    from ecentric_workspace.platform.esign import signing_files
    old = ctx["pkg"]
    decl = ctx.get("decl") if "decl" in ctx else signing_files.declared(business_doctype,
                                                                        business_name)
    if decl is not None and decl.get("error"):
        frappe.throw(_(_REFUSE_VI["refuse:signing_files_unavailable"]))
    new = pkgsvc.create_revision(old.name)
    # Tep ky do nghiep vu khai: bo dong + o ky cua tep KHONG con la tep ky (ban PDF cu).
    dropped = []
    if decl is not None:
        for f in pkgsvc.package_files(new.name):
            if f.get("requires_signature") and not signing_files.is_signing_file(
                    business_doctype, business_name, signing_files.dsf_file_url(f), decl,
                    sha=f.get("sha256")):
                dropped.append(f.get("file_name"))
                pkgsvc.remove_file(f.name)
    doc_id = frappe.db.get_value("EC Digital Signature Package", old.name, "scts_document_id")
    if doc_id:
        # provider_cancel.sweep (*/10) huy tai lieu cu - CUNG khoa / danh sach cho phep / xac minh
        # nhu huy phieu bi tu choi. Khong huy dong bo o day: cancel_one rollback giao dich.
        events.emit("PollTick", package=old.name, erp_actor=frappe.session.user,
                    verification_result=SUPERSEDED_FOR_EDIT,
                    request_meta={"new_package": new.name, "document_id": doc_id})
    events.emit("PollTick", package=new.name, erp_actor=frappe.session.user,
                verification_result="reopened_for_edit",
                request_meta={"old_package": old.name, "dropped_files": dropped,
                              "approval_request": ctx["ar"]})
    return {"reopened": True, "new_package": new.name, "old_package": old.name,
            "cancel_pending": bool(doc_id), "dropped_files": dropped}


#: Vet tren goi cu: da thay bang ban sua sau "Can bo sung" -> provider_cancel huy tai lieu cu.
SUPERSEDED_FOR_EDIT = "superseded_for_edit"


def reopen_notice(result):
    """One sentence for the person who pressed the button - never a silent change.

    Tu 31/08 `revised` khong bao gio con True (on_request_reopened tu choi thay vi tao ban
    moi), nen ham nay luon tra chuoi rong. Giu lai co chu dich: neu duong tao ban moi duoc
    mo lai thi cau thong bao da san, khong phai viet lai tu dau. KHONG phai code chet bi bo
    quen - do la thu da lam panel nguoi de nghi bien mat may ngay hoi 28/08.
    """
    if not result.get("revised"):
        return ""
    if result.get("force_restart"):
        return _("Tài liệu ký đã được tạo phiên bản mới. Vì đã có chữ ký số được thu thập "
                 "trên bộ tài liệu cũ, quy trình duyệt bắt đầu lại từ cấp 1 và các cấp phải "
                 "ký lại.")
    return _("Tài liệu ký đã được tạo phiên bản mới. Hãy chuẩn bị và khoá lại gói ký để "
             "chứng từ bổ sung được đưa vào.")


#: Goi ky cua mot ban nhap CHUA GUI: khong co lenh nao sang nha cung cap, khong co chu ky.
_DISCARDABLE = ("Draft",)


def on_draft_discarded(business_doctype, business_name):
    """Phieu CHUA GUI bi huy (= xoa): don goi ky nhap cua no truoc, de xoa duoc phieu.

    05/09, EC-PAYR-2026-00043: chi Hien bam "Huy yeu cau" tren ban nhap -> "Cannot delete or
    cancel because EC Payment Request ... is linked with EC Digital Signature Package
    EC-DSP-2026-00031". Tu khi co "Thiet lap chu ky", moi ban nhap deu co goi ky Draft tro
    vao phieu, nen duong xoa ban nhap (command_service.cancel -> delete_doc) chet.

    Chi don khi MOI goi cua phieu deu la Draft, chua co ma chung tu SCTS va chua co chan ky
    nao. Goi da khoa / da sang nha cung cap thi tu choi - phieu do khong con la "nhap" ve
    mat chung cu, phai di duong huy sau khi gui (engine.cancel). Fail-closed.

    Thu tu: vi tri ky -> dong tep (tep SAO CHEP xoa theo; tep LIEN KET la dinh kem cua phieu,
    Frappe xoa cung phieu) -> su kien -> goi. Tat ca `delete_permanently=False`: vao Deleted
    Document, khoi phuc duoc. Su kien la bang append-only (on_trash nem loi) - o day co y bo
    qua on_trash (`ignore_on_trash`) vi CHU THE cua vet la ban nhap chua tung ton tai voi ai
    ngoai nguoi soan; khong con phieu thi vet "da tai tep X" khong con noi ve cai gi.
    Tra {"discarded": [ten goi]} de nguoi goi ghi vet neu can.
    """
    pkgs = frappe.get_all("EC Digital Signature Package",
                          filters={"business_doctype": business_doctype,
                                   "business_name": business_name},
                          fields=["name", "status", "scts_document_id"])
    for p in pkgs:
        legs = frappe.db.count("EC Digital Signature Request", {"package": p.name})
        if p.status not in _DISCARDABLE or p.scts_document_id or legs:
            frappe.throw(_("Phiếu này đã có gói ký {0} ({1}) - không xoá bản nháp được. "
                           "Hãy huỷ yêu cầu theo luồng phê duyệt.").format(p.name, p.status))
    discarded = []
    for p in pkgs:
        for pl in frappe.get_all("EC Digital Signature Placement", filters={"package": p.name},
                                 pluck="name"):
            frappe.delete_doc("EC Digital Signature Placement", pl, ignore_permissions=True,
                              delete_permanently=False)
        for row in frappe.get_all("EC Digital Signature File", filters={"package": p.name},
                                  fields=["name", "file", "file_is_linked"]):
            frappe.delete_doc("EC Digital Signature File", row.name, ignore_permissions=True,
                              delete_permanently=False)
            if row.file and not int(row.file_is_linked or 0) and frappe.db.exists("File", row.file):
                frappe.delete_doc("File", row.file, ignore_permissions=True,
                                  delete_permanently=False)
        for ev in frappe.get_all("EC Digital Signature Event", filters={"package": p.name},
                                 pluck="name"):
            frappe.delete_doc("EC Digital Signature Event", ev, ignore_permissions=True,
                              ignore_on_trash=True, delete_permanently=False)
        frappe.delete_doc("EC Digital Signature Package", p.name, ignore_permissions=True,
                          delete_permanently=False)
        discarded.append(p.name)
    return {"discarded": discarded}


# --------------------------------------------------------------------------------------------
# Phieu DA DONG (huy / tu choi): ERP tu don phan ky so cua no.
# --------------------------------------------------------------------------------------------
# Danh sach trang thai: xem state.CLOSED_REQUEST / CANCEL_ON_CLOSE / PARK_ON_CLOSE. Moi trang thai
# trong CANCEL_ON_CLOSE deu co canh -> Cancelled trong may trang thai - khong them canh moi nao.
# Chan DANG CHAY khong bi huy: job co the dang gui lenh. Moi lenh moi deu bi chot binding chan
# (`request_not_pending`, thay that tren 00641 ngay 11/11); neu no roi Manual Review thi lan
# quet sau don.
CLOSED_REQUEST = sm.CLOSED_REQUEST
_CANCEL_ON_CLOSE = sm.CANCEL_ON_CLOSE
_PARK_ON_CLOSE = sm.PARK_ON_CLOSE

# GOI KY KHONG bi huy (QC 12/11): moi duong doc cua trang chi tiet (document_setup.
# _current_package, service.get_signing_status, api.document_signature_overlay) bo qua goi
# Cancelled -> phieu da dong mat het phan ky so tren man hinh, ke ca chu ky da co. Huy goi cung
# khong chan them gi: moi lenh moi da bi chot binding (`request_not_pending`) chan.


def on_request_closed(approval_request, reason=None):
    """Phieu `approval_request` da Huy / Tu choi: huy chan ky + goi con treo, dong viec mo.

    11/11/2026, EC-PAYR-2026-00641: Thu tu huy phieu luc 15:02 ngay 10/11. Chan ky nguoi de
    nghi van nam o Manual Review, ToDo "esign: signing request needs manual review" van mo, trang
    van hanh van bao "can xu ly". Bam "Gui lai co kiem" thi bi chan `request_not_pending:
    Cancelled` - dung, nhung la mot viec khong ai can lam nua. Hoan chot 12/11: "ERP tu huy va
    dong luon viec".

    CHI phia ERP. Tai lieu ben cong eContract KHONG bi dong vao (huy ben cong la lenh ghi khong
    dao nguoc duoc len he ngoai - viec rieng, can quyet rieng).

    Trang thai chan ky doc LAI CO KHOA (events.current_status) truoc khi quyet: worker co the
    vua dua chan Retryable Failure sang Provider Accepted, hoac binding vua dua no sang
    Permanent Failure, sau lan get_all (QC 12/11 tai hien ca hai).

    Idempotent, an toan khi chay lai. Khong bao gio cham chan da `Approval Completed` (chu ky
    that). Khong huy goi ky (xem tren). Tra dict dem de nguoi goi ghi vet.
    """
    status = frappe.db.get_value("EC Approval Request", approval_request, "approval_status")
    if status not in CLOSED_REQUEST:
        return {"skipped": "request_not_closed", "status": status}
    why = reason or ("request_closed:%s" % status)
    out = {"cancelled_legs": [], "parked_legs": [], "closed_todos": 0}
    legs = frappe.get_all("EC Digital Signature Request",
                          filters={"approval_request": approval_request,
                                   "status": ["in", _CANCEL_ON_CLOSE + _PARK_ON_CLOSE]},
                          pluck="name")
    for name in legs:
        cur = events.current_status("EC Digital Signature Request", name)
        if cur in _CANCEL_ON_CLOSE:
            events.set_dsr_status(name, "Cancelled", event_type="Cancelled",
                                  request_meta={"reason": why, "was": cur})
            out["cancelled_legs"].append(name)
        elif cur in _PARK_ON_CLOSE:
            out["parked_legs"].append(name)
        else:
            continue          # vua chay sang trang thai khac - de lan quet sau
        out["closed_todos"] += _close_leg_todos(name)
    return out


def _close_leg_todos(dsr_name):
    """Dong ToDo dead-letter cua mot chan ky (tasks._dead_letter_todo tao, moi chan mot cai)."""
    n = 0
    for td in frappe.get_all("ToDo", filters={"reference_type": "EC Digital Signature Request",
                                              "reference_name": dsr_name, "status": "Open"},
                             pluck="name"):
        frappe.db.set_value("ToDo", td, "status", "Cancelled", update_modified=False)
        n += 1
    return n


def closed_requests_needing_cleanup(limit=200):
    """Phieu da dong ma con chan ky treo hoac ToDo mo. Dung cho cron quet (tasks)."""
    legs = frappe.get_all("EC Digital Signature Request",
                          filters={"status": ["in", _CANCEL_ON_CLOSE + _PARK_ON_CLOSE],
                                   "approval_request": ["is", "set"]},
                          fields=["name", "status", "approval_request"], limit_page_length=0)
    ars = sorted({leg.approval_request for leg in legs})
    if not ars:
        return []
    closed = set(frappe.get_all("EC Approval Request",
                                filters={"name": ["in", ars],
                                         "approval_status": ["in", CLOSED_REQUEST]},
                                pluck="name"))
    mine = [leg for leg in legs if leg.approval_request in closed]
    if not mine:
        return []
    todo_open = set(frappe.get_all("ToDo", filters={
        "reference_type": "EC Digital Signature Request",
        "reference_name": ["in", [leg.name for leg in mine]], "status": "Open"},
        pluck="reference_name"))
    need = sorted({leg.approval_request for leg in mine
                   if leg.status in _CANCEL_ON_CLOSE or leg.name in todo_open})
    return need[:limit]

