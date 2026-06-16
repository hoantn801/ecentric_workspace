# Copyright (c) 2026, eCentric and contributors
"""p001_homepage_action_center: replace the legacy ec-home-todo-widget on the
homepage Web Page with the Action Center widget.

This patch lives in source control so the production /home update is reviewable
and re-runnable; we never edit the Web Page by hand.

Targets the Web Page record whose route is 'home' (current production name:
'ecentric-workspace', verified by snapshot 2026-06-16).

Two surgical replacements inside main_section:
  1. Panel title 'Chờ phê duyệt' -> 'Việc cần làm'
  2. The whole <script id='ec-home-todo-widget'>...</script><!-- /ec-home-todo-widget -->
     block -> a new <script id='ec-action-center-widget'>...</script>...
     The new widget calls the Action Center API and uses item.action_url
     verbatim (NO frontend URL building, NO /approval hard-coding).

Idempotent: re-running after the patch already applied is a no-op (detected via
the NEW widget marker).

Fail-loud: if any of the required OLD markers cannot be found in main_section,
the patch raises ValidationError and does NOT mutate the Web Page. This guards
against silently corrupting an already-modified or drifted homepage.

Cache bust: both main_section and main_section_html are written and the Web
Page cache is cleared (per project convention - Frappe caches the rendered
homepage separately).
"""

import frappe


WP_ROUTE = "home"
WP_NAME_KNOWN = "ecentric-workspace"  # 2026-06-16 snapshot

OLD_TITLE = '<div class="panel-title">Chờ phê duyệt'
NEW_TITLE = '<div class="panel-title">Việc cần làm'

OLD_WIDGET_START = '<script id="ec-home-todo-widget">'
OLD_WIDGET_END   = '</script><!-- /ec-home-todo-widget -->'
NEW_WIDGET_START = '<script id="ec-action-center-widget">'
NEW_WIDGET_END   = '</script><!-- /ec-action-center-widget -->'


NEW_WIDGET_BODY = '''<script id="ec-action-center-widget">
// Action Center widget (replaces ec-home-todo-widget).
// Backend: ecentric_workspace.action_center.api.get_action_items
// IMPORTANT: this widget MUST NOT build any URL locally. It uses
// item.action_url verbatim. Source-specific badge / action label / title /
// subtitle are also supplied by the API. Adding any URL-building logic here
// is a regression -- the whole point of Action Center is one resolver.
(function(){
  'use strict';
  if (window._ecActionCenterInstalled) return;
  window._ecActionCenterInstalled = true;

  if (!document.getElementById('ec-action-center-css')) {
    var st = document.createElement('style');
    st.id = 'ec-action-center-css';
    st.textContent =
      '.ec-ac-card{display:block;padding:10px 12px;border:1px solid #e5e7eb;border-radius:10px;background:#fff;text-decoration:none;color:inherit;margin-bottom:8px;}' +
      '.ec-ac-card:hover{border-color:#2C3DA6;background:#f7f8fb;}' +
      '.ec-ac-row1{display:flex;align-items:center;gap:8px;margin-bottom:4px;font-size:11px;}' +
      '.ec-ac-pill{padding:1px 7px;border-radius:8px;color:#fff;font-weight:600;font-size:10px;letter-spacing:.3px;}' +
      '.ec-ac-src{padding:1px 7px;border-radius:8px;background:#eef0fb;color:#2C3DA6;font-weight:600;font-size:10px;letter-spacing:.4px;}' +
      '.ec-ac-time{margin-left:auto;color:#6b7280;font-size:11px;}' +
      '.ec-ac-title{font-size:13.5px;font-weight:600;color:#111827;line-height:1.35;margin-bottom:2px;}' +
      '.ec-ac-subtitle{font-size:11.5px;color:#6b7280;}' +
      '.ec-ac-action{display:inline-block;margin-top:6px;padding:3px 10px;border-radius:6px;background:#2C3DA6;color:#fff;font-size:11.5px;font-weight:600;}' +
      '.ec-ac-more{display:block;text-align:center;padding:10px;font-size:12.5px;color:#2C3DA6;font-weight:600;text-decoration:none;background:#f9fafb;border-top:1px solid #e5e7eb;}';
    document.head.appendChild(st);
  }

  var DISPLAY_LIMIT = 6;

  function esc(s){return String(s||'').replace(/[&<>\"']/g,function(c){return ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'})[c];});}

  function priColor(p){return p==='High'?'#dc2626':(p==='Low'?'#9ca3af':'#f59e0b');}
  function priLabel(p){return p==='High'?'CAO':(p==='Low'?'THẤP':'TB');}

  function ago(s){
    if(!s) return '';
    var t = new Date(String(s).replace(' ','T')+'Z');
    if(isNaN(t)) return '';
    var d = (Date.now()-t.getTime())/1000;
    if(d<60) return 'vừa xong';
    if(d<3600) return Math.floor(d/60)+' phút trước';
    if(d<86400) return Math.floor(d/3600)+' giờ trước';
    return Math.floor(d/86400)+' ngày trước';
  }

  function findPanel(){
    var nodes = document.querySelectorAll('.panel');
    for (var i=0; i<nodes.length; i++) {
      var t = nodes[i].querySelector('.panel-title');
      if (t && /Việc cần làm/.test(t.textContent)) return nodes[i];
    }
    return null;
  }

  function renderCards(items){
    var panel = findPanel();
    if (!panel) return;
    var listEl = panel.querySelector('.approval-list');
    if (!listEl) return;
    if (!items || items.length === 0) {
      listEl.innerHTML = '<div style=\"padding:24px;text-align:center;color:#6b7280;font-size:13px;\">Không có việc nào cần làm</div>';
      return;
    }
    var total = items.length;
    var shown = items.slice(0, DISPLAY_LIMIT);
    var html = shown.map(function(it){
      // Use action_url verbatim from the API. NO URL building here.
      var href = it.action_url || '#';
      return '<a href=\"' + esc(href) + '\" class=\"ec-ac-card\">' +
        '<div class=\"ec-ac-row1\">' +
          '<span class=\"ec-ac-pill\" style=\"background:' + priColor(it.priority) + ';\">' + priLabel(it.priority) + '</span>' +
          '<span class=\"ec-ac-src\">' + esc(it.source_label || '') + '</span>' +
          '<span class=\"ec-ac-time\">' + esc(ago(it.modified)) + '</span>' +
        '</div>' +
        '<div class=\"ec-ac-title\">' + esc(it.title || '') + '</div>' +
        '<div class=\"ec-ac-subtitle\">' + esc(it.subtitle || '') + '</div>' +
        '<span class=\"ec-ac-action\">' + esc(it.action_label || 'Mở') + '</span>' +
      '</a>';
    }).join('');
    if (total > DISPLAY_LIMIT) {
      var more = total - DISPLAY_LIMIT;
      var moreLink = '/app/todo/view/list?status=Open&allocated_to=' + encodeURIComponent((window.frappe && window.frappe.session && window.frappe.session.user) || '');
      html += '<a href=\"' + moreLink + '\" class=\"ec-ac-more\">Xem thêm ' + more + ' việc →</a>';
    }
    listEl.innerHTML = html;
  }

  function loadItems(){
    var panel = findPanel();
    if (!panel) return;
    fetch('/api/method/ecentric_workspace.action_center.api.get_action_items', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    })
    .then(function(r){ return r.json(); })
    .then(function(j){
      var msg = j && j.message ? j.message : j;
      if (msg && msg.success && msg.items) renderCards(msg.items);
    })
    .catch(function(e){ console.warn('[ec-action-center] load err', e); });
  }

  function init(){
    loadItems();
    // Re-poll every 90s so new ToDos appear without reload.
    setInterval(loadItems, 90000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  console.log('[ec-action-center-widget] installed');
})();
</script><!-- /ec-action-center-widget -->'''


