# Copyright (c) 2026, eCentric and contributors
"""Who handles the provider document NEXT, and with which provider transition.

Why this module exists
----------------------
eContract's workflow notifies a whole ROLE POOL unless the caller names the next handler.
On 2026-08-27 that let a colleague who was not the designated approver sign
EC-PAYR-2026-00026 forty seconds after it was submitted, bypassing the ERP approval chain
entirely. The portal itself always names the next handler (`toUsers`), and it refuses to
proceed without one - our API path simply never sent it.

Design
------
* The ERP approval chain is the ONLY source of truth for who comes next. We read the
  persisted approver rows, never a role or a guess.
* The provider-side transition metadata (transition id / name / action code / sign type) is
  CONFIG on the profile, never constants in code: they differ per workflow and per stage,
  and inventing them is how you sign the wrong stage.
* Fail SOFT, but never SILENT: when the next handler cannot be named (no verified provider
  mapping for that person, or no configured transition) the caller keeps the old pool-wide
  path and records exactly why, so the gap is visible in the audit trail instead of being
  discovered months later on a signed document.
"""
import frappe

AR = "EC Approval Request"
APPROVER = "EC Approval Request Approver"
LEVEL = "EC Approval Request Level"


def resolve_transition_config(profile_name, action, stage=None, step_index=None):
    """Provider transition metadata for (action, stage) from the profile, or None.

    `stage` lets one profile describe several steps of the same action - e.g. the requester
    submission and an approval level are both "Sign" but carry different provider ids.
    An exact stage match wins; a row with no stage acts as the default.

    `step_index` = SO CHU KY DA CO tren tai lieu truoc buoc sap gui, va no thang `stage`.

    Do tay tren cong 02/09, mot tai lieu, bam tuan tu: Trinh ky `-2`, duyet 1 `-9`, duyet 2
    `-10`, duyet 3 `-11`. transitionId chay theo THU TU BUOC trong quy trinh - khong theo
    nguoi, va khong theo cap duyet cua ERP (cung mot nguoi dung buoc 2 o tai lieu nay, cap 4
    o tai lieu khac).

    Cau hinh cu gan DUNG MOT id `-9` cho moi buoc duyet, nen:
      buoc 1 (`-2`) dung, buoc 2 (`-9`) dung, buoc 3 can `-10` -> 400, buoc 4 can `-11` -> 400.
    Sau 400 he lui ve pool, va pool chi ky duoc khi nguoi minh gui TINH CO dung la nguoi
    eContract dang cho - chi Lien trung nen ky duoc, chi Phuong trat nen 2xx roi im 20 phut.
    Hai buoc dau chay tot suot bao lau nay khong phai may: chung dung that.
    """
    if not profile_name:
        return None
    # Read the rows off the PARENT document. `EC Digital Signature Profile Transition` is a
    # child table (istable=1) and Frappe refuses a get_all() on one without a parent - the
    # first version of this function did exactly that, so every signing job died right after
    # BindingValidated with the DSR left sitting at Queued.
    try:
        profile = frappe.get_doc("EC Digital Signature Profile", profile_name)
    except Exception:
        return None
    rows = [{"transition_id": r.transition_id, "transition_name": r.transition_name,
             "process_action": r.process_action, "sign_type": r.sign_type,
             "stage": r.stage, "step_index": r.get("step_index"),
             "terminal": r.terminal}
            for r in (profile.get("transitions") or []) if r.action == action]
    if not rows:
        return None
    # Vi tri buoc THANG stage. Chi dung khi biet chac vi tri: `step_index=None` nghia la
    # khong dem duoc so chu ky tren tai lieu, va luc do doan mot vi tri con te hon dung
    # duong cu - doan sai thi 400 roi lui ve pool, tuc quay ve dung canh xo so da lam chi
    # Phuong ket 20 phut.
    if step_index is not None:
        theo_buoc = [r for r in rows if r.get("step_index") is not None
                     and int(r["step_index"]) == int(step_index)]
        if theo_buoc:
            row = theo_buoc[0]
            if row.get("transition_id") is None or not row.get("process_action"):
                return None
            return row
    exact = [r for r in rows if (r.get("stage") or "") == (stage or "")]
    default = [r for r in rows if not (r.get("stage") or "")]
    row = (exact or default or [None])[0]
    if not row:
        return None
    if row.get("transition_id") is None or not row.get("process_action"):
        # Half-configured is worse than unconfigured: it would send a payload the provider
        # cannot act on. Treat it as absent so the caller falls back and says so.
        return None
    return {"transition_id": row["transition_id"],
            "transition_name": row.get("transition_name") or "",
            "process_action": row["process_action"],
            "sign_type": row.get("sign_type") or "",
            "terminal": bool(row.get("terminal"))}


