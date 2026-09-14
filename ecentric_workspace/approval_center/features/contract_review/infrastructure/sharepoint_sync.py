# Copyright (c) 2026, eCentric and contributors
"""Dua tep dinh kem cua Contract Review len SharePoint de moi nguoi review ONLINE (14/09, Hoan).

VI SAO. Tep dang nam trong Frappe (`/private/files/...`). Trinh duyet luon TAI .docx ve chu
khong mo - do la rang buoc cua Office (Word Online chi mo duoc tep nam tren SharePoint /
OneDrive), khong phai thieu cau hinh o dau. Muon "bam Mo la mo online" thi tep phai THUC SU
nam tren SharePoint.

QUYEN: Hoan chot cap cho DUNG nhung nguoi trong luong duyet (nguoi gui + cac cap duyet + CC),
KHONG dung link pham vi toan cong ty nhu Weekly Report. Hop dong co gia tri va dieu khoan
thanh toan; noi quyen xem ra ca cong ty la mot quyet dinh khac han, khong phai he qua phu cua
viec "cho mo online".

QUYEN SUA: Hoan chot cho SUA/comment truc tiep. Keo theo mot hau qua phai xu ly o cho khac:
ban tren SharePoint thanh ban song, ban dinh kem trong ERP thanh ban chup. Xem
`application/sharepoint_state.py` - cho do lo viec phat hien tep doi sau khi da co cap duyet.

Token: dung LAI `weekly_report.sharepoint.get_app_token` - app-only client_credentials, doc
client_secret tu Social Login Key, khong hardcode. Khong dung MSAL phia trinh duyet.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.weekly_report import sharepoint as wr_sp

#: Thu muc rieng cho ho so hop dong. KHONG dung chung "Weekly Reports".
CONTRACT_ROOT = "Contract Review"
BUSINESS_DT = "EC Contract Review Request"
LINK_DT = "EC SharePoint File Link"
TIMEOUT = 30


class SharePointChuaSan(Exception):
    """Graph chua dung duoc (chua cau hinh / mat mang). Goi ben ngoai TU quyet dinh xu ly."""


def _requests():
    import requests
    return requests


def _graph():
    return wr_sp.GRAPH


def _drive_url(rel_path):
    """URL cua mot duong dan trong thu vien mac dinh cua site."""
    from urllib.parse import quote
    return "%s/sites/%s/drive/root:/%s" % (_graph(), wr_sp.SITE_ID, quote(rel_path))


def duong_dan(business_name, file_name):
    """<CONTRACT_ROOT>/<ma phieu>/<ten tep da lam sach>.

    Moi phieu mot thu muc: doi chieu bang mat tren SharePoint khong phai do ma tep, va hai
    phieu dinh kem trung ten khong de len nhau."""
    return "%s/%s/%s" % (CONTRACT_ROOT, business_name, wr_sp.safe_filename(file_name))


def _noi_dung_tep(file_url):
    """Doc bytes cua tep tu kho Frappe. Khong doc bang duong dan tu chuoi nguoi dung dua
    vao - lay qua ban ghi File de khong the tro ra ngoai thu muc kho."""
    name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not name:
        raise SharePointChuaSan("Khong tim thay ban ghi File cho %s" % file_url)
    return frappe.get_doc("File", name).get_content()


def tai_len(file_url, file_name, business_name, token=None):
    """Dua MOT tep len SharePoint. Tra ve dict(item_id, web_url, last_modified).

    Dung upload session cho moi kich co - don gian hon la re nhanh theo dung luong, va
    hop dong .docx co the vuot nguong 4MB cua PUT truc tiep."""
    requests = _requests()
    token = token or wr_sp.get_app_token()
    rel = duong_dan(business_name, file_name)
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


#: Tai khoan dich vu - co trong luong duyet nhung khong phai NGUOI review. Khong cap quyen
#: vao hop dong cho chung: quyen thua la quyen rui ro, va mot dia chi khong phai hom thu that
#: con co the lam Graph tu choi ca lo. Danh sach nay khop theo phan truoc dau @.
TAI_KHOAN_DICH_VU = ("fabric.bot",)


def loc_nguoi_that(emails):
    """Tra ve (giu, bo). Bo tai khoan dich vu. KHONG im lang: ben goi in ra phan bi bo."""
    giu, bo = [], []
    for e in dict.fromkeys(emails or []):
        if not e or "@" not in e:
            continue
        if e.split("@")[0].lower() in TAI_KHOAN_DICH_VU:
            bo.append(e)
        else:
            giu.append(e)
    return giu, bo


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


def cap_quyen(item_id, emails, token=None, cho_sua=True, pha_thua_ke=False):
    """Cap quyen cho DUNG nhung email duoc liet ke. Tra ve dict(da_cap, bo_qua, link).

    DUONG DI: `createLink` voi scope="users" - KHONG phai `/invite`.

    Vi sao doi: 14/09 do tren tenant that, `/invite` tra ve `noResolvedUsers` - va khong MOT
    ai trong 10 dia chi resolve duoc. Zero nguoi resolve nghia la loi o ngu canh app-only
    (token khong dai dien cho nguoi dung nao nen Graph khong co "nguoi moi" de phan giai danh
    sach), chu khong phai mot dia chi hong lam hong ca lo. Trong khi do `createLink` chay that
    moi tuan qua `weekly_report.create_org_link` voi cung loai token - nen day la duong da co
    bang chung, khong phai phong doan thu hai.

    KHONG BAO GIO tu dong lui ve scope="organization" khi that bai. Cap nham cho ca cong ty
    quyen SUA hop dong con te hon nhieu so voi bao loi va de nguoi that quyet dinh.

    `pha_thua_ke=False` la mac dinh co chu y: dat True se GO quyen thua ke tu thu vien, tuc
    thu hoi quyen cua nhung nguoi dang co. Do la mot thay doi tru tren du lieu song, phai do
    `doc_quyen` truoc va co nguoi chot, khong lam kem theo mot lan tai tep.
    """
    requests = _requests()
    token = token or wr_sp.get_app_token()
    nguoi, bo = loc_nguoi_that(emails)
    if not nguoi:
        return {"da_cap": [], "bo_qua": bo, "link": None}
    than = {"type": "edit" if cho_sua else "view",
            "scope": "users",
            "recipients": [{"email": e} for e in nguoi],
            "sendInvitation": False}
    if pha_thua_ke:
        than["retainInheritedPermissions"] = False
    resp = requests.post(
        "%s/sites/%s/drive/items/%s/createLink" % (_graph(), wr_sp.SITE_ID, item_id),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        json=than, timeout=TIMEOUT)
    if resp.status_code not in (200, 201):
        raise SharePointChuaSan("Cap quyen that bai (%s): %s" % (resp.status_code, resp.text[:300]))
    link = ((resp.json() or {}).get("link") or {}).get("webUrl")
    return {"da_cap": nguoi, "bo_qua": bo, "link": link}


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


def ghi_lien_ket(file_url, business_name, ket_qua, da_cap):
    """Luu/cap nhat ban ghi noi tep Frappe voi tep SharePoint. Idempotent theo file_url."""
    ten = frappe.db.get_value(LINK_DT, {"file_url": file_url}, "name")
    doc = frappe.get_doc(LINK_DT, ten) if ten else frappe.new_doc(LINK_DT)
    doc.file_url = file_url
    doc.business_doctype = BUSINESS_DT
    doc.business_name = business_name
    doc.sp_item_id = ket_qua.get("item_id")
    doc.sp_web_url = ket_qua.get("web_url")
    doc.sp_last_modified = gio_he_thong(ket_qua.get("last_modified"))
    doc.sp_synced_at = now_datetime()
    doc.sp_granted_to = ", ".join(da_cap or [])
    doc.save(ignore_permissions=True)
    return doc.name
