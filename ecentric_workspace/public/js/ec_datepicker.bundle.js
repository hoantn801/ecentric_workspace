// Copyright (c) 2026, eCentric and contributors
// Bundle entry for the shared ec_datepicker. Referenced by hooks.py
// `web_include_js`; `bench build` (esbuild) emits a CONTENT-HASHED dist file,
// same cache-bust pattern as ec_shell.bundle.js. Loads on every website page
// but ec_datepicker.js is a hard no-op on Frappe Desk (/app/*) and only
// enhances native date / datetime-local inputs.
import "./ec_datepicker.js";