def next_level_approvers(approval_request, current_level):
    """ERP users who may act on the level AFTER `current_level` (pending rows only).

    `current_level` 0 means the requester leg: the next actors are level 1. Returns [] when
    the chain has no further level - the caller then has nobody to hand over to.
    """
    if not approval_request:
        return []
    nxt = int(current_level or 0) + 1
    rows = frappe.get_all(APPROVER,
                          filters={"approval_request": approval_request, "level_no": nxt,
                                   "status": "Pending"},
                          fields=["approver"], limit_page_length=0)
    seen, out = set(), []
    for r in rows:
        if r.approver and r.approver not in seen:
            seen.add(r.approver)
            out.append(r.approver)
    return out


def provider_ids_for(users, environment):
    """(ids, unmapped): provider user ids for `users` that have a VERIFIED mapping.

    Unverified or missing mappings are reported, never silently skipped - handing the
    document to an unverified identity is exactly the failure mode this module prevents.
    """
    # The module is `permissions`; every other file in this package imports it as `perms`.
    # Getting that alias wrong made the whole signing leg die on an ImportError.
    from ecentric_workspace.platform.esign import permissions as perms
    ids, unmapped = [], []
    for u in users or []:
        mapping = perms.verified_mapping(u, environment)
        pid = mapping and (mapping.get("scts_user_id") if isinstance(mapping, dict)
                           else getattr(mapping, "scts_user_id", None))
        if pid:
            ids.append(str(pid))
        else:
            unmapped.append(u)
    return ids, unmapped


#: What the provider calls the transitions we are allowed to drive. "Tu choi" is a rejection
#: and must never be taken by the approve path.
_APPROVE_TYPES = ("approve",)


def discover_transition(adapter, instance_id, provider_user_id):
    """Ask the PROVIDER which transition applies right now, instead of configuring one.

    Captured from the portal 2026-08-28:

        GET /api/Workflow/{instanceId}?userid={userId}
        -> availableTransitions[{transitionId, processAction, signType, isSigned, ...}]

    This replaces the per-stage config, which could not have worked. In one real workflow the
    four "Phe duyet" edges are -9, -10, -11 and -4, and the LAST one wants processAction
    WfFunctionRunSignedA with signType ky-chinh while the others want WfFunctionRunSignedOther
    with ky-tham-gia. One configured value per stage is therefore wrong on at least one step
    of every single document - which is exactly what happened.

    Returns (config, reason). config is None when we must not act.
    """
    if not hasattr(adapter, "available_transitions"):
        return None, "adapter_cannot_discover_transitions"
    try:
        avail = adapter.available_transitions(instance_id, provider_user_id) or []
    except Exception as exc:
        # Ghi CA noi dung loi, khong chi ten loai. Ban dau chi ghi type(exc).__name__ va lan
        # chay that 28/08 tra ve dung mot chu "SctsHttpError" - biet la hong nhung khong biet
        # ma trang thai, khong biet provider noi gi, nen lai phai doan. Dung cai sai da ton hai
        # dem: dung cong cu de nhin roi tu bit mat o dong cuoi.
        from ecentric_workspace.platform.esign.sanitize import safe_error
        return None, "transition_discovery_failed:%s" % safe_error(exc)
    if not avail:
        return None, "no_available_transition"
    picks = [t for t in avail if (t.get("transition_type") or "") in _APPROVE_TYPES]
    if not picks:
        # Never fall back to "the first one": the other edge on this state is "Tu choi".
        return None, "no_approve_transition:%s" % ",".join(
            str(t.get("transition_name") or "?") for t in avail)
    if len(picks) > 1:
        # Two ways forward is a business choice, not something to pick blindly.
        return None, "ambiguous_approve_transition:%s" % ",".join(
            str(t.get("transition_id")) for t in picks)
    t = picks[0]
    if t.get("transition_id") is None or not t.get("process_action"):
        return None, "incomplete_transition:%s" % t.get("transition_id")
    return t, None


#: Nhung ly do nghia la "nha cung cap noi KHONG duoc di" - phai dung lai, khong duoc lay cau
#: hinh cu ra dung thay. Khac han voi "khong hoi duoc" (mang loi, 4xx, adapter cu).
_REFUSALS = ("no_available_transition", "no_approve_transition",
             "ambiguous_approve_transition", "incomplete_transition",
             # pick_forward_edge (chang 2b). Khai SAN o day: ngay chuyen sang tin cong ma quen
             # dong nay thi "cong noi khong duoc di" bi coi nhu "khong hoi duoc" -> gui cau
             # hinh cu bat chap (QC 12/11).
             "no_forward_transition", "ambiguous_forward_transition")


def why_is_refusal(why):
    return bool(why) and any(str(why).startswith(r) for r in _REFUSALS)


