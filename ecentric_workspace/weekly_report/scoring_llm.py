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

    # Tai HET truoc, roi moi quyet dinh nen -- khong nen ngay khi mot tep lam
    # tran nguong.
    #
    # Ban dau viet kieu "tep nao lam tran thi nen tep do", va no sai: mot ban ghi
    # co nhieu deck, may tep dau da an gan het 7MB, nen tep cuoi du nen con 1MB
    # van khong lot vao phan con lai -> tu choi ca luot, trong khi nen DEU ca ba
    # tep thi vua. Bat gap 25/09 o WTU-2026-W37-HR-EMP-00011 (1 trong 3 ban thu).
    raw = []
    for url in slide_urls:
        got = gemini_api.fetch_pdf_bytes(url, token, dept_clean or "")
        if not got.get("ok"):
            return [], "tai PDF hong: %s" % (got.get("error") or "?")
        raw.append({"data": got["data"], "name": got.get("display_name") or ""})

    total = sum(len(r["data"]) for r in raw)
    if total > MAX_INLINE_TOTAL:
        # Chia ngan sach theo TY LE kich thuoc goc: tep to duoc nhieu cho hon,
        # va moi tep deu bi ep xuong chu khong don het len mot tep.
        notes = []
        for r in raw:
            share = int(MAX_INLINE_TOTAL * len(r["data"]) / float(total))
            if len(r["data"]) <= share:
                continue
            shrunk, note = gemini_api.shrink_pdf_for_inline(r["data"], max_bytes=share)
            if not shrunk:
                return [], ("tong PDF %d byte vuot tran inline %d va khong nen"
                            " du: %s" % (total, MAX_INLINE_TOTAL, note))
            r["data"] = shrunk
            if note:
                notes.append(note)
        total = sum(len(r["data"]) for r in raw)
        if total > MAX_INLINE_TOTAL:
            return [], ("sau khi nen tat ca van con %d byte > tran %d"
                        % (total, MAX_INLINE_TOTAL))

    files = [{"data": r["data"], "mime_type": "application/pdf",
              "display_name": r["name"]} for r in raw]
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
    # `files_prepared` = so tep CHUAN BI duoc. `files_in_request` (do
    # generate_json dat) = so tep THUC SU nam trong request da tao ra cau tra
    # loi. Hai so nay KHAC nhau khi Kie hong: bytes da tai ve nhung Google
    # khong dung duoc bytes, nen request di ra voi ZERO tep.
    #
    # 25/09: `files_sent` cu tra len(files) va nguoi goi kiem con so do -- cong
    # do dung dai luong, va WTU-2026-W39-NV00162 nhan 17/100 tren mot bao cao
    # ma model khong thay slide nao. Giu `files_sent` la BI DANH so tep that su
    # gui di, de khong ai vo tinh kiem nham lan nua.
    out["files_prepared"] = len(files)
    out["files_sent"] = int(res.get("files_in_request") or 0)
    if note:
        out["kie_skipped"] = note
    return out
