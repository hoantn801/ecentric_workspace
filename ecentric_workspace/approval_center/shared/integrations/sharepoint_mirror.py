# Copyright (c) 2026, eCentric and contributors
"""Soi guong tep dinh kem cua phieu duyet len SharePoint de review ONLINE (14/09, Hoan).

VI SAO CAN. Tep nam trong Frappe (`/private/files/...`) thi trinh duyet luon TAI .docx ve chu
khong mo - do la rang buoc cua Office (Word Online chi mo duoc tep nam tren SharePoint /
OneDrive), khong phai thieu cau hinh o dau. Muon "bam Mo la mo online" thi tep phai THUC SU
nam tren SharePoint.

VI SAO O `shared/` CHU KHONG PHAI TRONG FEATURE. Hai ly do:
  1. Phan hien thi (link + bang canh bao) nam o `shared/requests/query_service.py` - noi dung
     danh sach dinh kem cho CA 28 form. De phan tai len trong mot feature thi mot nua tinh
     nang nam trong nha, mot nua nam ngoai san.
  2. `test_feature_architecture` cam `application/` va `controllers/` cua feature nhac toi
     `infrastructure/` - ke ca trong chuoi. Ma cho tu nhien de goi dong bo lai chinh la
     `application/service.py` luc gui phieu. Dat o `shared/` thi het vuong, va vuong o day la
     kien truc dang noi dung chu khong phai kien truc phien nhieu.

KHONG CO BUOC CAP QUYEN - va do la QUYET DINH, khong phai thieu sot. 14/09 do tren tenant
that: nhom "Operation Members" DA co quyen `write` san tren thu vien cua site `operation`. Cap
quyen cho tung nguoi trong luong duyet khong he thu hep pham vi - no chi them mot lop ACL thu
hai len tren mot lop da mo san, roi bao cao "da cap quyen cho 9 nguoi" nhu the vua bao ve duoc
gi do. Hoan chot: quan quyen o MOT cho (thanh vien site SharePoint). Neu ai do trong luong
duyet mo khong duoc tep, cach sua la them ho vao site. Lich su ham `cap_quyen` cu (gom ca ly do
`/invite` khong dung duoc voi token app-only) nam o git log commit ee6243b.

Token: dung LAI `weekly_report.sharepoint.get_app_token` - app-only client_credentials, doc
client_secret tu Social Login Key, khong hardcode. Khong dung MSAL phia trinh duyet.
"""
import frappe
from frappe.utils import now_datetime

from ecentric_workspace.weekly_report import sharepoint as wr_sp

#: DANH SACH CHO PHEP - chi nhung loai phieu o day moi duoc dua dinh kem len SharePoint.
#:
#: Phai la danh sach CHO PHEP chu khong phai danh sach CAM: dinh kem cua phieu nghi viec, phieu
#: luong, phieu ky luat... khong duoc tu dong chay ra mot thu vien ma ca phong Operation doc
#: duoc. Them mot loai phieu vao day la mot quyet dinh ve quyen rieng tu, khong phai mot dong
#: cau hinh.
THU_MUC_THEO_PHIEU = {
    "EC Contract Review Request": "Contract Review",
}

LINK_DT = "EC SharePoint File Link"
TIMEOUT = 30


class SharePointChuaSan(Exception):
    """Graph chua dung duoc (chua cau hinh / mat mang). Goi ben ngoai TU quyet dinh xu ly."""


def duoc_soi_guong(business_doctype):
    return business_doctype in THU_MUC_THEO_PHIEU


def _requests():
    import requests
    return requests


def _graph():
    return wr_sp.GRAPH


def _drive_url(rel_path):
    """URL cua mot duong dan trong thu vien mac dinh cua site."""
    from urllib.parse import quote
    return "%s/sites/%s/drive/root:/%s" % (_graph(), wr_sp.SITE_ID, quote(rel_path))


def duong_dan(business_doctype, business_name, file_name):
    """<thu muc cua loai phieu>/<ma phieu>/<ten tep da lam sach>.

    Moi phieu mot thu muc: doi chieu bang mat tren SharePoint khong phai do ma tep, va hai
    phieu dinh kem trung ten khong de len nhau."""
    goc = THU_MUC_THEO_PHIEU.get(business_doctype)
    if not goc:
        raise SharePointChuaSan("Loai phieu %s khong nam trong danh sach cho phep" % business_doctype)
    return "%s/%s/%s" % (goc, business_name, wr_sp.safe_filename(file_name))


def _noi_dung_tep(file_url):
    """Doc bytes cua tep tu kho Frappe. Khong doc bang duong dan tu chuoi nguoi dung dua
    vao - lay qua ban ghi File de khong the tro ra ngoai thu muc kho."""
    name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not name:
        raise SharePointChuaSan("Khong tim thay ban ghi File cho %s" % file_url)
    return frappe.get_doc("File", name).get_content()