def signature_type_matches(required, mapping_type):
    """The transition says which KIND of signature the slot takes ("ky-chinh" /
    "ky-tham-gia"). Sending the wrong kind is how a document walks the whole workflow with
    its main-signature box left empty and nothing reported - observed on the portal test of
    2026-08-28, where four approvals completed and "Ky chinh" still read "Chua co".

    An unstated requirement is not a licence to send anything; it just cannot be checked.
    """
    want = str(required or "").strip().lower()
    if not want:
        return True
    return want == str(mapping_type or "").strip().lower()


def _mapped_signature_type(dsr, environment):
    """Which KIND of signature this leg is about to use. The DSR stores the signature id, not
    its type, so read it back off the verified mapping - the same row the id came from."""
    user = dsr.get("actor_user") or dsr.get("approver")
    if not user:
        return None
    try:
        from ecentric_workspace.platform.esign import permissions as perms
        m = perms.verified_mapping(user, environment) or {}
    except Exception:
        return None
    return m.get("signature_type")


def targeted_handover_enabled():
    """ON by default from 2026-08-28 chieu, sau khi co capture doi chieu duoc.

    Sang cung ngay minh TAT duong nay: mot lan eContract nhan transition (2xx,
    EC-PAYR-2026-00032) roi de chung tu ket - khong dong workflow, khong chu ky, khong con
    nut "Xu ly" cho chinh nguoi duoc chi dinh. Duong pool tho hon thi ky duoc, nen duong
    dung tren giay phai nhuong duong dang chay.

    Chieu 28/08 Hoan chup duoc lenh "Xu ly" cua chinh portal tren dung mot chung tu do ERP
    tao ra, va no THANH CONG:

        POST /api/Workflow/transition   (Content-Length 19169)
        { instanceId, userId, toUsers:[...], transitionId:"-2",
          transitionName:"Trinh ky", processAction:"WfFunctionRunSignedOther",
          signType:"ky-tham-gia", signatureInfo:{id,name,image}, comment:"" }

    Doi chieu tung truong voi cai minh gui: HINH DANG GIONG HET, va cau hinh bac nguoi
    trinh (p088) trung tung chu. Khac biet duy nhat tim duoc la `signatureInfo.name`:
    portal gui ten hien thi "Ky tham gia", minh gui ma "ky-tham-gia" vi khong co ten nao
    khac de gui. Da sua bang cach doc ten thang tu GetSignatures thay vi suy ra.

    Khong khang dinh do la nguyen nhan - khong co bang chung. Nhung mot bien so da bi loai,
    con duong pool thi dang BAO DAM phat cho ca 7 truong bo phan, nen can can da nghieng
    lai. Tat khan cap: `bench set-config ec_esign_targeted_handover 0`.
    """
    v = frappe.conf.get("ec_esign_targeted_handover")
    if v is None or v == "":
        return True
    try:
        return bool(int(v))
    except Exception:
        # Cau hinh sai kieu ("yes", "on") khong duoc am tham tro ve mac dinh - noi ro roi
        # giu duong dang chay.
        return str(v).strip().lower() not in ("0", "false", "no", "off")


def requester_actor_split_enabled():
    """OFF mac dinh. Bat: `bench set-config ec_esign_requester_actor_split 1` - va DUNG bat.

    Thu nghiem 04/09 03:28 tren EC-PAYR-2026-00050 (chung tu 97a98c9d): gui userId = tai
    khoan tich hop, signatureInfo (id, signerId, hsmId) = cua chi Hien. SCTS NHAN (2xx, khong
    fallback, task chuyen sang L1) - nhung chu ky dong len PDF la cua TAI KHOAN TICH HOP:

        Tham gia/signed @04/09/2026 03:28 hoan.tran@ecentric.vn

    Ket luan cung: SCTS ky bang chung thu cua `userId`; `signatureInfo` KHONG doi duoc chu
    chu ky. Bat co nay len = moi phieu cua nguoi de nghi khac deu mang chu ky cua tai khoan
    tich hop o o "Nguoi de nghi" va TU DONG di tiep sang cap duyet. Nguy hiem hon that bai
    cu (400, dung lai an toan). Giu code de bang chung tai hien duoc; mac dinh OFF.

    Boi canh: eContract giao buoc "Khoi tao hop dong" cho tai khoan TAO tai lieu bat ke vai
    tro tren node (thu 02:21). Nguoi trinh khong giu task -> userId cua ho bi 400. Chan
    duyet chay duoc vi toUsers cua buoc truoc da giao task cho DUNG nguoi ky.
    """
    v = frappe.conf.get("ec_esign_requester_actor_split")
    if v is None or v == "":
        return False
    try:
        return bool(int(v))
    except Exception:
        return str(v).strip().lower() not in ("0", "false", "no", "off")


