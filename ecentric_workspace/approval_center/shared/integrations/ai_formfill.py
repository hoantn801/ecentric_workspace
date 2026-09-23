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

#: Tran ban nhap cua tab "Tao hang loat".
#:
#: DEM QUYET DINH CUA NGUOI DUYET, khong dem cong suat may. 10 phieu trong mot lo la 10
#: lan mot nguoi khac phai doc va chiu trach nhiem; con so nay la mot phat bieu ve gioi
#: han cua su chu y, nen no khong duoc phep noi ra chi vi server chay kip.
#:
#: KHAC HAN `ai_attachments.MAX_FILES = 5`: cai kia dem TEP CUA MOT quyet dinh (mot hop
#: dong co the co 3 phu luc), cai nay dem SO QUYET DINH. Lan lon hai con so nay la lan lon
#: hai thu khac nhau ve ban chat - da ghi o DESIGN §3.3.
MAX_BATCH_DRAFTS = 10

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
    hints = dict(getattr(definition, "ai_hints", None) or {})
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
            # Chi dan rieng cho AI dung TRUOC mo ta hien tren man hinh: no la thu cu the
            # hon, va khi hai cai mau thuan thi cai viet rieng cho AI phai thang.
            "hint": "; ".join(x for x in (hints.get(fieldname), (df.description or "")) if x)[:400],
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


# Model tra ve CHU "none"/"null" thay vi null JSON - do 23/09/2026 tren Kie gemini-3-8-flash
# (Google 2.5 Flash cung de bai thi tra null dung chuan). Khong chan o day thi truong chu nhan
# nguyen chu "none" vao form: ten nguoi nhan "none", ngan hang "null". Chi so khop CA CHUOI -
# "Nonestop Co" hay "null tru" van la gia tri that.
_NULL_WORDS = frozenset(("none", "null", "nil", "n/a", "undefined", "-", "\u2014"))


def _is_null_word(value):
    return isinstance(value, str) and value.strip().lower() in _NULL_WORDS


def _check(spec, value):
    """-> (ok, gia_tri_sach, ma_ly_do). Bo HAN khi truot; khong cat bot, khong sua cho vua."""
    fieldtype = spec["fieldtype"]

    if value is None or _is_null_word(value):
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
    # `frappe.throw` khong chi NEM - no con XEP MOT DONG vao `message_log`, va Frappe goi
    # nguyen dong do ve client trong `_server_messages` roi TU VE MOT MODAL. Nen probe bat
    # duoc exception van chua du: nguoi dung thay hop thoai "Vui long nhap day du cac truong
    # bat buoc" bat len ngay sau khi AI dien, y het nhu phieu vua bi tu choi gui.
    # Chup lai roi tra nguyen trang thai cu - KHONG xoa trang, vi cho nay co the da co
    # thong diep cua nguoi khac dat truoc.
    dong_cu = list(getattr(frappe.local, "message_log", None) or [])
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
        try:
            frappe.local.message_log = dong_cu
        except Exception:
            pass


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
            "files_count": int(kw.get("files_count") or 0),
            "files_note": (kw.get("files_note") or "")[:500],
        })
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), "EC AI Formfill: khong ghi duoc log")
        return None


# ------------------------------------------------- prompt + responseSchema ---

_JSON_TYPE = {
    "Currency": "number", "Float": "number", "Percent": "number", "Int": "integer",
}

#: Truong duoc kem trich dan nguon. Hai o dat nhat khi sai - so tien va so tai khoan di qua
#: 5 cap ky roi thanh mot lenh chuyen tien - va la dung loai sai ma cong loc KHONG do duoc
#: (dung hinh dang, sai noi dung). Hien doan van ban goc canh o bien viec xem lai tu PHAN
#: DOAN thanh DOI CHIEU HAI CHUOI.
QUOTE_FIELDTYPES = frozenset(("Currency",))
QUOTE_FIELDNAMES = frozenset(("bank_account_number", "payment_amount"))


def wants_quote(spec):
    return spec["fieldname"] in QUOTE_FIELDNAMES or spec["fieldtype"] in QUOTE_FIELDTYPES


def response_schema(schema):
    """Doi schema cua form thanh `responseSchema` cua Gemini.

    MOI truong deu la `string` tru so - ke ca `Select` co options "0"/"8"/"10". Khai chung
    la number thi model tra ve 10 va nhanh Select o `gate` (so khop chuoi chinh xac) se bo
    truong do trong im lang. `gate` da ep `str()` de phong, day la lop thu hai.
    """
    props = {}
    for spec in schema:
        node = {"type": _JSON_TYPE.get(spec["fieldtype"], "string"),
                "description": (spec["label"] + (" - " + spec["hint"] if spec["hint"] else ""))[:300],
                "nullable": True}
        if spec["fieldtype"] == "Select" and spec.get("options"):
            node["type"] = "string"
            node["enum"] = list(spec["options"])
        props[spec["fieldname"]] = node
        if wants_quote(spec):
            props[spec["fieldname"] + "__source"] = {
                "type": "string", "nullable": True,
                "description": "Doan van ban goc (toi da 160 ky tu) chua gia tri cua "
                               + spec["label"] + ". Chep nguyen van, khong dien giai.",
            }
    return {"type": "object", "properties": props}


