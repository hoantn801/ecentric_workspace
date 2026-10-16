# Copyright (c) 2026, eCentric and contributors
"""BAN DOI CHUNG: chup tep hop dong tren SharePoint tai MOI quyet dinh duyet (16/10/2026).

VAN DE (Finance bao). Nguoi duyet sua ban SONG tren Word Online o che do track changes. Nguoi
duyet sau co the Accept/Reject thay doi hoac xoa comment cua nguoi truoc - va cong suc cua nguoi
truoc mat sach. Khong con gi chung minh cap 2 da thay gi, da sua gi luc bam "Duyet".

PHUONG AN A (PO Hoan duyet). Moi khi co quyet dinh - Duyet / Tu choi / Yeu cau bo sung, va moc
"hoan tat duyet" - he thong tu tai tep Office dang soi guong VE NGUYEN TRANG, luu hai ban
RIENG TU gan vao phieu nghiep vu:
  1. dinh dang goc (.docx...) - giu nguyen track changes + comment. DAY la bang chung (sha256).
  2. ban PDF do Graph chuyen (`?format=pdf`) - de doc nhanh tren dien thoai. Co the thieu neu
     Graph khong chuyen duoc; thieu PDF khong lam hong ban chup.
Moi lan chup la mot ban ghi `EC SharePoint Snapshot` bat bien.

NOI VAO DAU. Engine (`transitions.log_action`) goi nguoi nghe quyet dinh khai theo DocType
(`_DECISION_OBSERVERS`, cung khuon `_FULFILLMENT_HANDLERS`); Contract Review dang ky
`service.on_decision`, ham do chi `enqueue(..., enqueue_after_commit=True)` vao `chup_nen` o day.
Engine khong biet SharePoint la gi; module nay khong biet engine chay ra sao.

KHONG BAO GIO lam hong giao dich duyet: chay nen SAU commit, nuot moi loi + `log_error`.
Giao dich duyet rollback thi Frappe huy luon hang doi after-commit - khong co ban chup ma.

IDEMPOTENT. Khoa `<EC Approval Action>|<sp_item_id>` la `unique`: chay lai job, hay hai job
cham nhau, deu khong sinh ban trung. Noi dung trung byte voi ban chup ngay truoc cua cung tep
(vd cap cuoi duyet roi engine ghi "hoan tat") thi DUNG LAI tep cu, khong luu them.

KHONG DAY NGUOC LEN SHAREPOINT. Ban doi chung gan vao phieu nghiep vu, nen moi cho duyet dinh
kem phai loai chung ra bang `sharepoint_mirror.tep_doi_chung` (dau moc tuong minh theo ten ban
ghi File, khong theo tien to ten tep).
"""
import hashlib

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from ecentric_workspace.weekly_report import sharepoint as wr_sp
from ecentric_workspace.approval_center.shared.integrations import sharepoint_mirror as mirror

SNAP_DT = mirror.SNAP_DT
LINK_DT = mirror.LINK_DT
ACTION_DT = "EC Approval Action"

#: Gia tri `EC Approval Action.action` duoc tinh la QUYET DINH. "Approved" gom ca dong cua
#: tung cap lan dong "All levels approved" (level_no rong) ma `complete_approval` ghi.
QUYET_DINH = ("Approved", "Rejected", "Information Requested")

#: Chi tep Office moi sua duoc tren Office Online - PDF/anh tren SharePoint khong ai sua duoc
#: nen chup lai la thua.
DUOI_OFFICE = (".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt")

TIEN_TO = "[Đối chứng] "
#: `File.file_name` la Data(140).
TEN_TOI_DA = 140
#: Hop dong thuc te vai MB. Tep lon hon nguong nay thi bo qua + log, khong de mot tep 200MB
#: lam nghen worker `long` va day o dia.
TOI_DA_BYTE = 40 * 1024 * 1024
TIMEOUT = 60
#: Ky tu SharePoint/URL khong chiu (cung tap voi `weekly_report.sharepoint.ILLEGAL_NAME_CHARS`).
KY_TU_CAM = '"*:<>?/\\|#%\r\n\t'
NGUOI_HE_THONG = ("Administrator", "Guest")
#: Lech vai giay quanh moc quyet dinh la do lam tron cua SharePoint, khong phai nguoi sua.
DUNG_SAI_GIAY = 5


# --------------------------------------------------------------------------- #
# Ham THUAN - dat ten, nhan hien thi. Khong doc CSDL, test duoc khong can Frappe.
# --------------------------------------------------------------------------- #
def la_tep_office(file_name):
    return str(file_name or "").lower().endswith(DUOI_OFFICE)


