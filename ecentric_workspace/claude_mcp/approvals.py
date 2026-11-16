# Copyright (c) 2026, eCentric and contributors
"""Lên NHÁP phiếu Approval Center cho MỌI form người dùng được tạo + gắn tệp + đặt ô ký số.

Luồng Claude làm (vd 10 hợp đồng cần đề nghị thanh toán):
    list_forms -> get_form(PAYMENT_REQUEST)                 ô nào, bắt buộc gì, ô nào người lập tự làm
    list_my_uploads / read_file                            đọc từng hợp đồng (link /claude_tep)
    create_draft_request(code, fields, files)  x10         -> mã phiếu + ô còn thiếu
    (hỏi người dùng ô thiếu) -> update_draft_request
    get_signing_setup / place_signature                    form có ký số: ô ký đặt sẵn
    -> người dùng mở link, xem lại, tự bấm Gửi.

KHÔNG BAO GIỜ GỬI PHIẾU. Không có công cụ submit; người lập tự bấm Gửi trên web.

Dùng lại nguyên các luật của "AI điền hộ" (approval_center/api/ai_formfill.py), không viết luật thứ hai:
  * _require_form_open: thẻ form Active + người này thấy được (vai trò / phòng ban).
  * build_schema + gate: chỉ ô trong editable_fields, trừ clone_exclude_fields + ai_exclude_fields
    (vd "Chi phí hợp lệ?", ô tích cam kết, nguồn chứng từ, chia đợt): đó là cam kết/quyết định của
    người lập, máy KHÔNG điền thay. Claude báo lại để người dùng tự chọn trên form.
  * _o_bat_buoc_may_tu_dien: Select bắt buộc mà new_doc tự lấp lựa chọn đầu -> xoá về rỗng.
  * command_service.save_draft: đúng hàm nút "Lưu nháp" gọi (employee/department/company, tiêu đề,
    gắn tệp qua `_attachments`).
"""
import frappe

from ecentric_workspace.claude_mcp import files as F
from ecentric_workspace.claude_mcp.protocol import ToolError


def _ai():
    from ecentric_workspace.approval_center.api import ai_formfill as api
    from ecentric_workspace.approval_center.shared.integrations import ai_formfill as svc
    return api, svc


def _definition(code):
    from ecentric_workspace.approval_center.shared.registry import get_definition
    try:
        return get_definition(str(code or "").strip())
    except KeyError:
        raise ToolError("Không có form mã '%s'. Gọi list_forms để xem mã đúng." % code) from None


def _definition_by_doctype(doctype):
    from ecentric_workspace.approval_center.shared.registry import get_definition_for_doctype
    try:
        return get_definition_for_doctype(doctype)
    except KeyError:
        raise ToolError("Loại phiếu %s không làm qua Claude được." % doctype) from None


def _link(definition, name):
    from frappe.utils import get_url
    from ecentric_workspace.action_center.resolvers import build_approval_url
    return get_url(build_approval_url(definition.business_doctype, name))


def _ref(definition, name):
    return "%s/%s" % (definition.business_doctype, name)


def _split_ref(reference):
    if not reference or "/" not in str(reference):
        raise ToolError("reference phải có dạng '<DocType>/<mã phiếu>' (create_draft_request trả về).")
    doctype, name = str(reference).split("/", 1)
    return _definition_by_doctype(doctype), name


# ------------------------------------------------------------------ đọc form
def list_forms():
    from ecentric_workspace.approval_center.shared import catalog_api
    from ecentric_workspace.approval_center.shared.registry import get_definition
    out = []
    for t in catalog_api.list_catalog().get("types") or []:
        code = t.get("approval_code")
        if t.get("card_status") != "Active" or not t.get("route") or not code:
            continue
        try:
            get_definition(code)
            supported = True
        except KeyError:
            supported = False   # form cũ (MSO/SO/PO...) chưa qua engine chung
        out.append({k: v for k, v in {
            "code": code, "name": t.get("approval_title") or t.get("title") or code,
            "group": t.get("category_name"), "description": (t.get("description") or "")[:200] or None,
            "claude_can_draft": supported,
        }.items() if v not in (None, "")})
    return {"forms": out, "note": "Chỉ các form bạn được tạo. claude_can_draft=false: làm trực tiếp trên web."}


