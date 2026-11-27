# Copyright (c) 2026, eCentric and contributors
"""So do quy trinh theo vai tro cho bai huong dan - dung LAI bo ve cua Thu vien tai lieu ISO.

Vi sao khong tu viet: trang /tai-lieu/<ma> da co san cach xem quy trinh ma PO chot 05/10
(so do mermaid to, Doc/Ngang, phong to, chon vai tro thi to sang buoc cua vai tro do + "Viec cua
<vai tro>"). Bai huong dan (vd hop dong, 22/11/2026) muon y het cach do. Nen o day:
  * du lieu quy trinh viet theo DUNG dinh dang goi ISO (tom_tat, vai_tro, buoc, so_do_mermaid,
    cau_hoi_thuong_gap - xem NHIEU_LOP/iso/HUONG_DAN_DONG_GOI_QUY_TRINH.md);
  * vai tro -> nut duoc tinh bang `iso_docs.view.flow` (ham thuan cua ISO), luat kiem nut so do
    lay tu `iso_docs.package` - mot luat, hai noi dung;
  * markup dung dung cac moc (data-eti-flow, #eti-src, .eti-chip...) ma `ec_iso_docs.js` doc, va
    trang nap chinh tep JS do. Khong chep lai JS ve so do.

THUAN, khong frappe: dia chi mermaid / JS do page_sync truyen vao (lay tu iso_docs.pages luc sync).
Moi loi noi dung NEM ValueError luc sync, giong anh thieu: khong de trang len song voi so do hong.
"""
import json

from ecentric_workspace.iso_docs import package as iso_package
from ecentric_workspace.iso_docs import view as iso_view

#: Web Page co the di qua Jinja: cam cap ngoac nay lot vao HTML sinh ra.
_JINJA_MARKS = ("{{", "}}", "{%", "%}", "{#", "#}")


def _esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def errors(pkg):
    """-> [loi]. Phan luat cua goi ISO ap duoc cho mot bai huong dan (khong co ma, phong ban)."""
    e = []
    if not isinstance(pkg, dict):
        return ["quy trinh khong phai doi tuong JSON"]
    tt = pkg.get("tom_tat") or {}
    for k in ("dung_khi", "chuan_bi", "ket_qua"):
        if not (tt.get(k) or "").strip():
            e.append("tom_tat thieu %s" % k)
    codes = {r.get("ma") for r in pkg.get("vai_tro") or [] if isinstance(r, dict) and r.get("ten")}
    if not codes:
        e.append("vai_tro rong")
    steps = pkg.get("buoc") or []
    if not steps or len(steps) > iso_package.MAX_STEPS:
        e.append("so buoc phai tu 1 den %d" % iso_package.MAX_STEPS)
    ids = []
    for b in steps:
        bid = b.get("id") or ""
        if not iso_package.STEP_ID_RE.match(bid):
            e.append("buoc.id sai dang: %r" % bid)
        ids.append(bid)
        for k in ("stt", "ten", "A", "R", "dien_giai"):
            if not b.get(k):
                e.append("buoc %s thieu %s" % (bid, k))
        for r in [b.get("A")] + list(b.get("R") or []):
            if r and r not in codes:
                e.append("buoc %s nhac vai tro %r khong co trong vai_tro" % (bid, r))
        fe = (b.get("form_erp") or "").strip()
        if fe and not fe.startswith("/"):
            e.append("buoc %s: form_erp phai bat dau bang /" % bid)
    if len(ids) != len(set(ids)):
        e.append("buoc.id bi trung")
    src = pkg.get("so_do_mermaid") or ""
    if not src.strip().startswith("flowchart TD"):
        e.append("so_do_mermaid phai bat dau bang 'flowchart TD'")
    low = src.lower()
    e.extend("so_do_mermaid co tu khoa cam: %r" % bad.strip()
             for bad in iso_package.MERMAID_FORBIDDEN if bad in low)
    nodes = iso_package.mermaid_nodes(src)
    missing = [i for i in ids if i not in nodes]
    extra = [n for n in nodes if n not in ids]
    if missing:
        e.append("so do thieu nut cho buoc: %s" % ", ".join(missing))
    if extra:
        e.append("so do co nut khong ung voi buoc nao: %s" % ", ".join(extra))
    return e


