// Copyright (c) 2026, eCentric and contributors
// Governed "Verify Mapping" action for EC SCTS User Mapping.
// The verified status is set ONLY by the backend verify_mapping method (which pulls the
// provider signatures and confirms ownership) - never by hand in the UI. The button is
// visible only after the mapping is saved, and only to System Managers.
frappe.ui.form.on("EC SCTS User Mapping", {
  refresh: function (frm) {
    // Never allow the verification result to be edited manually in the UI.
    ["mapping_status", "verified_at", "verified_by", "signature_meta_summary"].forEach(
      function (f) { frm.set_df_property(f, "read_only", 1); });

    if (!frm.is_new() && !frm.is_dirty() && frappe.user.has_role("System Manager")) {
      frm.add_custom_button(__("Verify Mapping"), function () {
        frappe.call({
          method: "ecentric_workspace.approval_center.esign.api.verify_mapping",
          args: { mapping_name: frm.doc.name },
          freeze: true,
          freeze_message: __("Đang xác minh với SCTS…"),
        }).then(function (r) {
          if (r && r.message && r.message.verified) {
            frappe.show_alert({ message: __("Đã xác minh ánh xạ."), indicator: "green" });
            frm.reload_doc();
          }
        }).catch(function () {
          // Safe, secret-free error. The server throw (also sanitized) is shown by frappe;
          // this is the fallback message.
          frappe.msgprint({
            title: __("Xác minh thất bại"),
            message: __("Không xác minh được ánh xạ. Kiểm tra cấu hình SCTS (Site, thông tin đăng nhập) rồi thử lại."),
            indicator: "red",
          });
        });
      });
    }
  },
});
