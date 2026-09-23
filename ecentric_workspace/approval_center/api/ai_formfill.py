# Copyright (c) 2026, eCentric and contributors
"""Endpoint AI dien ho - CHUNG cho 28 form, la mot adapter transport, khong hon.

VI SAO O `api/` CHU KHONG O `features/<form>/controllers/`. Endpoint nay nhan `approval_code`
va tra schema tu `shared/registry`; dat no trong controllers cua mot form vua sai tang vua la
dung cai copy-paste 28 lan ma ca thiet ke nay dung de tranh. `api/` da la tang "stable public
dotted-path adapter" theo ADR-001 §5, va nam ngoai pham vi quet cua `test_feature_architecture`
- rang buoc duoc thoa bang CAU TRUC dung, khong phai bang ne chu.

SERVER KHONG GHI GI VAO PHIEU. Endpoint tra ve de trang tu dien; nguoi dung xem, sua, tu bam
Gui. "AI khong bao gio submit" o day duoc noi rong thanh "AI khong bao gio ghi vao phieu".
"""
import time

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.integrations import ai_attachments as att
from ecentric_workspace.approval_center.shared.integrations import ai_formfill as svc
from ecentric_workspace.approval_center.shared.registry import get_definition
from ecentric_workspace import gemini_api

PILOT_ROLE = "EC AI Formfill Pilot"


def _pilot_allowed(user=None):
    """Giai doan 1: chi tai khoan pilot. Giai doan 3 mo cho tat ca = BO ham nay, mot dong.

    Bang Role chu khong phai `if user == "hoan.tran@..."` - CLAUDE.md cam nhanh theo ten
    nguoi trong code dung chung, va role thi tra duoc trong Desk.
    """
    roles = frappe.get_roles(user or frappe.session.user)
    return PILOT_ROLE in roles or "System Manager" in roles


@frappe.whitelist()
def bootstrap(approval_code):
    """Trang hoi truoc khi ve nut. Che nut khong phai la phep kiem - phep kiem that o
    `suggest`; day chi la de khong ve mot nut bam vao se bao loi."""
    if svc.is_disabled() or not _pilot_allowed():
        return {"enabled": False}
    used = svc.used_today()
    cap = svc.daily_cap()
    definition = get_definition(approval_code)
    return {"enabled": True, "remaining": max(0, cap - used), "cap": cap,
            "max_chars": svc.MAX_NOTE_CHARS,
            "max_files": att.MAX_FILES,
            "file_exts": sorted(att.MIME_BY_EXT.keys()),
            # Tab "Tao hang loat". `has_flags` de man hinh biet co ve cot dau hieu hay khong
            # - form nao chua khai `batch_flagger` thi cot do khong ton tai, chu khong phai
            # ve mot cot rong roi goi mot endpoint luon tra {}.
            "batch": {"max_drafts": svc.MAX_BATCH_DRAFTS,
                      "has_flags": definition.batch_flagger is not None,
                      # Duong dan api CUA FORM, do SERVER dat - man hinh chi viec goi.
                      # Bundle KHONG duoc tu ghep chuoi nay: no la asset dung chung, doan
                      # ten module tu `approval_code` la dung lai dung cai anh xa 28 dong
                      # ma registry sinh ra de xoa bo.
                      "ns": ("ecentric_workspace.approval_center.api.%s."
                             % (definition.feature or "")) if definition.feature else ""}}


