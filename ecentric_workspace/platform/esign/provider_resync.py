# Copyright (c) 2026, eCentric and contributors
"""Dong bo lai ERP -> nha cung cap ky so khi tai lieu ben nha cung cap THIEU chu ky ERP da gui.

Vi sao (15/11/2026, chuyen SCTS -> CMC signx). CMC chep du lieu khoang trua thu 6 13/11; chieu
thu 6 ERP van ky tren SCTS. Ket qua: 25 chu ky / 17 phieu DNTT co trong ERP (nguoi duyet DA
duyet, ERP DA gui va xac minh tren SCTS) nhung CMC khong co; 3 tai lieu CMC khong co ca tai lieu.
Hoan chot 15/11: "nguoi duyet da duyet roi nen chung ta chi ban lai thoi".

"Ban lai" = gui lai DUNG lenh ERP da gui luc dau, cho tung chan ky DA HOAN TAT ma tai lieu ben
nha cung cap chua co: cung tai khoan (tich hop, hoac token rieng cua nguoi de nghi), cung chu ky
(effective_scts_user_id + effective_signature_id cua chan ky), dung buoc, dung nguoi nhan.

Chot an toan (moi cai deu DUNG lai, khong doan) - QC Opus 15/11 hai vong:
  * Chi ban lai chan ky ma ERP DA TUNG GUI (co su kien HandoverTargeted / ProviderAccepted cua
    chinh worker). Chan "nhan ve" tu cong (nguoi ky tay tren cong, vd Ky chinh bang
    OfficeSignTool) -> DUNG: ERP chua bao gio gui lenh do, khong duoc gui thay.
  * Buoc gui (transition id) va nguoi nhan phai KHOP lenh goc ghi trong su kien HandoverTargeted
    khi su kien co ghi.
  * KHONG BAO GIO gui ca nhom (pool / bulk-process). Chi `transition` co ten nguoi nhan.
  * Truoc MOI lan gui: doc lai tai lieu; cac chu ky dang co phai la cua dung cac chan ky ERP dau
    tien (danh tinh, theo thu tu); vi tri chan sap gui == so chu ky dang co == dong cau hinh
    theo vi tri; cong phai DANG MO dung canh do cho chinh nguoi ky.
  * Anh xa chu ky hien tai phai CON KHOP chu ky chan ky da dung; chu ky con hieu luc tren cong.
  * Goi dang co chan ky ERP dang bay (Queued / Provider Accepted / Verifying / ...) -> DUNG.
  * Lan ban lai truoc cho chan nay chua xac minh -> DUNG (lenh ky khong idempotent), tru khi
    nguoi truc xac nhan da xem cong (ack_prior_attempt=1).
  * Khoa theo goi suot ca lan chay (redis nx). Moi lan chay that chi MOT chan (gioi han thoi
    gian request web); gui xong phai thay DUNG MOT chu ky moi cua dung nguoi.
  * Chay thu la mac dinh. System Manager, bat buoc ly do (>= 10 ky tu).
  * KHONG dong vao trang thai duyet ERP. Moi lan gui / xac minh ghi su kien bat bien tren chan ky
    (ResendExecuted / PollTick, source=provider_resync).
"""
import time

import frappe
from frappe import _

from ecentric_workspace.platform.esign import events
from ecentric_workspace.platform.esign import next_handler
from ecentric_workspace.platform.esign import permissions as perms
from ecentric_workspace.platform.esign.providers import get_adapter
from ecentric_workspace.platform.esign.providers.base import ProviderError
from ecentric_workspace.platform.esign.sanitize import safe_error

DSR = "EC Digital Signature Request"
PKG = "EC Digital Signature Package"
LEVEL = "EC Approval Request Level"
APPROVER = "EC Approval Request Approver"
MAPPING = "EC SCTS User Mapping"
SETTINGS = "EC Digital Signature Provider Settings"
EVENT = "EC Digital Signature Event"

MIN_REASON = 10
#: Cho chu ky xuat hien sau khi gui (giay, cong don ~45s). Chu ky thuong len sau 2-40 giay.
VERIFY_WAITS = (2, 3, 4, 6, 8, 10, 12)
SOURCE = "provider_resync"
LOCK_SECONDS = 600
#: Chan ky ERP dang bay tren goi: worker cua no dem buoc tren cung tai lieu -> khong chen vao.
_LIVE = ("Draft", "Prepared", "Queued", "Provider Accepted", "Verifying", "Retryable Failure",
         "Signed", "Manual Review")
_DEAD_DOC = ("cancelled", "rejected")

_LEG_FIELDS = ["name", "actor_type", "actor_user", "approver", "action", "status",
               "effective_scts_user_id", "effective_signature_id", "request_level",
               "approval_request", "completed_at", "provider", "environment", "package",
               "creation"]


class _Stop(Exception):
    pass


# --------------------------------------------------------------------------- tien ich
def _settings(provider, environment):
    s = frappe.db.get_value(SETTINGS, {"provider": provider, "environment": environment}, "*",
                            as_dict=True)
    if not s:
        frappe.throw(_("Chưa có cấu hình nhà cung cấp cho {0}/{1}.").format(provider, environment))
    return s