def tai_len(business_doctype, file_url, file_name, business_name, token=None):
    """Dua MOT tep len SharePoint. Tra ve dict(item_id, web_url, last_modified).

    Dung upload session cho moi kich co - don gian hon la re nhanh theo dung luong, va
    hop dong .docx co the vuot nguong 4MB cua PUT truc tiep."""
    requests = _requests()
    token = token or wr_sp.get_app_token()
    rel = duong_dan(business_doctype, business_name, file_name)
    noi_dung = _noi_dung_tep(file_url)

    phien = wr_sp.create_deck_upload_session(rel, token)
    tong = len(noi_dung)
    resp = requests.put(
        phien,
        headers={"Content-Length": str(tong),
                 "Content-Range": "bytes 0-%d/%d" % (max(tong - 1, 0), tong)},
        data=noi_dung, timeout=TIMEOUT)
    if resp.status_code not in (200, 201):
        raise SharePointChuaSan("Tai len that bai (%s): %s" % (resp.status_code, resp.text[:300]))
    item = resp.json() or {}
    return {"item_id": item.get("id"),
            "web_url": item.get("webUrl"),
            "last_modified": item.get("lastModifiedDateTime")}


# --------------------------------------------------------------------------- #
# KHONG co buoc cap quyen o day - va do la mot QUYET DINH, khong phai thieu sot.
#
# 14/09 do tren tenant that: tep nam trong thu vien cua site `operation`, ma nhom
# "Operation Members" DA co quyen `write` san. Nghia la buoc cap quyen cho tung nguoi trong
# luong duyet khong he thu hep pham vi - no chi them mot lop ACL thu hai len tren mot lop da
# mo san, roi bao cao "da cap quyen cho 9 nguoi" nhu the vua bao ve duoc cai gi do.
#
# Hoan chot: quan quyen o MOT cho (thanh vien site SharePoint), khong dung he thu hai song
# song. Neu ai do trong luong duyet mo khong duoc tep, cach sua la them ho vao site - khong
# phai them mot vong cap quyen theo tung tep.
#
# Dung khoi phuc `cap_quyen` neu khong co quyet dinh moi. Lich su cai ham do (gom ca ly do
# `/invite` khong dung duoc voi token app-only) nam o git log commit ee6243b.
# --------------------------------------------------------------------------- #


