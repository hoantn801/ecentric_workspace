# eCentric ERP Bot — Microsoft Teams personal notification bot (V1)

This is the **primary** Teams delivery path for Notification Delivery v1: a personal
(1:1) **proactive** bot that DMs each employee. Channel webhook is only a system-critical
fallback. The manifest lives in the app at
`ecentric_workspace/notification_center/teams_app/manifest.json`.

## Architecture / flow

```
ERP event → publish_notification_event → EC Notification Delivery Log (channel=teams, Pending)
          → enqueue providers.teams.deliver  (background, after commit)
              → provider=teams_bot (primary):
                  recipient email
                    → EC Teams Conversation (stored conversation reference)?  ── yes → send
                    → no → Graph: email → Entra user → aadObjectId
                          → Graph: ensure bot installed for user (proactive install)
                          → Bot Framework: create 1:1 conversation → store reference → send
                  send = Bot Framework proactive Adaptive Card (event type, title, short
                         content, người giao/yêu cầu, hạn, “Mở trong ERP” button)
              → provider=webhook (system_critical ONLY): channel MessageCard fallback
```

Outcomes recorded on `EC Notification Delivery Log`:
- **Sent** (`provider=teams_bot` or `webhook` or `teams_bot+webhook`)
- **Skipped** — bot not installed / not provisionable (`NO_GRAPH_FOR_PROVISION`, `INSTALL_*`),
  user blocked the bot (`BOT_BLOCKED`), conversation gone (`CONVERSATION_GONE`),
  no credential (`NO_CREDENTIAL`) — no retry, business transaction untouched.
- **Failed** — transient (token / 5xx / network) — bounded retry (≤4, backoff 1/5/30 min)
  via the existing `process_teams_retries` 5-min scheduler.

## Components you must provide (external — blocked in sandbox)

1. **Azure Bot registration** (Azure Bot / Bot Channels Registration) with the **Microsoft
   Teams** channel enabled. Gives you `bot app id` (GUID) + `app password` (client secret).
2. **Teams app package**: `manifest.json` (edit placeholders) + `color.png` (192×192) +
   `outline.png` (32×32), zipped. Set:
   - `id` = Teams app GUID, `bots[0].botId` = bot app id.
   - `bots[0].scopes = ["personal"]`, `isNotificationOnly = true`.
3. **Entra app registration for Graph** (can be the same app) with **application** permissions:
   - `User.Read.All` (email → aadObjectId),
   - `TeamsAppInstallation.ReadWriteForUser.All` (proactive install),
   - **admin consent granted** (tenant admin).
4. **Bot web service** (separate small Node/Python service, not Frappe): hosts the Bot
   Framework messaging endpoint. On the `conversationUpdate` / first message it captures the
   `TurnContext.getConversationReference(...)` and **POSTs it to Frappe**:
   `POST /api/method/ecentric_workspace.notification_center.api.save_teams_conversation`
   with `{user, aad_object_id, reference}` (authenticated as a service user with the
   System Manager role via API key). Frappe stores it in `EC Teams Conversation`.
   On-demand provisioning (Graph install + Bot Framework create-conversation) is also
   implemented server-side so a reference can be created without waiting for the user.
5. **Rollout / install for all employees**: either a **Teams app setup policy** (admin
   pins/pre-installs the app for everyone) or rely on the server-side Graph proactive
   install per user on first notification.

## site_config keys (server-side only — NEVER hardcoded, never sent to browser)

```
ec_teams_provider              teams_bot        # primary; "webhook" = sc-only; "disabled"/"dryrun"
ec_teams_bot_app_id            <bot app GUID>
ec_teams_bot_app_password      <bot client secret>
ec_teams_bot_id                28:<bot app GUID>
ec_teams_bot_default_service_url  https://smba.trafficmanager.net/<region>/
ec_graph_tenant_id             <tenant GUID>
ec_graph_client_id             <graph app GUID>
ec_graph_client_secret         <graph secret>
ec_teams_app_external_id       <Teams catalog app id, for proactive install>
ec_teams_webhook_url           <optional: system_critical channel webhook/Workflow URL>
```

## External blocker

The sandbox has **no Microsoft tenant**: no bot registration, no Graph admin consent, no
Teams app publish. The adapter, manifest, Graph + Bot Framework code, conversation store,
ingest API and tests are complete and run in dry-run/mock. **To go live you must** create
the bot + Graph app, grant admin consent, publish the Teams app + setup policy, deploy the
bot web service, and set the site_config keys above. Until then Teams deliveries record
`Skipped / NO_CREDENTIAL` and ERP toast/sound/desktop/inbox are unaffected.
