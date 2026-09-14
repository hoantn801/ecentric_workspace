// Copyright (c) 2026, eCentric and contributors
// Man hinh EC Web Push Settings: hai nut de van hanh web push MA KHONG CAN SHELL.
//
// Site chay tren Frappe Cloud - khong ai co shell de go `bench execute`. Neu khong co
// hai nut nay thi cach duy nhat de sinh khoa VAPID la sinh o may khac roi dan khoa
// BI MAT vao o nhap, tuc la bi mat di qua chat/email. Sinh ngay tren server thi khoa
// khong bao gio roi khoi server.

frappe.ui.form.on("EC Web Push Settings", {
  refresh: function (frm) {
    if (!frm.doc.vapid_public_key) {
      frm.add_custom_button(__("Sinh khoá VAPID"), function () {
        frappe.confirm(
          __("Sinh cặp khoá VAPID mới và bật web push?"),
          function () {
            frappe.call({
              method:
                "ecentric_workspace.notification_center.providers.webpush.generate_vapid_keys_api",
              freeze: true,
              freeze_message: __("Đang sinh khoá…"),
              callback: function (r) {
                var m = r.message || {};
                if (m.ok) {
                  frappe.show_alert({ message: __("Đã sinh khoá và bật web push."), indicator: "green" });
                  frm.reload_doc();
                } else {
                  frappe.msgprint(m.reason || __("Không sinh được khoá."));
                }
              },
            });
          }
        );
      }).addClass("btn-primary");
    }

    if (frm.doc.enabled && frm.doc.vapid_public_key) {
      frm.add_custom_button(__("Gửi thử cho tôi"), function () {
        frappe.call({
          method:
            "ecentric_workspace.notification_center.providers.webpush.send_test_push",
          freeze: true,
          callback: function (r) {
            var m = r.message || {};
            if (m.ok) {
              frappe.show_alert({
                message: __("Đã gửi tới {0}/{1} thiết bị.", [m.sent, m.devices]),
                indicator: "green",
              });
            } else {
              // Ba trang thai hay gap, moi cai mot cach xu ly khac han nhau.
              frappe.msgprint({
                title: __("Chưa gửi được"),
                message: m.detail || m.reason || __("Lỗi không rõ."),
                indicator: "orange",
              });
            }
          },
        });
      });
    }

    if (frm.doc.vapid_public_key) {
      frm.dashboard.add_indicator(
        __("Thiết bị đã đăng ký: đang đếm…"),
        "blue"
      );
      frappe.db
        .count("EC Web Push Subscription", { filters: { active: 1 } })
        .then(function (n) {
          frm.dashboard.clear_headline();
          frm.dashboard.set_headline(
            __("Đang có <b>{0}</b> thiết bị đã bật thông báo.", [n])
          );
        });
    }
  },
});
