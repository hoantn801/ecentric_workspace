// Copyright (c) 2026, eCentric and contributors
// Governed Signing Inbox desk page. Scope + pagination + counts come entirely from the
// permission-scoped signing_inbox endpoint; this controller renders only what it returns.
frappe.pages["ec-signing-inbox"].on_page_load = function (wrapper) {
  var page = frappe.ui.make_app_page({
    parent: wrapper, title: __("Signing Inbox"), single_column: true,
  });
  var BUCKETS = [["my_pending", "Chờ tôi ký"], ["ready_to_sign", "Sẵn sàng ký"],
    ["package_incomplete", "Gói chưa đủ"], ["awaiting_provider", "Chờ nhà cung cấp"],
    ["verification_pending", "Đang xác minh"], ["signed_file_pending", "Chờ tệp ký"],
    ["manual_review", "Cần rà soát"], ["completed", "Hoàn tất"]];
  var st = { bucket: "my_pending", start: 0, page_length: 20, total: 0 };
  var $body = $('<div class="ec-inbox-body" style="padding:8px"></div>').appendTo(page.body);

  function esc(s) { return frappe.utils.escape_html(s == null ? "" : String(s)); }
  function load() {
    frappe.call({
      method: "ecentric_workspace.approval_center.esign.api.signing_inbox",
      args: { filters: JSON.stringify({ bucket: st.bucket }),
              start: st.start, page_length: st.page_length },
    }).then(function (r) {
      var m = r.message || {};
      st.total = m.total || 0;
      var tabs = BUCKETS.map(function (b) {
        return '<button class="btn btn-xs ec-tab' + (st.bucket === b[0] ? " btn-primary" : "") +
          '" data-b="' + b[0] + '">' + esc(b[1]) + " (" + ((m.counts || {})[b[0]] || 0) + ")</button>";
      }).join(" ");
      var approx = m.approximate_count ? " (≈)" : "";
      var rows = (m.rows || []).map(function (row) {
        return "<tr><td>" + esc(row.business_name) + "</td><td>" + esc(row.requester) +
          "</td><td>" + esc(row.amount) + " " + esc(row.currency || "") + "</td><td>" +
          esc(row.active_level) + "</td><td>" + esc(row.stage) + "</td><td>" +
          esc(row.file_count) + "</td><td>" + esc(row.dsr_status) + "</td><td>" +
          esc(row.safe_error || "") + "</td></tr>";
      }).join("");
      $body.html(tabs +
        '<div style="margin:6px 0">Scope: ' + esc(m.scope_total) + approx +
        " · hiển thị " + (m.rows || []).length + "/" + st.total + "</div>" +
        '<table class="table table-bordered"><thead><tr><th>Yêu cầu</th><th>Người tạo</th>' +
        "<th>Số tiền</th><th>Cấp</th><th>Giai đoạn</th><th>Tệp</th><th>DSR</th><th>Lỗi</th>" +
        "</tr></thead><tbody>" + rows + "</tbody></table>" +
        '<button class="btn btn-xs" id="ecInbPrev">‹</button> ' +
        '<button class="btn btn-xs" id="ecInbNext">›</button>');
      $body.find(".ec-tab").on("click", function () {
        st.bucket = $(this).data("b"); st.start = 0; load();
      });
      $body.find("#ecInbPrev").on("click", function () {
        if (st.start >= st.page_length) { st.start -= st.page_length; load(); } });
      $body.find("#ecInbNext").on("click", function () {
        if (st.start + st.page_length < st.total) { st.start += st.page_length; load(); } });
    });
  }
  load();
};
