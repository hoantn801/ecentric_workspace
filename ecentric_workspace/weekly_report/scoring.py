# Copyright (c) 2026, eCentric and contributors
"""Cham diem + tom tat bao cao tuan, qua Kie (chinh) / Google (du phong).

Port cua hai Server Script `gemini_score_report` va `gemini_summarize_report`
(ban goc 25/09 o erp-inspection/snapshots/weekly_ai_20260925_115127). Chung goi
thang Google tu trong sandbox; tu 17-18/09 moi lan goi tra 400 va cham diem
dung han. Ly do doi:

  * Kie KHONG dung duoc URI cua Google Files API, phai gui bytes inline. Viec
    tai PDF + chon Kie/Google nam o `weekly_report/scoring_llm.score_via_llm`
    (buoc 1, do chat LLM-provider lam). File nay KHONG tu tai tep va KHONG tu
    quyet nha cung cap -- ban dau tu viet lai phan do va da sai: no bo qua tep
    tai hong roi cham tiep tren cac tep con lai, tuc cham tren deck thieu.
  * Server Script goi Google qua frappe.integrations, va raise_for_status() vut
    mat than phan hoi -- ca tuan chi con chu "400 Bad Request", khong ai biet vi
    sao. Trong app, _call_google() giu nguyen `error.message` cua Google.

HAI THAY DOI HANH VI so voi ban goc, deu co chu y:

1. TRU DIEM TRE CHI MOT LAN. Ban goc chua khoi `if doc.late_submission:` HAI
   LAN lien tiep (dong 208 va 227), ca hai truoc khi luu -- nen bao cao nop tre
   bi tru 20 diem chu khong phai 10, va `overall_score_before_late` bi khoi thu
   hai ghi de bang diem DA tru, tuc chinh truong dung de truy vet cung sai. Co
   tu 20/07/2026, ngay tinh nang ra doi. 143 ban ghi mang dau hieu nay.
2. `responseSchema` THAT thay vi mo ta hinh dang JSON trong van ban prompt roi
   tu go rao ```json. Schema dung sinh tu chinh `field_key`/`max_points` cua
   rubric nen ten truong khop tuyet doi voi cai dang luu o `ai_score_breakdown`.

Doan "GRADING STANCE" trong prompt goc cung bi lap hai lan; o day chi con mot.

Barem KHONG hardcode: doc tu DocType `EC Scoring Rubric` / `EC Scoring Tier`
(sua duoc o Desk), chi quay ve `System Settings.ec_scoring_rubric` khi rong --
giong het ban goc.
"""

import json

import frappe

from ecentric_workspace.weekly_report import scoring_llm

WTU = "Weekly Team Update"
LATE_PENALTY = 10

# Cac truong chung moi barem deu phai tra ve.
_COMMON_SCHEMA = {
    "overall_score": {"type": "integer", "minimum": 0, "maximum": 100},
    "ai_usage_score": {"type": "integer", "minimum": 0, "maximum": 100},
    "structure_score": {"type": "integer", "minimum": 0, "maximum": 100},
    "feedback": {"type": "string"},
    "highlights": {"type": "array", "items": {"type": "string"}},
    "improvements": {"type": "array", "items": {"type": "string"}},
}

# Dung khi khong co dong nao trong EC Scoring Rubric -- y het ban goc.
_LEGACY_FIELDS = (
    ("slide_deck_score", 40),
    ("ai_tools_score", 25),
    ("overall_status_score", 25),
    ("optional_bonus", 10),
    ("penalty", 20),
)

_DEFAULT_TIERS = ("Outstanding", "Good", "Acceptable", "Below")


def _rubric_rows():
    """-> (criteria, tiers). Loi khi doc DocType KHONG duoc lam hong lan cham."""
    try:
        criteria = frappe.get_all(
            "EC Scoring Rubric", filters={"enabled": 1},
            fields=["criterion_name", "field_key", "max_points", "is_penalty",
                    "description", "display_order"],
            order_by="display_order asc")
        tiers = frappe.get_all(
            "EC Scoring Tier", filters={"enabled": 1},
            fields=["tier_name", "tier_icon", "min_score", "max_score"],
            order_by="min_score desc")
        return criteria, tiers
    except Exception:
        return [], []