def doc_quyen(item_id, token=None):
    """Liet ke quyen HIEN CO tren mot tep. Chi doc.

    Dung de tra loi mot cau hoi quyet dinh ca thiet ke: nguoi trong cong ty da co quyen vao
    thu vien nay san chua? Neu roi thi buoc cap quyen la thua; neu chua thi phai cap that.
    Doan bang cam tinh thi khong biet duoc."""
    requests = _requests()
    token = token or wr_sp.get_app_token()
    resp = requests.get(
        "%s/sites/%s/drive/items/%s/permissions" % (_graph(), wr_sp.SITE_ID, item_id),
        headers={"Authorization": "Bearer " + token}, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise SharePointChuaSan("Doc quyen that bai (%s): %s" % (resp.status_code, resp.text[:300]))
    ra = []
    for p in (resp.json() or {}).get("value", []):
        ai = []
        for gi in (p.get("grantedToIdentitiesV2") or ([p["grantedToV2"]] if p.get("grantedToV2") else [])):
            u = (gi or {}).get("user") or (gi or {}).get("siteGroup") or (gi or {}).get("group") or {}
            ai.append(u.get("email") or u.get("displayName") or "?")
        ra.append({"vai_tro": ",".join(p.get("roles") or []),
                   "thua_ke": bool(p.get("inheritedFrom")),
                   "cho": ", ".join(ai) or (p.get("link") or {}).get("scope") or "?"})
    return ra


def doc_moc_sua(item_id, token=None):
    """Moc sua gan nhat cua tep tren SharePoint, DA doi ve gio he thong, hoac None.

    Tra ve datetime chu khong phai chuoi ISO: ben goi se dem no di so voi moc duyet trong ERP,
    ma moc duyet la gio he thong. Tra ve chuoi UTC o day thi moi cho goi deu phai nho tu doi -
    va cho nao quen thi lech bay tieng mot cach im lang."""
    requests = _requests()
    token = token or wr_sp.get_app_token()
    resp = requests.get(
        "%s/sites/%s/drive/items/%s?$select=id,webUrl,lastModifiedDateTime" % (
            _graph(), wr_sp.SITE_ID, item_id),
        headers={"Authorization": "Bearer " + token}, timeout=TIMEOUT)
    if resp.status_code != 200:
        return None
    return gio_he_thong((resp.json() or {}).get("lastModifiedDateTime"))


def gio_he_thong(iso):
    """Doi moc thoi gian ISO-8601 UTC cua Graph ("2026-09-14T08:58:18Z") sang gio he thong.

    HAI ly do, ly do thu hai moi la ly do that:
      1. MariaDB khong nhan chu "T" va "Z" trong cot Datetime - do that 14/09 nem
         (1292, "Incorrect datetime value: '2026-09-14T08:58:18Z'").
      2. Quan trong hon: Graph tra ve gio UTC, con moc duyet trong ERP la gio he thong
         (UTC+7). Luu nguyen chuoi UTC thi moi phep so "tep co bi sua sau khi duyet khong"
         deu lech BAY TIENG theo huong co loi cho ke sua - mot ban hop dong bi sua ngay sau
         khi duyet xong van trong nhu duoc sua tu truoc. Do dung la thu ma bang canh bao
         sinh ra de bat, nen sai o day thi tinh nang coi nhu khong ton tai.

    Tra ve datetime KHONG mang tzinfo (Frappe luu gio tran theo mui he thong).
    """
    if not iso:
        return None
    from frappe.utils import convert_utc_to_system_timezone, get_datetime
    txt = str(iso).strip()
    for bo in ("Z", "+00:00"):
        if txt.endswith(bo):
            txt = txt[: -len(bo)]
            break
    txt = txt.replace("T", " ")
    if "." in txt:
        txt = txt.split(".", 1)[0]
    return convert_utc_to_system_timezone(get_datetime(txt)).replace(tzinfo=None)


def ghi_lien_ket(business_doctype, file_url, business_name, ket_qua):
    """Luu/cap nhat ban ghi noi tep Frappe voi tep SharePoint. Idempotent theo file_url."""
    ten = frappe.db.get_value(LINK_DT, {"file_url": file_url}, "name")
    doc = frappe.get_doc(LINK_DT, ten) if ten else frappe.new_doc(LINK_DT)
    doc.file_url = file_url
    doc.business_doctype = business_doctype
    doc.business_name = business_name
    doc.sp_item_id = ket_qua.get("item_id")
    doc.sp_web_url = ket_qua.get("web_url")
    doc.sp_last_modified = gio_he_thong(ket_qua.get("last_modified"))
    doc.sp_synced_at = now_datetime()
    doc.save(ignore_permissions=True)
    return doc.name


def _dinh_kem(business_doctype, business_name):
    """Dinh kem cua mot phieu. Tep Office truoc: do la thu nguoi ta can mo bang Word Online."""
    tep = frappe.get_all(
        "File",
        filters={"attached_to_doctype": business_doctype, "attached_to_name": business_name},
        fields=["file_name", "file_url"], order_by="creation asc")
    duoi = (".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt")
    office = [t for t in tep if (t.file_name or "").lower().endswith(duoi)]
    khac = [t for t in tep if t not in office]
    return office + khac


def dong_bo_phieu(business_doctype, business_name):
    """Dua MOI dinh kem cua mot phieu len SharePoint va ghi lien ket. Tra ve dict tong ket.

    Idempotent: chay lai thi ghi de tep tren SharePoint va cap nhat ban ghi lien ket theo
    `file_url`, khong sinh ban trung. Goi lai sau khi nguoi dung them tep la an toan.

    KHONG nem ra ngoai vi MOT tep hong: mot tep loi khong duoc keo theo ca phieu khong len duoc
    tep nao. Tra ve danh sach `hong` de ben goi ghi log.
    """
    if not duoc_soi_guong(business_doctype):
        return {"bo_qua": "loai phieu khong nam trong danh sach cho phep",
                "xong": [], "hong": [], "so_tep": 0}
    tep = _dinh_kem(business_doctype, business_name)
    if not tep:
        return {"xong": [], "hong": [], "so_tep": 0}
    token = wr_sp.get_app_token()
    xong, hong = [], []
    for t in tep:
        try:
            kq = tai_len(business_doctype, t.file_url, t.file_name, business_name, token=token)
            ghi_lien_ket(business_doctype, t.file_url, business_name, kq)
            xong.append(t.file_name)
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             "SharePoint soi guong %s / %s" % (business_name, t.file_name))
            hong.append(t.file_name)
    return {"xong": xong, "hong": hong, "so_tep": len(tep)}


def dong_bo_nen(business_doctype, business_name):
    """Diem vao cho `frappe.enqueue`. Phai la ham CAP MODULE thi enqueue moi tro toi duoc.

    Bat HET loi: day la viec chay nen sau khi nguoi dung da gui phieu xong. Hong thi ghi log de
    sua, tuyet doi khong nem nguoc ra - mot su co mang cua Microsoft khong duoc phep lam hong
    mot lan gui phieu da thanh cong.
    """
    try:
        return dong_bo_phieu(business_doctype, business_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "SharePoint soi guong nen %s" % business_name)
        return None
