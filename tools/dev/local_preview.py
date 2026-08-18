# Copyright (c) 2026, eCentric and contributors
"""Local static+mock preview for Approval Center frontend fragments.

Stopgap for when a real Frappe bench isn't available locally: serves
ecentric_workspace/approval_center/frontend/*.main_section.html wrapped in a
shell that stubs out window.frappe.call (and /api/method/upload_file) with
fake data, so pages render and buttons wire up without a live site. Also
serves the real ec_shell.js / ec_shell.bundle.css / notification_center.js
(the global chrome every page loads via hooks.py web_include_js/css) so the
sidebar/topbar render styled instead of as raw unstyled fallback markup.

NOT a substitute for testing against a real bench/site before push -- the
data is fake and there is no permission/business-logic checking. Use it to
check layout, CSS, and JS wiring only.

Usage:
    python tools/dev/local_preview.py [port]   # default port 8787
"""
import http.server
import importlib
import json
import socketserver
import sys
import traceback
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "ecentric_workspace"
FRONTEND_DIR = APP_DIR / "approval_center" / "frontend"
PUBLIC_DIR = APP_DIR / "public"
STUBS_DIR = ROOT / "tools" / "ci" / "stubs"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8787


def _discover_page_routes():
    """route (no leading slash) -> zero-arg _html() from every page_sync.py.

    Same trick tools/ci/check.py uses to hash page HTML without a live site:
    a stub `frappe` (tools/ci/stubs) just thick enough to import the module,
    then call its real _html(). This is what makes sidebar links like
    /approvals or /approvals/dashboard work in the preview instead of 404ing
    -- those routes are served by hub_page_sync.py / dashboard/page_sync.py,
    not by a file under approval_center/frontend/.

    Not every page has this shape (pm/pages.py, legacy_pages/home -- Jinja/
    guarded, no plain _html()); those are silently skipped and still 404.
    """
    routes = {}
    for entry in (str(STUBS_DIR), str(ROOT)):
        if entry in sys.path:
            sys.path.remove(entry)
    sys.path.insert(0, str(STUBS_DIR))
    sys.path.insert(0, str(ROOT))
    for path in sorted(APP_DIR.rglob("*page_sync.py")):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        module_name = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        try:
            module = importlib.import_module(module_name)
        except Exception:
            sys.stderr.write("[preview] skip %s (import failed):\n%s\n" % (module_name, traceback.format_exc()))
            continue
        route = getattr(module, "ROUTE", None)
        html_fn = getattr(module, "_html", None)
        if isinstance(route, str) and callable(html_fn):
            routes[route.strip("/")] = (module_name, html_fn)
    return routes

# Global chrome every real web page loads via hooks.py web_include_js/web_include_css.
# Pages carry a static no-JS fallback for this (class "ec-shell-fallback"), but its CSS
# and hydration script live in these shared files -- without them the fallback renders
# unstyled (sidebar icons default to solid-fill SVGs, no layout). Served straight from
# source, not the hashed dist build bench produces.
SHELL_ASSETS = {
    "/ecshell/ec_shell.js": PUBLIC_DIR / "js" / "ec_shell.js",
    "/ecshell/ec_shell.bundle.css": PUBLIC_DIR / "css" / "ec_shell.bundle.css",
    "/ecshell/notification_center.js": PUBLIC_DIR / "js" / "notification_center.js",
}

MOCK_JS = r"""
window.frappe = window.frappe || {};
frappe.csrf_token = "dev-local-preview";
frappe.session = frappe.session || { user: "dev@local.test" };
(function () {
  var seq = 1000;
  function mockMessage(method, args) {
    var m = String(method || "").split(".").pop();
    if (m === "get_bootstrap") {
      return {
        tabs: { create: true, "my-requests": true, my_approvals: true },
        context: { user: "dev@local.test", employee_name: "Dev User (mock)" },
        form_options: {},
      };
    }
    if (/^list_/.test(m)) return { rows: [], total: 0 };
    if (/^search_/.test(m)) return [];
    if (/^get_detail/.test(m)) {
      return {
        name: (args && args.name) || "DEV-0001",
        approval_status: "Draft",
        request_title: "[MOCK] Sample request",
      };
    }
    if (m === "save_draft") return { name: (args && args.name) || "DEV-" + seq++ };
    return {};
  }
  frappe.call = function (opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
      setTimeout(function () {
        resolve({ message: mockMessage(opts.method, opts.args) });
      }, 150);
    });
  };
})();
"""

