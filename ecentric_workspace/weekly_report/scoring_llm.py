# Copyright (c) 2026, eCentric and contributors
"""Cong goi LLM cho duong CHAM DIEM bao cao tuan.

VI SAO TON TAI: `gemini_score_report` la Server Script chay trong
RestrictedPython. No goi thang Google bang fileUri, nen khong dung duoc Kie --
Kie chi nhan bytes inline. Lam bytes NGAY TRONG sandbox nghia la base64 bang
vong lap Python tung 3 byte; chinh khuon do da lam `gbs_push_pending_binaries`
chay 290 giay va keo uptime xuong 90.2% (24/08), roi tai phat 15/09 lam uptime
ve 0%. Khong lap lai.

Thay vao do: Server Script chi goi mot app method. App chay Python that -- co
base64, co timeout, va di qua cong AI chung (`platform/ai/gateway`, chot 28/09):
model chinh ben Kie, du phong cung ben Kie. Khong con Google.

BAT BIEN: ham nay KHONG dung toi barem, prompt hay schema. No nhan nguyen tu
Server Script va tra ve JSON. Diem so van do Server Script quyet dinh -- doi
cach cham la viec khac, khong lan vao day.
"""
import json

import frappe

from ecentric_workspace import gemini_api


#: Kie khuyen nghi ~10MB cho inline; base64 phong ~33%. Tru hao con lai cho
#: prompt + rubric. Vuot nguong -> thu nen; nen khong duoc thi KHONG cham.
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


#: giay. Deck bao cao tuan la PDF nhieu trang: Kie 3.8 mat 15-30s cho MOT tep nho (log AI dien
#: ho 23-24/09) va co luc treo ~33s roi moi tra 500 (probe 28/09). Tran cu 30s cat ngang
#: dung khoang do -> 538 ReadTimeout 25-28/09. Cho request web (bam cham tay): 100s tong.
WEB_BUDGET = 100
#: Job nen tren queue `long` (ai_retrigger.process_one): du rong cho mot lan thu dai.
JOB_ATTEMPT_TIMEOUT = 150
JOB_BUDGET = 200


@frappe.whitelist(methods=["POST"])
def score_via_llm(prompt, response_schema, system_instruction=None,
                  file_uris=None, slide_deck=None, dept_clean=None,
                  budget=None, attempt_timeout=None):
    """Goi AI cho duong cham diem / tom tat, qua cong AI chung.

    POST chu khong GET: Frappe ROLLBACK moi thao tac ghi trong request GET.

    Tham so:
      prompt, response_schema, system_instruction : chuyen nguyen tu nguoi goi
      file_uris  : BO QUA tu 28/09 (URI Google Files) - giu tham so de nguoi goi cu khong vo
      slide_deck : chuoi URL SharePoint (nhieu dong) -- tai bytes tu day, gui inline
      dept_clean : ten phong ban da bo hau to " - XX", de dung rel_path

    -> {"ok","data","error","provider","fell_back","model","latency_ms","files_sent",
        "files_prepared","attempts"}
    """
    if isinstance(response_schema, str):
        response_schema = json.loads(response_schema)

    urls = [u.strip() for u in (slide_deck or "").split("\n") if u.strip()]
    files, why = _bytes_for_kie(urls, dept_clean) if urls else ([], "")
    if urls and not files:
        # Co slide ma khong tai duoc DU -> KHONG goi AI. Cham tren phan chu cua form thi
        # ra mot con diem vo nghia (slide chiem 75/100 barem) - su co 25/09, 17/100.
        return {"ok": False, "data": None, "error": "khong gui duoc slide: %s" % why,
                "provider": gemini_api.KIE_PROVIDER, "fell_back": False, "model": "",
                "latency_ms": 0, "files_sent": 0, "files_prepared": 0, "attempts": [],
                "kie_skipped": why}

    res = gemini_api.generate_json(
        prompt=prompt,
        response_schema=response_schema,
        system_instruction=system_instruction,
        files=files or None,
        budget=budget or WEB_BUDGET,
        timeout=attempt_timeout,
        purpose="weekly_report",
    )
    out = dict(res)
    # `files_prepared` = so tep CHUAN BI duoc. `files_sent` = so tep THUC SU nam trong
    # request da tao ra cau tra loi (su co 25/09: hai con so nay tung khac nhau va con so sai
    # da cho mot diem 17/100 di qua). Nguoi goi phai kiem `files_sent`.
    out["files_prepared"] = len(files)
    out["files_sent"] = int(res.get("files_in_request") or 0)
    return out
