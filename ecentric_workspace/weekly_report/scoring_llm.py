# Copyright (c) 2026, eCentric and contributors
"""Cong goi LLM cho duong CHAM DIEM bao cao tuan.

VI SAO TON TAI: `gemini_score_report` la Server Script chay trong
RestrictedPython. No goi thang Google bang fileUri, nen khong dung duoc Kie --
Kie chi nhan bytes inline. Lam bytes NGAY TRONG sandbox nghia la base64 bang
vong lap Python tung 3 byte; chinh khuon do da lam `gbs_push_pending_binaries`
chay 290 giay va keo uptime xuong 90.2% (24/08), roi tai phat 15/09 lam uptime
ve 0%. Khong lap lai.

Thay vao do: Server Script chi goi mot app method. App chay Python that -- co
base64, co timeout, co retry, va dung lai `gemini_api.generate_json` (Kie chinh,
Google du phong) da chay tot cho duong AI dien ho.

BAT BIEN: ham nay KHONG dung toi barem, prompt hay schema. No nhan nguyen tu
Server Script va tra ve JSON. Diem so van do Server Script quyet dinh -- doi
cach cham la viec khac, khong lan vao day.
"""
import json

import frappe

from ecentric_workspace import gemini_api


#: Kie khuyen nghi ~10MB cho inline; base64 phong ~33%. Tru hao con lai cho
#: prompt + rubric. Vuot nguong -> khong thu Kie, di thang Google.
MAX_INLINE_TOTAL = gemini_api.KIE_INLINE_MAX_BYTES


def _bytes_for_kie(slide_urls, dept_clean):
    """Tai PDF ve bytes de gui inline cho Kie. -> (files, ly_do_bo_qua).

    Khong tai duoc DU tep thi tra ([], ly_do): gui THIEU tep con te hon loi, vi
    model van cham diem -- cham tren du lieu khong day du, kieu sai kho thay
    nhat va no di thang vao KPI.
    """
    if not slide_urls:
        return [], "khong co slide"
    try:
        from ecentric_workspace.weekly_report import sharepoint
        token = sharepoint.get_app_token()
    except Exception as exc:
        return [], "khong lay duoc Graph token: %s" % exc
    if not token:
        return [], "Graph token rong"

    files, total = [], 0
    for url in slide_urls:
        got = gemini_api.fetch_pdf_bytes(url, token, dept_clean or "")
        if not got.get("ok"):
            return [], "tai PDF hong: %s" % (got.get("error") or "?")
        data = got["data"]
        total += len(data)
        if total > MAX_INLINE_TOTAL:
            # THEM 25/09 (chat Weekly Report, Hoan chot): thu NEN truoc khi bo
            # cuoc. Truoc day vuot tran la di thang Google -- ma Google dang tra
            # 400 tu 17/09, nen "du phong" luc nay la luoi rach va deck lon se
            # khong bao gio co diem.
            #
            # Ky luat tat-ca-hoac-khong-gi GIU NGUYEN: nen duoc thi di Kie voi DU
            # tep; nen khong duoc thi van tra ([], ly_do) nhu cu. Nen co san chat
            # luong (SHRINK_MIN_SCALE) -- qua san thi tu choi, vi slide mo qua thi
            # model VAN cham, cham tren thu no khong doc noi.
            total -= len(data)
            shrunk, note = gemini_api.shrink_pdf_for_inline(
                data, max_bytes=max(0, MAX_INLINE_TOTAL - total))
            if not shrunk:
                return [], "tong PDF vuot tran inline %d va khong nen duoc: %s" % (
                    MAX_INLINE_TOTAL, note)
            data = shrunk
            total += len(data)
        files.append({"data": data, "mime_type": "application/pdf",
                      "display_name": got.get("display_name") or ""})
    return files, ""


@frappe.whitelist(methods=["POST"])
def score_via_llm(prompt, response_schema, system_instruction=None,
                  file_uris=None, slide_deck=None, dept_clean=None):
    """Goi LLM cho duong cham diem. Kie chinh, Google du phong.

    POST chu khong GET: Frappe ROLLBACK moi thao tac ghi trong request GET, nen
    duong nay phai la POST de con ghi duoc log/diem sau do.

    Tham so:
      prompt, response_schema, system_instruction : chuyen nguyen tu Server Script
      file_uris  : JSON list [{"uri","mime_type"}] -- duong GOOGLE dung cai nay
      slide_deck : chuoi URL SharePoint (nhieu dong) -- duong KIE tai bytes tu day
      dept_clean : ten phong ban da bo hau to " - XX", de dung rel_path

    -> {"ok","data","error","provider","fell_back","model","latency_ms","files_sent"}
    """
    if isinstance(response_schema, str):
        response_schema = json.loads(response_schema)
    uris = file_uris
    if isinstance(uris, str):
        uris = json.loads(uris or "[]")
    uris = uris or []

    files = [dict(u) for u in uris if (u or {}).get("uri")]
    note = ""

    if gemini_api.provider() == gemini_api.KIE_PROVIDER:
        urls = [u.strip() for u in (slide_deck or "").split("\n") if u.strip()]
        data_files, why = _bytes_for_kie(urls, dept_clean)
        if data_files:
            # Giu ca `uri` cua Google trong cung phan tu: neu Kie hong,
            # generate_json roi ve Google va van co URI de dung, khong phai
            # tai lai lan hai.
            for i, f in enumerate(data_files):
                if i < len(files):
                    f["uri"] = files[i].get("uri")
            files = data_files
        else:
            note = why  # se di Google; generate_json tu ghi log fallback

    res = gemini_api.generate_json(
        prompt=prompt,
        response_schema=response_schema,
        system_instruction=system_instruction,
        files=files or None,
    )
    out = dict(res)
    out["files_sent"] = len(files)
    if note:
        out["kie_skipped"] = note
    return out
