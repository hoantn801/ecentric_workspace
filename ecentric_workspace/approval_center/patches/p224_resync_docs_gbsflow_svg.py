# Copyright (c) 2026, eCentric and contributors
"""/docs/gbs-flow: 3 so do thanh SVG ve san trong HTML - 29/09/2026.

Brief NHIEU_LOP/brief_gbs.md muc 5 ("noi dung tai lieu nam san trong HTML, khong viet lai bang JS").
Do bang NHIEU_LOP/do_lop_trang.js truoc khi sua: gone 54 (ma nguon mermaid hien ra roi bi SVG de
len), add 81, api 10. Trang nap mermaid 10.9 tu CDN chi de ve 3 hinh co dinh.

Sua o NGUON trang (A65): 3 khoi <pre class="mermaid"> -> <pre class="gfd-mmd"><svg>...</svg></pre>
(SVG lay tu chinh trang live, bo data-* va <symbol> khong dung); bo <script src=mermaid>,
mermaid.initialize va 2 lan mermaid.run. Do lai tren HTML moi: gone 2 / add 8 / mv 0 / api 10 -
phan con lai la the ten nguoi dung + menu cua Shell. Nguon so do: legacy_pages/docs_gbsflow/diagrams.md.

Idempotent: sync() tra ve "unchanged" tren site da co san ban nay.
"""
import frappe

_EXPECT_HAS = ('class="gfd-mmd"', 'id="gbs-flow-docs"')
_EXPECT_NOT = ("mermaid.min.js", "mermaid.run(")


def execute():
    from ecentric_workspace.legacy_pages.docs_gbsflow import page_sync as docs

    try:
        res = docs.sync()
        action = (res or {}).get("action")
        frappe.log_error("p224 docs/gbs-flow sync=%s" % action, "p224 gbs-flow svg")
        if action == "refused":
            frappe.log_error(
                "p224 docs/gbs-flow: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong "
                "nam trong BASELINE/SUPERSEDES - trang KHONG duoc cap nhat. Doi chieu live_sha trong ket "
                "qua roi them vao SUPERSEDES_SHA256.", "p224 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "docs/gbs-flow"}, "main_section_html") or ""
        bad = [m for m in _EXPECT_HAS if m not in html] + [m for m in _EXPECT_NOT if m in html]
        if bad:
            frappe.log_error("p224 docs/gbs-flow: landmark sai=%s" % bad, "p224 KHONG toi noi")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p224 docs/gbs-flow failed")