def build_rubric_text(criteria, tiers):
    """PURE. Van ban barem dua vao prompt. Giu dung dinh dang ban goc."""
    parts = ["# Scoring Rubric (from EC Scoring Rubric DocType)"]
    for c in criteria:
        prefix = "[Penalty] " if c.get("is_penalty") else ""
        parts.append("## " + prefix + str(c.get("criterion_name") or "")
                     + " - " + str(c.get("max_points") or 0) + " diem")
        if c.get("description"):
            parts.append(str(c.get("description")))
    if tiers:
        parts.append("")
        parts.append("## Tiers")
        for t in tiers:
            parts.append("- " + str(t.get("tier_icon") or "") + " "
                         + str(t.get("tier_name") or "") + ": "
                         + str(t.get("min_score") or 0) + "-"
                         + str(t.get("max_score") or 0))
    return "\n".join(parts)


def build_schema(criteria, tiers):
    """PURE. responseSchema tu barem.

    Ban goc nhet hinh dang JSON vao van ban prompt roi hy vong model tra dung.
    Schema that thi model KHONG the tra sai ten truong -- va ten truong o day
    chinh la cai duoc luu vao `ai_score_breakdown` roi doc lai o UI, nen sai ten
    la mat diem thanh phan ma khong ai thay.
    """
    props = {}
    required = []
    for c in criteria:
        key = (c.get("field_key") or "").strip()
        if not key:
            continue
        props[key] = {"type": "integer", "minimum": 0,
                      "maximum": int(c.get("max_points") or 0)}
        required.append(key)
    if not props:
        for key, mx in _LEGACY_FIELDS:
            props[key] = {"type": "integer", "minimum": 0, "maximum": mx}
            required.append(key)

    names = [str(t.get("tier_name") or "") for t in tiers if t.get("tier_name")]
    props["tier"] = {"type": "string", "enum": names or list(_DEFAULT_TIERS)}
    required.append("tier")

    for key, spec in _COMMON_SCHEMA.items():
        props[key] = spec
        required.append(key)

    return {"type": "object", "properties": props, "required": required}


def build_report_text(doc, slide_files):
    """PURE. Khoi 'REPORT FORM'. Port nguyen van."""
    t = "# Weekly Report\n"
    t += ("Name: " + (doc.full_name or "") + " | Week: " + (doc.week_label or "")
          + " | Dept: " + (doc.department or "") + "\n")
    t += ("Status: " + (doc.overall_status or "-") + " | Mood: "
          + (doc.mood or "-") + "\n\n")
    t += "## REQUIRED\n"
    t += "Slide Deck: " + str(len(slide_files)) + " files\n"
    for f in slide_files:
        t += "  - " + f + "\n"
    t += "AI Tools: " + (doc.ai_tools_used or "(none)") + "\n"
    t += "Status: " + (doc.overall_status or "(empty)") + "\n\n"
    t += "## OPTIONAL (bonus)\n"
    t += "what_done: " + (doc.what_done or "(empty)") + "\n"
    t += "pending_progress: " + (doc.pending_progress or "(empty)") + "\n"
    t += "plan_next_week: " + (doc.plan_next_week or "(empty)") + "\n"
    t += "blockers_help: " + (doc.blockers_help or "(empty)") + "\n"
    t += "ai_use_case: " + (doc.ai_use_case or "(empty)") + "\n"
    return t


GRADING_STANCE = (
    "GRADING STANCE - CHAM NGHIEM KHAC:\n"
    "- Diem mac dinh cua moi tieu chi la MOC THAP NHAT trong barem; chi nang len"
    " moc cao hon khi co BANG CHUNG cu the trich dan duoc tu slide.\n"
    "- Phan van giua 2 moc -> chon moc THAP.\n"
    "- Noi dung chung chung/template, khong co so lieu -> KHONG dat moc cao.\n"
    "- 85+ (Outstanding) chi danh cho bao cao vuot troi hiem gap; ky vong phan"
    " lon bao cao roi vao khoang 55-80.\n"
    "- Trong feedback, neu ro bang chung cho tung muc diem da cho.\n"
    "- KHONG tu tru diem nop tre hay copy: he thong tu dong xu ly cac penalty"
    " nay ngoai AI.\n"
)