def api_account_provider_user_id(settings):
    """SCTS userId cua TAI KHOAN TICH HOP (Provider Settings.username), qua mapping Active +
    Verified cua chinh moi truong do. None khi khong co - nguoi goi giu nguyen hanh vi cu,
    KHONG bia."""
    from ecentric_workspace.platform.esign.permissions import verified_mapping
    if isinstance(settings, dict):
        user = settings.get("username")
        env = settings.get("environment")
    else:
        user = getattr(settings, "username", None)
        env = getattr(settings, "environment", None)
    if not user or not env:
        return None
    m = verified_mapping(user, env)
    return (m or {}).get("scts_user_id") or None


def requester_actor(dsr, settings, stage):
    """Ai gui lenh ky cho chan nay thay cho nguoi ky, hoac None (= chinh nguoi ky).

    Chi ap dung cho stage 'requester'. Cung mot nguoi (nguoi trinh chinh la tai khoan tich
    hop - 10 goi dau cua Hoan) thi tra None, de payload y het truoc va khong doi duong da
    chay duoc."""
    if stage != "requester" or not requester_actor_split_enabled():
        return None
    actor = api_account_provider_user_id(settings)
    if not actor or str(actor) == str(dsr.get("effective_scts_user_id") or ""):
        return None
    return actor


def provider_step_index(adapter, instance_id):
    """So chu ky DA hoan tat tren tai lieu = vi tri cua buoc sap gui. (index, ly do).

    Dem tu NHA CUNG CAP, khong tu dem ben ERP. ERP dem se lech ngay khi co nguoi ky thang
    tren cong eContract - ma dieu do xay ra that: chan Ky chinh bat buoc phai ky tay bang
    OfficeSignTool, nen moi ho so deu co it nhat mot buoc khong di qua ERP.

    Tra `None` khi khong dem duoc - nguoi goi PHAI hieu la "khong biet", khong duoc coi la 0.
    Coi la 0 se gui `-2` (Trinh ky) cho mot tai lieu dang o giua chung.
    """
    if adapter is None or not instance_id or not hasattr(adapter, "poll_status"):
        return None, "khong co adapter hoac ma tai lieu"
    try:
        doc = adapter.poll_status(instance_id)
    except Exception as exc:
        from ecentric_workspace.platform.esign.sanitize import safe_error
        return None, "khong hoi duoc nha cung cap: %s" % safe_error(exc)
    signers = (getattr(doc, "signers", None) or []) if doc is not None else []
    if not signers:
        # KHONG tra 0. Danh sach rong nghia la khong doc duoc chan ky, khong phai "chua ai ky".
        return None, "tai lieu khong tra ve chan ky nao"
    return len([s for s in signers
                if str(s.get("status") or "").strip().lower() == "signed"]), None


#: Buoc chuyen cua luot ky lay tu dau. Ghi vao su kien de dem duoc, khong phai doan.
SOURCE_DISCOVERED = "discovered"            # hoi cong (availableTransitions)
SOURCE_STEP_INDEX = "step_index"            # dem chu ky tren tai lieu -> dong cau hinh theo vi tri
SOURCE_PROFILE_DEFAULT = "profile_default"  # dong mac dinh theo stage tren ho so

DISCOVERY_OFF = "off"
DISCOVERY_SHADOW = "shadow"


def transition_discovery_mode():
    """'shadow' (mac dinh) | 'off'. `bench set-config ec_esign_transition_discovery off`.

    CHANG 2 (11/11/2026): doc buoc hien tai tu cong thay vi dem chu ky.

    Do tren prod 11/11: 0/546 goi co ma workflow instance, nen `discover_transition` - viet
    tu 28/08 - CHUA CHAY THAT LAN NAO; moi luot ky tu thang 8 deu lay buoc bang dem chu ky.
    Dem chu ky dung voi DNTT (5/5 buoc deu ky) va sai voi hop dong (ke toan duyet khong ky),
    va sai ca voi DNTT khi co nguoi ky tay tren cong (00295, 29/09).

    'shadow' = hanh vi gui lenh GIU NGUYEN tung chu; chi them mot lan HOI (GET) song song va
    ghi lai cong noi gi, cong co dong y voi cach dem khong. Chuyen sang dung ket qua hoi cong
    la mot buoc RIENG, sau khi so lieu shadow sach - khong lam trong ban nay.
    'off' = khong hoi them gi (cong tat neu buoc hoi lam cham hoac gay loi).

    Gia tri la thi KHONG am tham tat: van 'shadow', vi shadow khong doi hanh vi gui.
    """
    # KHONG `or ""`: `bench set-config ... 0` luu so 0, va `0 or ""` la "" -> cong tat khong tat.
    raw = frappe.conf.get("ec_esign_transition_discovery")
    v = "" if raw is None else str(raw).strip().lower()
    if v in ("0", "false", "no", DISCOVERY_OFF):
        return DISCOVERY_OFF
    return DISCOVERY_SHADOW