def get_form(code):
    api, svc = _ai()
    definition = _definition(code)
    api._require_form_open(definition.code)
    meta = frappe.get_meta(definition.business_doctype)
    schema = svc.build_schema(definition)
    fields = []
    for s in schema:
        f = {"field": s["fieldname"], "label": s["label"], "type": s["fieldtype"], "required": s["reqd"]}
        if s.get("hint"):
            f["hint"] = s["hint"]
        if s.get("options"):
            f["options"] = list(s["options"])[:60]
        if s.get("link_doctype"):
            f["link_to"] = s["link_doctype"]
        if s.get("maxlength"):
            f["max_length"] = s["maxlength"]
        fields.append(f)
    blocked = set(definition.clone_exclude_fields or ()) | set(getattr(definition, "ai_exclude_fields", ()) or ())
    user_only = []
    for fn in definition.editable_fields:
        df = meta.get_field(fn)
        if df is not None and fn in blocked and fn not in ("department", "company"):
            user_only.append({"field": fn, "label": df.label or fn, "required": bool(df.reqd)})
    attach = [{"field": fn, "label": meta.get_field(fn).label or fn, "required": bool(meta.get_field(fn).reqd)}
              for fn in definition.editable_fields
              if meta.get_field(fn) is not None and meta.get_field(fn).fieldtype in ("Attach", "Attach Image")]
    esign = bool(getattr(definition.submitter, "requester_esign", False))
    return {
        "code": definition.code,
        "fields": fields,
        "attachment_fields": attach,
        "user_must_fill_on_web": user_only,
        "digital_signature": esign,
        "notes": [
            "Chỉ điền các ô trong `fields`. Ô trong `user_must_fill_on_web` là cam kết/quyết định của người lập: "
            "Claude KHÔNG điền, hãy nhắc người dùng tự chọn trên form trước khi bấm Gửi.",
            "Ô Link chỉ nhận giá trị có trong `options` (khi có danh sách).",
            "Ngày dạng YYYY-MM-DD, số tiền là số (không dấu chấm phân cách).",
        ] + (["Form có ký số: sau khi tạo nháp dùng get_signing_setup + place_signature để đặt ô ký."]
             if esign else []),
    }


# ------------------------------------------------------------------ tạo / sửa nháp
def _clean(definition, raw):
    api, svc = _ai()
    if not isinstance(raw, dict):
        raise ToolError("fields phải là object {tên_ô: giá_trị}.")
    schema = svc.build_schema(definition)
    accepted, dropped = svc.gate(schema, raw)
    blocked = set(definition.clone_exclude_fields or ()) | set(getattr(definition, "ai_exclude_fields", ()) or ())
    accepted = {k: v for k, v in accepted.items()
                if k in (definition.editable_fields or ()) and k not in blocked}
    return accepted, dropped


_REASON_VI = {"khong_trong_schema": "ô này Claude không được điền (hoặc không có trên form)",
              "rong": "trống", "sai_option": "không nằm trong danh sách lựa chọn",
              "khong_co_ban_ghi": "không tìm thấy trong danh mục", "khong_co_quyen": "không có quyền chọn giá trị này",
              "ngay_khong_hop_le": "ngày không hợp lệ", "ngay_ngoai_khoang": "ngày lệch quá 1 năm so với hôm nay",
              "khong_phai_so": "không phải số", "so_khong_duong": "số phải lớn hơn 0", "qua_dai": "quá dài"}


def _dropped_vi(dropped):
    return [{"field": d["field"], "why": _REASON_VI.get(d["reason"], d["reason"])} for d in dropped]


def _attachments_payload(definition, file_refs):
    rows = [F.resolve_file(r) for r in (file_refs or [])]
    for r in rows:
        if r.get("owner") != frappe.session.user:
            raise ToolError("Chỉ gắn được tệp do chính bạn tải lên: %s" % r.get("file_name"))
        if r.get("attached_to_doctype") and r.get("attached_to_name") and \
                r["attached_to_doctype"] != definition.business_doctype:
            raise ToolError("Tệp %s đang gắn vào hồ sơ khác." % r.get("file_name"))
    return rows


def _attach_field(definition):
    meta = frappe.get_meta(definition.business_doctype)
    for fn in definition.editable_fields:
        df = meta.get_field(fn)
        if df is not None and df.fieldtype in ("Attach", "Attach Image"):
            return fn
    return None


def _result(definition, name, dropped, extra=None):
    api, _svc = _ai()
    missing = api._con_thieu(definition, name)
    meta = frappe.get_meta(definition.business_doctype)
    blocked = set(definition.clone_exclude_fields or ()) | set(getattr(definition, "ai_exclude_fields", ()) or ())
    user_part = [m for m in missing if m["fieldname"] in blocked]
    claude_part = [m for m in missing if m["fieldname"] not in blocked]
    files = frappe.get_all("File", filters={"attached_to_doctype": definition.business_doctype,
                                            "attached_to_name": name},
                           fields=["name", "file_name"], order_by="creation asc")
    out = {"ok": True, "reference": _ref(definition, name), "name": name,
           "title": frappe.db.get_value(definition.business_doctype, name, "request_title")
           if meta.has_field("request_title") else None,
           "status": "Nháp (chưa gửi)",
           "missing_ask_user": [{"field": m["fieldname"], "label": m["label"]} for m in claude_part],
           "missing_user_fills_on_web": [{"field": m["fieldname"], "label": m["label"]} for m in user_part],
           "not_filled": _dropped_vi(dropped) or None,
           "attachments": [f.get("file_name") for f in files],
           "link": _link(definition, name),
           "next": ("Hỏi người dùng các ô missing_ask_user rồi gọi update_draft_request. "
                    if claude_part else "") +
                   ("Nhắc người dùng tự chọn các ô missing_user_fills_on_web trên form. " if user_part else "") +
                   "Người dùng mở link, kiểm tra và tự bấm Gửi."}
    out.update(extra or {})
    return {k: v for k, v in out.items() if v not in (None, [])}


