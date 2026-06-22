# Copyright (c) 2026, eCentric and contributors
"""eCentric ERP Bot -- Microsoft Teams 1:1 PERSONAL proactive messaging.

This is the PRIMARY Teams delivery path. The bot sends a private message directly to each
recipient (personal scope), never to a channel. Flow:

    ERP user email
      -> Microsoft Entra user (Graph)        [providers.graph.email_to_aad_object_id]
      -> aadObjectId
      -> (ensure the bot is installed for the user, Graph proactive install)
      -> Bot Framework conversation reference (create or reuse, stored in
         EC Teams Conversation)
      -> proactive activity (Adaptive Card) via Bot Framework REST

Conversation references are captured either when the user first opens/installs the bot
(the bot's own web service POSTs them to api.save_teams_conversation) OR provisioned on
demand here via Graph install + Bot Framework create-conversation.

Credentials come from site_config (NEVER hardcoded):
    ec_teams_bot_app_id, ec_teams_bot_app_password, ec_teams_bot_id
    ec_teams_bot_default_service_url   (e.g. https://smba.trafficmanager.net/<region>/)
Graph credentials are read by providers.graph.

Config-gated + fail-open: without credentials nothing runs and the caller records dry-run;
a delivery failure never affects the ERP business transaction.
"""
import json

import frappe

from ecentric_workspace.notification_center.providers import graph as graphmod

CONV_DT = "EC Teams Conversation"
TIMEOUT = 15
_BOT_LOGIN_BASE = "https://login.microsoftonline.com/"


def bot_config():
    conf = frappe.get_conf() if hasattr(frappe, "get_conf") else {}
    return {
        "app_id": conf.get("ec_teams_bot_app_id") or "",
        "app_password": conf.get("ec_teams_bot_app_password") or "",
        "bot_id": conf.get("ec_teams_bot_id") or "",
        "default_service_url": conf.get("ec_teams_bot_default_service_url") or "",
        # single-tenant Azure Bot: token authority is the tenant (falls back to graph tenant,
        # then to the multi-tenant botframework.com authority if neither is set).
        "tenant_id": conf.get("ec_teams_bot_tenant_id") or conf.get("ec_graph_tenant_id") or "",
    }


def is_configured(cfg=None):
    cfg = cfg or bot_config()
    return bool(cfg["app_id"] and cfg["app_password"])


# --------------------------------------------------------- conversation reference store
def resolve_conversation(recipient):
    """Return the stored conversation reference dict for a user, or None."""
    try:
        if not frappe.db.exists(CONV_DT, recipient):
            return None
        doc = frappe.get_doc(CONV_DT, recipient)
        if not doc.get("conversation_id") or not doc.get("service_url"):
            return None
        return {
            "service_url": doc.get("service_url"),
            "conversation_id": doc.get("conversation_id"),
            "bot_id": doc.get("bot_id"),
            "aad_object_id": doc.get("aad_object_id"),
            "tenant_id": doc.get("tenant_id"),
        }
    except Exception:
        return None


def save_conversation_reference(user, reference, aad_object_id=None, installed=1):
    """Upsert the conversation reference for a user (called by the bot's ingest endpoint or
    by on-demand provisioning). `reference` is the Bot Framework conversationReference."""
    ref = reference if isinstance(reference, dict) else (json.loads(reference or "{}"))
    conv = (ref.get("conversation") or {})
    if frappe.db.exists(CONV_DT, user):
        doc = frappe.get_doc(CONV_DT, user)
    else:
        doc = frappe.get_doc({"doctype": CONV_DT, "user": user})
    doc.service_url = ref.get("serviceUrl") or doc.get("service_url")
    doc.conversation_id = conv.get("id") or doc.get("conversation_id")
    doc.bot_id = (ref.get("bot") or {}).get("id") or doc.get("bot_id")
    doc.tenant_id = conv.get("tenantId") or ref.get("tenantId") or doc.get("tenant_id")
    if aad_object_id:
        doc.aad_object_id = aad_object_id
    doc.conversation_reference = json.dumps(ref)
    doc.installed = installed
    doc.last_synced_at = frappe.utils.now_datetime()
    doc.last_error = ""
    doc.save(ignore_permissions=True)
    return doc.name


# ----------------------------------------------------------------- Bot Framework calls
def get_bot_token(cfg=None):
    """App token for Bot Framework (scope api.botframework.com). Returns (ok, token/err)."""
    cfg = cfg or bot_config()
    if not is_configured(cfg):
        return False, "NO_BOT_CREDENTIAL"
    import requests
    # single-tenant bot -> tenant authority; else multi-tenant botframework.com authority
    authority = _BOT_LOGIN_BASE + (cfg.get("tenant_id") or "botframework.com") + "/oauth2/v2.0/token"
    try:
        r = requests.post(authority, data={
            "grant_type": "client_credentials", "client_id": cfg["app_id"],
            "client_secret": cfg["app_password"],
            "scope": "https://api.botframework.com/.default"}, timeout=TIMEOUT)
        if r.status_code == 200:
            return True, r.json().get("access_token")
        return False, "BOTTOKEN_" + str(r.status_code)
    except Exception as e:
        return False, "BOTTOKEN_EXC_" + type(e).__name__