def pick_forward_edge(transitions):
    """Canh DI TIEP (khong phai tu choi / huy) trong availableTransitions. (canh, None) hoac
    (None, ly_do).

    Khong chi dua vao `transitionType == "approve"`. Do tren cong 12/11/2026, quy trinh DNTT
    5 chu ky, buoc Ke toan truong (state -7): canh "Phe duyet" `-11` mang transitionType
    "normal" - CUNG kieu voi canh "Tu choi" `-12`. Khac nhau o cho canh di tiep KY
    (isSigned + processAction), canh tu choi khong. Luat cu (`_APPROVE_TYPES`) se tra
    "no_approve_transition" dung o buoc do.

    Nen: canh di tiep = transitionType approve, HOAC (isSigned va co processAction). Hai canh
    thoa -> khong chon thay ai, tra ly do. Khong canh nao -> tra ly do kem ten cac canh co.
    """
    rows = [t for t in (transitions or []) if isinstance(t, dict)]
    if not rows:
        return None, "no_available_transition"
    picks = [t for t in rows
             if (t.get("transition_type") or "") in _APPROVE_TYPES
             or (t.get("requires_signature") and t.get("process_action"))]
    if not picks:
        return None, "no_forward_transition:%s" % ",".join(
            str(t.get("transition_name") or t.get("transition_id") or "?") for t in rows)
    if len(picks) > 1:
        return None, "ambiguous_forward_transition:%s" % ",".join(
            str(t.get("transition_id")) for t in picks)
    t = picks[0]
    if t.get("transition_id") is None:
        return None, "incomplete_transition"
    return t, None


def shadow_probe(dsr, adapter, document_id):
    """Hoi cong buoc hien tai cua tai lieu - CHI DOC, MOT lan GET, khong bao gio nem loi.

    `GET /api/Workflow/instance/{ma tai lieu}?userId=` (xem SctsClient.
    get_workflow_instance_by_document): tra `currentStateId` + canh chuyen dang mo. Tra dict de
    ghi vao su kien.

    KHONG ghi gi vao goi: `workflow_instance_id()` doc `scts_workflow_instance_id` cho CA lenh
    ghi, nen luu no = doi duong gui lenh ky. Do 11-12/11: ma instance TRUNG ma tai lieu tren
    moi tai lieu da hoi, nen cung khong co gi de luu.
    """
    if adapter is None or not document_id:
        return {"ok": False, "why": "no_adapter_or_document"}
    if not hasattr(adapter, "workflow_state_for_document"):
        return {"ok": False, "why": "adapter_cannot_read_state"}
    try:
        state, why = adapter.workflow_state_for_document(document_id,
                                                         dsr.get("effective_scts_user_id"))
        if not state:
            return {"ok": False, "why": why}
        edge, why = pick_forward_edge(state.get("transitions"))
        out = {"ok": edge is not None, "why": why,
               "current_state_id": state.get("current_state_id"),
               "instance_is_document": (str(state.get("instance_id")).lower()
                                        == str(document_id).lower())
               if state.get("instance_id") else None,
               # Du truong cua MOI canh dang mo - de kiem luat chon canh tren quy trinh hop
               # dong (duyet khong ky, buoc doi tac, buoc cuoi) truoc khi tin no (QC 12/11).
               "edges": [{"id": t.get("transition_id"), "type": t.get("transition_type"),
                          "signed": bool(t.get("requires_signature")),
                          "pa": t.get("process_action"), "st": t.get("sign_type"),
                          "to": t.get("to_state"), "term": bool(t.get("terminal"))}
                         for t in (state.get("transitions") or [])][:10]}
        if edge is not None:
            out.update({"transition_id": edge.get("transition_id"),
                        "process_action": edge.get("process_action"),
                        "sign_type": edge.get("sign_type"),
                        # Duong chinh (discover_transition) tu choi canh thieu processAction
                        # ("incomplete_transition"). "ok" chi la cong TRA LOI duoc; "sendable"
                        # moi la gui duoc - so lieu shadow phai tach hai cai (QC 12/11).
                        "sendable": bool(edge.get("process_action"))})
        return out
    except Exception as exc:
        from ecentric_workspace.platform.esign.sanitize import safe_error
        return {"ok": False, "why": "probe_failed:%s" % safe_error(exc)}


def _same_transition(probe, cfg):
    """Cong va cach dem co chon CUNG mot canh khong. So ca ba truong: cung id ma khac
    processAction / signType van la ky sai o (ca 28/08: o 'Ky chinh' bo trong)."""
    def norm(v):
        return str(v if v is not None else "").strip().lower()
    return all(norm(probe.get(k)) == norm(cfg.get(k))
               for k in ("transition_id", "process_action", "sign_type"))