def build_instruction(rubric_text, report_text):
    """PURE. Prompt cham diem.

    Ban goc lap GRADING STANCE hai lan (noi them ma khong doc lai phan da co);
    o day mot lan. Khong con doan mo ta hinh dang JSON: responseSchema lo viec do.
    """
    return (
        "Score weekly report per rubric.\n"
        + GRADING_STANCE
        + "PDF dinh kem la NOI DUNG CHINH (slide deck) - phan tich ky de cham"
          " diem slide_deck_score.\n"
        "Form text fields chi la metadata bo sung.\n\n"
        "RUBRIC:\n" + rubric_text + "\n\nREPORT FORM:\n" + report_text
    )


def slide_filenames(doc):
    """PURE. Ten tep hien thi, chi de dua vao prompt."""
    out = []
    for u in (doc.slide_deck or "").split("\n"):
        u = u.strip()
        if u and "/" in u:
            name = u.rsplit("/", 1)[1]
            name = name.replace("%20", " ").replace("%26", "&").replace("%23", "#")
            out.append(name)
    return out


def _google_uris(doc):
    """URI Google con han, de score_via_llm co duong du phong.

    Kie khong dung duoc URI nay, nhung neu Kie hong thi generate_json roi ve
    Google va can chung -- khong co thi lan du phong di tay khong.
    """
    now_str = frappe.utils.now()
    out = []
    try:
        for fu in json.loads(doc.gemini_file_uris or "[]"):
            exp = (fu or {}).get("expires_at", "")
            if exp and exp > now_str and fu.get("uri"):
                out.append({"uri": fu["uri"],
                            "mime_type": fu.get("mime_type") or "application/pdf"})
    except Exception:
        return []
    return out


def _dept_clean(department):
    dept = department or ""
    return dept.rsplit(" - ", 1)[0] if " - " in dept else dept


def _apply_late_penalty(parsed, doc, tiers):
    """Tru diem nop tre -- MOT LAN. He thong tru, khong phai AI (AI khong biet han).

    Ban goc chay khoi nay hai lan nen tru 20. O day `overall_score_before_late`
    giu diem GOC that, de lan sau con truy duoc.
    """
    if not doc.late_submission:
        return parsed
    base = int(parsed.get("overall_score") or 0)
    new_score = base - LATE_PENALTY
    if new_score < 0:
        new_score = 0
    parsed["overall_score_before_late"] = base
    parsed["late_penalty_applied"] = LATE_PENALTY
    parsed["penalty"] = int(parsed.get("penalty") or 0) + LATE_PENALTY
    parsed["overall_score"] = new_score
    for t in tiers:
        lo = t.get("min_score") or 0
        hi = t.get("max_score") or 0
        if lo <= new_score <= hi:
            parsed["tier"] = t.get("tier_name") or parsed.get("tier")
            break
    return parsed


def _assert_deck_reached_model(res, record_name):
    """Chan viec cham diem tren bao cao KHONG co slide nao toi duoc model.

    Chuoi hong that, phat hien 25/09 ngay sau khi tro cron vao duong nay:
      1. Kie timeout (api.kie.ai chet) -> _bytes_for_kie tra rong;
      2. ban ghi khong co `gemini_file_uris` con han -- dung tinh trang hai bao
         cao W39, vi chung ket CHINH VI upload Google hong;
      3. generate_json duoc goi voi files=None -> Google cham chi tren phan text
         cua form, khong mot slide nao;
      4. tra ok=True -> diem duoc ghi vao ho so.
    `slide_deck_score` chiem 75/100 cua barem, nen day la mot con diem vo nghia
    duoc dan nhan la co that, va no chay thang vao KPI.

    Ban `collect_deck_files` truoc do co chot `if not files: return error`; luc
    chuyen sang score_via_llm chot do bi bo ma khong thay bang gi. Day la cho thay.
    """
    if int(res.get("files_sent") or 0) > 0:
        return None
    why = res.get("kie_skipped") or "khong ro"
    return {"success": False, "record": record_name,
            "error": ("KHONG co tep slide nao toi duoc model -- tu choi cham de"
                      " khong tao ra mot con diem vo nghia. Ly do: " + str(why))[:700],
            "provider": res.get("provider"), "model": res.get("model"),
            "files_sent": 0}