def nhan_hanh_dong(action, level_no):
    """Nhan doc duoc cho mot quyet dinh: "sau duyệt cấp 2", "khi trả lại cấp 1"..."""
    cap = (" cấp %s" % level_no) if level_no else ""
    if action == "Approved":
        return ("sau duyệt" + cap) if level_no else "hoàn tất duyệt"
    if action == "Rejected":
        return "khi từ chối" + cap
    if action == "Information Requested":
        return "khi trả lại" + cap
    return str(action or "")


def ten_ngan(actor, full_name=None):
    """Hai chu cuoi cua ho ten ("Nguyen Thu Trinh" -> "Thu Trinh"). Tai khoan he thong ->
    "Hệ thống" (dong "hoan tat duyet" do engine ghi bang Administrator)."""
    if not actor or actor in NGUOI_HE_THONG:
        return "Hệ thống"
    ten = " ".join(str(full_name or "").split())
    if not ten:
        return str(actor).split("@")[0]
    chu = ten.split(" ")
    return " ".join(chu[-2:])


def lam_sach(text):
    out = "".join(" " if c in KY_TU_CAM else c for c in str(text or ""))
    return " ".join(out.split()).strip(" .")


def ten_tep(ten_goc, nhan, nguoi, moc, duoi):
    """`[Đối chứng] <tên gốc> – <nhãn> – <người> – <dd-mm-yyyy HHhMM><đuôi>`, toi da 140 ky tu.

    Gio dung `HHhMM` chu khong `HH:MM`: dau hai cham hong duong dan Graph va bi Windows cam.
    Cat bot TEN GOC khi qua dai - phan nhan/nguoi/gio moi la thu phan biet cac ban chup."""
    goc = str(ten_goc or "tep")
    if "." in goc:
        goc = goc.rsplit(".", 1)[0]
    goc = lam_sach(goc) or "tep"
    hau = " – %s – %s – %s" % (lam_sach(nhan), lam_sach(nguoi)[:40],
                                get_datetime(moc).strftime("%d-%m-%Y %Hh%M"))
    duoi = str(duoi or "").lower()
    con = TEN_TOI_DA - len(TIEN_TO) - len(hau) - len(duoi)
    if len(goc) > con:
        goc = goc[:max(con, 8)].rstrip(" .-–")
    return (TIEN_TO + goc + hau)[:TEN_TOI_DA - len(duoi)] + duoi


def duoi_cua(file_name):
    t = str(file_name or "")
    return ("." + t.rsplit(".", 1)[1].lower()) if "." in t else ""


# --------------------------------------------------------------------------- #
# Graph - chi DOC. Moi loi goi deu co timeout.
# --------------------------------------------------------------------------- #
def _requests():
    import requests
    return requests


def _item_url(item_id):
    return "%s/sites/%s/drive/items/%s" % (wr_sp.GRAPH, wr_sp.SITE_ID, item_id)


def _auth(token):
    return {"Authorization": "Bearer " + token}


def doc_metadata(item_id, token):
    """eTag + moc sua + nguoi sua + dung luong cua tep, NGAY LUC NAY."""
    resp = _requests().get(
        _item_url(item_id) + "?$select=id,name,eTag,cTag,size,lastModifiedDateTime,lastModifiedBy",
        headers=_auth(token), timeout=TIMEOUT)
    if resp.status_code != 200:
        raise mirror.SharePointChuaSan("Doc metadata that bai (%s): %s"
                                       % (resp.status_code, (resp.text or "")[:300]))
    j = resp.json() or {}
    ai = ((j.get("lastModifiedBy") or {}).get("user") or {})
    return {"etag": j.get("eTag") or j.get("cTag"),
            "size": j.get("size"),
            "last_modified": mirror.gio_he_thong(j.get("lastModifiedDateTime")),
            "last_modified_by": ai.get("email") or ai.get("displayName")}


def doc_phien_ban(item_id, token):
    """Ma phien ban hien tai ("4.0"...) hoac None. Thu tu tra ve cua /versions khong duoc
    Graph cam ket, nen lay ban co moc sua lon nhat. Hong thi None - khong dang de mat ban chup."""
    try:
        resp = _requests().get(_item_url(item_id) + "/versions",
                               headers=_auth(token), timeout=TIMEOUT)
        if resp.status_code != 200:
            return None
        ds = (resp.json() or {}).get("value") or []
        if not ds:
            return None
        return max(ds, key=lambda v: str(v.get("lastModifiedDateTime") or "")).get("id")
    except Exception:
        return None


