# Copyright (c) 2026, eCentric and contributors
"""AI dien ho mot bieu mau Approval Center - SCHEMA, CONG LOC, PROBE, TRAN GOI.

Module nay KHONG biet form nao ca. No nhan mot `ApprovalDefinition` va lam viec bang
`editable_fields` + Frappe meta. Them mot form thu 29 khong phai sua file nay.

BA THU module nay bao dam, va khong thu nao trong so do la "goi Gemini":

  1. SCHEMA tu sinh (`build_schema`) - AI chi biet nhung truong ma form that su cho ghi.
  2. CONG LOC per-field (`gate`) - truong nao AI bia / sai option / khong co ban ghi thi
     BO HAN. Khong cat bot, khong sua cho vua. Moi lan bo deu co ma ly do de giai doan 3
     do duoc.
  3. PROBE (`probe`) - chay validator THAT cua form trong mot savepoint roi ROLLBACK.

VI SAO PROBE PHAI ROLLBACK. `validate_payment` GHI DATABASE: no goi `chot_brand_ngoai`, ham
nay `insert()` mot ban ghi `Brand`. Chay validator len du lieu chua duoc nguoi xac nhan ma
khong rollback thi mot ten brand doc nham tu hop dong se thanh mot hang vinh vien trong danh
muc. Ket qua probe CHI de bao "ban nhap nay chua gui duoc: <ly do>", KHONG dung de bo truong
- validator nem loi o truong dau tien hong voi mot cau chung chung, no khong quy duoc trach
nhiem ve truong nao.

Cong loc chi bat duoc sai HINH DANG va sai KHONG TON TAI. No khong bat duoc dung hinh dang
nhung sai noi dung (so tien doc nham dong, payee la ben doi tac thay vi nguoi thu huong).
Do la ly do giai doan 3 phai do ti le sua tay TUNG TRUONG.
"""
import json

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

#: Kieu truong AI khong bao gio duoc dien.
#: `Check` nam trong day co chu dich: moi o tick tren cac form nay deu la mot KHANG DINH cua
#: nguoi dung ("toi xac nhan...", "brand chua co trong danh muc"), khong phai du kien doc
#: duoc tu ho so. Mot luat re, khong can cau hinh tung form.
AI_SKIP_FIELDTYPES = frozenset((
    "Attach", "Attach Image", "Table", "Table MultiSelect", "Signature", "Password",
    "Button", "Section Break", "Column Break", "Tab Break", "HTML", "Heading",
    "Read Only", "Image", "Geolocation", "Code", "Barcode", "Check", "Fold",
    "Color", "Duration", "Rating", "Icon", "Attach Image", "Dynamic Link",
))

#: Danh muc Link qua nguong nay thi KHONG gui ung vien cho AI - prompt se phinh ra ma khong
#: giup gi. Bo ung vien khong lam mat an toan: phep kiem ton tai o `gate` van chay.
CANDIDATE_CAP = 200

#: Tran de phong, khong phai han ngach. Mot vong lap loi ben client goi duoc vai tram luot
#: truoc khi ai kip thay - su co quota 429 ngay 20/07 bat dau dung nhu vay.
DEFAULT_DAILY_CAP = 50
#: Do dai toi da cua doan text nguoi dung dan vao.
MAX_NOTE_CHARS = 8000

LOG_DOCTYPE = "EC AI Formfill Log"


# ---------------------------------------------------------------- cong tac ---

def _disabled_flag(value):
    """PURE. `bool("0")` la True trong Python - mot site_config ghi "0" ma doc bang bool()
    thi thanh TAT. Copy dung ngu nghia cua `alerts.api_omisell.parse_disabled_flag`; khong
    import cheo module (ADR-001: ranh gioi module di qua API khai bao, khong reach-through).
    """
    if value is True:
        return True
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)):
        return value == 1
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def is_disabled():
    return _disabled_flag(frappe.conf.get("ec_ai_formfill_disabled"))


def daily_cap():
    try:
        return max(1, int(frappe.conf.get("ec_ai_formfill_daily_cap") or DEFAULT_DAILY_CAP))
    except (TypeError, ValueError):
        return DEFAULT_DAILY_CAP