def plan_handover(dsr, profile_name, environment, stage=None, adapter=None, instance_id=None,
                  document_id=None):
    """Ke hoach gui cho luot ky nay + (shadow) cong noi gi. Xem `_plan_handover_core`.

    Lop boc nay KHONG doi ke hoach: `mode`, `to_users`, `config` la cua `_plan_handover_core`
    nguyen ven. No chi gan them `discovery_probe` de su kien ghi lai duoc.
    """
    plan = _plan_handover_core(dsr, profile_name, environment, stage=stage, adapter=adapter,
                               instance_id=instance_id, document_id=document_id)
    # Moi loi o phan quan sat dung lai O DAY. tasks.py boc lenh goi nay trong try va roi ve
    # POOL khi co loi - de mot loi quan sat lot ra la doi duong gui, dung dieu shadow cam lam.
    try:
        if transition_discovery_mode() != DISCOVERY_SHADOW:
            return plan
        if plan.get("reason") == "targeted_handover_disabled":
            return plan         # duong chinh da tat: khong ton them lenh goi nao
        probe = shadow_probe(dsr, adapter, document_id or instance_id)
        if probe.get("ok") and plan.get("mode") == "transition" and plan.get("config"):
            probe["agree"] = _same_transition(probe, plan["config"])
        plan["discovery_probe"] = probe
    except Exception as exc:
        plan["discovery_probe"] = {"ok": False, "why": "shadow_wrapper_failed:%s"
                                   % type(exc).__name__}
    return plan