def tai_ve(item_id, token, pdf=False):
    """Bytes cua tep. `pdf=True` -> Graph chuyen sang PDF (`?format=pdf`). Graph tra 302 sang
    URL tai da ky san; `requests` tu theo va tu bo header Authorization khi doi host."""
    url = _item_url(item_id) + "/content" + ("?format=pdf" if pdf else "")
    resp = _requests().get(url, headers=_auth(token), timeout=TIMEOUT, allow_redirects=True)
    if resp.status_code != 200:
        raise mirror.SharePointChuaSan("Tai %s that bai (%s): %s" % (
            "PDF" if pdf else "tep", resp.status_code, (resp.text or "")[:300]))
    noi_dung = resp.content or b""
    if not noi_dung:
        raise mirror.SharePointChuaSan("Graph tra ve tep rong")
    if len(noi_dung) > TOI_DA_BYTE:
        raise mirror.SharePointChuaSan("Tep qua lon (%d byte)" % len(noi_dung))
    return noi_dung


# --------------------------------------------------------------------------- #
# Chup
# --------------------------------------------------------------------------- #
def tep_can_chup(business_doctype, business_name):
    """Tep Office DANG soi guong cua phieu: co ban ghi lien ket (sp_item_id) VA tep van con
    dinh tren phieu. Tep da bi go khoi phieu (thay tep luc gui lai) thi ban tren SharePoint la
    ban mo coi - chup no la chup nham. Ban doi chung bi loai san qua `_dinh_kem`."""
    con = {t.get("file_url"): t.get("file_name")
           for t in mirror._dinh_kem(business_doctype, business_name)}
    ra = []
    for r in frappe.get_all(LINK_DT,
                            filters={"business_doctype": business_doctype,
                                     "business_name": business_name,
                                     "sp_item_id": ["is", "set"]},
                            fields=["name", "file_url", "sp_item_id"],
                            order_by="creation asc", limit_page_length=0) or []:
        ten = con.get(r.get("file_url"))
        if ten and la_tep_office(ten):
            ra.append(frappe._dict(link=r.get("name"), file_url=r.get("file_url"),
                                   file_name=ten, sp_item_id=r.get("sp_item_id")))
    return ra


def _luu_tep(business_doctype, business_name, file_name, noi_dung):
    return frappe.get_doc({
        "doctype": "File", "file_name": file_name, "is_private": 1,
        "attached_to_doctype": business_doctype, "attached_to_name": business_name,
        "content": noi_dung,
    }).insert(ignore_permissions=True)


def _tai_on_dinh(item_id, token):
    """Tai tep va doc eTag TRUOC + SAU. Lech nghia la ai do vua luu len trong luc tai -> thu
    lai mot lan. Van lech thi giu ban tai lan cuoi va ghi `sp_on_dinh = 0` cho trung thuc."""
    meta, noi_dung = None, None
    for _lan in range(2):
        meta = doc_metadata(item_id, token)
        if (meta.get("size") or 0) > TOI_DA_BYTE:
            raise mirror.SharePointChuaSan("Tep qua lon (%s byte)" % meta.get("size"))
        noi_dung = tai_ve(item_id, token)
        sau = doc_metadata(item_id, token)
        if (sau.get("etag") or "") == (meta.get("etag") or ""):
            return meta, noi_dung, True
    return meta, noi_dung, False