def create_draft_request(code, fields=None, files=None):
    api, _svc = _ai()
    definition = _definition(code)
    api._require_form_open(definition.code)
    accepted, dropped = _clean(definition, fields or {})
    rows = _attachments_payload(definition, files)
    payload = dict(accepted)
    if rows:
        payload["_attachments"] = [{"url": r["file_url"], "name": r.get("file_name")} for r in rows]
        af = _attach_field(definition)
        if af and not payload.get(af):
            payload[af] = rows[0]["file_url"]
    from ecentric_workspace.approval_center.shared.requests import command_service
    res = command_service.save_draft(definition, name=None, payload=payload)
    name = res.get("name")
    # Select bắt buộc mà máy vừa tự lấp (lựa chọn đầu tiên) -> trả về "chưa trả lời" (xem ai_formfill)
    for fn in api._o_bat_buoc_may_tu_dien(definition):
        if fn not in accepted:
            frappe.db.set_value(definition.business_doctype, name, fn, "", update_modified=False)
    return _result(definition, name, dropped)


def update_draft_request(reference, fields=None, files=None):
    definition, name = _split_ref(reference)
    api, _svc = _ai()
    api._require_form_open(definition.code)
    accepted, dropped = _clean(definition, fields or {})
    rows = _attachments_payload(definition, files)
    payload = dict(accepted)
    if rows:
        payload["_attachments"] = [{"url": r["file_url"], "name": r.get("file_name")} for r in rows]
        af = _attach_field(definition)
        if af and not frappe.db.get_value(definition.business_doctype, name, af):
            payload[af] = rows[0]["file_url"]
    if not payload:
        raise ToolError("Không có gì để cập nhật. " + "; ".join(
            "%s: %s" % (d["field"], d["why"]) for d in _dropped_vi(dropped)))
    from ecentric_workspace.approval_center.shared.requests import command_service
    command_service.save_draft(definition, name=name, payload=payload)   # tự chặn phiếu đã gửi / của người khác
    return _result(definition, name, dropped)


# ------------------------------------------------------------------ ký số
def _doc_file(definition, name, ref):
    """Tệp ĐANG GẮN vào phiếu ứng với `ref` (mã File gắn phiếu, mã tệp vừa tải lên, file_url hoặc tên tệp).

    Lưu nháp có thể gắn tệp bằng một dòng File MỚI (attach_extra_files) thay vì dòng tệp mồ côi
    người dùng tải lên, nên so theo file_url / tên tệp chứ không chỉ theo mã."""
    rows = frappe.get_all("File", filters={"attached_to_doctype": definition.business_doctype,
                                           "attached_to_name": name},
                          fields=["name", "file_name", "file_url", "owner", "attached_to_doctype",
                                  "attached_to_name"], order_by="creation asc")
    ref = str(ref or "").strip()
    url = None
    if ref and not any(r["name"] == ref for r in rows):
        try:
            url = F.resolve_file(ref).get("file_url")
        except ToolError:
            url = None
    for r in rows:
        if ref in (r["name"], r.get("file_url"), r.get("file_name")) or (url and r.get("file_url") == url):
            return r
    raise ToolError("Tệp '%s' chưa gắn vào phiếu %s. Gắn bằng update_draft_request(files=[...]) trước." % (ref, name))


