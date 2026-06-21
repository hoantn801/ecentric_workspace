# Copyright (c) 2026, eCentric and contributors
"""Microsoft Teams delivery adapter (Notification Delivery v1).

Config-driven -- NOTHING is hardcoded. Reads provider + credentials from site_config:
    ec_teams_provider      : "disabled" (default) | "dryrun" | "webhook" | "graph"
    ec_teams_webhook_url    : Teams Incoming Webhook / Workflow URL   (webhook mode)
    ec_teams_graph_*        : reserved for a future Graph chatMessage sender (graph mode)

When no production credential is configured the adapter runs in DRYRUN: it builds the
exact payload it WOULD send and records the delivery as 'Skipped' (provider=dryrun) --
it never invents an endpoint. The secret is never logged and never sent to the browser.

Teams is always invoked from a background job (frappe.enqueue), never in the request
transaction. deliver() is the enqueued entry point; it updates the EC Notification
Delivery Log row and applies bounded retry.
"""
import json

import frappe

DELIVERY_DT = "EC Notification Delivery Log"
MAX_ATTEMPTS = 4
TIMEOUT = 15
_RETRY_BACKOFF_MIN = (1, 5, 30)  # minutes between attempts 1->2, 2->3, 3->4


def get_config():
    conf = frappe.get_conf() if hasattr(frappe, "get_conf") else {}
    provider = (conf.get("ec_teams_provider") or "disabled").strip().lower()
    return {
        "provider": provider,
        "webhook_url": conf.get("ec_teams_webhook_url") or "",
    }


import re as _re

def _plain(s):
    """Strip any HTML and collapse whitespace -> Teams gets plain text only."""
    if not s:
        return ""
    return _re.sub(r"\s+", " ", _re.sub(r"<[^>]*>", " ", str(s))).strip()


def build_card(d):
    """Build a plain-text-safe Teams MessageCard from a delivery-log doc/dict. No raw HTML,
    no sensitive data beyond what the recipient may already see in the ERP."""
    title = _plain(d.get("title") or d.get("event_type") or "Notification")
    desc = _plain(d.get("message") or "")
    facts = []
    if d.get("recipient"):
        # Webhook/Workflow posts to a CHANNEL (not a per-user DM); naming the intended
        # recipient keeps the channel message honest about who must act.
        facts.append({"name": "For", "value": str(d["recipient"])})
    if d.get("actor"):
        facts.append({"name": "From", "value": str(d["actor"])})
    if d.get("deadline"):
        facts.append({"name": "Deadline", "value": str(d["deadline"])})
    if d.get("event_type"):
        facts.append({"name": "Type", "value": str(d["event_type"])})
    card = {
        "@type": "MessageCard", "@context": "https://schema.org/extensions",
        "summary": title, "themeColor": _theme(d.get("severity")),
        "sections": [{"activityTitle": title, "text": desc, "facts": facts}],
    }
    url = d.get("action_url")
    if url:
        card["potentialAction"] = [{
            "@type": "OpenUri", "name": "Open in ERP",
            "targets": [{"os": "default", "uri": url}],
        }]
    return card


def _theme(severity):
    return {"urgent": "D13438", "action_required": "FFB900"}.get(severity, "0078D4")


def _post_webhook(url, card):
    """POST the card to the Teams webhook. Returns (ok, code, redacted_error)."""
    import requests  # frappe ships requests
    try:
        r = requests.post(url, data=json.dumps(card),
                          headers={"Content-Type": "application/json"}, timeout=TIMEOUT)
        if 200 <= r.status_code < 300:
            return True, str(r.status_code), ""
        return False, str(r.status_code), "teams webhook non-2xx"  # never echo body/secret
    except Exception as e:
        return False, "EXC", type(e).__name__  # type only, no URL/secret


def deliver(delivery_log):
    """Enqueued entry point. Sends one Teams message for the given delivery-log row and
    records the outcome. Idempotent: already-Sent rows are not resent."""
    try:
        doc = frappe.get_doc(DELIVERY_DT, delivery_log)
    except Exception:
        return
    if doc.get("status") == "Sent":
        return
    cfg = get_config()
    doc.attempt_count = (doc.attempt_count or 0) + 1
    doc.last_attempt_at = frappe.utils.now_datetime()
    doc.provider = cfg["provider"]

    payload = build_card({
        "title": doc.get("title") or "", "message": doc.get("message") or "",
        "event_type": doc.get("event_type"), "severity": doc.get("severity"),
        "action_url": doc.get("action_url") or "", "actor": doc.get("actor") or "",
        "recipient": doc.get("recipient") or "",
    })

    if cfg["provider"] in ("disabled", "dryrun") or (cfg["provider"] == "webhook" and not cfg["webhook_url"]):
        # No production credential -> do not invent an endpoint. Record + stop.
        doc.status = "Skipped"
        doc.provider = "dryrun"
        doc.error_code = "NO_CREDENTIAL"
        doc.error_message = "Teams provider not configured (dry-run)."
        doc.save(ignore_permissions=True)
        return

    if cfg["provider"] == "webhook":
        ok, code, err = _post_webhook(cfg["webhook_url"], payload)
    else:  # graph mode reserved -- not implemented in V1
        ok, code, err = False, "GRAPH_NI", "graph provider not implemented in V1"

    if ok:
        doc.status = "Sent"
        doc.sent_at = frappe.utils.now_datetime()
        doc.error_code = ""
        doc.error_message = ""
    else:
        if doc.attempt_count >= MAX_ATTEMPTS:
            doc.status = "Failed"
            doc.next_retry_at = None
        else:
            doc.status = "Failed"
            mins = _RETRY_BACKOFF_MIN[min(doc.attempt_count - 1, len(_RETRY_BACKOFF_MIN) - 1)]
            doc.next_retry_at = frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=mins)
        doc.error_code = code
        doc.error_message = err
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
                           queue="short", delivery_log=nm)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "process_teams_retries")
    return {"requeued": len(rows)}
