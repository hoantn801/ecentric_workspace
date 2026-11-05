/* pm_home_calendar_rsvp.test.js — RSVP widget "Lịch hôm nay" trang chủ (PO 05/11/2026:
 * "thi thoảng phản hồi RSVP rồi mà bấm lại nó không lưu").
 * Chạy: NODE_PATH=<node_modules có jsdom> node ecentric_workspace/public/js/pm/tests/pm_home_calendar_rsvp.test.js
 * Kiểm:
 *  - lời mời đã "Tạm nhận"/"Từ chối" (Graph tentativelyAccepted/declined) KHÔNG hiện lại nút Nhận/Từ chối;
 *  - bấm Nhận thành công -> dữ liệu dùng chung (_last) cập nhật: ecCalFocus vẽ lại thẻ hero, mở lại
 *    popover dòng thời gian, ecCalEvents() đều thấy "đã nhận" (trước: nút hiện lại như chưa lưu);
 *  - rsvp trả {ok:false} hoặc lỗi mạng -> hiện lỗi, không báo đã nhận. */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");
const SRC = fs.readFileSync(path.join(__dirname, "..", "..", "pm_home_calendar.js"), "utf8");
const res = [], ok = (n, c, x) => res.push({ n, c: !!c, x });
const p2 = n => (n < 10 ? "0" : "") + n;
const d0 = new Date(), DAY = d0.getFullYear() + "-" + p2(d0.getMonth() + 1) + "-" + p2(d0.getDate());
const HTML = '<!doctype html><html><head></head><body>' +
  '<div class="panel"><div class="panel-header"><div class="panel-title">Lịch hôm nay</div><a class="panel-action" href="#">x</a></div><div>placeholder</div></div>' +
  '<div class="ec2-tlwrap"><div class="ec2-tlbody" style="position:relative"></div><div class="ec2-tlempty">trống</div></div>' +
  '</body></html>';
const mtg = (id, hh, resp) => ({ id, subject: "Hop " + id, start: DAY + " " + p2(hh) + ":00:00", end: DAY + " " + p2(hh) + ":30:00",
  join_url: "", location: "P1", response: resp, showAs: "busy" });

function boot(meetings, rsvpReply) {
  const errors = [], calls = [], vc = new VirtualConsole();
  vc.on("error", (...a) => errors.push(a.map(String).join(" ")));
  vc.on("jsdomError", e => { if (!/Not implemented/.test(String(e && e.message))) errors.push("jsdomError " + (e && e.message)); });
  const dom = new JSDOM(HTML, { url: "https://team.ecentric.vn/app/home", runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc, beforeParse(w) {
    w.frappe = { csrf_token: "x" };
    w.Element.prototype.scrollIntoView = function () { };
    w.fetch = (url, opt) => {
      const body = JSON.parse((opt && opt.body) || "{}"); calls.push({ url, body });
      let msg;
      if (/schedule\.today$/.test(url)) msg = { date: DAY, now: DAY + " 07:00:00", sync_on: true, meetings: JSON.parse(JSON.stringify(meetings)), blocks: [], due_unscheduled: 0 };
      else if (/schedule\.rsvp$/.test(url)) { if (rsvpReply === "neterr") return Promise.reject(new Error("net")); msg = rsvpReply(body); }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ message: msg }) });
    };
  } });
  dom.window.eval(SRC);
  return { w: dom.window, errors, calls };
}
const tick = ms => new Promise(r => setTimeout(r, ms || 30));
const okReply = b => ({ ok: true, response: b.response, status: { accept: "accepted", decline: "declined", tentative: "tentativelyAccepted" }[b.response] });
const heroBtns = w => Array.prototype.map.call(w.document.querySelectorAll(".ec-lhn-hero button"), b => b.textContent);
const heroTxt = w => ((w.document.querySelector(".ec-lhn-hero .ec-lhn-btns") || {}).textContent || "");
const tlEv = (w, id) => Array.prototype.filter.call(w.document.querySelectorAll(".ec-lhn-ev"), e => e.textContent === "Hop " + id)[0];
const popBtns = w => Array.prototype.map.call(w.document.querySelectorAll("#ec-lhn-pop button"), b => b.textContent);