def _package(business_doctype, business_name):
    name = frappe.db.get_value(PKG, {"business_doctype": business_doctype,
                                     "business_name": business_name,
                                     "status": ["not in", ("Cancelled", "Superseded", "Draft")]},
                               "name", order_by="creation desc")
    if not name:
        return None
    return frappe.db.get_value(PKG, name, ["name", "status", "profile", "provider", "environment",
                                           "scts_document_id", "approval_request",
                                           "business_doctype", "business_name"], as_dict=True)


def _completed_legs(pkg_name):
    """Chan ky DA HOAN TAT cua goi theo thu tu ky: cap (nguoi de nghi = 0) roi thoi diem."""
    rows = frappe.get_all(DSR, filters={"package": pkg_name, "status": "Approval Completed",
                                        "action": "Sign"},
                          fields=_LEG_FIELDS, order_by="completed_at asc, creation asc",
                          limit_page_length=50)
    for r in rows:
        r["level_no"] = (0 if r.get("actor_type") == "Requester"
                         else int(frappe.db.get_value(LEVEL, r.get("request_level"), "level_no")
                                  or 0))
    rows.sort(key=lambda r: (r["level_no"], str(r.get("completed_at") or "")))
    return rows


def _live_legs(pkg_name, replay_level=None):
    """Chan ky ERP chan viec ban lai tren goi nay.

    Chan dang bay (Queued / Provider Accepted / Verifying / ...) luon chan: worker cua no dem
    buoc tren cung tai lieu. Chan Manual Review KHONG co worker chay; no chi chan khi o CUNG
    cap hoac cap TRUOC chan dang ban lai (16/11: CEO bam Duyet & Ky ca 11 phieu chieu 15/11 khi
    CMC con thieu chu ky KTT -> 11 chan CEO o Manual Review; chan KTT phai ban lai duoc truoc,
    roi chan CEO moi gui lai qua "Gui lai co kiem")."""
    rows = frappe.get_all(DSR, filters={"package": pkg_name, "status": ["in", list(_LIVE)]},
                          fields=["name", "status", "actor_type", "request_level"],
                          limit_page_length=20)
    out = []
    for x in rows:
        if x.status == "Manual Review" and replay_level is not None:
            lvl = (0 if x.get("actor_type") == "Requester"
                   else int(frappe.db.get_value(LEVEL, x.get("request_level"), "level_no") or 0))
            if lvl > int(replay_level):
                continue
        out.append(x)
    return out


def _signed_rows(state):
    return [s for s in (getattr(state, "signers", None) or [])
            if str(s.get("status") or "").lower() == "signed"]


def _aliases(leg):
    from ecentric_workspace.platform.esign import service as svc
    e = svc._emails_cua_cung_danh_tinh(leg)
    return {str(x).strip().lower() for x in ([e] if isinstance(e, str) else (e or [])) if x}


def _emails(rows):
    return [str(s.get("email") or "").strip().lower() for s in rows]


def _prefix_ok(legs, signed_emails):
    """`signed_emails` (chu ky dang co) la cua DUNG len(signed) chan ERP dau tien - so khop theo
    TAP (moi chu ky dung cho mot chan); thu tu o tung o duoc chot rieng bang vi tri + canh mo
    tren cong. (ok, ly_do)"""
    pool = list(signed_emails)
    for leg in legs[:len(pool)]:
        hit = next((e for e in pool if e in _aliases(leg)), None)
        if hit is None:
            return False, "identity_mismatch:%s" % leg.get("name")
        pool.remove(hit)
    return True, None


def _leg_view(leg):
    return {"signature_request": leg.get("name"), "actor_type": leg.get("actor_type"),
            "level_no": leg.get("level_no"), "approver": leg.get("approver"),
            "completed_at": str(leg.get("completed_at") or "")}


def _require_reason(reason):
    if len((reason or "").strip()) < MIN_REASON:
        frappe.throw(_("Bắt buộc nêu lý do (tối thiểu {0} ký tự).").format(MIN_REASON))


def _user_token_adapter(leg, settings):
    """Adapter cho chan ky nay: token rieng cua nguoi de nghi khi ERP luc dau cung dung token do
    (tasks.process_signing_request), con lai tai khoan tich hop. (adapter, ly_do_dung)."""
    from ecentric_workspace.platform.esign import user_link
    adapter = get_adapter(settings)
    if leg.get("actor_type") == "Requester" and user_link.needs_own_token(leg.get("actor_user"),
                                                                           settings):
        tok = user_link.token_for(leg.get("actor_user"), leg.get("environment"))
        if not tok:
            return None, "requester_token_missing:%s" % leg.get("actor_user")
        adapter.use_user_token(tok)
    return adapter, None