def chup_mot(act, ref, nguon, token, full_name=None):
    """Chup MOT tep cho MOT quyet dinh. Tra ve ten ban ghi, hoac None neu da chup roi."""
    khoa = "%s|%s" % (act.name, nguon.sp_item_id)
    if frappe.db.exists(SNAP_DT, {"khoa": khoa}):
        return None
    meta, noi_dung, on_dinh = _tai_on_dinh(nguon.sp_item_id, token)
    sha = hashlib.sha256(noi_dung).hexdigest()
    moc = get_datetime(act.action_time) if act.action_time else now_datetime()
    nhan = nhan_hanh_dong(act.action, act.level_no)
    nguoi = ten_ngan(act.actor, full_name)

    doc = frappe.new_doc(SNAP_DT)
    doc.update({
        "khoa": khoa, "business_doctype": ref.reference_doctype,
        "business_name": ref.reference_name, "approval_request": act.approval_request,
        "approval_action": act.name, "level_no": act.level_no or 0, "actor": act.actor,
        "action": act.action, "action_label": nhan, "action_time": moc,
        "captured_at": now_datetime(), "source_file_url": nguon.file_url,
        "source_file_name": nguon.file_name, "sp_link": nguon.link,
        "sp_item_id": nguon.sp_item_id, "sp_etag": meta.get("etag"),
        "sp_last_modified": meta.get("last_modified"),
        "sp_last_modified_by": meta.get("last_modified_by"),
        "sp_on_dinh": 1 if on_dinh else 0, "sha256": sha, "size_bytes": len(noi_dung),
    })
    cu = frappe.get_all(SNAP_DT,
                        filters={"business_doctype": ref.reference_doctype,
                                 "business_name": ref.reference_name,
                                 "sp_item_id": nguon.sp_item_id, "sha256": sha},
                        fields=["name", "docx_file", "docx_file_url", "pdf_file", "pdf_file_url"],
                        order_by="creation desc", limit_page_length=1) or []
    cu = cu[0] if cu and cu[0].get("docx_file") else None
    if cu:
        doc.reused_from = cu.get("name")
        doc.docx_file, doc.docx_file_url = cu.get("docx_file"), cu.get("docx_file_url")
    else:
        f = _luu_tep(ref.reference_doctype, ref.reference_name,
                     ten_tep(nguon.file_name, nhan, nguoi, moc, duoi_cua(nguon.file_name)),
                     noi_dung)
        doc.docx_file, doc.docx_file_url = f.name, f.file_url
    if cu and cu.get("pdf_file"):
        doc.pdf_file, doc.pdf_file_url = cu.get("pdf_file"), cu.get("pdf_file_url")
    else:
        # PDF chi de doc nhanh. Graph khong chuyen duoc (dinh dang la, tep hong...) thi ghi
        # loi lai va VAN luu ban chup - ban goc moi la bang chung.
        try:
            pdf = tai_ve(nguon.sp_item_id, token, pdf=True)
            fp = _luu_tep(ref.reference_doctype, ref.reference_name,
                          ten_tep(nguon.file_name, nhan, nguoi, moc, ".pdf"), pdf)
            doc.pdf_file, doc.pdf_file_url = fp.name, fp.file_url
        except Exception as e:
            doc.pdf_error = str(e)[:500]
    doc.sp_version_id = doc_phien_ban(nguon.sp_item_id, token)
    doc.insert(ignore_permissions=True)
    return doc.name


def chup_quyet_dinh(approval_action):
    """Chup moi tep Office dang soi guong cua phieu cho MOT dong quyet dinh. Tong ket dict.

    Commit sau MOI tep, rollback khi tep do hong: tep A hong khong duoc keo mat ban chup cua
    tep B, va mot ban ghi File da tao ma chua kip co ban ghi doi chung (tuc chua co dau moc)
    phai bien mat theo rollback - neu khong, no se bi coi la tep nguoi dung va bi day len
    SharePoint o lan soi guong sau."""
    act = frappe.db.get_value(ACTION_DT, approval_action,
                              ["name", "approval_request", "level_no", "actor", "action",
                               "action_time"], as_dict=True)
    if not act or act.action not in QUYET_DINH:
        return {"bo_qua": "khong phai quyet dinh"}
    ref = frappe.db.get_value("EC Approval Request", act.approval_request,
                              ["reference_doctype", "reference_name"], as_dict=True)
    if not ref or not mirror.duoc_soi_guong(ref.reference_doctype):
        return {"bo_qua": "loai phieu khong soi guong"}
    nguon = tep_can_chup(ref.reference_doctype, ref.reference_name)
    if not nguon:
        return {"so_tep": 0, "xong": [], "da_co": [], "hong": []}
    token = wr_sp.get_app_token()
    full = frappe.db.get_value("User", act.actor, "full_name") if act.actor else None
    xong, da_co, hong = [], [], []
    for n in nguon:
        try:
            ten = chup_mot(act, ref, n, token, full)
            frappe.db.commit()
            (xong if ten else da_co).append(n.file_name)
        except Exception as e:
            frappe.db.rollback()
            if isinstance(e, getattr(frappe, "DuplicateEntryError", ())):
                # Job khac vua chup xong dung tep nay cho dung quyet dinh nay (khoa unique).
                da_co.append(n.file_name)
                continue
            frappe.log_error(frappe.get_traceback(),
                             "Ban doi chung %s / %s" % (ref.reference_name, n.file_name))
            hong.append(n.file_name)
    return {"so_tep": len(nguon), "xong": xong, "da_co": da_co, "hong": hong}


def chup_nen(approval_action):
    """Diem vao cho `frappe.enqueue`. Nuot MOI loi: Microsoft co su co thi lan duyet VAN da
    thanh cong; hong thi ghi log, chay lai `chup_quyet_dinh(<action>)` la bu duoc (idempotent)."""
    try:
        return chup_quyet_dinh(approval_action)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Ban doi chung nen %s" % approval_action)
        return None