def create_conversation(aad_object_id, tenant_id, service_url, cfg=None, token=None):
    """Create a 1:1 conversation with the user (requires the bot installed for the user).
    Returns (ok, conversation_id_or_errcode)."""
    cfg = cfg or bot_config()
    service_url = service_url or cfg["default_service_url"]
    if not service_url:
        return False, "NO_SERVICE_URL"
    if not token:
        ok, token = get_bot_token(cfg)
        if not ok:
            return False, token
    import requests
    try:
        body = {"bot": {"id": cfg["bot_id"]},
                "members": [{"id": aad_object_id, "aadObjectId": aad_object_id}],
                "channelData": {"tenant": {"id": tenant_id}}, "isGroup": False}
        r = requests.post(service_url.rstrip("/") + "/v3/conversations",
                          json=body, headers={"Authorization": "Bearer " + token},
                          timeout=TIMEOUT)
        if r.status_code in (200, 201):
            return True, r.json().get("id")
        return False, "CONVCREATE_" + str(r.status_code)
    except Exception as e:
        return False, "CONVCREATE_EXC_" + type(e).__name__


def _post_activity(conv, activity, cfg=None, token=None):
    """POST one activity into an existing conversation. Returns (ok, code, redacted_err)."""
    cfg = cfg or bot_config()
    if not token:
        ok, token = get_bot_token(cfg)
        if not ok:
            return False, token, "bot token failed"
    import requests
    try:
        url = conv["service_url"].rstrip("/") + "/v3/conversations/" + conv["conversation_id"] + "/activities"
        r = requests.post(url, json=activity,
                          headers={"Authorization": "Bearer " + token}, timeout=TIMEOUT)
        if 200 <= r.status_code < 300:
            return True, str(r.status_code), ""
        return False, str(r.status_code), "bot activity non-2xx"
    except Exception as e:
        return False, "EXC", type(e).__name__


def provision_conversation(recipient, cfg=None):
    """On-demand: map email -> aadObjectId (Graph), ensure the bot is installed, then
    create a conversation. Returns (ok, conv_dict_or_None, code, err)."""
    cfg = cfg or bot_config()
    if not graphmod.is_configured():
        return False, None, "NO_GRAPH_FOR_PROVISION", "Graph not configured to provision"
    ok, oid = graphmod.email_to_aad_object_id(recipient)
    if not ok:
        return False, None, oid, "email->aadObjectId failed"
    ok, status = graphmod.ensure_bot_installed(oid)
    if not ok:
        return False, None, status, "bot install failed/blocked"
    gcfg = graphmod.graph_config()
    ok, conv_id = create_conversation(oid, gcfg["tenant_id"], cfg["default_service_url"], cfg)
    if not ok:
        return False, None, conv_id, "create conversation failed"
    conv = {"service_url": cfg["default_service_url"], "conversation_id": conv_id,
            "bot_id": cfg["bot_id"], "aad_object_id": oid, "tenant_id": gcfg["tenant_id"]}
    try:
        save_conversation_reference(recipient, {
            "serviceUrl": conv["service_url"], "conversation": {"id": conv_id, "tenantId": gcfg["tenant_id"]},
            "bot": {"id": cfg["bot_id"]}}, aad_object_id=oid, installed=1)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "save_conversation_reference")
    return True, conv, "", ""


def send_personal(recipient, activity, cfg=None):
    """Deliver one personal proactive message. Returns (outcome, provider, code, err) where
    outcome in {'sent','retry','skip'}. 'skip' = not installed / blocked / not provisionable
    (no retry); 'retry' = transient (token/network/5xx)."""
    cfg = cfg or bot_config()
    if not is_configured(cfg):
        return ("skip", "teams_bot", "NO_BOT_CREDENTIAL", "Teams bot not configured")
    conv = resolve_conversation(recipient)
    if not conv:
        ok, conv, code, err = provision_conversation(recipient, cfg)
        if not ok:
            return ("skip", "teams_bot", code, err)     # e.g. NOT installed -> clear skip
    ok, code, err = _post_activity(conv, activity, cfg)
    if ok:
        return ("sent", "teams_bot", "", "")
    if str(code) == "403":
        return ("skip", "teams_bot", "BOT_BLOCKED", "user blocked the bot")
    if str(code) == "404":
        return ("skip", "teams_bot", "CONVERSATION_GONE", "conversation no longer exists")
    return ("retry", "teams_bot", str(code), err)