def _lock(pkg_name):
    key = "esign:provider_resync:%s" % pkg_name
    try:
        ok = frappe.cache().set(key, "1", nx=True, ex=LOCK_SECONDS)
    except Exception:
        ok = False                     # khong khoa duoc thi KHONG chay (khac voi duong ky)
    if not ok:
        frappe.throw(_("Gói {0} đang được đồng bộ - đợi lượt trước xong.").format(pkg_name))
    return key


def _unlock(key):
    try:
        frappe.cache().delete(key)
    except Exception:
        pass


# --------------------------------------------------------------------------- lenh goc
def _original_send(leg_name):
    """Lenh ERP da gui cho chan ky nay, lay tu su kien cua worker. (lenh, ly_do_dung).

    Chi nhan khi lenh DA DUNG la `transition` co ten nguoi nhan (HandoverTargeted) va nha cung
    cap da nhan (ProviderAccepted). Khong co -> chan nhan ve tu cong (nguoi ky tay, dong bo vao
    ERP): ERP chua bao gio gui -> khong gui thay. Lenh goc roi ve POOL (HandoverPoolFallback moi
    hon HandoverTargeted) -> ERP chua tung gui transition nay -> khong tu che ra (QC 15/11)."""
    rows = frappe.get_all(EVENT, filters={"signature_request": leg_name,
                                          "event_type": ["in", ["HandoverTargeted",
                                                                "ProviderAccepted",
                                                                "HandoverPoolFallback"]]},
                          fields=["event_type", "request_meta", "creation"],
                          order_by="creation desc", limit_page_length=20)
    targeted = [x for x in rows if x.event_type == "HandoverTargeted"]
    pool = [x for x in rows if x.event_type == "HandoverPoolFallback"]
    if not targeted or not any(x.event_type == "ProviderAccepted" for x in rows):
        return None, "leg_not_sent_by_erp"
    if pool and str(pool[0].creation) >= str(targeted[0].creation):
        return None, "original_was_pool"
    meta = frappe.parse_json(targeted[0].request_meta) if targeted[0].request_meta else {}
    return (meta or {}), None


#: Chuoi trong request_meta (frappe.as_json: `"key": "value"`) - KHONG khop
#: "provider_resync_recreate" (su kien tao lai, cap goi).
_SEND_MARK = '%"source": "' + SOURCE + '"%'
#: Ket qua cua lan gui truoc ma coi la DA XONG: xac minh duoc, hoac cong TU CHOI chac chan
#: (khong gui gi). Con lai (khong ro / chua thay) -> phai xem cong truoc khi gui lai.
_RESOLVED = ("resync_verified", "resync_send_rejected")
#: Xac nhan da xem cong chi hop le khi lan gui truoc da qua it nhat chung nay (lenh transition
#: chay bat dong bo; cong co the "2xx roi im" toi 20 phut).
ACK_MIN_AGE_MINUTES = 30


def _prior_unverified(leg_name):
    """Lan ban lai truoc cho chan nay chua co ket qua ro -> su kien gui (name, creation)."""
    sends = frappe.get_all(EVENT, filters={"signature_request": leg_name,
                                           "event_type": "ResendExecuted",
                                           "request_meta": ["like", _SEND_MARK]},
                           fields=["name", "creation"], order_by="creation desc",
                           limit_page_length=1)
    if not sends:
        return None
    for mark in _RESOLVED:
        if frappe.get_all(EVENT, filters={"signature_request": leg_name,
                                          "event_type": "PollTick",
                                          "verification_result": ["like", mark + "%"],
                                          "creation": [">=", sends[0].creation]},
                          fields=["name"], limit_page_length=1):
            return None
    return sends[0]


# --------------------------------------------------------------------------- 1. token (2b)
def probe_user_tokens(environment=None):
    """CHI DOC: token "Ket noi SCTS" cua tung nguoi co con dung duoc tren nha cung cap HIEN TAI
    khong. Moi nguoi MOT lenh GET (danh sach chu ky cua chinh ho) bang token cua ho. Khong ghi gi,
    khong tra token."""
    from ecentric_workspace.platform.esign import user_link
    settings, env = user_link.default_context()
    env = environment or env
    rows = frappe.get_all(MAPPING, filters={"environment": env, "active": 1,
                                            "mapping_status": "Verified",
                                            "api_token_expires_at": ["is", "set"]},
                          fields=["frappe_user", "scts_user_id"], order_by="frappe_user asc",
                          limit_page_length=500)
    out = []
    for r in rows:
        tok = user_link.token_for(r.frappe_user, env)
        if not tok:
            out.append({"user": r.frappe_user, "result": "expired_or_missing"})
            continue
        adapter = get_adapter(settings)
        adapter.use_user_token(tok)
        try:
            adapter.list_user_signatures(r.scts_user_id)
            out.append({"user": r.frappe_user, "result": "ok"})
        except ProviderError as e:
            out.append({"user": r.frappe_user,
                        "result": "rejected" if e.code == "scts_user_token_rejected"
                        else "error:%s" % e.code})
        except Exception as e:                      # khong de mot nguoi lam hong ca bao cao
            out.append({"user": r.frappe_user, "result": "error:%s" % safe_error(e)[:80]})
    return {"environment": env, "base_url": settings.get("base_url"), "checked": len(out),
            "ok": len([x for x in out if x["result"] == "ok"]),
            "rejected": len([x for x in out if x["result"] == "rejected"]), "rows": out}


