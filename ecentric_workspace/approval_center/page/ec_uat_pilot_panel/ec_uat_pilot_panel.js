// Copyright (c) 2026, eCentric and contributors
// SCTS UAT Pilot Control Panel desk page - System Manager only (enforced by the Page roles
// AND by every governed endpoint it calls). Redacted; apply=1 requires confirmation and is
// only enabled when readiness is all-green. Never reveals credentials/tokens/Base64.
frappe.pages["ec-uat-pilot-panel"].on_page_load = function (wrapper) {
  var page = frappe.ui.make_app_page({
    parent: wrapper, title: __("SCTS UAT Pilot Control Panel"), single_column: true,
  });
  var $b = $('<div style="padding:8px"></div>').appendTo(page.body);
  function esc(s) { return frappe.utils.escape_html(s == null ? "" : String(s)); }
  $b.html(
    '<input class="form-control" id="ecUatPr" style="max-width:360px;display:inline-block" ' +
    'placeholder="Payment Request (UAT/VOID/TEST)"> ' +
    '<button class="btn btn-xs" id="ecUatRefresh">Kiểm tra sẵn sàng</button> ' +
    '<button class="btn btn-xs" id="ecUatPreview">Xem trước (apply=0)</button> ' +
    '<button class="btn btn-xs btn-danger" id="ecUatApply" disabled>Probe apply=1</button>' +
    '<div id="ecUatOut" style="margin-top:8px"></div>');
  function readiness() {
    frappe.call({ method: "ecentric_workspace.approval_center.esign.api.uat_pilot_readiness",
      args: { payment_request_name: $b.find("#ecUatPr").val() || undefined } })
      .then(function (r) {
        var m = r.message || {};
        $b.find("#ecUatApply").prop("disabled", !m.ready);
        var stageLbl = m.stage ? (" [" + (m.actor_type || "") + ": " + m.stage + "]") : "";
        $b.find("#ecUatOut").html("<b>" + (m.ready ? "READY" : "NOT READY") + "</b>" +
          "<span style='color:#555'>" + frappe.utils.escape_html(stageLbl) + "</span> " +
          esc((m.blocking_items || []).join(", ")) +
          "<pre>" + esc(JSON.stringify(m.checks || {}, null, 2)) + "</pre>");
      }, function () { $b.find("#ecUatOut").text("Chỉ System Manager."); });
  }
  $b.find("#ecUatRefresh").on("click", readiness);
  $b.find("#ecUatPreview").on("click", function () {
    frappe.call({ method: "ecentric_workspace.approval_center.esign.api.run_scts_uat_pilot_probe",
      type: "POST", args: { payment_request_name: $b.find("#ecUatPr").val(), apply: 0 } })
      .then(function (r) { $b.find("#ecUatOut").html("<pre>" +
        esc(JSON.stringify(r.message, null, 2)) + "</pre>"); });
  });
  $b.find("#ecUatApply").on("click", function () {
    if (!window.confirm("Chạy probe apply=1 (một lần gửi UAT, không tự gửi lại)?")) return;
    frappe.call({ method: "ecentric_workspace.approval_center.esign.api.run_scts_uat_pilot_probe",
      type: "POST", args: { payment_request_name: $b.find("#ecUatPr").val(), apply: 1 } })
      .then(function (r) { $b.find("#ecUatOut").html("<pre>" +
        esc(JSON.stringify(r.message, null, 2)) + "</pre>"); });
  });
  readiness();
};