# --------------------------------------------------------------------------- #
# Doc cho man hinh + chot chan xoa
# --------------------------------------------------------------------------- #
def ds_ban_doi_chung(business_doctype, business_name):
    """Danh sach ban doi chung cua phieu, MOI NHAT TRUOC. CHI goi SAU khi da qua cong quyen
    xem phieu (`query_service.detail`) - ham nay khong tu kiem quyen."""
    rows = frappe.get_all(
        SNAP_DT,
        filters={"business_doctype": business_doctype, "business_name": business_name},
        fields=["name", "level_no", "actor", "action", "action_label", "action_time",
                "captured_at", "source_file_name", "docx_file_url", "pdf_file_url",
                "pdf_error", "sp_last_modified", "sp_last_modified_by", "sp_on_dinh",
                "sha256"],
        order_by="action_time desc, creation desc", limit_page_length=0) or []
    ai = sorted({r.get("actor") for r in rows if r.get("actor")})
    ten = {}
    if ai:
        ten = {u.get("name"): u.get("full_name") for u in frappe.get_all(
            "User", filters={"name": ["in", ai]}, fields=["name", "full_name"])}
    ra = []
    for r in rows:
        sua_sau = False
        if r.get("sp_last_modified") and r.get("action_time"):
            sua_sau = (get_datetime(r["sp_last_modified"]) - get_datetime(r["action_time"])
                       ).total_seconds() > DUNG_SAI_GIAY
        ra.append({
            "level_no": r.get("level_no") or 0,
            "actor": r.get("actor"),
            "actor_name": ("Hệ thống" if r.get("actor") in NGUOI_HE_THONG
                           else (ten.get(r.get("actor")) or r.get("actor"))),
            "action": r.get("action"), "action_label": r.get("action_label"),
            "action_time": r.get("action_time"), "captured_at": r.get("captured_at"),
            "source_file_name": r.get("source_file_name"),
            "docx_file_url": r.get("docx_file_url"), "pdf_file_url": r.get("pdf_file_url"),
            "pdf_loi": bool(r.get("pdf_error")),
            "sp_last_modified": r.get("sp_last_modified"),
            "sp_last_modified_by": r.get("sp_last_modified_by"),
            "sp_on_dinh": bool(r.get("sp_on_dinh")),
            # Tep doi GIUA luc bam nut va luc chup (job nen tre): noi ro, khong gia vo.
            "sua_sau_quyet_dinh": sua_sau,
            "sha256": (r.get("sha256") or "")[:12],
        })
    return ra


def tach_ban_doi_chung(business_doctype, business_name, rows):
    """(dinh kem cua nguoi dung, ban doi chung). Loai theo TEN ban ghi File - goi TRUOC khi
    gop trung theo `file_url` (xem `sharepoint_mirror.tep_doi_chung`)."""
    if not mirror.duoc_soi_guong(business_doctype):
        return rows, []
    loai = mirror.tep_doi_chung(business_doctype, business_name)
    if loai:
        rows = [r for r in (rows or []) if r.get("name") not in loai]
    return rows, ds_ban_doi_chung(business_doctype, business_name)


def chan_xoa_tep_doi_chung(doc, method=None):
    """hooks.doc_events File.on_trash. Tep la ban doi chung -> tu choi, ke ca System Manager.

    Vi sao chan ca nguoi gui phieu: tep gan vao phieu cua ho, ma Frappe cho chu phieu go dinh
    kem. Ban chup ghi lai comment cua nguoi duyet tren hop dong CUA nguoi gui - de ho xoa duoc
    thi chinh la lo hong ma tinh nang nay sinh ra de bit. Muon xoa that (don du lieu test):
    System Manager xoa ban ghi `EC SharePoint Snapshot` TRUOC (de lai vet trong Deleted
    Document), luc do tep het la ban doi chung va xoa duoc nhu thuong."""
    if getattr(frappe.flags, "ec_allow_snapshot_file_delete", False):
        frappe.log_error("%s (%s) xoa voi co ec_allow_snapshot_file_delete boi %s"
                         % (doc.name, doc.get("file_name"), frappe.session.user),
                         "ban doi chung: xoa tep OVERRIDE")
        return
    if not getattr(doc, "name", None):
        return
    if frappe.db.exists(SNAP_DT, {"docx_file": doc.name}) \
            or frappe.db.exists(SNAP_DT, {"pdf_file": doc.name}):
        frappe.throw(_("Không được xoá bản đối chứng ({0}) — đây là bản chụp bất biến của hợp "
                       "đồng tại một quyết định duyệt.").format(doc.get("file_name") or doc.name),
                     frappe.PermissionError)