def used_today(user=None):
    """Dem HANG trong bang log, khong dung bo dem trong cache.

    Hang song sot qua restart, tra duoc, va dung la bang ma giai doan 3 se do. Mot counter
    trong Redis thi flush mot cai la mat va khong ai doi chieu duoc.
    """
    user = user or frappe.session.user
    if not frappe.db.exists("DocType", LOG_DOCTYPE):
        return 0
    return frappe.db.count(LOG_DOCTYPE, {
        "request_user": user,
        "creation": [">=", "%s 00:00:00" % nowdate()],
        "outcome": ["in", ("ok", "error")],
    })


# ------------------------------------------------------------------ schema ---

def _candidates(link_doctype):
    """Ung vien cho mot truong Link, da kiem quyen doc cua nguoi dang goi.

    Tra None khi danh muc qua lon hoac khong doc duoc - AI van doan duoc va `gate` van bat
    duoc, vi phep kiem ton tai khong phu thuoc vao viec co gui ung vien hay khong. Danh sach
    ung vien la de TANG DO CHINH XAC, khong phai de bao dam dung.
    """
    if not link_doctype:
        return None
    try:
        rows = frappe.get_all(link_doctype, pluck="name", limit_page_length=CANDIDATE_CAP + 1,
                              order_by="modified desc")
    except Exception:
        return None
    if not rows or len(rows) > CANDIDATE_CAP:
        return None
    return sorted(rows)


def build_schema(definition):
    """Hop dong cua mot form voi AI, sinh tu `editable_fields` + Frappe meta.

    PHAI di qua `frappe.get_meta()`, KHONG duoc doc DocType JSON trong repo: 7 truong cua
    payment_request (`ec_loai_chi_phi`, `ec_brand`, `ec_ky_chi_phi`, `ec_vat_pct`...) la
    Custom Field, khong nam trong `ec_payment_request.json`. Meta gop Custom Field vao; file
    JSON thi khong.
    """
    meta = frappe.get_meta(definition.business_doctype)
    blocked = set(definition.clone_exclude_fields or ()) | set(
        getattr(definition, "ai_exclude_fields", ()) or ())
    schema = []
    for fieldname in definition.editable_fields:
        if fieldname in blocked:
            continue
        df = meta.get_field(fieldname)
        if df is None or df.fieldtype in AI_SKIP_FIELDTYPES:
            continue
        item = {
            "fieldname": fieldname,
            "label": df.label or fieldname,
            "fieldtype": df.fieldtype,
            "reqd": bool(df.reqd),
            "hint": (df.description or "")[:300],
        }
        if df.fieldtype == "Select":
            item["options"] = [o.strip() for o in (df.options or "").split("\n") if o.strip()]
        elif df.fieldtype == "Link":
            item["link_doctype"] = df.options
            item["options"] = _candidates(df.options)
        elif df.fieldtype in ("Data", "Small Text"):
            item["maxlength"] = int(df.length or 0) or 140
        schema.append(item)
    return tuple(schema)


# -------------------------------------------------------------- cong loc ---

_DATE_WINDOW_DAYS = 366


def _check(spec, value):
    """-> (ok, gia_tri_sach, ma_ly_do). Bo HAN khi truot; khong cat bot, khong sua cho vua."""
    fieldtype = spec["fieldtype"]

    if value is None:
        return False, None, "rong"

    if fieldtype == "Select":
        # `ec_vat_pct` co options la "0"/"8"/"10" - chuoi TRONG NHU so. Model tra ve 10 (so)
        # thay vi "10" (chuoi) ma khong ep str() thi roi thang vao `sai_option` va truong VAT
        # khong bao gio len duoc form, lang le.
        text = str(value).strip()
        return (True, text, None) if text in (spec.get("options") or []) else (False, None, "sai_option")

    if fieldtype == "Link":
        name = str(value).strip()
        if not name:
            return False, None, "rong"
        dt = spec.get("link_doctype")
        if not dt or not frappe.db.exists(dt, name):
            return False, None, "khong_co_ban_ghi"
        if not frappe.has_permission(dt, "read", doc=name):
            return False, None, "khong_co_quyen"
        return True, name, None

    if fieldtype in ("Date", "Datetime"):
        try:
            parsed = getdate(value)
        except Exception:
            return False, None, "ngay_khong_hop_le"
        today = getdate(nowdate())
        if abs((parsed - today).days) > _DATE_WINDOW_DAYS:
            return False, None, "ngay_ngoai_khoang"
        return True, str(parsed), None

    if fieldtype in ("Currency", "Float", "Int", "Percent"):
        try:
            number = float(str(value).replace(",", "").replace(" ", ""))
        except (TypeError, ValueError):
            return False, None, "khong_phai_so"
        if number != number or number in (float("inf"), float("-inf")):
            return False, None, "khong_phai_so"
        if number <= 0:
            return False, None, "so_khong_duong"
        return True, (int(number) if fieldtype == "Int" else number), None

    text = str(value).strip()
    if not text:
        return False, None, "rong"
    limit = spec.get("maxlength")
    if limit and len(text) > limit:
        # Cat cut mot so tai khoan trong im lang te hon mot o de trong.
        return False, None, "qua_dai"
    return True, text, None


