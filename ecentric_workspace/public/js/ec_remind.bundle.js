// Copyright (c) 2026, eCentric and contributors
//
// Nut "Nhac nguoi xu ly" dung chung cho moi form phe duyet (01/10/2026, Hoan).
//
// Server quyet dinh het (shared/requests/remind.py): ai duoc bam (chi nguoi gui), nhac ai
// (dung nguoi dang giu phieu), 15 phut mot lan. O day chi ve nut theo `capabilities`
// (can_remind / remind_wait_seconds) va goi endpoint `remind` cua chinh form do qua ham
// `call` cua trang. Mot ban duy nhat - khong chep vao tung main_section.html (A65 muc 3).
//
// GIAO KEO VOI TRANG (2 dong moi form):
//   actionPanelHTML:   if(window.EcRemind) btns.push(EcRemind.buttonHTML(cap));
//   handleActionClick: if(a==="remind") return window.EcRemind&&EcRemind.run(call,name,{toast:toast,mapErr:mapErr,done:refreshDetail});
(function () {
  "use strict";
  if (window.EcRemind) return;
  function mins(sec) { return Math.max(1, Math.ceil((Number(sec) || 0) / 60)); }
  function buttonHTML(cap) {
    cap = cap || {};
    if (!cap.can_remind) return "";
    var wait = Number(cap.remind_wait_seconds) || 0;
    if (wait > 0) {
      return '<button type="button" class="btn" disabled title="Mỗi phiếu nhắc được 15 phút một lần">🔔 Nhắc lại sau ' + mins(wait) + " phút</button>";
    }
    return '<button type="button" class="btn" data-act="remind" title="Báo trên ERP và Teams cho người đang xử lý phiếu">🔔 Nhắc người xử lý</button>';
  }
  var busy = false;
  function run(call, name, opts) {
    opts = opts || {};
    var toast = opts.toast || function () {};
    if (busy || typeof call !== "function") return;
    busy = true;
    var btn = document.querySelector('[data-act="remind"]');
    if (btn) btn.disabled = true;
    return call("remind", { name: name }).then(function (res) {
      var who = (res && res.reminded) || [];
      toast("Đã nhắc " + (who.length ? who.join(", ") : "người xử lý") + ".");
    }).catch(function (e) {
      toast(opts.mapErr ? opts.mapErr(e) : "Không nhắc được. Thử lại sau.", true);
    }).then(function () {
      busy = false;
      if (typeof opts.done === "function") opts.done();
    });
  }
  window.EcRemind = { buttonHTML: buttonHTML, run: run };
})();
