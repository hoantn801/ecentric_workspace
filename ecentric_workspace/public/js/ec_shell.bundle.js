// Copyright (c) 2026, eCentric and contributors
// Bundle entry for ERP Shell v1. Referenced by hooks.py `web_include_js`;
// `bench build` (esbuild) emits a CONTENT-HASHED dist file, same cache-bust
// pattern as notification_center.bundle.js. Loads on every website page but
// ec_shell.js is a hard no-op unless the page opts in via [data-ec-shell="1"].
import "./ec_shell.js";