# --------------------------------------------------------------------------- 2. ke hoach
def plan(business_doctype, business_name):
    """CHI DOC: chan ky ERP nao chua co tren tai lieu ben nha cung cap."""
    pkg = _package(business_doctype, business_name)
    if not pkg:
        return {"ok": False, "reason": "no_package"}
    legs = _completed_legs(pkg.name)
    base = {"package": pkg.name, "document_id": pkg.scts_document_id,
            "erp_signed": len(legs), "legs": [_leg_view(x) for x in legs]}
    if not pkg.scts_document_id:
        return dict(base, ok=False, reason="no_provider_document")
    settings = _settings(pkg.provider, pkg.environment)
    adapter = get_adapter(settings)
    try:
        state = adapter.poll_status(pkg.scts_document_id)
    except ProviderError as e:
        if e.code == "scts_document_not_found":
            return dict(base, ok=True, document_missing=True, provider_signed=0,
                        missing=[_leg_view(x) for x in legs], action="recreate")
        return dict(base, ok=False, reason="poll_failed:%s" % e.code)
    status = str(getattr(state, "status", "") or "").lower()
    signed = _signed_rows(state)
    n_p = len(signed)
    base.update({"provider_signed": n_p, "provider_status": getattr(state, "status", None)})
    if status in _DEAD_DOC:
        return dict(base, ok=False, reason="provider_document_%s" % status)
    if n_p > len(legs):
        return dict(base, ok=False, reason="provider_ahead_of_erp")
    ok, why = _prefix_ok(legs, _emails(signed))
    if not ok:
        return dict(base, ok=False, reason=why)
    if n_p == len(legs):
        return dict(base, ok=True, in_sync=True, missing=[])
    return dict(base, ok=True, missing=[_leg_view(x) for x in legs[n_p:]], action="replay")


