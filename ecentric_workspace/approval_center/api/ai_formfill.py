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
from ecentric_workspace.approval_center.shared.requests import command_service
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


# --- G2b: lo chi TAO BAN NHAP ------------------------------------------------------
#
# CHOT VOI HOAN 23/09: che do hang loat chi DIEN + DINH TEP + TAO NHAP. Nguoi dung tu mo
# tung phieu, tu dien not phan cua ho, tu bam Gui. Ban dau toi lam no gui luon; sai, va cai
# sai do khong phai o giao dien ma o chinh de bai: hai trong so cac o bat buoc la PHAN DOAN
# CUA CON NGUOI ("Chi phi hop le?", o tich xac nhan) - khong ai uy quyen cho may duoc.


def _o_bat_buoc_may_tu_dien(definition):
    """Cac o Select BAT BUOC ma AI KHONG duoc phep dien.

    DAY LA CAI BAY DA XAY RA THAT, 23/09. `frappe.new_doc` lap mot Select bat buoc KHONG CO
    default bang LUA CHON DAU TIEN cua no. Payload cua lo khong gui `is_cost_valid` va
    `has_purchase_request`, nen ca hai thanh "Yes" - options la "Yes\nNo".

    `is_cost_valid` la o "Chi phi hop le?". May vua tra loi "Co" thay nguoi dung tren mot
    phieu chua ai doc. Do la mot khang dinh sai trong ho so tai chinh, va no IM LANG - khong
    loi, khong canh bao, chi la mot chu "Yes" trong o ma le ra nguoi lap phai tu chon.

    O tich xac nhan thoat duoc CHI NHO MAY: no tinh co co `default = "No"`. Xoa cai default
    ay di la lo hang loat tu ky luon ca cam ket trach nhiem.

    Nen danh sach nay SUY RA TU META, khong viet tay: form thu 29 them mot Select bat buoc
    vao `ai_exclude_fields` thi no tu duoc bao ve, khong ai phai nho.
    """
    meta = frappe.get_meta(definition.business_doctype)
    chan = set(definition.clone_exclude_fields or ()) | set(
        getattr(definition, "ai_exclude_fields", ()) or ())
    ra = []
    for fieldname in chan:
        df = meta.get_field(fieldname)
        if df is not None and df.fieldtype == "Select" and df.reqd:
            ra.append(fieldname)
    return ra


def _con_thieu(definition, name):
    """O bat buoc nao con trong -> tra ve [{fieldname, label}] cho man hinh noi ra.

    Doc META chu khong theo danh sach cung: mot danh sach cung lech khoi form la lech am tham.
    """
    meta = frappe.get_meta(definition.business_doctype)
    doc = frappe.get_doc(definition.business_doctype, name)
    ra = []
    for df in meta.fields:
        if not df.reqd or df.fieldname not in (definition.editable_fields or ()):
            continue
        if not str(doc.get(df.fieldname) or "").strip():
            ra.append({"fieldname": df.fieldname, "label": frappe._(df.label or df.fieldname)})
    return ra


@frappe.whitelist(methods=["POST"])
def create_draft(approval_code, fields=None, log=None):
    """Tao MOT ban nhap tu ket qua AI. KHONG gui. Tra ve ma phieu + o nao con thieu."""
    if svc.is_disabled():
        frappe.throw(_("Tính năng AI điền hộ đang tắt."))
    if not _pilot_allowed():
        frappe.throw(_("Bạn chưa được bật tính năng AI điền hộ."), frappe.PermissionError)

    definition = get_definition(approval_code)
    data = frappe.parse_json(fields) if isinstance(fields, str) else (fields or {})
    if not isinstance(data, dict):
        frappe.throw(_("Dữ liệu không hợp lệ."))

    # Chi nhan nhung o AI duoc phep dien. Client la thu khong tin duoc: khong loc o day thi
    # mot request tu tay co the dat `is_cost_valid` hay o tich xac nhan qua duong nay.
    chan = set(definition.clone_exclude_fields or ()) | set(
        getattr(definition, "ai_exclude_fields", ()) or ())
    sach = {k: v for k, v in data.items()
            if k in (definition.editable_fields or ()) and k not in chan}

    ket = command_service.save_draft(definition, name=None, payload=sach)
    name = ket.get("name")

    # TRA LAI TRANG THAI "CHUA TRA LOI" cho nhung o may vua tu dien ho.
    #
    # Dung `db.set_value` chu khong dung `doc.save()`: luu lai se vap chinh phep kiem bat buoc
    # ma ta dang muon de NGO. Day la mot lan co tinh di vong qua validate, va no chinh dang:
    # ta khong ghi mot gia tri moi nao ca, ta XOA mot cau tra loi ma khong ai dua ra.
    for fieldname in _o_bat_buoc_may_tu_dien(definition):
        if fieldname in sach:
            continue
        try:
            frappe.db.set_value(definition.business_doctype, name, fieldname, "",
                                update_modified=False)
        except Exception:
            frappe.log_error(title="ai_formfill.create_draft: khong xoa duoc %s" % fieldname,
                             message=frappe.get_traceback())

    _dong_dau_log(log, name)
    return {"name": name, "missing": _con_thieu(definition, name)}


