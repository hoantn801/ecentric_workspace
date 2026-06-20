// Copyright (c) 2026, eCentric and contributors
// Bundle entry for the Global Notification Center asset.
// Referenced by hooks.py `web_include_js`. `bench build` (esbuild) emits this as a
// CONTENT-HASHED file (…/dist/js/notification_center.bundle.<hash>.js), so every
// deploy changes the URL and busts the immutable /assets cache uniformly across ALL
// website routes -- fixing stale-cache where some pages served an old asset version.
import "./notification_center.js";
