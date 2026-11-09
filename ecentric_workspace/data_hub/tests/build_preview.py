# Copyright (c) 2026, eCentric and contributors
"""Ban XEM THU tu chua (1 tep HTML) cua Trung tam Du lieu cho PO bam thu - KHONG phai test, khong deploy.

Trang = template THAT (www/du_lieu + templates/includes/data_hub) render tu service THAT tren bo mau
(tests/fake.sample), vo shell THAT (shell/server_nav + ec_shell.bundle.css), CSS + JS THAT nhung thang;
API thay bang ban gia doc du lieu that cua bo mau (POST chi bao "ban xem thu").

    python -m ecentric_workspace.data_hub.tests.build_preview /duong/dan/ra.html
"""
import html
import io
import json
import os
import sys

from ecentric_workspace.data_hub.tests import fake as F
from ecentric_workspace.data_hub import service as S
from ecentric_workspace.data_hub.tests import test_data_hub as T

APP = T.APP
ROUTES = {"index": "/du-lieu", "dieu_phoi": "/du-lieu/dieu-phoi", "quy_tac": "/du-lieu/quy-tac", "san_co": "/du-lieu/san-co"}


def _shell(route, roles):
    from ecentric_workspace.shell.tests import test_server_nav as TS
    saved = sys.modules.get("frappe")
    sys.modules["frappe"] = TS._fake_frappe()
    try:
        fb, nav, sn = TS._mods()
        ctx = nav.resolve_context(route)
        items = nav.compose(ctx, roles=roles)
        rail = nav.rail_spec(roles)
        section, panel, blocks, active, sig = sn.rail_parts(rail, ctx, items, route)
        inner = fb.mount_inner_html(panel, active, live=True, rail=rail, section=section, blocks=blocks)
        mount = ('<aside class="ec-shell-mount" data-ec-shell="1" aria-label="Điều hướng eCentric" data-ec-rail="1" '
                 'data-ec-context="%s">%s</aside>' % (ctx, inner))
        detail = {"/du-lieu": "", "/du-lieu/dieu-phoi": "Điều phối", "/du-lieu/quy-tac": "Quy tắc thời hạn",
                  "/du-lieu/san-co": "Data availability"}[route]
        top = fb.render_topbar_inner(route, fb.make_detail(fb._esc(detail)) if detail else None, chat=False)
        return mount, top
    finally:
        if saved is not None:
            sys.modules["frappe"] = saved


def _read(*p):
    return io.open(os.path.join(APP, *p), encoding="utf-8").read()


STUB = r"""
<script>
(function(){
  var API = window.parent.__EDH_API, ME = %(me)s;
  window.__edhNoReload = true;
  window.frappe = {csrf_token: "preview"};
  function reply(data, ok, msg){ return Promise.resolve({ok: ok !== false, status: ok === false ? 417 : 200,
    json: function(){ return Promise.resolve({message: {success: ok !== false, message: msg || "", data: data}}); }}); }
  window.fetch = function(u, o){
    var m = u.split("data_hub.api.")[1].split("?")[0], q = {};
    if (o && o.method === "POST") { q = JSON.parse(o.body || "{}"); }
    else { new URL(u, location.href).searchParams.forEach(function(v, k){ q[k] = v; }); }
    if (m === "get_ticket") { var d = (API.details[q.code] || {})[ME]; return d ? reply(d) : reply(null, false, "Không tìm thấy yêu cầu này."); }
    if (m === "gantt") return reply(q.start ? API.gantt_next : API.gantt);
    if (m === "preview_due") return reply(API.preview[q.code] || {});
    if (m === "people") return reply(API.people);
    setTimeout(function(){ window.parent.postMessage({toast: "Bản xem thử: “" + m + "” đã gửi đúng dữ liệu, nhưng không ghi gì."}, "*"); }, 50);
    if (m === "create") return reply({code: "DR-2026-0011"});
    if (m === "accept") return reply({status: "Đang xử lý", due: q.due_date, pm_task: "TASK-2026-00099", warning: ""});
    if (m === "update") return reply({changes: ["…"], warnings: [], status: ""});
    return reply({});
  };
  document.addEventListener("click", function(e){
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a) return;
    var h = a.getAttribute("href");
    if (/^\/du-lieu/.test(h)) { e.preventDefault(); window.parent.postMessage({go: h.split("?")[0]}, "*"); }
    else if (/^\//.test(h)) { e.preventDefault(); window.parent.postMessage({toast: "Bản xem thử: liên kết " + h + " mở trong ERP thật."}, "*"); }
  }, true);
})();
</script>
"""


