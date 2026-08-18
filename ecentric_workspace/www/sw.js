/*
 * eCentric ERP - Service Worker (PWA baseline)
 * ---------------------------------------------------------------------------
 * Served by Frappe at:  https://team.ecentric.vn/sw.js   -> scope "/"
 * Source file:          ecentric_workspace/www/sw.js
 * Version:              see EC_SW_VERSION below (bump on every change)
 *
 * WHY THIS FILE LIVES IN www/ (and not in public/ or /files/)
 *   A service worker can only control URLs at or below its own path. Only a
 *   script served from the site root gives scope "/", which is what an ERP
 *   with routes spread over /approvals, /pm, /ec-hr, /weekly-update needs.
 *   public/ resolves to /assets/... and /files/... is under /files - both are
 *   too deep. www/ is the only app-owned folder that maps to the site root.
 *
 * HOW FRAPPE SERVES THIS FILE (verified against frappe source, v16)
 *   - StaticPage refuses it twice over: "js" is in UNSUPPORTED_STATIC_PAGE_TYPES
 *     and StaticPage only serves binary files. So it is TemplatePage that
 *     renders www/sw.js.
 *   - TemplatePage passes the file through Jinja before sending it.
 *     => THIS FILE MUST NEVER CONTAIN JINJA TOKENS, i.e. no double-open-brace,
 *        no open-brace-percent, no open-brace-hash - not even inside comments.
 *        Keep object and block braces from ever touching each other.
 *   - Content-Type comes from mimetypes.guess_type(path) -> text/javascript,
 *     which is what the service worker spec requires. Do not rename the file
 *     to something without a .js extension.
 *
 * SCOPE OF THIS WORKER - DELIBERATELY MINIMAL
 *   This ERP is permission-aware: the same URL returns different data per user
 *   (EC Viewer Permission, ownership rules, payroll visibility). A cached
 *   response is a permission leak waiting to happen. So this worker caches
 *   NOTHING. It exists only to make the app installable and to give us a
 *   versioned place to grow from later.
 *
 *   If caching is ever added, the rules are: static /assets/** only, never a
 *   navigation request, never an /api/** response, and bump EC_SW_VERSION.
 */

var EC_SW_VERSION = "2026-08-18.1";

/* Take over as soon as a new version is deployed instead of waiting for every
 * tab to close. Safe here because the worker holds no cached state. */
self.addEventListener("install", function () {
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});

/* INTENTIONAL NO-OP.
 * We register a fetch listener but never call event.respondWith(), so every
 * request falls through to the browser's normal network path - no caching, no
 * interception, no behaviour change. The listener is here because Chrome's
 * install-prompt heuristics still look for a fetch handler, and Chrome 117+
 * detects no-op fetch handlers and skips them, so this costs nothing.
 * Do not add respondWith() here without reading the SCOPE note above. */
self.addEventListener("fetch", function () {
  return;
});

/* Diagnostics: from any page console run
 *   navigator.serviceWorker.controller.postMessage("EC_SW_PING")
 * after subscribing to navigator.serviceWorker.onmessage, to see which
 * version is actually live. */
self.addEventListener("message", function (event) {
  if (event.data !== "EC_SW_PING") {
    return;
  }
  if (event.source && event.source.postMessage) {
    event.source.postMessage({ ec_sw_version: EC_SW_VERSION });
  }
});
