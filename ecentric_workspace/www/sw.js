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

var EC_SW_VERSION = "2026-09-15.1";

/* Anh dai dien cua thong bao day (large icon, hien o BEN PHAI the tren Android).
 * KHONG gui thi may tu ve mot vong tron chu cai suy ra tu TEN MIEN - dung la
 * chu "T" cua team.ecentric.vn ma moi nguoi nhin thay tren the ngay 14/09.
 * Dung file da co san cho PWA (cung anh manifest dung), da kiem: public, 512x512,
 * tra ve 200 khi khong kem cookie - service worker tai duoc trong moi hoan canh. */
var EC_PUSH_ICON = "/files/ec-erp-icon-512.png";

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

/* ---------------------------------------------------------------------------
 * WEB PUSH
 * ---------------------------------------------------------------------------
 * Day la ly do duy nhat service worker nay ton tai ngoai viec cho cai PWA:
 * chi service worker moi nhan duoc push khi KHONG co tab nao dang mo, va do moi
 * la luc can thong bao nhat (dien thoai nam trong tui, chua cham cong).
 *
 * Payload do `providers/webpush.py` gui len, dang JSON:
 *     title, body, url, tag, event_id
 * Neu payload hong hoac rong, van phai hien MOT thong bao: cac trinh duyet nhan
 * "userVisibleOnly" se tu hien "This site has been updated in the background"
 * neu handler khong goi showNotification - te hon la mot thong bao chung chung
 * cua minh.
 *
 * KHONG dung dau ngoac nhon lien nhau o file nay - xem ghi chu Jinja o dau file.
 */
self.addEventListener("push", function (event) {
  var data = null;
  try {
    data = event.data ? event.data.json() : null;
  } catch (e) {
    data = null;
  }
  if (!data) {
    data = { title: "eCentric ERP", body: "Ban co thong bao moi.", url: "/" };
  }
  var title = data.title || "eCentric ERP";
  var opts = {
    body: data.body || "",
    icon: data.icon || EC_PUSH_ICON,
    tag: data.tag || "ec-notification",
    renotify: true,
    requireInteraction: false,
    /* Gio cua SU KIEN, khong phai gio may nhan duoc. Push co the den muon vai phut
     * (dien thoai ngu, mang chap chon); lay Date.now() se xep sai thu tu va hien
     * "vua xong" cho mot loi nhac tu 20 phut truoc. */
    timestamp: Number(data.ts) || Date.now(),
    lang: "vi",
    data: { url: data.url || "/", event_id: data.event_id || "" }
  };
  event.waitUntil(self.registration.showNotification(title, opts));
});

/* Bam vao thong bao: dua nguoi dung toi dung trang. Neu da co tab cua ERP dang mo
 * thi FOCUS tab do roi dieu huong, thay vi mo them mot tab thu tu. */
self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  var target = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        var c = list[i];
        if (c.url.indexOf(self.location.origin) === 0 && "focus" in c) {
          if ("navigate" in c) {
            return c.navigate(target).then(function (nc) {
              return nc ? nc.focus() : null;
            });
          }
          return c.focus();
        }
      }
      return self.clients.openWindow ? self.clients.openWindow(target) : null;
    })
  );
});

/* Push service co the xoay endpoint bat ky luc nao. Khi do dang ky cu chet va
 * nguoi dung im lang khong nhan duoc gi nua - tru khi ta dang ky lai va bao server.
 * Trinh duyet hien tai ho tro su kien nay khong dong deu, nen day chi la LOP DU
 * PHONG; duong chinh van la ec_webpush.js dong bo lai moi lan mo trang. */
self.addEventListener("pushsubscriptionchange", function (event) {
  event.waitUntil(
    self.registration.pushManager.getSubscription().then(function (sub) {
      if (!sub) {
        return null;
      }
      var j = sub.toJSON();
      var body = new URLSearchParams();
      body.append("endpoint", j.endpoint || "");
      body.append("p256dh", (j.keys && j.keys.p256dh) || "");
      body.append("auth", (j.keys && j.keys.auth) || "");
      return fetch(
        "/api/method/ecentric_workspace.notification_center.api.webpush_subscribe",
        { method: "POST", credentials: "include", body: body }
      );
    })
  );
});
