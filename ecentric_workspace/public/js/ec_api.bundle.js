// Copyright (c) 2026, eCentric and contributors
// Bundle entry for ec_api.js (one shared client for app-method calls on website pages).
// Referenced by hooks.py `web_include_js`; `bench build` emits a content-hashed file.
// Defines window.ecApi only -- never wraps window.fetch, never runs on its own.
import "./ec_api.js";
