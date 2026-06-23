# Copyright (c) 2026, eCentric and contributors
"""Microsoft Graph helper for the Teams notification bot.

Graph is used ONLY to (a) map an ERP user email -> Microsoft Entra user -> aadObjectId,
and (b) proactively install the Teams app/bot for a user when it is missing (the app\ninstalls ITSELF, so the least-privilege APP permission is\nTeamsAppInstallation.ReadWriteSelfForUser.All, plus User.Read.All for the mapping).\nGraph is NOT
used to send chat messages (no app-only chatMessage send) -- delivery goes through the Bot
Framework proactive path (providers.teams_bot).

All credentials come from site_config (NEVER hardcoded):
    ec_graph_tenant_id, ec_graph_client_id, ec_graph_client_secret
    ec_teams_app_external_id   (the Teams app id from the manifest, for install binding)

Every function is config-gated and returns a clear (ok, value/error) tuple; nothing runs
without credentials, so the sandbox stays in dry-run.
"""
import frappe

TIMEOUT = 15
_GRAPH = "https://graph.microsoft.com/v1.0"
_LOGIN = "https://login.microsoftonline.com"


def graph_config():
    """Graph application identity. IDENTITY MODEL: ONE single-tenant App Registration is used
    for BOTH the Azure Bot and Graph -- required because TeamsAppInstallation.ReadWriteSelfForUser.All
    lets the app install ITSELF, so the Graph caller must be the same app as the bot. The Graph
    keys therefore DEFAULT to the bot's identity; set ec_graph_* only if you deliberately split
    them (not recommended -- self-install would break)."""
    conf = frappe.get_conf() if hasattr(frappe, "get_conf") else {}
    bot_app = conf.get("ec_teams_bot_app_id") or ""
    bot_secret = conf.get("ec_teams_bot_app_password") or ""
    bot_tenant = conf.get("ec_teams_bot_tenant_id") or ""
    return {
        "tenant_id": conf.get("ec_graph_tenant_id") or bot_tenant or "",
        "client_id": conf.get("ec_graph_client_id") or bot_app or "",
        "client_secret": conf.get("ec_graph_client_secret") or bot_secret or "",
        "teams_app_external_id": conf.get("ec_teams_app_external_id") or "",
    }


def identity_aligned():
    """True when the resolved Graph client_id == the bot app id (the single-identity model
    required for self-install). Used as a readiness check before enabling Teams."""
    from ecentric_workspace.notification_center.providers import teams_bot
    gid = graph_config().get("client_id")
    return bool(gid) and gid == teams_bot.bot_config().get("app_id")


def is_configured(cfg=None):
    cfg = cfg or graph_config()
    return bool(cfg["tenant_id"] and cfg["client_id"] and cfg["client_secret"])


def get_app_token(cfg=None):
    """App-only Graph token (client_credentials). Returns (ok, token_or_errcode)."""
    cfg = cfg or graph_config()
    if not is_configured(cfg):
        return False, "NO_GRAPH_CREDENTIAL"
    import requests
    try:
        r = requests.post(
            _LOGIN + "/" + cfg["tenant_id"] + "/oauth2/v2.0/token",
            data={"client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                  "scope": "https://graph.microsoft.com/.default",
                  "grant_type": "client_credentials"},
            timeout=TIMEOUT)
        if r.status_code == 200:
            return True, r.json().get("access_token")
        return False, "TOKEN_" + str(r.status_code)     # never echo body/secret
    except Exception as e:
        return False, "TOKEN_EXC_" + type(e).__name__


def email_to_aad_object_id(email, token=None, cfg=None):
    """Resolve ERP user email -> Entra user aadObjectId. Returns (ok, oid_or_errcode)."""
    cfg = cfg or graph_config()
    if not token:
        ok, token = get_app_token(cfg)
        if not ok:
            return False, token
    import requests
    try:
        r = requests.get(_GRAPH + "/users/" + email + "?$select=id",
                         headers={"Authorization": "Bearer " + token}, timeout=TIMEOUT)
        if r.status_code == 200:
            return True, r.json().get("id")
        return False, "USER_" + str(r.status_code)
    except Exception as e:
        return False, "USER_EXC_" + type(e).__name__


def aad_object_id_to_email(aad_object_id, token=None, cfg=None):
    """Reverse map Entra aadObjectId -> ERP email (mail or userPrincipalName). Used by the
    validated messaging endpoint to map an inbound activity's user to a Frappe User.
    Returns (ok, email_or_errcode)."""
    cfg = cfg or graph_config()
    if not token:
        ok, token = get_app_token(cfg)
        if not ok:
            return False, token
    import requests
    try:
        r = requests.get(_GRAPH + "/users/" + aad_object_id + "?$select=userPrincipalName,mail",
                         headers={"Authorization": "Bearer " + token}, timeout=TIMEOUT)
        if r.status_code == 200:
            j = r.json()
            return True, (j.get("mail") or j.get("userPrincipalName"))
        return False, "USER_" + str(r.status_code)
    except Exception as e:
        return False, "USER_EXC_" + type(e).__name__


def ensure_bot_installed(aad_object_id, token=None, cfg=None):
    """Proactively install the Teams app/bot for the user (Graph
    /users/{id}/teamwork/installedApps). Idempotent: an already-installed app returns ok.
    Returns (ok, status_or_errcode)."""
    cfg = cfg or graph_config()
    if not cfg["teams_app_external_id"]:
        return False, "NO_TEAMS_APP_ID"
    if not token:
        ok, token = get_app_token(cfg)
        if not ok:
            return False, token
    import requests
    try:
        body = {"teamsApp@odata.bind":
                _GRAPH + "/appCatalogs/teamsApps/" + cfg["teams_app_external_id"]}
        r = requests.post(
            _GRAPH + "/users/" + aad_object_id + "/teamwork/installedApps",
            json=body, headers={"Authorization": "Bearer " + token}, timeout=TIMEOUT)
        if r.status_code in (200, 201):
            return True, "installed"
        if r.status_code == 409:
            return True, "already_installed"     # idempotent
        return False, "INSTALL_" + str(r.status_code)
    except Exception as e:
        return False, "INSTALL_EXC_" + type(e).__name__
