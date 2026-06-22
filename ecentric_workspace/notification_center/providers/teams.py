# Copyright (c) 2026, eCentric and contributors
"""Microsoft Teams delivery dispatcher (Notification Delivery v1).

PRIMARY path = the eCentric ERP Bot sending a 1:1 PERSONAL proactive message to the
recipient (providers.teams_bot). The channel **webhook** is an OPTIONAL fallback used ONLY
for system_critical broadcasts -- it is a channel post, never described as a personal DM.

Provider modes (site_config `ec_teams_provider`, NOTHING hardcoded):
    "disabled" (default) | "dryrun"  -> record dry-run, send nothing
    "teams_bot"                      -> personal bot (needs ec_teams_bot_* + Graph creds)
    "webhook"                        -> system_critical channel fallback only
Both may be configured together (bot primary + webhook system_critical safety net).

Teams is always a background job (frappe.enqueue), never inline in the business
transaction. deliver() is the enqueued entry point; it updates the EC Notification Delivery
Log and applies bounded retry. Secrets are never logged. Fail-open by construction.
"""
import json
import re as _re

import frappe

from ecentric_workspace.notification_center.providers import teams_bot

DELIVERY_DT = "EC Notification Delivery Log"
MAX_ATTEMPTS = 4
TIMEOUT = 15
_RETRY_BACKOFF_MIN = (1, 5, 30)  # minutes between attempts 1->2, 2->3, 3->4


def get_config():
    conf = frappe.get_conf() if hasattr(frappe, "get_conf") else {}
    provider = (conf.get("ec_teams_provider") or "disabled").strip().lower()
    return {"provider": provider, "webhook_url": conf.get("ec_teams_webhook_url") or ""}


def _plain(s):
    """Strip any HTML and collapse whitespace -> Teams gets plain text only."""
    if not s:
        return ""
    return _re.sub(r"\s+", " ", _re.sub(r"<[^>]*>", " ", str(s))).strip()


def _abs_url(url):
    """Action.OpenUrl needs an absolute https URL; action_url is a same-origin path."""
    u = str(url or "")
    if not u:
        return ""
    if u.startswith("http://") or u.startswith("https://"):
        return u
    try:
        return frappe.utils.get_url().rstrip("/") + u
    except Exception:
        return u


def _doc_payload(doc):
    return {"title": doc.get("title") or "", "message": doc.get("message") or "",
            "event_type": doc.get("event_type"), "severity": doc.get("severity"),
            "action_url": doc.get("action_url") or "", "actor": doc.get("actor") or "",
            "recipient": doc.get("recipient") or "", "deadline": doc.get("deadline") or ""}


# ----------------------------------------------------- personal bot Adaptive Card
def build_personal_activity(d):
    """Bot Framework message activity carrying an Adaptive Card for a 1:1 personal message:
    event type, title, short content, assigner/requester, deadline, 'Mở trong ERP' button."""
    title = _plain(d.get("title") or d.get("event_type") or "Thông báo")
    desc = _plain(d.get("message") or "")
    facts = []
    if d.get("actor"):
        facts.append({"title": "Người giao/yêu cầu:", "value": str(d["actor"])})
    if d.get("deadline"):
        facts.append({"title": "Hạn:", "value": str(d["deadline"])})
    if d.get("event_type"):
        facts.append({"title": "Loại:", "value": str(d["event_type"])})
    body = [{"type": "TextBlock", "text": title, "weight": "Bolder",
             "size": "Medium", "wrap": True}]
    if desc:
        body.append({"type": "TextBlock", "text": desc, "wrap": True})
    if facts:
        body.append({"type": "FactSet", "facts": facts})
    card = {"type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4", "body": body}
    url = _abs_url(d.get("action_url"))
    if url:
        card["actions"] = [{"type": "Action.OpenUrl", "title": "Mở trong ERP", "url": url}]
    return {"type": "message",
            "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive",
                             "content": card}]}


# ----------------------------------------------------- channel webhook MessageCard
def build_card(d):
    """MessageCard for the system_critical CHANNEL webhook fallback (NOT a personal DM).
    Names the intended recipient so the channel knows who must act."""
    title = _plain(d.get("title") or d.get("event_type") or "Notification")
    desc = _plain(d.get("message") or "")
    facts = []
    if d.get("recipient"):
        facts.append({"name": "For", "value": str(d["recipient"])})
    if d.get("actor"):
        facts.append({"name": "From", "value": str(d["actor"])})
    if d.get("deadline"):
        facts.append({"name": "Deadline", "value": str(d["deadline"])})
    if d.get("event_type"):
        facts.append({"name": "Type", "value": str(d["event_type"])})
    card = {"@type": "MessageCard", "@context": "https://schema.org/extensions",
            "summary": title, "themeColor": _theme(d.get("severity")),
            "sections": [{"activityTitle": title, "text": desc, "facts": facts}]}
    url = _abs_url(d.get("action_url"))
    if url:
        card["potentialAction"] = [{"@type": "OpenUri", "name": "Open in ERP",
                                    "targets": [{"os": "default", "uri": url}]}]
    return card