def get_signing_setup(reference):
    from ecentric_workspace.platform.esign import document_setup as ds
    from ecentric_workspace.platform.esign import placement_service as ps
    definition, name = _split_ref(reference)
    bd = definition.business_doctype
    st = ds.get_document_setup_state(bd, name)
    plan = st.get("signer_plan") or {}
    if not plan.get("resolved"):
        return {"reference": reference, "digital_signature": False,
                "note": "Phiếu này không cần ký số (hoặc chưa cấu hình ký số cho loại phiếu này).",
                "reason": plan.get("reason")}
    docs = []
    slots = None
    for d in st.get("documents") or []:
        item = {"file": d["document_ref"], "file_name": d.get("display_name"),
                "requires_signature": d.get("requires_signature"),
                "is_pdf": d.get("direct_signing_supported"),
                "signers_placed": "%s/%s" % (d.get("covered_slot_count") or 0, d.get("required_signer_slots") or 0)}
        if d.get("requires_signature") and d.get("direct_signing_supported"):
            pst = ps.placement_state(bd, name, d["document_ref"])
            if slots is None:
                slots = [{"slot_key": s["slot_key"], "signer": s["label"], "kind": s.get("kind"),
                          "people": [c.get("full_name") or c.get("user") for c in s.get("candidates") or []][:5]}
                         for s in pst.get("required_slots") or []]
            item["placed"] = [{"slot_key": p["signer_slot_key"], "page": p["page_index"]}
                              for p in pst.get("placements") or []]
            try:
                row = _doc_file(definition, name, d["document_ref"])
                item["anchors"] = [{"page": a["page"], "text": a["text"]}
                                   for a in F.signature_anchors(F.file_bytes(row))]
            except Exception:
                item["anchors"] = []
        docs.append(item)
    try:
        from ecentric_workspace.platform.esign import requester
        ready = requester.requester_signing_readiness(bd, name) or {}
        checks = ready.get("checks") or {}
        account = {"requester_must_sign": checks.get("requester_signature_required"),
                   "checks": {k: v for k, v in checks.items() if k not in ("not_submitted", "is_owner")}}
    except Exception:
        account = None
    return {"reference": reference, "digital_signature": True, "editable": st.get("editable"),
            "signers": slots or [], "documents": docs, "my_signing_account": account,
            "how_to": ("Mỗi tệp cần ký phải có đủ ô cho mọi signer. Đọc tệp (read_file) để biết bên nào là eCentric, "
                       "rồi place_signature(file, slot_key, anchor_text=<một dòng trong anchors>). Không chắc thì "
                       "đừng đặt, báo người dùng tự kéo ô trên web. Tệp chỉ là chứng từ kèm theo (không ai ký) -> "
                       "set_requires_signature(false)."),
            "link": _link(definition, name)}


def place_signature(reference, file, slot_key, anchor_text=None, occurrence=1, page=None, x=None, y=None,
                    width=None, height=None):
    from ecentric_workspace.platform.esign import placement_service as ps
    from ecentric_workspace.claude_mcp.tools import fold
    definition, name = _split_ref(reference)
    row = _doc_file(definition, name, file)
    if anchor_text:
        want = fold(anchor_text)
        hits = [a for a in F.text_positions(F.file_bytes(row)) if want and want in fold(a["text"])]
        if page:
            hits = [a for a in hits if a["page"] == int(page)]
        n = max(1, int(occurrence or 1))
        if len(hits) < n:
            raise ToolError("Không thấy dòng '%s' trong tệp (lần thứ %s). Gọi get_signing_setup xem danh sách anchors."
                            % (anchor_text, n))
        box = F.box_under(hits[n - 1], width=float(width or 150), height=float(height or 60))
    elif page and x is not None and y is not None:
        box = {"page_index": int(page), "x": float(x), "y": float(y),
               "width": float(width or 150), "height": float(height or 60)}
    else:
        raise ToolError("Cần anchor_text, hoặc page + x + y (điểm, gốc trên-trái).")
    box["signer_slot_key"] = slot_key
    res = ps.save_placement(definition.business_doctype, name, row["name"], box)
    if not res.get("ok"):
        why = {"invalid_slot_key": "slot_key không đúng (lấy từ get_signing_setup.signers)",
               "not_pdf": "tệp không phải PDF, không đặt ô ký được",
               "supporting_document": "tệp đang là chứng từ kèm theo (không cần ký)",
               "stale_or_foreign_attachment": "tệp không gắn vào phiếu này"}.get(res.get("reason"), res.get("reason"))
        raise ToolError("Không đặt được ô ký: %s." % why)
    prog = (res.get("state") or {}).get("progress") or {}
    return {"ok": True, "reference": reference, "file": row.get("file_name"), "slot_key": slot_key,
            "page": box["page_index"], "box": {k: box[k] for k in ("x", "y", "width", "height")},
            "signers_placed": "%s/%s" % (prog.get("covered", 0), prog.get("required", 0)),
            "note": "Nhắc người dùng xem lại vị trí ô ký trên web trước khi Gửi."}


def set_requires_signature(reference, file, requires_signature):
    from ecentric_workspace.platform.esign import document_setup as ds
    definition, name = _split_ref(reference)
    row = _doc_file(definition, name, file)
    res = ds.set_document_requires_signature(definition.business_doctype, name, row["name"],
                                             bool(requires_signature), confirm=True) or {}
    if res.get("ok") is False:
        raise ToolError("Không đổi được: %s" % res.get("reason"))
    return {"ok": True, "file": row.get("file_name"), "requires_signature": bool(requires_signature)}