# --------------------------------------------------------------------------- 3. gui mot chan
def _next_users(approval_request, level_no):
    """Nguoi nhan buoc tiep theo = nguoi cua cap ERP ke tiep. Cap do da duyet roi thi uu tien
    CHINH NGUOI da duyet (ho se ky buoc do khi ban lai chan sau); chua duyet thi nguoi dang cho."""
    rows = frappe.get_all(APPROVER, filters={"approval_request": approval_request,
                                             "level_no": int(level_no) + 1},
                          fields=["approver", "status"], limit_page_length=50)
    done = [r.approver for r in rows if r.status == "Approved"]
    pend = [r.approver for r in rows if r.status == "Pending"]
    seen, out = set(), []
    for u in (done or pend):
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _send_plan(leg, legs, pkg, settings, adapter, ack_prior_attempt=False):
    """Lenh se gui cho chan ky nay. Nem _Stop(ly_do) khi mot dieu kien hong."""
    env = settings.get("environment")
    targeted, why_orig = _original_send(leg.get("name"))
    if why_orig:
        raise _Stop(why_orig)
    prior = _prior_unverified(leg.get("name"))
    if prior and not ack_prior_attempt:
        raise _Stop("prior_resync_unverified:%s" % prior.name)
    if prior:
        from frappe.utils import add_to_date, get_datetime, now_datetime
        if get_datetime(prior.creation) > add_to_date(now_datetime(),
                                                      minutes=-ACK_MIN_AGE_MINUTES):
            raise _Stop("prior_too_recent:%s" % prior.name)
    if not leg.get("effective_scts_user_id") or not leg.get("effective_signature_id"):
        raise _Stop("leg_missing_identity")
    m = perms.verified_mapping(leg.get("actor_user") or leg.get("approver"), env)
    if not m or str(m.get("scts_user_id")) != str(leg.get("effective_scts_user_id")) \
            or str(m.get("signature_id")) != str(leg.get("effective_signature_id")):
        raise _Stop("mapping_changed_since_signing")
    vr = adapter.validate_signature_owner(leg.get("effective_scts_user_id"),
                                          leg.get("effective_signature_id"))
    if not vr:
        raise _Stop("signature_owner:%s" % getattr(vr, "reason", "?"))
    doc_id = pkg.scts_document_id
    state = adapter.poll_status(doc_id)
    status = str(getattr(state, "status", "") or "").lower()
    if status in _DEAD_DOC:
        raise _Stop("provider_document_%s" % status)
    signed = _signed_rows(state)
    ok, why = _prefix_ok(legs, _emails(signed))
    if not ok:
        raise _Stop(why)
    pos = [x.get("name") for x in legs].index(leg.get("name"))
    if pos != len(signed):
        raise _Stop("position_mismatch:leg=%s provider_signed=%s" % (pos, len(signed)))
    stage = "requester" if leg.get("actor_type") == "Requester" else "approval"
    from ecentric_workspace.platform.esign.package import workflow_instance_id
    inst_id = workflow_instance_id(pkg.name) or doc_id
    buoc, why = next_handler.provider_step_index(adapter, doc_id)
    if buoc is None or int(buoc) != pos:
        raise _Stop("step_unknown:%s" % (why or buoc))
    cfg = next_handler.resolve_transition_config(pkg.profile, "Sign", stage=stage,
                                                 step_index=buoc)
    if not cfg or cfg.get("step_index") is None or int(cfg["step_index"]) != int(buoc):
        raise _Stop("no_step_config:%s/%s" % (stage, buoc))
    # Loai chu ky (ky-tham-gia / ky-chinh): anh xa tren prod KHONG ghi loai (15/11: moi anh xa
    # deu trong) -> doc tu CHINH chu ky do tren cong (GetSignatures da chuan hoa: "type").
    have = m.get("signature_type")
    if not have:
        own = next((x for x in (adapter.list_user_signatures(
            leg.get("effective_scts_user_id")) or [])
            if str(x.get("id")) == str(leg.get("effective_signature_id"))), None)
        have = (own or {}).get("type")
    if not have:
        raise _Stop("signature_type_unknown")
    if not next_handler.signature_type_matches(cfg.get("sign_type"), have):
        raise _Stop("signature_type_mismatch:%s/%s" % (cfg.get("sign_type"), have))
    if targeted.get("transition_id") not in (None, "") \
            and str(targeted.get("transition_id")) != str(cfg.get("transition_id")):
        raise _Stop("differs_from_original:%s!=%s" % (cfg.get("transition_id"),
                                                      targeted.get("transition_id")))
    if targeted.get("signer_user_id") not in (None, "") \
            and str(targeted.get("signer_user_id")) != str(leg.get("effective_scts_user_id")):
        raise _Stop("signer_differs_from_original")
    # Cong phai DANG MO dung canh nay cho chinh nguoi ky - nguon thu hai, doc lap voi dem.
    wstate, why2 = adapter.workflow_state_for_document(doc_id, leg.get("effective_scts_user_id"))
    if wstate is None:
        raise _Stop("portal_state_unreadable:%s" % why2)
    open_ids = [str(t.get("transition_id")) for t in (wstate.get("transitions") or [])]
    if str(cfg.get("transition_id")) not in open_ids:
        raise _Stop("portal_disagrees:want=%s open=%s" % (cfg.get("transition_id"),
                                                          ",".join(open_ids) or "-"))
    users = _next_users(leg.get("approval_request"), leg.get("level_no") or 0)
    if users:
        ids, unmapped = next_handler.provider_ids_for(users, env)
        if unmapped or not ids:
            raise _Stop("next_handler_unmapped:%s" % ",".join(unmapped))
        if hasattr(adapter, "eligible_recipients"):
            eligible = adapter.eligible_recipients(inst_id, cfg.get("transition_id"),
                                                   leg.get("effective_scts_user_id"))
            if eligible is not None:
                ids = [i for i in ids if str(i) in eligible]
                if not ids:
                    raise _Stop("no_eligible_recipient")
        orig_to = [str(x) for x in (targeted.get("to_users") or [])]
        if orig_to and not set(ids) <= set(orig_to):
            raise _Stop("recipients_differ_from_original")
    elif cfg.get("terminal"):
        ids = []
    else:
        raise _Stop("no_next_level_user")
    return {"cfg": cfg, "to_users": ids, "erp_users": users, "step_index": buoc,
            "instance_id": inst_id, "stage": stage, "before": _emails(signed),
            "actor_user_id": next_handler.requester_actor(leg, settings, stage)}


def _verify(adapter, doc_id, before, aliases):
    """Gui xong: phai thay THEM DUNG MOT chu ky, cua dung nguoi. (ok, ly_do)."""
    last = "no_poll"
    for w in VERIFY_WAITS:
        time.sleep(w)
        try:
            state = adapter.poll_status(doc_id)
        except ProviderError as e:
            last = "poll_failed:%s" % e.code
            continue
        now = _emails(_signed_rows(state))
        rest = list(now)
        for e in before:
            if e in rest:
                rest.remove(e)
        if len(now) > len(before) + 1:
            return False, "resync_unverified:extra_signatures:%d->%d" % (len(before), len(now))
        if len(rest) == 1 and rest[0] in aliases:
            return True, "resync_verified:%d->%d" % (len(before), len(now))
        if rest:
            return False, "resync_unverified:wrong_signer"
        last = "not_yet:%d->%d" % (len(before), len(now))
    return False, "resync_unverified:%s" % last