BANNER = (
    '<div style="position:fixed;top:0;left:0;right:0;z-index:99999;'
    'background:#b45309;color:#fff;font:600 12px/1.4 -apple-system,sans-serif;'
    'padding:4px 10px;text-align:center">'
    "LOCAL PREVIEW &mdash; MOCK DATA, KHÔNG PHẢI BACKEND THẬT &mdash; __NAME__"
    "</div><div style=\"height:22px\"></div>"
)

SHELL = (
    "<!doctype html><html><head><meta charset=\"utf-8\">"
    "<title>__TITLE__ (local preview)</title>"
    "<link rel=\"stylesheet\" href=\"/ecshell/ec_shell.bundle.css\">"
    "<script>__MOCKJS__</script>"
    "<script src=\"/ecshell/ec_shell.js\"></script>"
    "<script src=\"/ecshell/notification_center.js\"></script>"
    "</head><body>" + BANNER + "__FRAGMENT__</body></html>"
)

INDEX_STYLE = "font:14px -apple-system,sans-serif;padding:24px;max-width:640px;margin:0 auto"

PAGE_ROUTES = _discover_page_routes()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[preview] " + (fmt % args) + "\n")

    def _send(self, body, content_type="text/html; charset=utf-8", code=200):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj, code=200):
        self._send(json.dumps(obj), "application/json; charset=utf-8", code)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._index()
        if path.startswith("/page/"):
            return self._page(path[len("/page/"):])
        if path in SHELL_ASSETS:
            return self._asset(SHELL_ASSETS[path])
        route = PAGE_ROUTES.get(path.strip("/"))
        if route:
            return self._route(path.strip("/"), route)
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)  # drain body; content is not needed by the mock
        if path == "/api/method/upload_file":
            return self._send_json({"message": {"file_url": "/files/mock-upload.png", "file_name": "mock-upload.png"}})
        if path.startswith("/api/method/"):
            return self._send_json({"message": {}})
        self.send_error(404)

    def _index(self):
        files = sorted(p.name for p in FRONTEND_DIR.glob("*.main_section.html"))
        items = "".join('<li><a href="/page/%s">%s</a></li>' % (n, n) for n in files)
        routes = "".join(
            '<li><a href="/%s">/%s</a></li>' % (r, r) for r in sorted(PAGE_ROUTES)
        )
        body = (
            "<!doctype html><meta charset='utf-8'><title>Approval Center - Local Preview</title>"
            "<body style='%s'>"
            "<h2>Approval Center &mdash; Local Preview (mock data)</h2>"
            "<p style='color:#b45309'>Nút bấm gọi API giả (không phải backend thật). "
            "Chỉ dùng để xem layout/CSS/luồng thao tác trước khi push, "
            "không thay thế test trên bench/site thật.</p>"
            "<h3>Real routes (sidebar links work, %d found)</h3><ul>%s</ul>"
            "<h3>By file (approval_center/frontend only)</h3><ul>%s</ul></body>"
        ) % (INDEX_STYLE, len(PAGE_ROUTES), routes, items)
        self._send(body)

    def _asset(self, fp):
        if not fp.is_file():
            return self.send_error(404)
        content_type = "text/css; charset=utf-8" if fp.suffix == ".css" else "text/javascript; charset=utf-8"
        self._send(fp.read_text(encoding="utf-8"), content_type)

    def _page(self, name):
        fp = FRONTEND_DIR / name
        if not fp.is_file() or fp.suffix != ".html" or "/" in name or "\\" in name:
            return self.send_error(404)
        self._render(name, fp.read_text(encoding="utf-8"))

    def _route(self, route, route_entry):
        module_name, html_fn = route_entry
        try:
            fragment = html_fn()
        except Exception:
            sys.stderr.write("[preview] /%s: _html() raised:\n%s\n" % (route, traceback.format_exc()))
            return self.send_error(500, "_html() raised in %s -- see server console" % module_name)
        self._render("/" + route, fragment)

    def _render(self, label, fragment):
        html = (
            SHELL.replace("__TITLE__", label)
            .replace("__MOCKJS__", MOCK_JS)
            .replace("__NAME__", label)
            .replace("__FRAGMENT__", fragment)
        )
        self._send(html)


def main():
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print("Local preview: http://127.0.0.1:%d/  (%d real routes, Ctrl+C to stop)" % (PORT, len(PAGE_ROUTES)))
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