SYSTEM_INSTRUCTION = (
    "Ban doc mot doan van ban tieng Viet (hop dong, email, mo ta khoan chi) va dien vao mot "
    "bieu mau noi bo.\n"
    "LUAT CUNG:\n"
    "1. KHONG CHAC THI DE TRONG (null). Mot o trong re hon mot o sai trong nhu dung - nguoi "
    "dung se phai tu tim so, con mot o da dien thi ho chi gat dau.\n"
    "2. Chi dien nhung truong co trong schema. Khong bia them truong.\n"
    "3. Truong Select chi duoc nhan DUNG mot gia tri trong danh sach cho phep.\n"
    "4. Voi truong co khoa `<ten>__source`, chep NGUYEN VAN doan van ban ma ban lay gia tri "
    "ra, khong dien giai, khong tom tat.\n"
    "5. Khong suy dien ngay thang tu ngu canh mo ho. Van ban khong noi ro thi de trong.\n"
    "6. Neu co tep dinh kem, doc NOI DUNG tep. Tep va van ban mau thuan nhau thi de TRONG o "
    "do va ghi mau thuan vao `<ten>__source` - dung tu chon mot ben, nguoi dung moi la nguoi "
    "biet ben nao dung."
)


def build_prompt(schema, note, current=None, attach_block=""):
    """Prompt: hop dong truong + nhung gi nguoi dung DA go + van ban nguon + ten cac tep.

    `attach_block` chi la DANH SACH TEN tep (tu `ai_attachments.prompt_block`); noi dung
    tep di rieng bang phan `fileData` cua request, khong nhet vao day.
    """
    lines = ["CAC TRUONG CAN DIEN:"]
    for spec in schema:
        bit = "- %s (%s)" % (spec["fieldname"], spec["label"])
        if spec.get("options"):
            bit += " | chi nhan: " + " / ".join(str(o) for o in spec["options"][:40])
            if len(spec["options"]) > 40:
                bit += " / ..."
        if spec["hint"]:
            bit += " | " + spec["hint"]
        lines.append(bit)
    filled = {k: v for k, v in (current or {}).items() if v not in (None, "", [])}
    if filled:
        lines.append("\nNGUOI DUNG DA TU DIEN (DE NGUYEN, dung ghi de):")
        for k, v in sorted(filled.items()):
            lines.append("- %s = %s" % (k, v))
    if attach_block:
        lines.append(attach_block)
    lines.append("\nVAN BAN NGUON:\n" + (note or "(khong co - doc tu tep dinh kem)"))
    return "\n".join(lines)


def split_sources(raw):
    """Tach `<ten>__source` ra khoi gia tri truong. -> (values, sources).

    Trich dan khong di qua `gate` (no khong phai gia tri cua truong nao), nhung cung khong
    duoc vao thang form: no chi la chu de nguoi dung doi chieu.
    """
    values, sources = {}, {}
    for key, value in (raw or {}).items():
        if key.endswith("__source"):
            if value and not _is_null_word(value):
                sources[key[:-8]] = str(value)[:200]
        else:
            values[key] = value
    return values, sources


def _squash(text):
    return " ".join(str(text or "").lower().split())


def verify_sources(schema, values, sources, note, has_files):
    """Truong BAT BUOC trich dan (so tai khoan, so tien) phai co trich dan NAM TRONG van ban.

    -> (values_giu_lai, dropped). Do 23/09/2026: Kie gemini-3-8-flash nhan mot ghi chu KHONG he
    co so tai khoan van tra ve `bank_account_number = "19034567890123"` KEM trich dan bia
    "STK: 19034567890123 tai Techcombank". Trich dan bia qua duoc `gate` (gate khong biet van
    ban nguon) - day la cho duy nhat doi chieu duoc.

    Co tep dinh kem thi BO QUA: noi dung tep khong co o day duoi dang chu, doi chieu voi rieng
    ghi chu se bo nham gia tri doc dung tu tep.
    """
    if has_files:
        return dict(values or {}), []
    haystack = _squash(note)
    kept, dropped = dict(values or {}), []
    for spec in schema:
        name = spec["fieldname"]
        if not wants_quote(spec) or name not in kept:
            continue
        value = kept[name]
        if value is None or _is_null_word(value) or str(value).strip() == "":
            continue
        src = _squash(sources.get(name))
        if not src or src not in haystack:
            kept.pop(name)
            dropped.append({"field": name, "reason": "trich_dan_khong_co_trong_van_ban"})
    return kept, dropped