def _replay_one(pkg, legs, leg, reason, dry_run, ack_prior_attempt=False):
    """Mot chan ky: ke hoach (chay thu) hoac gui + xac minh. Tra dong ket qua."""
    settings = _settings(pkg.provider, pkg.environment)
    view = _leg_view(leg)
    adapter, why = _user_token_adapter(leg, settings)
    if adapter is None:
        return dict(view, result="stop", reason=why)
    try:
        sp = _send_plan(leg, legs, pkg, settings, adapter, ack_prior_attempt)
    except _Stop as s:
        return dict(view, result="stop", reason=str(s))
    except ProviderError as e:                      # chua gui gi - an toan
        return dict(view, result="stop", reason="provider_error:%s" % e.code)
    view.update(transition_id=sp["cfg"].get("transition_id"), step_index=sp["step_index"],
                to_users=sp["to_users"], erp_users=sp["erp_users"], stage=sp["stage"])
    if dry_run:
        return dict(view, result="would_send")
    live = _live_legs(pkg.name, leg.get("level_no"))
    if live:            # ai do vua bam Duyet & Ky trong luc lap ke hoach
        return dict(view, result="stop", reason="live_legs:%s" % ",".join(x.name for x in live))
    events.emit("ResendExecuted", signature_request=leg.get("name"), package=pkg.name,
                erp_actor=frappe.session.user,
                request_meta={"source": SOURCE, "ly_do": reason,
                              "transition_id": sp["cfg"].get("transition_id"),
                              "step_index": sp["step_index"], "to_users": sp["to_users"],
                              "document_id": pkg.scts_document_id,
                              "ack_prior_attempt": bool(ack_prior_attempt)})
    frappe.db.commit()              # vet "da gui" phai ton tai ke ca khi buoc sau hong
    try:
        adapter.transition_with_recipients(sp["instance_id"], leg.get("effective_scts_user_id"),
                                           sp["to_users"], sp["cfg"],
                                           leg.get("effective_signature_id"),
                                           actor_user_id=sp["actor_user_id"])
    except ProviderError as e:
        amb = bool(getattr(e, "ambiguous", False))
        events.emit("PollTick", signature_request=leg.get("name"), package=pkg.name,
                    verification_result=("resync_send_unknown:%s" if amb
                                         else "resync_send_rejected:%s") % e.code,
                    error_summary=safe_error(e), request_meta={"source": SOURCE})
        frappe.db.commit()
        return dict(view, result="send_failed", reason=e.code,
                    ambiguous=bool(getattr(e, "ambiguous", False)))
    ok, why = _verify(adapter, pkg.scts_document_id, sp["before"], _aliases(leg))
    events.emit("PollTick", signature_request=leg.get("name"), package=pkg.name,
                verification_result=why, request_meta={"source": SOURCE})
    frappe.db.commit()
    return dict(view, result="verified" if ok else "unverified", reason=why)


# --------------------------------------------------------------------------- 4. ban lai
def replay(business_doctype, business_name, reason, dry_run=True, ack_prior_attempt=False):
    """Ban lai sang nha cung cap chan ky ERP da hoan tat KE TIEP ma tai lieu chua co.
    Chay that: MOT chan moi lan goi (goi lai cho chan sau)."""
    _require_reason(reason)
    p = plan(business_doctype, business_name)
    if not p.get("ok") or p.get("in_sync"):
        return dict(p, results=[])
    if p.get("document_missing"):
        return dict(p, ok=False, reason="document_missing:dung recreate_document", results=[])
    pkg = _package(business_doctype, business_name)
    live = _live_legs(pkg.name, (p["missing"][0] or {}).get("level_no"))
    if live:
        return dict(p, ok=False, reason="live_legs:%s" % ",".join(
            "%s(%s)" % (x.name, x.status) for x in live), results=[])
    key = _lock(pkg.name)
    try:
        legs = _completed_legs(pkg.name)
        missing = [x for x in legs if x["name"] in
                   {m["signature_request"] for m in p["missing"]}]
        if not missing:
            return dict(p, ok=False, reason="legs_changed_retry", results=[])
        res = _replay_one(pkg, legs, missing[0], reason, bool(dry_run), ack_prior_attempt)
    finally:
        _unlock(key)
    remaining = len(p["missing"]) - (1 if res.get("result") == "verified" else 0)
    return dict(p, dry_run=bool(dry_run), results=[res], remaining=remaining)


def _foreign_doc_check(pkg, legs, settings):
    """Tai lieu CON tren cong nhung tao NHAM tai khoan (16/11, 00675). (creator, ly do loi).

    Cho phep thay khi VA CHI KHI: tai lieu dang xu ly (khong huy / tu choi / xong), KHONG co chu
    ky nao, nguoi tao doc duoc va KHONG phai nguoi de nghi (moi ten goi cua ho), va ma chung tu
    tren cong khop ma goi da gui (dung la tai lieu cua goi nay)."""
    adapter = get_adapter(settings)
    try:
        state = adapter.poll_status(pkg.scts_document_id)
    except ProviderError as e:
        return None, "foreign_poll:%s" % e.code
    status = str(getattr(state, "status", "") or "").lower()
    if status in _DEAD_DOC or status in ("completed", "rejected", "cancelled"):
        return None, "foreign_doc_status:%s" % status
    if _signed_rows(state):
        return None, "foreign_doc_has_signatures"
    ident = getattr(state, "identity", None) or {}
    creator = str(ident.get("creator_email") or "").strip().casefold()
    if not creator:
        return None, "foreign_doc_creator_unknown"
    if creator in {a.casefold() for a in _aliases(legs[0])}:
        return None, "foreign_doc_created_by_requester"
    sent_code = frappe.db.get_value(PKG, pkg.name, "doc_code_sent") or pkg.business_name
    if str(ident.get("doc_code") or "").strip() != str(sent_code or "").strip():
        return None, "foreign_doc_code_mismatch"
    return creator, None


