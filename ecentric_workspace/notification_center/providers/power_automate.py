# Copyright (c) 2026, eCentric and contributors
"""Teams delivery via Power Automate + Microsoft Copilot Studio agent.

ERP -> secure Power Automate HTTP trigger (OAuth, Specific-users-in-tenant) -> Teams connector
"Post as Microsoft Copilot Studio agent / Chat with agent" -> delivery result -> ERP Delivery Log.

ERP remains the source of truth for recipients, dedupe, retries, audit and action URLs; this
provider only POSTs the event and classifies the flow's response. It is config-gated and
fail-open: a failure here only affects the Teams Delivery Log row, never ERP toast/sound/native.

site_config (NOTHING hardcoded; flow URL + secret are sensitive, never logged/committed):
    ec_pa_flow_url            HTTP trigger URL of the flow
    ec_pa_oauth_tenant_id     (falls back to ec_teams_bot_tenant_id / ec_graph_tenant_id)
    ec_pa_oauth_client_id     ERP service-principal app id
    ec_pa_oauth_client_secret ERP service-principal secret
    ec_pa_oauth_audience      default "https://service.flow.microsoft.com/"
"""
TIMEOUT = 20
_LOGIN = "https://login.microsoftonline.com/"


def pa_config():
    import frappe
    conf = frappe.get_conf() if hasattr(frappe, "get_conf") else {}
    return {
        "flow_url": conf.get("ec_pa_flow_url") or "",
        "tenant_id": (conf.get("ec_pa_oauth_tenant_id") or conf.get("ec_teams_bot_tenant_id")
                      or conf.get("ec_graph_tenant_id") or ""),
        "client_id": conf.get("ec_pa_oauth_client_id") or "",
        "client_secret": conf.get("ec_pa_oauth_client_secret") or "",
        "audience": conf.get("ec_pa_oauth_audience") or "https://service.flow.microsoft.com/",
    }


def is_configured(cfg=None):
    cfg = cfg or pa_config()
    return bool(cfg["flow_url"] and cfg["tenant_id"] and cfg["client_id"] and cfg["client_secret"])


def get_pa_token(cfg=None):
    """client_credentials token for the Power Automate / Flow service.

    Power Automate **public cloud** requires the Azure AD **v1** token endpoint with a
    ``resource`` parameter so the issued token carries ``aud = https://service.flow.microsoft.com/``
    *with the trailing slash*. The v2 endpoint + ``scope=<resource>/.default`` drops the trailing
    slash (aud = ...microsoft.com, no slash) and the flow trigger rejects it with 403. So we MUST
    use:
        POST https://login.microsoftonline.com/{tenant}/oauth2/token
             grant_type=client_credentials, resource=https://service.flow.microsoft.com/
    Do NOT switch this to /oauth2/v2.0/token or scope=<resource>/.default for Power Automate.

    Returns (ok, token_or_errcode). Secret/token are never logged."""
    cfg = cfg or pa_config()
    if not (cfg["tenant_id"] and cfg["client_id"] and cfg["client_secret"]):
        return False, "NO_PA_CREDENTIAL"
    import requests
    # v1 audience: keep the resource EXACTLY as configured (trailing slash preserved).
    resource = cfg["audience"]
    try:
        r = requests.post(
            _LOGIN + cfg["tenant_id"] + "/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "resource": resource,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return True, r.json().get("access_token")
        # status code only -- never echo the response body (may contain token/secret material)
        return False, "PATOKEN_" + str(r.status_code)
    except Exception as e:
        return False, "PATOKEN_EXC_" + type(e).__name__


def _post_flow(url, payload, token):
    """POST the event to the flow. Returns (status_code, body_dict). Never logs url/token."""
    import requests
    r = requests.post(url, json=payload,
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                      timeout=TIMEOUT)
    try:
        body = r.json()
    except Exception:
        body = {}
    return r.status_code, body


def send_event(payload, cfg=None):
    """Deliver one event via the flow. Returns (outcome, provider, code, err) where outcome in
    {'sent','retry','skip'}. Maps Copilot proactive status 200/100/300 and connector/auth/
    throttling errors to retryable vs permanent."""
    cfg = cfg or pa_config()
    prov = "power_automate_copilot"
    if not is_configured(cfg):
        return ("skip", prov, "NO_PA_CREDENTIAL", "Power Automate not configured")
    ok, token = get_pa_token(cfg)
    if not ok:
        # token endpoint failure is transient (refresh next attempt)
        return ("retry", prov, token, "oauth token failed")
    try:
        status, body = _post_flow(cfg["flow_url"], payload, token)
    except Exception as e:
        return ("retry", prov, "EXC", type(e).__name__)

    # transport-level classification
    if status == 401:
        return ("retry", prov, "PA_401", "unauthorized (token)")
    if status == 403:
        return ("skip", prov, "PA_403", "forbidden (service principal not allowed on trigger)")
    if status == 429:
        return ("retry", prov, "PA_429", "throttled")
    if 500 <= status < 600:
        return ("retry", prov, "PA_" + str(status), "flow 5xx")
    if not (200 <= status < 300):
        return ("skip", prov, "PA_" + str(status), "flow non-2xx (e.g. malformed payload)")

    # 2xx -> Copilot proactive status mapping from the structured body
    code = str((body or {}).get("copilot_code") or (body or {}).get("status") or "")
    if code in ("200", "delivered"):
        return ("sent", prov, "200", "")
    if code in ("100", "not_installed"):
        return ("skip", prov, "NOT_INSTALLED", "recipient has not installed the agent")
    if code in ("300", "skipped"):
        return ("skip", prov, "SKIPPED_ACTIVE_CONVERSATION",
                "recipient in active conversation; policy skipped")
    if (body or {}).get("retryable") is True:
        return ("retry", prov, "PA_UNKNOWN", "retryable per flow")
    return ("skip", prov, "PA_UNKNOWN_BODY", "unrecognized flow response")


def build_payload(doc):
    """Build the ERP->flow JSON contract from a Delivery Log doc."""
    return {
        "event_id": doc.get("event_id"),
        "dedupe_key": doc.get("dedupe_key"),
        "event_type": doc.get("event_type"),
        "severity": doc.get("severity"),
        "recipient": doc.get("recipient"),          # UPN / email
        "title": doc.get("title") or "",
        "message": doc.get("message") or "",
        "action_url": doc.get("action_url") or "",   # absolute ERP deep link
        "reference_doctype": doc.get("reference_doctype") or "",
        "reference_name": doc.get("reference_name") or "",
    }