def gate(schema, raw):
    """-> (accepted: dict, dropped: list[dict]). Day la cho "AI bia thi bo" duoc THI HANH."""
    by_name = {item["fieldname"]: item for item in schema}
    accepted, dropped = {}, []
    for key, value in (raw or {}).items():
        spec = by_name.get(key)
        if spec is None:
            dropped.append({"field": key, "reason": "khong_trong_schema"})
            continue
        ok, cleaned, reason = _check(spec, value)
        if ok:
            accepted[key] = cleaned
        else:
            dropped.append({"field": key, "reason": reason})
    return accepted, dropped


# --------------------------------------------------------------- probe ---

PROBE_SAVEPOINT = "ec_ai_formfill_probe"


def probe(definition, merged):
    """Chay validator THAT cua form roi rollback. -> {"ok": bool, "message": str|None}.

    Khong bao gio dung de bo truong (xem docstring dau file). Form nao khong khai validator
    thi bao khong chay duoc thay vi im lang tra ve "dat".
    """
    validator = getattr(definition.submitter, "validator", None)
    if not callable(validator):
        return {"ok": None, "message": None, "skipped": "khong_co_validator"}
    frappe.db.savepoint(PROBE_SAVEPOINT)
    try:
        doc = frappe.new_doc(definition.business_doctype)
        doc.update({k: v for k, v in (merged or {}).items() if doc.meta.has_field(k)})
        doc.requested_by = frappe.session.user
        validator(doc)
        return {"ok": True, "message": None}
    except frappe.ValidationError as exc:
        return {"ok": False, "message": str(exc)[:400]}
    except Exception as exc:
        return {"ok": False, "message": ("%s: %s" % (type(exc).__name__, exc))[:400]}
    finally:
        # ROLLBACK VO DIEU KIEN. `chot_brand_ngoai` co the da insert mot Brand truoc khi
        # validator nem loi; `finally` la cho duy nhat bat duoc ca hai duong.
        frappe.db.rollback(save_point=PROBE_SAVEPOINT)


# ----------------------------------------------------------------- log ---

def write_log(**kw):
    """Ghi mot dong cho MOI luot goi. Vua la han muc (xem `used_today`), vua la du lieu do
    cua giai doan 3. Ghi hong thi KHONG lam hong luot goi - log la best-effort."""
    if not frappe.db.exists("DocType", LOG_DOCTYPE):
        return None
    try:
        doc = frappe.new_doc(LOG_DOCTYPE)
        doc.update({
            "approval_code": kw.get("approval_code"),
            "request_user": kw.get("user") or frappe.session.user,
            "input_chars": int(kw.get("input_chars") or 0),
            "latency_ms": int(kw.get("latency_ms") or 0),
            "model": kw.get("model"),
            "outcome": kw.get("outcome") or "ok",
            # Luu GIA TRI, khong chi ten truong: khong co gia tri thi giai doan 3 khong phan
            # biet duoc "nguoi dung sua vi AI sai" voi "nguoi dung go them cho day du".
            "fields_offered": json.dumps(kw.get("fields_offered") or {}, ensure_ascii=False),
            "fields_dropped": json.dumps(kw.get("fields_dropped") or [], ensure_ascii=False),
            "probe_passed": 1 if kw.get("probe_passed") else 0,
            "probe_message": (kw.get("probe_message") or "")[:500],
            "error": (kw.get("error") or "")[:500],
        })
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), "EC AI Formfill: khong ghi duoc log")
        return None