def _theme(severity):
    return {"urgent": "D13438", "action_required": "FFB900"}.get(severity, "0078D4")


def _post_webhook(url, card):
    """POST the card to the Teams channel webhook. Returns (ok, code, redacted_error)."""
    import requests
    try:
        r = requests.post(url, data=json.dumps(card),
                          headers={"Content-Type": "application/json"}, timeout=TIMEOUT)
        if 200 <= r.status_code < 300:
            return True, str(r.status_code), ""
        return False, str(r.status_code), "teams webhook non-2xx"
    except Exception as e:
        return False, "EXC", type(e).__name__


def _mark_sent(doc, provider):
    doc.status = "Sent"
    doc.provider = provider
    doc.sent_at = frappe.utils.now_datetime()
    doc.error_code = ""
    doc.error_message = ""


def _mark_retry_or_fail(doc, provider, code, err):
    doc.provider = provider or "teams_bot"
    if (doc.attempt_count or 0) >= MAX_ATTEMPTS:
        doc.status = "Failed"
        doc.next_retry_at = None
    else:
        doc.status = "Failed"
        mins = _RETRY_BACKOFF_MIN[min((doc.attempt_count or 1) - 1, len(_RETRY_BACKOFF_MIN) - 1)]
        doc.next_retry_at = frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=mins)
    doc.error_code = code or "UNKNOWN"
    doc.error_message = err or ""


def deliver(delivery_log):
    """Enqueued entry point. Delivers one Teams notification (personal bot primary; channel
    webhook only as a system_critical fallback) and records the outcome. Idempotent:
    already-Sent rows are not resent."""
    try:
        doc = frappe.get_doc(DELIVERY_DT, delivery_log)
    except Exception:
        return
    if doc.get("status") == "Sent":
        return

    cfg = get_config()
    botcfg = teams_bot.bot_config()
    doc.attempt_count = (doc.attempt_count or 0) + 1
    doc.last_attempt_at = frappe.utils.now_datetime()

    enabled = cfg["provider"] not in ("disabled", "dryrun")
    is_sc = doc.get("event_type") == "system_critical"
    use_bot = enabled and cfg["provider"] == "teams_bot" and teams_bot.is_configured(botcfg)
    use_webhook_sc = enabled and is_sc and bool(cfg["webhook_url"])

    if not use_bot and not use_webhook_sc:
        # No production credential for the applicable path -> never invent an endpoint.
        doc.provider = "dryrun"
        doc.status = "Skipped"
        doc.error_code = "NO_CREDENTIAL"
        doc.error_message = "Teams bot not configured (dry-run)."
        doc.save(ignore_permissions=True)
        return

    payload = _doc_payload(doc)
    outcome = provider = code = err = None

    # 1) PRIMARY: personal 1:1 bot
    if use_bot:
        outcome, provider, code, err = teams_bot.send_personal(
            doc.get("recipient"), build_personal_activity(payload), botcfg)
        if outcome == "sent":
            _mark_sent(doc, provider)
            doc.save(ignore_permissions=True)
            return

    # 2) FALLBACK: system_critical channel webhook (broadcast, NOT a personal DM)
    if use_webhook_sc:
        wok, wcode, werr = _post_webhook(cfg["webhook_url"], build_card(payload))
        if wok:
            _mark_sent(doc, ((provider + "+webhook") if provider else "webhook"))
            doc.save(ignore_permissions=True)
            return
        if outcome is None:                       # webhook-only path failed transiently
            outcome, provider, code, err = "retry", "webhook", wcode, werr

    # 3) not sent -> Skipped (bot not installed / blocked) or Failed+retry (transient)
    if outcome == "skip":
        doc.provider = provider or "teams_bot"
        doc.status = "Skipped"
        doc.next_retry_at = None
        doc.error_code = code or "SKIPPED"
        doc.error_message = err or ""
    else:
        _mark_retry_or_fail(doc, provider, code, err)
    doc.save(ignore_permissions=True)


def process_teams_retries():
    """Scheduler entry: re-enqueue Teams deliveries that failed and are due for retry.
    Bounded by MAX_ATTEMPTS; idempotent (re-running finds nothing new)."""
    now = frappe.utils.now_datetime()
    rows = frappe.get_all(DELIVERY_DT, filters={
        "channel": "teams", "status": "Failed",
        "next_retry_at": ["<=", now],
        "attempt_count": ["<", MAX_ATTEMPTS],
    }, pluck="name", limit=200)
    for nm in rows:
        try:
            frappe.enqueue("ecentric_workspace.notification_center.providers.teams.deliver",
                           queue="default", delivery_log=nm)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "process_teams_retries")
    return {"requeued": len(rows)}
