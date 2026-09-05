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


def _signable_content_verdict(pkg):
    """`unchanged` | `changed` | `unreadable` - BA ket qua, khong phai hai.

    Truoc day ham nay tra bool va gop "khong doc duoc" vao "da doi", voi ly le: lam lai goi
    ky la phien toai, con bo qua mot thay doi that su thi de nguyen chu ky cu tren mot to
    trinh da khac. Ly le do dung KHI "da doi" chi ton mot vong ky lai.

    Tu 31/08 "da doi" nghia la TU CHOI HAN duong gui lai. Luc do gop hai thu vao mot nghia
    la: mot tep khong doc duoc tren dia (bi don, mount loi, sai quyen) se chan vinh vien moi
    lan gui lai cua phieu do - va thong bao con noi sai su that ("tai lieu da thay doi").
    Van fail-closed, nhung noi dung cai minh biet.
    """
    try:
        signable = [f for f in pkgsvc.package_files(pkg.name) if f.get("requires_signature")]
    except Exception:
        return "unreadable"
    locked = {f.get("sha256") for f in signable if f.get("sha256")}
    if not locked or len(locked) != len(signable):
        return "unreadable"             # thieu ma bam -> khong so duoc, va do la mot su co

    present = _attached_signable_shas(pkg)
    if present is None:
        return "unreadable"
    # Con nguyen ven tung tep da ky -> chi la dinh kem THEM, khong dung toi noi dung da ky.
    return "unchanged" if locked.issubset(present) else "changed"


def _attached_signable_shas(pkg):
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
    verdict = _signable_content_verdict(pkg)
    if verdict == "unchanged":
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
    frappe.throw(_("Tài liệu cần ký đã thay đổi so với bộ đã ký. Đường “Gửi lại” không xử lý "
                   "được trường hợp này: chữ ký số ký lên một nội dung cụ thể, và nhà cung "
                   "cấp chỉ nhận danh sách tệp lúc tạo tài liệu.\n\n"
                   "Hãy đề nghị cấp duyệt bấm “Từ chối”, rồi dùng “Tạo phiếu mới từ phiếu "
                   "này” — nội dung và tệp đính kèm sẽ được chép sang phiếu mới."))


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