(async () => {
  // 1) already tentatively accepted / declined -> answered label, no RSVP buttons
  let b = boot([mtg("T1", 9, "tentativelyAccepted")], okReply); await tick(400);
  ok("hero: Tạm nhận hiện là đã phản hồi, không còn nút Nhận/Từ chối", heroBtns(b.w).length === 0 && /Đã tạm nhận/.test(heroTxt(b.w)), heroBtns(b.w).join(","));
  tlEv(b.w, "T1").click(); await tick();
  ok("popover: Tạm nhận không hiện nút Nhận/Từ chối", popBtns(b.w).length === 0 && /Đã tạm nhận/.test(b.w.document.getElementById("ec-lhn-pop").textContent), popBtns(b.w).join(","));
  b.w.close();
  b = boot([mtg("D1", 9, "declined")], okReply); await tick(400);
  ok("hero: Từ chối hiện là đã phản hồi", heroBtns(b.w).length === 0 && /Đã từ chối/.test(heroTxt(b.w)));
  b.w.close();

  // 2) answer from the hero, then re-render / reopen -> still answered
  b = boot([mtg("A1", 9, "none"), mtg("A2", 11, "notResponded")], okReply); await tick(400);
  ok("chưa phản hồi: hero có nút Nhận + Từ chối", heroBtns(b.w).join(",") === "Nhận,Từ chối", heroBtns(b.w).join(","));
  b.w.document.querySelector(".ec-lhn-hero button").click(); await tick(60);
  const rs = b.calls.filter(c => /rsvp$/.test(c.url));
  ok("gửi schedule.rsvp đúng event_id + response", rs.length === 1 && rs[0].body.event_id === "A1" && rs[0].body.response === "accept");
  ok("sau khi Nhận: hero hiện Đã nhận", /Đã nhận/.test(heroTxt(b.w)) && heroBtns(b.w).length === 0);
  b.w.ecCalFocus("A1"); await tick();
  ok("ecCalFocus vẽ lại từ dữ liệu chung: vẫn Đã nhận, không hiện lại nút", heroBtns(b.w).length === 0 && /Đã nhận/.test(heroTxt(b.w)), heroBtns(b.w).join(","));
  ok("ecCalEvents() trả response=accepted cho A1", (b.w.ecCalEvents().filter(e => e.id === "A1")[0] || {}).response === "accepted");
  tlEv(b.w, "A1").click(); await tick();
  ok("mở lại popover dòng thời gian: Đã nhận, không có nút Nhận", popBtns(b.w).indexOf("Nhận") < 0 && /Đã nhận/.test(b.w.document.getElementById("ec-lhn-pop").textContent), popBtns(b.w).join(","));
  ok("không lỗi console", b.errors.length === 0, b.errors.slice(0, 2).join(" | "));
  b.w.close();

  // 3) answer from the timeline popover -> label readable on the white card + reopen persists
  b = boot([mtg("P1", 9, "none")], okReply); await tick(400);
  tlEv(b.w, "P1").click(); await tick();
  Array.prototype.filter.call(b.w.document.querySelectorAll("#ec-lhn-pop button"), x => x.textContent === "Từ chối")[0].click(); await tick(60);
  const lab = b.w.document.querySelector("#ec-lhn-pop .ec-lhn-btns span");
  ok("popover: sau Từ chối hiện 'Đã từ chối' màu đọc được trên nền trắng", lab && /Đã từ chối/.test(lab.textContent) && !/CECBF6/i.test(lab.getAttribute("style") || ""), lab && lab.outerHTML);
  b.w.document.body.click(); tlEv(b.w, "P1").click(); await tick();
  ok("mở lại popover: vẫn Đã từ chối", popBtns(b.w).length === 0 && /Đã từ chối/.test(b.w.document.getElementById("ec-lhn-pop").textContent), popBtns(b.w).join(","));
  b.w.close();

  // 4) failures are shown, never reported as saved
  b = boot([mtg("F1", 9, "none")], () => ({ ok: false, code: "RSVP_403" })); await tick(400);
  b.w.document.querySelector(".ec-lhn-hero button").click(); await tick(60);
  ok("{ok:false}: hiện lỗi kèm mã, nút vẫn còn", /RSVP_403/.test(heroTxt(b.w)) && heroBtns(b.w).length === 2 && !/Đã nhận/.test(heroTxt(b.w)));
  b.w.close();
  b = boot([mtg("F2", 9, "none")], "neterr"); await tick(400);
  b.w.document.querySelector(".ec-lhn-hero button").click(); await tick(60);
  ok("lỗi mạng: hiện lỗi (trước: im lặng)", /Không gửi được/.test(heroTxt(b.w)));
  b.w.close();

  let fail = 0;
  res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - fail}/${res.length} passed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