def _plan_handover_core(dsr, profile_name, environment, stage=None, adapter=None,
                        instance_id=None, document_id=None):
    """What to send for this leg: {mode, ...}.

    mode == "transition" -> name the next handler explicitly (the governed path).
    mode == "pool"       -> provider decides the recipients; `reason` says why we had to.

    `instance_id` = ma WORKFLOW INSTANCE (Workflow GET / transition / users-for-transition);
    `document_id` = ma DOCUMENT (Document GET, de dem chu ky da co). Hai ma KHAC nhau tren
    eContract (package.workflow_instance_id). Truoc 08/09 provider_step_index nhan instance id
    -> GET /api/Document/{instanceId} 404 moi khi goi da co scts_workflow_instance_id -> khong
    dem duoc -> roi ve cau hinh ho so khong co vi tri buoc (lop loi "-9 cho moi buoc"). Khong
    truyen document_id thi dung instance_id nhu cu (goi cu chua co instance id thi hai ma bang
    nhau).
    """
    if not targeted_handover_enabled():
        return {"mode": "pool", "reason": "targeted_handover_disabled"}
    cfg = None
    why = None
    discovery_note = None
    if adapter is not None and instance_id:
        cfg, why = discover_transition(adapter, instance_id,
                                       dsr.get("effective_scts_user_id"))
    if cfg is None and why_is_refusal(why):
        # Nha cung cap noi ro KHONG duoc di: dung lai. Khac han voi "khong hoi duoc".
        return {"mode": "pool", "reason": why}
    if cfg is None and why:
        # Khong HOI duoc (mang loi, 4xx, adapter cu) thi van con cau hinh tren ho so lam duong
        # lui. Ro rang la kem hon - id co the sai o mot so cap - nhung van dich danh nguoi ky
        # tiep theo, con hon phat cho ca vai tro. Lan chay 28/08 rot thang ve pool va SCTS gui
        # cho BAY truong bo phan chi vi mot loi HTTP.
        discovery_note = why
    if cfg is not None:
        want = cfg.get("sign_type")
        have = _mapped_signature_type(dsr, environment)
        if cfg.get("requires_signature") and not signature_type_matches(want, have):
            return {"mode": "pool",
                    "reason": "signature_type_mismatch:need=%s have=%s" % (want, have or "?")}
    buoc = None
    source = SOURCE_DISCOVERED if cfg is not None else None
    if cfg is None:
        buoc, vi_sao_buoc = provider_step_index(adapter, document_id or instance_id)
        if buoc is None and vi_sao_buoc:
            discovery_note = "%s; vi tri buoc: %s" % (discovery_note or "-", vi_sao_buoc)
        cfg = resolve_transition_config(profile_name, dsr.get("action") or "Sign",
                                        stage=stage, step_index=buoc)
        # Dong theo vi tri buoc mang khoa `step_index`; dong mac dinh theo stage thi khong.
        source = (SOURCE_STEP_INDEX
                  if cfg and buoc is not None and cfg.get("step_index") is not None
                  and int(cfg["step_index"]) == int(buoc)
                  else SOURCE_PROFILE_DEFAULT)
    if not cfg:
        # Biet vi tri buoc ma khong co dong cau hinh => day la buoc NGOAI day da chup duoc.
        # Voi mau "5 chu ky" thi buoc do la KY CHINH: `signToken=1`, `hsmId=null`, tuc ky
        # bang OfficeSignTool tren may nguoi ky. Gui pool o day la hua mot viec khong the
        # lam - dung cai da de chan HOF treo 20 phut roi vao Manual Review.
        return {"mode": "pool",
                "reason": "no_transition_config:%s%s%s" % (
                    stage or "default",
                    (" buoc=%s" % buoc) if buoc is not None else "",
                    (" after " + discovery_note) if discovery_note else "")}

    ar = dsr.get("approval_request")
    level = dsr.get("request_level_no")
    if level is None:
        level = 0 if (dsr.get("actor_type") == "Requester") else _level_of(dsr)
    users = next_level_approvers(ar, level)
    if not users:
        if cfg.get("terminal"):
            # Final step: nobody comes after, and the config says so explicitly.
            return {"mode": "transition", "to_users": [], "config": cfg,
                    "transition_source": source}
        return {"mode": "pool", "reason": "no_next_level_approver"}

    ids, unmapped = provider_ids_for(users, environment)
    if not ids:
        return {"mode": "pool", "reason": "next_handler_unmapped:%s" % ",".join(unmapped)}

    # Chuoi duyet cua ERP KHONG bat buoc trung chuoi cua eContract, va khi lech thi eContract
    # im lang bo ca lenh - 2xx, khong dong workflow, khong chu ky.
    #
    # 28/08 20:25, EC-PAYR-2026-00034: ERP gui toUsers = [Lam (CEO), Hoan]. Khong gi xay ra.
    # Cung chung tu do, lenh cua portal voi toUsers MOT nguoi chay ngay. Buoc ke tiep la
    # "Truong bo phan"; Lam giu vai CEO nen khong nhan duoc buoc do.
    #
    # Nen hoi eContract truoc khi gui. `None` = khong hoi duoc (giu nguyen danh sach, ghi
    # lai ly do); mot tap RONG hoac loc het = bang chung that su rang khong ai nhan duoc,
    # luc do lui ve pool con hon gui mot lenh chac chan bi bo.
    dropped = []
    eligible = None
    if adapter is not None and instance_id and hasattr(adapter, "eligible_recipients"):
        eligible = adapter.eligible_recipients(
            instance_id, cfg.get("transition_id"), dsr.get("effective_scts_user_id"))
    if eligible is not None:
        keep = [i for i in ids if str(i) in eligible]
        dropped = [i for i in ids if str(i) not in eligible]
        if not keep:
            return {"mode": "pool",
                    "reason": "no_eligible_recipient:%d_de_xuat_0_duoc_nhan" % len(ids)}
        ids = keep

    out = {"mode": "transition", "to_users": ids, "config": cfg,
           "unmapped": unmapped, "erp_users": users}
    if dropped:
        # Bi loai KHONG duoc im lang: no co nghia chuoi duyet ERP va quy trinh eContract
        # dang lech nhau, va do la thu can nguoi sua chu khong phai code.
        out["dropped_not_eligible"] = dropped
    if eligible is None and adapter is not None and instance_id:
        out["recipients_unverified"] = True
    if discovery_note:
        # Dung duong lui thi phai NOI RA, khong de no trong nhu duong chinh dang chay tot.
        out["fallback_config"] = True
        out["discovery_error"] = discovery_note
    out["transition_source"] = source
    return out


def portal_stage_for(dsr):
    """Khoa `stage` cua dong cau hinh buoc cho chan nay o che do LAY BUOC TU CONG:
    "requester" cho chan nguoi lap, "level:<n>" cho cap duyet n cua ERP."""
    if dsr.get("actor_type") == "Requester":
        return "requester"
    level = dsr.get("request_level_no")
    if level is None:
        level = _level_of(dsr)
    return "level:%s" % int(level or 0)


def _configured_step(profile_name, action, stage):
    """Dong cau hinh buoc (action, stage) CHINH XAC tren ho so, hoac None. Khac
    resolve_transition_config: khong co dong mac dinh, va buoc KHONG KY khong co processAction
    van hop le (cong gui processAction null)."""
    if not profile_name:
        return None
    try:
        profile = frappe.get_doc("EC Digital Signature Profile", profile_name)
    except Exception:
        return None
    rows = [r for r in (profile.get("transitions") or [])
            if r.action == action and (r.stage or "").strip() == stage
            and r.transition_id is not None]
    if len(rows) != 1:
        return None
    r = rows[0]
    return {"transition_id": r.transition_id, "transition_name": r.transition_name or "",
            "process_action": r.process_action or "", "sign_type": r.sign_type or "",
            "terminal": bool(r.terminal)}


#: action cua dong cau hinh buoc theo action cua chan ky.
STEP_ACTION = {"Sign": "Sign", "Approve": "Forward"}