def build(out_path):
    r, pm, c = F.sample()
    css = _read("public", "css", "ec_data_hub.bundle.css")
    shell_css = _read("public", "css", "ec_shell.bundle.css")
    js = _read("public", "js", "ec_data_hub.bundle.js")
    _, api = T.fixture_pages()
    roles = {F.THU: ["Employee"], F.LINH: ["Employee", "EC Data Team"]}
    docs = {}
    for who in (F.THU, F.LINH):
        for page, build_ctx in (("index", lambda u: S.index_page(u, repo=r)), ("dieu_phoi", lambda u: S.ops_page(u, repo=r)),
                                ("quy_tac", lambda u: S.rules_page(u, repo=r)), ("san_co", lambda u: S.avail_page(u, repo=r))):
            mount, top = _shell(ROUTES[page], roles[who])
            out = T._env().get_template("www/du_lieu/%s.html" % page).render(
                base_template_path="templates/base.html", edh_shell_mount=mount, edh_topbar=top, edh_css="", edh_js="",
                title="Trung tâm Dữ liệu", **build_ctx(who))
            out = out.replace('<link rel="stylesheet" href="">', "<style>%s\n%s\nbody{margin:0;background:#f7f8fb}</style>" % (shell_css, css))
            out = out.replace('<script src="" defer></script>', STUB % {"me": json.dumps(who)} + "<script>%s</script>" % js.replace("</script", "<\\/script"))
            out = out.replace("NAVBAR", "").replace("FOOTER", "")
            docs["%s|%s" % ("user" if who == F.THU else "team", ROUTES[page])] = out
    shell = """<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Xem thử · Trung tâm Dữ liệu (đợt 1)</title><style>
body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;background:#f7f8fb}
.pv-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:8px 14px;background:#fffbe6;border-bottom:1px solid #f1e3a6;font-size:13px;position:sticky;top:0;z-index:5}
.pv-bar b{margin-right:8px}.pv-rb{border:1px solid #d1d5db;background:#fff;border-radius:999px;padding:4px 12px;cursor:pointer;font:inherit}
.pv-rb.on{background:#2C3DA6;color:#fff;border-color:#2C3DA6}.pv-sep{width:1px;height:20px;background:#e5d9a8;margin:0 6px}
.pv-w{margin-left:auto;display:flex;gap:6px}iframe{display:block;border:0;width:100%%;height:calc(100vh - 44px);background:#fff;margin:0 auto}
.pv-toast{position:fixed;left:50%%;bottom:20px;transform:translateX(-50%%);background:#111827;color:#fff;padding:10px 16px;border-radius:10px;font-size:13px;z-index:9;display:none}
</style></head><body>
<div class="pv-bar"><b>Xem thử · Trung tâm Dữ liệu (đợt 1)</b><span>Vai trò:</span>
<button class="pv-rb on" data-role="user">Nhân viên (Thu Nguyễn · Commercial)</button><button class="pv-rb" data-role="team">Team Data (Linh Vương)</button>
<span class="pv-sep"></span><span class="pv-w"><button class="pv-rb on" data-w="100%%">Máy tính</button><button class="pv-rb" data-w="390px">Điện thoại 390px</button></span></div>
<iframe id="pv" title="Trang xem thử"></iframe><div class="pv-toast" id="pvt"></div>
<script>
window.__EDH_API = %(api)s;
var DOCS = %(docs)s, role = "user", route = "/du-lieu";
function show(){ var k = role + "|" + route; document.getElementById("pv").srcdoc = DOCS[k] || DOCS[role + "|/du-lieu"]; }
document.querySelectorAll("[data-role]").forEach(function(b){ b.onclick = function(){ role = b.dataset.role;
  document.querySelectorAll("[data-role]").forEach(function(x){ x.classList.toggle("on", x === b); });
  if (role === "user" && route !== "/du-lieu" && route !== "/du-lieu/san-co") route = "/du-lieu"; show(); }; });
document.querySelectorAll("[data-w]").forEach(function(b){ b.onclick = function(){
  document.querySelectorAll("[data-w]").forEach(function(x){ x.classList.toggle("on", x === b); });
  document.getElementById("pv").style.width = b.dataset.w; }; });
window.addEventListener("message", function(e){ var m = e.data || {};
  if (m.go) { route = m.go; show(); }
  if (m.toast) { var t = document.getElementById("pvt"); t.textContent = m.toast; t.style.display = "block"; clearTimeout(window.__t); window.__t = setTimeout(function(){ t.style.display = "none"; }, 3500); } });
show();
</script></body></html>""" % {"api": json.dumps(api, ensure_ascii=False, default=str).replace("</", "<\\/"),
                                   "docs": json.dumps(docs, ensure_ascii=False).replace("</", "<\\/")}
    with io.open(out_path, "w", encoding="utf-8") as fh:
        fh.write(shell)
    return out_path


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "data_hub_d1_preview.html"))