def _resolve_wp_name():
    """Try the known name; fall back to a route lookup; fail loudly if both miss."""
    if frappe.db.exists("Web Page", WP_NAME_KNOWN):
        return WP_NAME_KNOWN
    rows = frappe.get_all(
        "Web Page", filters={"route": WP_ROUTE},
        fields=["name"], limit_page_length=1,
    )
    if rows:
        return rows[0]["name"]
    raise frappe.ValidationError(
        "p001_homepage_action_center: cannot find Web Page (tried name="
        + WP_NAME_KNOWN + " and route=" + WP_ROUTE + ")"
    )


def execute():
    wp_name = _resolve_wp_name()
    wp = frappe.get_doc("Web Page", wp_name)
    main = wp.main_section or ""

    # Idempotent: NEW widget already there -> no-op.
    if NEW_WIDGET_START in main and NEW_WIDGET_END in main:
        try:
            frappe.logger("action_center").info(
                "p001: already migrated; no-op on Web Page " + wp_name)
        except Exception:
            pass
        return

    # Fail-loud pre-checks.
    missing = []
    if OLD_TITLE not in main:
        missing.append("OLD_TITLE")
    if OLD_WIDGET_START not in main:
        missing.append("OLD_WIDGET_START")
    if OLD_WIDGET_END not in main:
        missing.append("OLD_WIDGET_END")
    if missing:
        raise frappe.ValidationError(
            "p001_homepage_action_center: required OLD markers not found in "
            "Web Page '" + wp_name + "' main_section: " + ", ".join(missing)
            + ". Refusing to mutate (production may have drifted)."
        )

    # 1. Replace card title (first occurrence).
    new_main = main.replace(OLD_TITLE, NEW_TITLE, 1)

    # 2. Replace the widget block (start .. end inclusive).
    s = new_main.find(OLD_WIDGET_START)
    if s < 0:
        raise frappe.ValidationError(
            "p001: OLD_WIDGET_START vanished after title replace (impossible)")
    e = new_main.find(OLD_WIDGET_END, s)
    if e < 0:
        raise frappe.ValidationError(
            "p001: OLD_WIDGET_END not found AFTER OLD_WIDGET_START -- "
            "widget block is malformed; refusing to mutate.")
    e_full = e + len(OLD_WIDGET_END)
    new_main = new_main[:s] + NEW_WIDGET_BODY + new_main[e_full:]

    # Post-check: NEW markers must be present and OLD widget id must be gone.
    if (NEW_WIDGET_START not in new_main
            or NEW_WIDGET_END not in new_main
            or OLD_WIDGET_START in new_main):
        raise frappe.ValidationError(
            "p001: post-substitution sanity check failed -- aborting save.")

    # Write back to BOTH main_section and main_section_html (cache bust).
    wp.main_section = new_main
    wp.main_section_html = new_main
    wp.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Web Page")
    try:
        frappe.logger("action_center").info(
            "p001: migrated Web Page " + wp_name + " to Action Center widget")
    except Exception:
        pass