def recreate_document(business_doctype, business_name, reason, dry_run=True,
                      replace_foreign=False):
    """Tai lieu KHONG CON ben nha cung cap (404): tao lai bang dung tep + o ky da khoa cua goi,
    bang dung tai khoan luc dau (token nguoi de nghi). CHI TAO - cac chan ky (nguoi de nghi truoc)
    ban lai bang `replay`, moi lan goi mot chan. Goi giu nguyen ma bam / phien ban; chi doi ma tai
    lieu (ma cu, ma instance cu, ma tep cu vao su kien cap goi).""" 
    _require_reason(reason)
    p = plan(business_doctype, business_name)
    pkg = _package(business_doctype, business_name)
    prior_old = None
    if p.get("reason") == "no_provider_document" and pkg \
            and not pkg_error_code(pkg.name):
        # Lan tao lai truoc ket thuc MO HO (vd CMC tra 500 cho AddDocument) va SM da doi soat:
        # xac nhan KHONG co tai lieu nao duoc tao (clear_create_ambiguity) -> goi khong con ma
        # tai lieu. Cho tao lai, lay ma cu tu su kien tao lai truoc (16/11, 00675).
        prior_old = _prior_recreate_old_id(pkg.name)
        if prior_old:
            p = dict(p, ok=True, document_missing=True, provider_signed=0,
                     missing=p.get("legs") or [], action="recreate", document_id=prior_old,
                     reason=None)
    foreign_creator = None
    if replace_foreign:
        # Thay tai lieu tao NHAM tai khoan: tai lieu PHAI con (khong 404) - 404 thi dung duong
        # tao lai thuong. Kiem chi tiet o _foreign_doc_check (sau khi co legs/settings).
        if not p.get("ok") or p.get("document_missing") or not pkg or not pkg.scts_document_id:
            return dict(p, ok=False, reason=p.get("reason") or "replace_foreign_needs_existing_doc")
    elif not p.get("ok") or not p.get("document_missing"):
        return dict(p, ok=False, reason=p.get("reason") or "document_not_missing")
    legs = _completed_legs(pkg.name)
    if not legs or legs[0].get("actor_type") != "Requester":
        return dict(p, ok=False, reason="no_completed_requester_leg")
    if replace_foreign:
        foreign_creator, why_f = _foreign_doc_check(pkg, legs,
                                                     _settings(pkg.provider, pkg.environment))
        if why_f:
            return dict(p, ok=False, reason=why_f)
        p = dict(p, replace_foreign=True, foreign_creator=foreign_creator)
    # Thay tai lieu nham: chan cap duyet o Manual Review (vd lenh cua cap 1 roi vao tai lieu
    # nham) KHONG chan - gui lai sau qua "Gui lai co kiem". Chan dang bay van chan.
    live = _live_legs(pkg.name, replay_level=0 if replace_foreign else None)
    if live:
        return dict(p, ok=False, reason="live_legs:%s" % ",".join(x.name for x in live))
    _t, why_orig = _original_send(legs[0]["name"])
    if why_orig:
        return dict(p, ok=False, reason=why_orig)
    if pkg_error_code(pkg.name) == "create_outcome_unknown":
        return dict(p, ok=False, reason="create_outcome_unknown:doi soat truoc")
    settings = _settings(pkg.provider, pkg.environment)
    adapter, why = _user_token_adapter(legs[0], settings)
    if adapter is None:
        return dict(p, ok=False, reason=why)
    try:
        # (a) token nguoi de nghi con dung tren cong hien tai; (b) 404 KHONG phai do quyen xem:
        # nguoi tao tai lieu cung khong thay no (QC 15/11 - neu khong se tao trung tai lieu).
        adapter.list_user_signatures(legs[0].get("effective_scts_user_id"))
        if not replace_foreign:
            try:
                adapter.poll_status(pkg.scts_document_id or prior_old)
                return dict(p, ok=False, reason="document_visible_to_requester")
            except ProviderError as e:
                if e.code != "scts_document_not_found":
                    return dict(p, ok=False, reason="requester_poll:%s" % e.code)
        m = perms.verified_mapping(legs[0].get("actor_user"), settings.get("environment"))
        if not m or str(m.get("scts_user_id")) != str(legs[0].get("effective_scts_user_id")) \
                or str(m.get("signature_id")) != str(legs[0].get("effective_signature_id")):
            return dict(p, ok=False, reason="mapping_changed_since_signing")
        if not adapter.validate_signature_owner(legs[0].get("effective_scts_user_id"),
                                                legs[0].get("effective_signature_id")):
            return dict(p, ok=False, reason="signature_owner")
    except ProviderError as e:
        return dict(p, ok=False, reason="requester_token:%s" % e.code)
    from ecentric_workspace.platform.esign import package as pkgsvc
    files = pkgsvc.package_files(pkg.name)
    if not int(settings.get("allow_document_creation") or 0):
        return dict(p, ok=False, reason="document_creation_gated")
    if dry_run:
        return dict(p, dry_run=True, would_create={
            "files": len(files), "placements": len(pkgsvc.package_placements(pkg.name)),
            "as_requester": legs[0].get("actor_user")},
            then_replay=[_leg_view(x) for x in legs])
    key = _lock(pkg.name)
    try:
        if _live_legs(pkg.name, replay_level=0 if replace_foreign else None):
            return dict(p, ok=False, reason="live_legs")
        req_leg = frappe.db.get_value(DSR, legs[0]["name"], "*", as_dict=True)
        old = frappe.db.get_value(PKG, pkg.name, ["scts_document_id",
                                                  "scts_workflow_instance_id"],
                                  as_dict=True, for_update=True)
        old_files = {f.name: f.get("scts_document_file_id") for f in files}
        # Pha 1 (commit rieng): xoa ma cu + CAM tu tao (create_outcome_unknown). Request chet
        # giua chung thi worker khac gap moc nay se CHO doi soat, khong tao tai lieu thu hai
        # (QC 15/11). Su kien o cap GOI (khong gan chan ky): khong lan voi "lan gui truoc".
        frappe.db.set_value(PKG, pkg.name, {"scts_document_id": None,
                                            "scts_workflow_instance_id": None,
                                            "error_code": "create_outcome_unknown",
                                            "error_message": "provider_resync: dang tao lai "
                                                             "tai lieu - neu thay moc nay lau, "
                                                             "doi soat tren cong truoc"})
        events.emit("ResendExecuted", package=pkg.name, erp_actor=frappe.session.user,
                    request_meta={"source": SOURCE + "_recreate", "ly_do": reason,
                                  "old_document_id": old.scts_document_id or prior_old,
                                  "old_instance_id": old.scts_workflow_instance_id,
                                  "old_file_ids": old_files,
                                  "requester_leg": legs[0]["name"],
                                  # thay tai lieu tao nham tai khoan: ai da tao ban cu (ban cu
                                  # KHONG bi huy tren cong - de nguyen cho ops tu xu ly)
                                  "replaced_foreign_creator": foreign_creator})
        frappe.db.commit()
        # Pha 2: go moc (chua commit) -> tao -> commit cung luc voi ma moi.
        frappe.db.set_value(PKG, pkg.name, {"error_code": None, "error_message": None})
        from ecentric_workspace.platform.esign import tasks
        try:
            new_id = tasks._ensure_provider_document(req_leg, settings, adapter)
        except ProviderError as e:
            if not getattr(e, "ambiguous", False):
                # Chac chan KHONG tao: tra lai nhu cu, goi khong mo coi. KHONG BAO GIO de trong
                # ma tai lieu: goi trong ma + nguoi de nghi da ky = lan bam duyet ke tiep tu tao
                # tai lieu bang tai khoan tich hop (16/11, 00675). Lan truoc da xoa ma (prior_old)
                # thi tra ma cu do (tai lieu da chet -> worker gap 404 va dung lai an toan).
                frappe.db.set_value(PKG, pkg.name, {
                    "scts_document_id": old.scts_document_id or prior_old,
                    "scts_workflow_instance_id": old.scts_workflow_instance_id,
                    "error_code": None, "error_message": None})
            # mo ho: _ensure da dat create_outcome_unknown -> doi soat, khong tao lai
            frappe.db.commit()
            return dict(p, ok=False, reason="create_failed:%s" % e.code,
                        old_document_id=old.scts_document_id,
                        ambiguous=bool(getattr(e, "ambiguous", False)))
        frappe.db.commit()
    finally:
        _unlock(key)
    # Chan nguoi de nghi (va cac chan sau) ban lai bang replay - MOT lan goi rieng moi chan,
    # de lenh tao va lenh ky khong chung mot request web (thoi gian).
    return dict(p, ok=True, created=True, old_document_id=old.scts_document_id,
                new_document_id=new_id,
                next_step="goi resync_replay cho tung chan (%d chan)" % len(legs))


def _prior_recreate_old_id(pkg_name):
    """Ma tai lieu CU ghi trong su kien tao lai (cap goi) gan nhat, hoac None."""
    rows = frappe.get_all(EVENT, filters={"package": pkg_name, "event_type": "ResendExecuted",
                                          "request_meta": ["like", '%"source": "' + SOURCE
                                                           + '_recreate"%']},
                          fields=["request_meta"], order_by="creation desc", limit_page_length=1)
    if not rows:
        return None
    meta = frappe.parse_json(rows[0].request_meta) if rows[0].request_meta else {}
    return (meta or {}).get("old_document_id") or None


def pkg_error_code(pkg_name):
    return frappe.db.get_value(PKG, pkg_name, "error_code")