def _dong_dau_log(log_name, business_name):
    """Noi dong log cua luot AI vao phieu vua tao.

    De man hinh CON TO DUOC MAU O LAN MO SAU. Ban do vang/do hien nay chay bang `S.filled` -
    mot bien trong bo nho trinh duyet cua dung phien da chay AI; mo lai ban nhap hom sau,
    hoac nguoi khac mo, thi khong con gi de to. Cho luu la `business_doc` tren dong log:
    DocType do da khai san truong nay tu dau (cung voi `handed_off_at`) va chua ai dung.
    Nho vay KHONG phai them truong vao 28 doctype phieu, khong phai migrate.

    `log_name` do CLIENT gui len nen phai kiem: chi dong dau len dong cua CHINH nguoi dang
    goi, va chi khi dong do con trong. Khong kiem thi mot request tu tay co the gan phieu
    cua minh vao luot AI cua nguoi khac.
    """
    if not log_name or not business_name:
        return
    try:
        row = frappe.db.get_value(svc.LOG_DOCTYPE, log_name,
                                  ["request_user", "business_doc"], as_dict=True)
        if not row or row.get("request_user") != frappe.session.user:
            return
        if (row.get("business_doc") or "").strip():
            return
        frappe.db.set_value(svc.LOG_DOCTYPE, log_name, {
            "business_doc": business_name,
            "handed_off_at": frappe.utils.now_datetime(),
        }, update_modified=False)
    except Exception:
        # Dau moc la thu tang them. Hong o day khong duoc lam hong viec tao phieu.
        frappe.log_error(title="ai_formfill._dong_dau_log", message=frappe.get_traceback())


@frappe.whitelist()
def marks(approval_code, name):
    """O nao tren phieu `name` la do AI dien. CHI DOC.

    Tra ve {"fields": [fieldname], "labels": {fieldname: nhan}, "at": <luc ban giao>}.

    KHONG tra ve GIA TRI ma AI de xuat - gia tri hien tai nam ngay tren phieu roi, va gia
    tri CU (truoc khi nguoi dung sua) la du lieu do cua giai doan 3, khong phai thu man hinh
    can. Tra it nhat co the.

    Quyen: hoi dung cau hoi "nguoi nay co doc duoc phieu do khong". Khong tu dat luat rieng -
    luat da nam trong `has_permission` cua chinh doctype phieu, va mot luat thu hai o day som
    muon se lech khoi no.
    """
    definition = get_definition(approval_code)
    name = (name or "").strip()
    if not name:
        return {"fields": [], "labels": {}, "at": None}
    if not frappe.has_permission(definition.business_doctype, doc=name, ptype="read"):
        raise frappe.PermissionError

    row = frappe.db.get_value(
        svc.LOG_DOCTYPE,
        {"business_doc": name, "approval_code": definition.code},
        ["name", "fields_offered", "handed_off_at"], as_dict=True, order_by="creation desc")
    if not row:
        return {"fields": [], "labels": {}, "at": None}
    try:
        offered = frappe.parse_json(row.get("fields_offered") or "{}") or {}
    except Exception:
        offered = {}
    if not isinstance(offered, dict):
        return {"fields": [], "labels": {}, "at": None}

    meta = frappe.get_meta(definition.business_doctype)
    fields, labels = [], {}
    for fieldname in offered.keys():
        df = meta.get_field(fieldname)
        if df is None:
            continue
        fields.append(fieldname)
        labels[fieldname] = _(df.label or fieldname)
    return {"fields": fields, "labels": labels, "at": row.get("handed_off_at")}