def render(pkg, mermaid_js, flow_js):
    """Goi quy trinh -> HTML: tom tat, so do theo vai tro, bang buoc, cau hoi thuong gap, 2 script."""
    errs = errors(pkg)
    if errs:
        raise ValueError("guides: quy trinh sai - " + "; ".join(errs))
    f = iso_view.flow(pkg)
    roles_json = json.dumps(f["roles"], ensure_ascii=False)
    h = []
    if f["facts"]:
        h.append('<dl class="gfacts">%s</dl>' % "".join(
            '<div class="gfact"><dt>%s</dt><dd>%s</dd></div>' % (_esc(lbl), _esc(txt))
            for lbl, txt in f["facts"]))
    chips = "".join('<button class="eti-chip" type="button" data-r="%s" aria-pressed="false">%s</button>'
                    % (_esc(r["ma"]), _esc(r["ten"])) for r in f["roles"])
    h.append(
        '<section class="gflow" data-eti-flow data-roles="%s" aria-labelledby="gflow-h">'
        '<div class="gflow-head"><h2 id="gflow-h">Sơ đồ quy trình</h2>'
        '<div class="gflow-tools">'
        '<div class="gseg" role="group" aria-label="Hướng sơ đồ">'
        '<button class="gbtn" type="button" data-dir="TD" aria-pressed="false">Dọc</button>'
        '<button class="gbtn" type="button" data-dir="LR" aria-pressed="false">Ngang</button></div>'
        '<div class="gseg" role="group" aria-label="Phóng to, thu nhỏ sơ đồ">'
        '<button class="gbtn" type="button" data-z="-1" aria-label="Thu nhỏ">−</button>'
        '<button class="gbtn" type="button" data-z="0">Vừa khung</button>'
        '<button class="gbtn" type="button" data-z="1" aria-label="Phóng to">+</button></div>'
        '</div></div>'
        '<div class="grolebar"><span class="glbl" id="gflow-roles">Bạn là</span>'
        '<div class="gchips" role="group" aria-labelledby="gflow-roles">'
        '<button class="eti-chip is-on" type="button" data-r="" aria-pressed="true">Tất cả</button>%s</div></div>'
        '<p class="gmut">Chọn vai trò để tô sáng các bước của bạn và xem danh sách việc ngay dưới sơ đồ.</p>'
        '<div class="eti-flowbox" id="eti-flow" aria-label="Sơ đồ quy trình">'
        '<p class="gmut" id="eti-flow-msg">Đang vẽ sơ đồ…</p></div>'
        '<pre id="eti-src" hidden>%s</pre>'
        '<div class="eti-mine" id="eti-mine" hidden><h3 id="eti-mine-t"></h3>'
        '<ol class="eti-mine-list" id="eti-mine-list"></ol></div>'
        '</section>' % (_esc(roles_json), chips, _esc(pkg.get("so_do_mermaid"))))
    rows = "".join(
        '<tr id="buoc-%s"><td class="gno">%s</td><td>%s%s</td><td>%s</td><td>%s</td></tr>'
        % (_esc(b.get("id")), _esc(b.get("stt")), _esc(b.get("ten")),
           (' <a href="%s">Mở form</a>' % _esc(b["form_erp"])) if b.get("form_erp") else "",
           _esc(b.get("who")), _esc(b.get("dien_giai")))
        for b in f["steps"])
    h.append('<details class="gsteps" open><summary><h2>Diễn giải từng bước</h2>'
             '<span class="gmut">%d bước</span></summary>'
             '<div class="gtbl"><table><thead><tr><th scope="col">Bước</th><th scope="col">Việc</th>'
             '<th scope="col">Chịu trách nhiệm</th><th scope="col">Diễn giải</th></tr></thead>'
             '<tbody>%s</tbody></table></div></details>' % (len(f["steps"]), rows))
    faq = [x for x in f["faq"] if isinstance(x, dict) and x.get("hoi")]
    if faq:
        h.append('<h2>Câu hỏi thường gặp</h2>' + "".join(
            '<details class="gfaq"><summary>%s</summary><p>%s</p></details>'
            % (_esc(x["hoi"]), _esc(x.get("dap"))) for x in faq))
    # defer: chay theo thu tu, truoc su kien load - ec_iso_docs.js ve so do luc load.
    h.append('<script src="%s" defer></script><script src="%s" defer></script>'
             % (_esc(mermaid_js), _esc(flow_js)))
    out = "".join(h)
    bad = [m for m in _JINJA_MARKS if m in out]
    if bad:
        raise ValueError("guides: quy trinh sinh ra cap ngoac Jinja %s - doi chu trong goi" % bad)
    return out


def render_file(path, mermaid_js, flow_js):
    with open(path, encoding="utf-8") as fh:
        return render(json.load(fh), mermaid_js, flow_js)