@frappe.whitelist(methods=["POST"])
def suggest(approval_code, note=None, current=None, files=None):
    """Doc `note` + tep dinh kem, tra ve nhung o AI de xuat. KHONG ghi gi vao phieu.

    THU TU KIEM - fail-closed, re truoc:
      1. cong tac site_config   -> nem (khong ai can do cai nay)
      2. role pilot             -> nem PermissionError
      3. ma form la that        -> nem (registry tu nem)
      4. tran ngay / do dai / khoa -> TRA VE, KHONG NEM
      5. quyen doc TUNG tep     -> bo tep do, TRA VE ly do (`ai_attachments.collect`)

    Tep dinh kem di vao sau buoc 4 va khong bao gio di truoc: moi tep la mot lan doc dia +
    mot lan tai len Gemini.

    Vi sao 4 tra ve chu khong nem: `frappe.throw` rollback transaction, tuc dong log bi mat
    dung luc can nhat. Chi nem cho loi quyen that - nhung cai do khong can do.
    """
    if svc.is_disabled():
        frappe.throw(_("Tính năng AI điền hộ đang tắt."))
    if not _pilot_allowed():
        frappe.throw(_("Bạn chưa được bật tính năng AI điền hộ."), frappe.PermissionError)

    definition = get_definition(approval_code)          # ma la -> nem, dung cho
    note = (note or "").strip()
    current = frappe.parse_json(current) if isinstance(current, str) else (current or {})
    file_urls = frappe.parse_json(files) if isinstance(files, str) else (files or [])
    parts, rejected, files_note = [], [], ""

    def _refuse(kind, **extra):
        svc.write_log(approval_code=approval_code, input_chars=len(note), outcome=kind,
                      files_count=len(parts), files_note=files_note)
        return dict({"refused": kind, "fields": {}, "dropped_count": 0,
                     "files_rejected": rejected}, **extra)

    used, cap = svc.used_today(), svc.daily_cap()
    if used >= cap:
        return _refuse("refused_quota", cap=cap)
    if len(note) > svc.MAX_NOTE_CHARS:
        return _refuse("refused_too_long", max_chars=svc.MAX_NOTE_CHARS)

    # Doc tep SAU cac phep kiem re. Moi tep la mot lan doc dia + mot lan tai len Gemini; lam
    # viec do roi moi phat hien nguoi dung het luot la tra gia cho mot cau tra loi da biet.
    # `collect` khong nem: mot tep hong chi lam mat tep do, khong lam mat ca luot.
    if file_urls:
        parts, rejected = att.collect(file_urls)
        files_note = "; ".join("%s: %s" % (r["file"], r["message"]) for r in rejected)

    if not note and not parts:
        # Van ban trong va khong tep nao doc duoc -> khong co gi de doc.
        return _refuse("empty")

    schema = svc.build_schema(definition)
    started = time.time()
    res = gemini_api.generate_json(
        prompt=svc.build_prompt(schema, note, current, att.prompt_block(parts)),
        response_schema=svc.response_schema(schema),
        system_instruction=svc.SYSTEM_INSTRUCTION,
        files=parts,
    )
    if not res["ok"]:
        if res.get("error") == "no_key":
            return _refuse("refused_no_key")
        svc.write_log(approval_code=approval_code, input_chars=len(note), outcome="error",
                      model=res.get("model"), latency_ms=res.get("latency_ms"),
                      error=res.get("error"),
                      files_count=len(parts), files_note=files_note)
        # Luot hong KHONG tinh vao tran: bat nguoi dung tra gia cho mot su co cua nha cung
        # cap la sai, va no khuyen khich ho bam lai lien tuc.
        return {"error": res.get("error"), "fields": {}, "dropped_count": 0,
                "files_rejected": rejected}

    values, sources = svc.split_sources(res["data"])
    # Doi chieu trich dan TRUOC gate: so tai khoan bia kem trich dan bia van qua duoc gate.
    values, dropped_src = svc.verify_sources(schema, values, sources, note, bool(parts))
    accepted, dropped = svc.gate(schema, values)
    dropped = dropped_src + dropped
    # Nguoi dung da tu go thi giu nguyen - AI khong de len.
    accepted = {k: v for k, v in accepted.items()
                if str(current.get(k) or "").strip() == ""}
    merged = dict(current, **accepted)
    probe = svc.probe(definition, merged)

    log_name = svc.write_log(
        approval_code=approval_code, input_chars=len(note), outcome="ok",
        model=res.get("model"), latency_ms=int((time.time() - started) * 1000),
        fields_offered=accepted, fields_dropped=dropped,
        files_count=len(parts), files_note=files_note,
        probe_passed=probe.get("ok"), probe_message=probe.get("message"))

    return {
        "fields": accepted,
        # Chi tra SO LUONG cho man hinh; ly do tung truong nam trong log de giai doan 3 doc.
        "dropped_count": len(dropped),
        "dropped": dropped,
        "sources": {k: v for k, v in sources.items() if k in accepted},
        "probe": {"ok": probe.get("ok"), "message": probe.get("message")},
        "files_read": [p["display_name"] for p in parts],
        "files_rejected": rejected,
        "remaining": max(0, cap - used - 1),
        "log": log_name,
    }


@frappe.whitelist(methods=["POST"])
def batch_flags(approval_code, rows=None):
    """Ba dau hieu ngoai le cho mot LO ban nhap. CHI DOC, va chi tra ve boolean.

    Vi sao endpoint nay ton tai rieng thay vi tra co ngay trong `suggest`: hai dau hieu
    trong ba chi co nghia KHI DA CO CA LO. `suggest` chay mot tep mot lan (de mot tep hong
    khong keo ca lo xuong, va de man hinh ve duoc tung dong mot) nen luc do chua ai biet
    dong ben canh la gi. "Trung so tai khoan trong cung lo" khong ton tai duoc o tang do.

    KHONG tra so lan, KHONG tra so tien, KHONG tra ten ai tao phieu cu. Chi dung/sai. Gia
    tri canh bao nam o chu "moi"; moi chi tiet them la mot cai oracle khong ai xin.
    """
    if svc.is_disabled():
        frappe.throw(_("Tính năng AI điền hộ đang tắt."))
    if not _pilot_allowed():
        frappe.throw(_("Bạn chưa được bật tính năng AI điền hộ."), frappe.PermissionError)

    definition = get_definition(approval_code)
    flagger = definition.batch_flagger
    if flagger is None:
        return {}
    rows = frappe.parse_json(rows) if isinstance(rows, str) else (rows or [])
    if not isinstance(rows, list):
        return {}
    # Tran cung, ap o SERVER. Tran ben client la goi y giao dien; tran that phai o day,
    # neu khong thi mot lo 500 dong la 1000 truy van chi bang cach sua mot bien trong console.
    rows = rows[:svc.MAX_BATCH_DRAFTS]
    try:
        return flagger(rows, frappe.session.user) or {}
    except Exception:
        # Dau hieu la thu TANG THEM. Hong o day khong duoc phep lam hong man hinh tao phieu.
        frappe.log_error(title="ai_formfill.batch_flags", message=frappe.get_traceback())
        return {}
