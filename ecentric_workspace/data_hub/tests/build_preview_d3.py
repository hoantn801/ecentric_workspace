# Copyright (c) 2026, eCentric and contributors
"""Ban XEM THU tu chua (1 tep HTML) trang Quy tac thoi han - dot 3 - cho PO bam thu. KHONG phai test,
khong deploy. Template + service + CSS/JS THAT tren bo mau; POST chi bao "ban xem thu".

    python -m ecentric_workspace.data_hub.tests.build_preview_d3 /duong/dan/ra.html
"""
import io
import json
import sys

from ecentric_workspace.data_hub.tests import fake as F  # noqa: I001  (dat frappe gia truoc)
from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import rules_service as R
from ecentric_workspace.data_hub import service as S
from ecentric_workspace.data_hub.tests import build_preview as BP
from ecentric_workspace.data_hub.tests import test_data_hub_d3 as T3
from ecentric_workspace.data_hub.tests import test_data_hub as T

STUB = r"""
<script>
(function(){
  window.__edhNoReload = true;
  window.frappe = {csrf_token: "preview"};
  window.fetch = function(u, o){
    var m = u.split("data_hub.api.")[1].split("?")[0];
    setTimeout(function(){ window.parent.postMessage({toast: "Bản xem thử: “" + m + "” đã gửi đúng dữ liệu, nhưng không ghi gì."}, "*"); }, 50);
    return Promise.resolve({ok: true, status: 200, json: function(){ return Promise.resolve({message: {success: true, message: "", data: {}}}); }});
  };
  document.addEventListener("click", function(e){
    var a = e.target.closest && e.target.closest("a[href]");
    if (a) { e.preventDefault(); window.parent.postMessage({toast: "Bản xem thử: liên kết " + a.getAttribute("href") + " mở trong ERP thật."}, "*"); }
  }, true);
})();
</script>
"""

STATES = (
    ("propose", "Team Data · chưa có đề xuất", F.LINH),
    ("draft", "Team Data · bản nháp của tôi", F.LINH),
    ("pending", "Team Data · đã gửi, chờ duyệt", F.LINH),
    ("approver", "Người duyệt quy tắc · chờ duyệt", F.HOAN),
    ("history", "Sau khi duyệt · lịch sử v1→v2", F.LINH),
)


def _repo(state):
    r, pm, c = F.sample()
    if state in ("draft", "pending", "approver", "history"):
        T3.propose(r, days={"pbi_new": 10}, reason="Dashboard mới hay cần 3+ nguồn, 7 ngày thường trễ.")
    if state in ("pending", "approver", "history"):
        R.submit(F.LINH, "SLA-v2", repo=r)
    if state == "approver":
        r.role_map[F.HOAN].discard(C.DEFAULT_DATA_TEAM_ROLE)
    if state == "history":
        R.decide(F.HOAN, "SLA-v2", "approve", "Đồng ý", repo=r)
    return r


def build(out_path):
    css = BP._read("public", "css", "ec_data_hub.bundle.css")
    rcss = BP._read("public", "css", "ec_data_hub_rules.bundle.css")
    shell_css = BP._read("public", "css", "ec_shell.bundle.css")
    js = BP._read("public", "js", "ec_data_hub.bundle.js")
    rjs = BP._read("public", "js", "ec_data_hub_rules.bundle.js")
    docs = {}
    for key, _label, who in STATES:
        r = _repo(key)
        roles = sorted(r.roles(who))
        mount, top = BP._shell("/du-lieu/quy-tac", roles)
        ctx = S.rules_page(who, repo=r)
        out = T._env().get_template("www/du_lieu/quy_tac.html").render(
            base_template_path="templates/base.html", edh_shell_mount=mount, edh_topbar=top, edh_css="", edh_js="",
            edh_rules_css="", edh_rules_js="", title="Quy tắc thời hạn", **ctx)
        out = out.replace('<link rel="stylesheet" href="">',
                          "<style>%s\n%s\nbody{margin:0;background:#f7f8fb}</style>" % (shell_css, css), 1)
        out = out.replace('<link rel="stylesheet" href="">', "<style>%s</style>" % rcss, 1)
        out = out.replace('<script src="" defer></script>', STUB + "<script>%s</script>" % js.replace("</script", "<\\/script"), 1)
        out = out.replace('<script src="" defer></script>', "<script>%s</script>" % rjs.replace("</script", "<\\/script"), 1)
        docs[key] = out.replace("NAVBAR", "").replace("FOOTER", "")
    buttons = "".join('<button class="pv-rb%s" data-s="%s">%s</button>' % (" on" if i == 0 else "", k, lab)
                      for i, (k, lab, _w) in enumerate(STATES))
    page = """<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Xem thử · Quy tắc thời hạn (đợt 3)</title><style>
body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;background:#f7f8fb}
.pv-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:8px 14px;background:#fffbe6;border-bottom:1px solid #f1e3a6;font-size:13px;position:sticky;top:0;z-index:5}
.pv-rb{border:1px solid #d1d5db;background:#fff;border-radius:999px;padding:4px 12px;cursor:pointer;font:inherit}
.pv-rb.on{background:#2C3DA6;color:#fff;border-color:#2C3DA6}.pv-w{margin-left:auto;display:flex;gap:6px}
iframe{display:block;border:0;width:100%%;height:calc(100vh - 44px);background:#fff;margin:0 auto}
.pv-toast{position:fixed;left:50%%;bottom:20px;transform:translateX(-50%%);background:#111827;color:#fff;padding:10px 16px;border-radius:10px;font-size:13px;z-index:9;display:none}
</style></head><body>
<div class="pv-bar"><b>Xem thử · Quy tắc thời hạn (đợt 3)</b>%(buttons)s
<span class="pv-w"><button class="pv-rb on" data-w="100%%">Máy tính</button><button class="pv-rb" data-w="390px">Điện thoại 390px</button></span></div>
<iframe id="pv" title="Trang xem thử"></iframe><div class="pv-toast" id="pvt"></div>
<script>
var DOCS = %(docs)s;
function show(k){ document.getElementById("pv").srcdoc = DOCS[k]; }
document.querySelectorAll("[data-s]").forEach(function(b){ b.onclick = function(){
  document.querySelectorAll("[data-s]").forEach(function(x){ x.classList.toggle("on", x === b); }); show(b.dataset.s); }; });
document.querySelectorAll("[data-w]").forEach(function(b){ b.onclick = function(){
  document.querySelectorAll("[data-w]").forEach(function(x){ x.classList.toggle("on", x === b); });
  document.getElementById("pv").style.width = b.dataset.w; }; });
window.addEventListener("message", function(e){ var m = e.data || {}; if (m.toast) { var t = document.getElementById("pvt");
  t.textContent = m.toast; t.style.display = "block"; clearTimeout(window.__t); window.__t = setTimeout(function(){ t.style.display = "none"; }, 3500); } });
show("%(first)s");
</script></body></html>""" % {"buttons": buttons, "docs": json.dumps(docs, ensure_ascii=False).replace("</", "<\\/"),
                                   "first": STATES[0][0]}
    with io.open(out_path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return out_path


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "data_hub_d3_quy_tac_preview.html"))