def plan_portal_step(dsr, state, profile_name, environment, adapter=None, instance_id=None):
    """Ke hoach gui buoc o che do LAY BUOC TU CONG (ho so bat `trust_portal_transitions`,
    12/11/2026, hop dong WF09).

    Buoc gui = dong cau hinh (action, stage "requester" | "level:<n>") tren ho so - transition
    id cua quy trinh la HANG SO theo quy trinh (WF09: -2 trinh KT, -3 KTTH, -4 KTT, -5 CEO
    chuyen doi tac; doc dinh nghia quy trinh tren cong 12/11). Cong chi dung de XAC NHAN: canh
    do PHAI dang mo trong availableTransitions; processAction / signType / co ky / buoc dich
    lay tu canh cua cong. KHONG doan theo transitionType: WF09 canh tu choi va canh doi tac ky
    deu la RETURN_CREATOR, canh duyet khong ky khong co loai rieng - luat "canh di tiep" cua
    DNTT khong dung o day.

    KHONG BAO GIO tra "pool", khong dem chu ky.
    Tra {mode: "transition", to_users, erp_users, config, state_before, to_state}
      | {mode: "wait", reason}   - cong chua toi buoc nay (canh chua mo): hoi lai sau
      | {mode: "stop", reason}   - can nguoi sua cau hinh / anh xa.
    """
    stage = portal_stage_for(dsr)
    action = STEP_ACTION.get(dsr.get("action") or "Sign")
    want = _configured_step(profile_name, action, stage)
    if not want:
        return {"mode": "stop", "reason": "no_step_config:%s/%s" % (action, stage)}
    edges = (state or {}).get("transitions") or []
    open_ = [t for t in edges if str(t.get("transition_id")) == str(want["transition_id"])]
    if not open_:
        return {"mode": "wait", "reason": "step_not_open:%s (dang mo: %s)" % (
            want["transition_id"], ",".join(str(t.get("transition_id")) for t in edges) or "-")}
    edge = open_[0]
    cfg = {"transition_id": want["transition_id"],
           "transition_name": edge.get("transition_name") or want["transition_name"],
           "process_action": edge.get("process_action") or want["process_action"],
           "sign_type": edge.get("sign_type") or want["sign_type"],
           "terminal": bool(edge.get("terminal")) or want["terminal"],
           "requires_signature": bool(edge.get("requires_signature"))}
    out = {"config": cfg, "state_before": str(state.get("current_state_id") or ""),
           "to_state": str(edge.get("to_state") or ""),
           "transition_source": SOURCE_DISCOVERED, "stage": stage}
    ar = dsr.get("approval_request")
    if stage == "requester":
        # Nguoi lap trinh cho cap cong DAU TIEN - chinh la cap dang mo (portal_steps), khong
        # phai cap 1 (vd Truong phong chi duyet tren ERP).
        level = int(frappe.db.get_value(AR, ar, "current_level") or 0) - 1
    else:
        level = int(stage.split(":")[1])
    users = next_level_approvers(ar, level)
    if not users:
        if cfg["terminal"]:
            out.update({"mode": "transition", "to_users": [], "erp_users": []})
            return out
        # Buoc ke tiep tren cong khong co nguoi ERP (vd CEO `-5` sang DOI TAC). Chua lam (PR-D):
        # DUNG, khong gui toUsers rong (= ca nhom vai tro). Ho so WF09 KHONG duoc bat truoc PR-D.
        return {"mode": "stop", "reason": "no_next_level_approver:partner_step_not_supported"}
    ids, unmapped = provider_ids_for(users, environment)
    if unmapped or not ids:
        # Thieu anh xa mot nguoi = cong giao buoc cho thieu nguoi. Dung lai, noi ro ai.
        return {"mode": "stop", "reason": "next_handler_unmapped:%s" % ",".join(unmapped)}
    if adapter is not None and instance_id and hasattr(adapter, "eligible_recipients"):
        eligible = adapter.eligible_recipients(instance_id, cfg.get("transition_id"),
                                               dsr.get("effective_scts_user_id"))
        if eligible is not None:
            dropped = [i for i in ids if str(i) not in eligible]
            if dropped:
                # Chuoi ERP va quy trinh cong lech nhau: nguoi ERP chon khong nhan duoc buoc nay.
                return {"mode": "stop", "reason": "recipient_not_eligible:%s"
                                                  % ",".join(str(i) for i in dropped)}
        else:
            out["recipients_unverified"] = True
    out.update({"mode": "transition", "to_users": ids, "erp_users": users})
    return out


def _level_of(dsr):
    rl = dsr.get("request_level")
    if not rl:
        return 0
    return int(frappe.db.get_value(LEVEL, rl, "level_no") or 0)
