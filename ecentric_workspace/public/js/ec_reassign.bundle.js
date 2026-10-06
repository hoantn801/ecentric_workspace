// Copyright (c) 2026, eCentric and contributors
//
// Nut "Chuyen nguoi xu ly" dung chung cho cac form co buoc xu ly (05/10/2026, Hoan: Hiring +
// Daily Target chua co nut nay, anh Tuan nhan Hiring 00007 roi khong chuyen cho Luc duoc).
//
// Server quyet dinh het: ai duoc chuyen (capabilities.can_reassign = chu viec / quan tri),
// danh sach nguoi nhan (list_reassign_targets = Fulfiller cau hinh cua quy trinh - KHONG cho
// go email tu do), engine tu choi nguoi khong du dieu kien (reassign_fulfillment). Endpoint
// co san tu bind_fulfillment; o day chi ve nut + hop chon.
//
// GIAO KEO VOI TRANG (2 dong):
//   actionPanelHTML:   if(window.EcReassign) btns.push(EcReassign.buttonHTML(cap));
//   handleActionClick: if(a==="reassign") return window.EcReassign&&EcReassign.run(call,name,{modal:modal,toast:toast,mapErr:mapErr,done:refreshDetail});
(function () {
  "use strict";
  if (window.EcReassign) return;
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function buttonHTML(cap) {
    return cap && cap.can_reassign
      ? '<button type="button" class="btn" data-act="reassign">Chuyển người xử lý</button>' : "";
  }
  function run(call, name, opts) {
    opts = opts || {};
    var toast = opts.toast || function () {};
    var err = function (e) { return opts.mapErr ? opts.mapErr(e) : "Không chuyển được. Thử lại sau."; };
    return call("list_reassign_targets", { name: name }).then(function (res) {
      var rows = (res && res.targets) || [], cur = (res && res.current_owner) || "";
      if (!rows.length) { toast("Không có ai khác đủ điều kiện nhận xử lý yêu cầu này.", true); return; }
      var optsHTML = rows.map(function (u) {
        return '<option value="' + esc(u.name) + '">' + esc((u.full_name || u.name) + " · " + u.name) + "</option>";
      }).join("");
      opts.modal("Chuyển người xử lý",
        '<div class="summary-row"><span>Đang xử lý</span><b>' + esc(cur || "—") + "</b></div>"
        + '<div class="fld"><label>Chuyển cho <span class="req">*</span></label><select id="m-newowner" data-ec-no-formkit>' + optsHTML + "</select></div>"
        + '<div class="hint">Người nhận sẽ được giao việc và nhận thông báo. Việc đang giao cho bạn sẽ được đóng lại.</div>',
        { okLabel: "Chuyển", onConfirm: function (ov) {
          var nu = (ov.querySelector("#m-newowner").value || "");
          if (!nu) { toast("Chưa chọn người nhận.", true); return Promise.reject(); }
          return call("reassign_fulfillment", { name: name, new_user: nu }).then(function () {
            toast("Đã chuyển cho " + nu + ".");
            if (typeof opts.done === "function") opts.done();
          }).catch(function (e) {
            toast(err(e), true);
            if (typeof opts.done === "function") opts.done();
            return Promise.reject(e);
          });
        } });
    }).catch(function (e) { toast(err(e), true); });
  }
  window.EcReassign = { buttonHTML: buttonHTML, run: run };
})();