def score_report(record_name):
    """Cham diem mot bao cao. -> dict {"success", ...}."""
    doc = frappe.get_doc(WTU, record_name)
    errors = []

    criteria, tiers = _rubric_rows()
    if criteria:
        rubric_text = build_rubric_text(criteria, tiers)
    else:
        rubric_text = frappe.db.get_single_value(
            "System Settings", "ec_scoring_rubric") or ""
    schema = build_schema(criteria, tiers)

    prompt = build_instruction(rubric_text, build_report_text(doc, slide_filenames(doc)))
    res = scoring_llm.score_via_llm(
        prompt=prompt,
        response_schema=schema,
        file_uris=_google_uris(doc),
        slide_deck=doc.slide_deck or "",
        dept_clean=_dept_clean(doc.department),
    )
    if not res.get("ok"):
        return {"success": False, "record": record_name,
                "error": str(res.get("error"))[:700],
                "provider": res.get("provider"), "model": res.get("model")}

    refused = _assert_deck_reached_model(res, record_name)
    if refused:
        return refused

    parsed = _apply_late_penalty(res["data"], doc, tiers)

    doc.overall_ai_score = int(parsed.get("overall_score") or 0)
    doc.ai_usage_score = int(parsed.get("ai_usage_score") or 0)
    doc.structure_score = int(parsed.get("structure_score") or 0)
    doc.ai_status = parsed.get("tier") or ""
    doc.ai_feedback = parsed.get("feedback") or ""
    doc.ai_score_breakdown = json.dumps(parsed)
    doc.save(ignore_permissions=True)

    return {"success": True, "record": record_name, "scores": parsed,
            "pdf_files_analyzed": res.get("files_sent"),
            "provider": res.get("provider"), "model": res.get("model"),
            "fell_back": res.get("fell_back"), "kie_skipped": res.get("kie_skipped")}


SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}


def build_summary_prompt(doc):
    """PURE. Prompt tom tat. Port nguyen van phan noi dung."""
    content = "Form data:\n"
    content += ("Nguoi: " + (doc.full_name or "?") + "  | Phong: "
                + (doc.department or "-") + "\n")
    content += ("Status: " + (doc.overall_status or "-") + " | Mood: "
                + (doc.mood or "-") + "\n")
    content += "AI Tools: " + (doc.ai_tools_used or "-") + "\n"
    content += "Da lam: " + (doc.what_done or "-") + "\n"
    content += "Dang do: " + (doc.pending_progress or "-") + "\n"
    content += "Plan: " + (doc.plan_next_week or "-") + "\n"
    content += "Blocker: " + (doc.blockers_help or "-") + "\n"
    content += "AI Use Case: " + (doc.ai_use_case or "-") + "\n"
    return (
        "Phan tich bao cao tuan + cac PDF dinh kem (slide deck = noi dung chinh).\n"
        "Viet tom tat 4-6 cau tieng Viet professional, theo cau truc"
        " Tong -> Phan -> Hop -> Insight.\n"
        "Trich xuat so lieu cu the, ten nguoi/team, achievement, risk,"
        " AI usage quality.\n"
        "Plain text, paragraph lien tuc, khong markdown.\n\n"
        + content + "\n\nTra ve JSON {\"summary\": \"<doan tom tat>\"}."
    )


def summarize_report(record_name):
    """Tom tat mot bao cao. -> dict.

    Ban goc tra ve van ban thuan; o day di qua generate_json nen phai boc trong
    mot truong `summary`. Lam vay de chi con MOT duong goi LLM (co du phong, co
    scrub key, co do latency) thay vi hai duong phai sua song song.
    """
    doc = frappe.get_doc(WTU, record_name)
    res = scoring_llm.score_via_llm(
        prompt=build_summary_prompt(doc),
        response_schema=SUMMARY_SCHEMA,
        file_uris=_google_uris(doc),
        slide_deck=doc.slide_deck or "",
        dept_clean=_dept_clean(doc.department),
    )
    if not res.get("ok"):
        return {"success": False, "record": record_name,
                "error": str(res.get("error"))[:700],
                "provider": res.get("provider"), "model": res.get("model")}

    refused = _assert_deck_reached_model(res, record_name)
    if refused:
        return refused

    summary = (res["data"].get("summary") or "").strip()
    if not summary:
        return {"success": False, "record": record_name,
                "error": "model tra ve summary rong",
                "provider": res.get("provider")}

    doc.ai_summary = summary
    doc.save(ignore_permissions=True)
    return {"success": True, "record": record_name, "summary": summary,
            "pdf_files_analyzed": res.get("files_sent"),
            "provider": res.get("provider"), "model": res.get("model"),
            "fell_back": res.get("fell_back"), "kie_skipped": res.get("kie_skipped")}
