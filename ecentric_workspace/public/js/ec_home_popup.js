// Copyright (c) 2026, eCentric and contributors
// Popup "Hôm nay ở eCentric" trên trang chủ (PO Hoàn chốt 29/09/2026).
// ĐẶC TẢ GIAO DIỆN: C:\dev\home-popup-su-kien\v3_ban_chot\popup_hom_nay_mockup_v3_chot.html
// (kiểu "Ảnh phủ kín"). Sửa ở đây phải giữ giống mockup - PO duyệt đúng bản đó.
//
// Nạp từ CHÍNH nguồn trang chủ (legacy_pages/home/main_section.html) bằng
// bundled_asset('ec_home_popup.bundle.js') + defer. Không nằm trong web_include_js.
//
// Luật (brief NHIEU_LOP/brief_popup_su_kien.md, A65):
//   * Popup NỔI (position:fixed + nền mờ), không chèn vào luồng trang, không dời gì của trang.
//     z-index 1040 < eC Mate (1045): nút eC Mate luôn nằm TRÊN nền mờ.
//   * Server (Jinja) đã cho biết có nội dung không: [data-ec-today="1"]. Không có -> không gọi API.
//   * Hiện mỗi lần mở trang chủ; tích "Không hiện lại hôm nay" -> nhớ trong trình duyệt theo
//     ngày + danh sách mục; trong ngày có mục MỚI (tin / sinh nhật / bạn mới) thì hiện lại.
//   * Chỉ hiện sau khi trang tải xong. Lỗi API -> im lặng (console), không toast cho cả công ty.
//   * File này không có cặp ngoặc nhọn kép / ngoặc-phần-trăm của Jinja.
(() => {
  'use strict';
  if (window.EcHomePopup) return;

  const API_GET = 'ecentric_workspace.home_today.api.get_today';
  const API_REACT = 'ecentric_workspace.home_today.api.toggle_reaction';
  const API_DRAW = 'ecentric_workspace.surveys.controllers.api.draw_result';
  const HIDE_KEY = 'ec_home_today_hide';
  const ROOT = 'ech-pop';
  const DUR = 7000;
  const COLORS = ['#2C3DA6', '#EF7CAF', '#10b981', '#e59400', '#7c5cd6', '#0e8fb3', '#d9534f'];
  const EMO = [['heart', '❤️'], ['flower', '🌸'], ['cake', '🎂'], ['party', '🎉']];
  const SCN = {
    news: { g: ['#0e8fb3', '#2C3DA6'], e: '📣', dots: ['#FFC000', '#fff', '#b8f5dd'] },
    bd: { g: ['#EF7CAF', '#7a4fc4'], e: '🎂', dots: ['#FFC000', '#fff', '#8fa0ff'] },
    new: { g: ['#10b981', '#0e7aa8'], e: '👋', dots: ['#FFC000', '#fff', '#b8f5dd'] },
    ev: { g: ['#2C3DA6', '#141c52'], e: '📅', dots: ['#FFC000', '#8fa0ff', '#fff'] },
    hol: { g: ['#FFC000', '#f08a24'], e: '🎆', dots: ['#fff', '#EF7CAF', '#2C3DA6'] },
    ann: { g: ['#7c5cd6', '#2C3DA6'], e: '🏅', dots: ['#FFC000', '#fff', '#EF7CAF'] },
    draw: { g: ['#7b3fe4', '#EF7CAF'], e: '🎰', dots: ['#FFC000', '#fff', '#8fa0ff'] },
    race: { g: ['#0f9f75', '#0ea5e9'], e: '🛒', dots: ['#FFC000', '#fff', '#b8f5dd'] },
  };

  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  // TEN goi do server tinh (Employee.first_name - ho so ERP ghi Ten Dem Ho); khong co thi chu dau.
  const given = (p) => (p && p.given) || String((p && p.name) || '').trim().split(/\s+/)[0] || '';
  const warn = (e) => { if (window.console && console.warn) console.warn('ec_home_popup:', e); };

  // ------------------------------------------------------------ nhớ "không hiện hôm nay" --
  const readHide = () => { try { return JSON.parse(window.localStorage.getItem(HIDE_KEY) || 'null'); } catch (e) { return null; } };
  const writeHide = (v) => { try { if (v) window.localStorage.setItem(HIDE_KEY, JSON.stringify(v)); else window.localStorage.removeItem(HIDE_KEY); } catch (e) { /* private mode */ } };
  const shouldShow = (data) => {
    const h = readHide();
    if (!h || h.d !== data.date) return true;
    const seen = new Set(h.k || []);
    return (data.keys || []).some((k) => !seen.has(k));
  };

  // ------------------------------------------------------------ CSS (một lần) ------------
  const P = '#' + ROOT;
  const CSS = [
    P + '{--navy:#2C3DA6;--navy-50:#eef0fb;--navy-100:#d9deef;--navy-900:#141c52;--yellow:#FFC000;--yellow-50:#fff8e1;',
    '--pink:#EF7CAF;--pink-50:#fdeef5;--green-50:#ecfdf5;--app-bg:#f7f8fb;--surface:#fff;--line:#e5e7eb;--line-soft:rgba(17,24,39,.07);',
    '--g400:#9ca3af;--g500:#6b7280;--g600:#4b5563;--g700:#374151;--g900:#111827;',
    'position:fixed;inset:0;z-index:1040;display:flex;align-items:center;justify-content:center;padding:22px;',
    "background:rgba(17,24,39,.5);font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:13.5px;line-height:1.5;color:var(--g900);animation:ech-in .2s ease}",
    P + ' *{box-sizing:border-box}',
    P + ' h2,' + P + ' h3,' + P + ' p{margin:0}',
    '@keyframes ech-in{from{opacity:0}}',
    P + ' .dlg{background:var(--surface);border-radius:18px;box-shadow:0 30px 70px rgba(0,0,0,.3);width:min(900px,100%);max-height:100%;display:flex;flex-direction:column;overflow:hidden}',
    P + ' .dlg:focus{outline:none}',
    P + ' .dh{display:flex;align-items:center;gap:12px;padding:14px 18px 14px 22px;border-bottom:1px solid var(--line)}',
    P + ' .dh .t{flex:1;min-width:0}',
    P + ' .dh h2{font-size:17px;font-weight:800;letter-spacing:-.2px;color:var(--g900);line-height:1.3}',
    P + ' .dh p{font-size:12px;color:var(--g500)}',
    P + ' .x{all:unset;cursor:pointer;width:32px;height:32px;border-radius:8px;display:grid;place-items:center;font-size:20px;line-height:1;color:var(--g600)}',
    P + ' .x:hover{background:var(--app-bg)}',
    P + ' .x:focus-visible{outline:3px solid var(--yellow)}',
    P + ' .dbody{display:grid;grid-template-columns:236px minmax(0,1fr);min-height:0;flex:1}',
    P + ' .thumbs{display:flex;flex-direction:column;gap:8px;padding:14px;background:var(--app-bg);border-right:1px solid var(--line);overflow:auto}',
    P + ' .th{all:unset;cursor:pointer;position:relative;display:grid;grid-template-columns:1fr;align-items:center;padding:0;height:74px;flex:none;border-radius:12px;overflow:hidden;min-width:0;transition:box-shadow .15s,opacity .15s}',
    P + ' .th::after{content:"";position:absolute;inset:0;border-radius:12px;background:linear-gradient(90deg,rgba(0,0,0,.35),rgba(0,0,0,0) 70%);pointer-events:none}',
    P + ' .th:focus-visible{outline:3px solid var(--yellow);outline-offset:1px}',
    P + ' .th .img{position:absolute;inset:0;width:100%;height:100%;border-radius:12px;overflow:hidden;display:block}',
    P + ' .th .img svg,' + P + ' .th .img img{width:100%;height:100%;display:block;object-fit:cover}',
    P + ' .th .tx{position:relative;z-index:1;min-width:0;display:flex;flex-direction:column;padding:0 34px 0 12px;color:#fff;text-shadow:0 1px 6px rgba(0,0,0,.35)}',
    P + ' .th .tt{font-weight:700;font-size:13px;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    P + ' .th .ts{font-size:11.5px;color:rgba(255,255,255,.9);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    P + ' .th .ct{position:absolute;z-index:2;top:6px;right:8px;background:var(--pink);color:#fff;font-size:10.5px;font-weight:800;border-radius:999px;padding:0 6px;line-height:16px}',
    P + ' .th .ct.soon{background:var(--yellow-50);color:#8a6400}',
    P + ' .th[aria-selected="true"]{box-shadow:0 0 0 3px var(--surface),0 0 0 5px var(--navy)}',
    P + ' .th:not([aria-selected="true"]){opacity:.78}',
    P + ' .th:hover{opacity:1}',
    P + ' .th .prog{position:absolute;z-index:2;left:10px;right:10px;bottom:3px;height:3px;border-radius:2px;overflow:hidden}',
    P + ' .th[aria-selected="true"] .prog{background:rgba(255,255,255,.35)}',
    P + ' .th[aria-selected="true"] .prog i{display:block;height:100%;width:0;background:#fff;animation:ech-prog ' + DUR + 'ms linear forwards}',
    P + ' .paused .th .prog i{animation-play-state:paused}',
    '@keyframes ech-prog{to{width:100%}}',
    P + ' .stage{display:flex;flex-direction:column;min-width:0;min-height:0;overflow:auto}',
    P + ' .hero{position:relative;height:170px;flex:none;overflow:hidden}',
    P + ' .hero svg,' + P + ' .hero img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}',
    // lop toi (::after) va chu (.cap/.cnt) nam TREN anh -> cho click xuyen xuong link
    P + ' .hero .hlink{position:absolute;inset:0;display:block;cursor:pointer}',
    P + ' .hero .hlink~.cap,' + P + ' .hero .hlink~.cnt{pointer-events:none}',
    P + ' .hero .hlink:focus-visible{outline:3px solid #fff;outline-offset:-3px}',
    P + ' .hero.photo::after{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(0deg,rgba(0,0,0,.55),rgba(0,0,0,0) 65%)}',
    P + ' .hero .cap{position:absolute;z-index:1;left:22px;bottom:16px;right:22px;color:#fff;text-shadow:0 2px 10px rgba(0,0,0,.25)}',
    P + ' .hero .cap small{font-size:11px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;opacity:.9}',
    P + ' .hero .cap h3{margin:2px 0 0;font-size:24px;font-weight:800;letter-spacing:-.4px;line-height:1.2;text-wrap:balance;color:#fff}',
    P + ' .hero .cnt{position:absolute;z-index:1;right:18px;top:14px;background:rgba(255,255,255,.2);backdrop-filter:blur(4px);color:#fff;font-size:12px;font-weight:700;border-radius:999px;padding:3px 10px;font-variant-numeric:tabular-nums}',
    P + ' .content{padding:16px 22px 18px;display:flex;flex-direction:column;gap:14px;animation:ech-fade .3s ease}',
    '@keyframes ech-fade{from{opacity:0;transform:translateY(4px)}}',
    P + ' .eyebrow{font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--g500)}',
    P + ' .ppl{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}',
    P + ' .pc{display:flex;gap:12px;align-items:flex-start;padding:12px;border:1px solid var(--line);border-radius:12px;min-width:0}',
    P + ' .pc .who{flex:1;min-width:0;display:flex;flex-direction:column}',
    P + ' .pc .nm{font-weight:700;font-size:14px}',
    P + ' .pc .rl,' + P + ' .sl .rl,' + P + ' .hol .rl,' + P + ' .note{font-size:12px;color:var(--g500)}',
    P + ' .ava{flex:none;width:42px;height:42px;border-radius:50%;display:grid;place-items:center;font-weight:800;font-size:14px;color:#fff;position:relative}',
    P + ' .ava.ring{box-shadow:0 0 0 3px var(--surface),0 0 0 5px var(--yellow)}',
    P + ' .ava.lg{width:64px;height:64px;font-size:21px}',
    P + ' .intro{margin:6px 0 0;padding:9px 12px;border-left:3px solid var(--yellow);background:var(--navy-50);border-radius:8px;font-size:12.5px;font-style:italic;color:var(--g700);white-space:pre-wrap}',
    P + ' .soonlist{display:flex;flex-direction:column}',
    P + ' .sl{display:grid;grid-template-columns:54px 30px 1fr;gap:10px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line-soft)}',
    P + ' .sl:last-child{border-bottom:0}',
    P + ' .sl time{font-variant-numeric:tabular-nums;font-weight:800;color:var(--navy);font-size:13px}',
    P + ' .sl .ava{width:30px;height:30px;font-size:11px}',
    P + ' .hol{display:grid;grid-template-columns:64px 1fr auto;gap:12px;align-items:center;padding:10px 12px;border:1px solid var(--line);border-radius:12px}',
    P + ' .hol .dd{text-align:center;border-radius:10px;background:var(--yellow-50);padding:5px 0;line-height:1.1}',
    P + ' .hol .dd b{display:block;font-size:20px;font-weight:800;color:#8a6400;font-variant-numeric:tabular-nums}',
    P + ' .hol .dd small{font-size:10.5px;font-weight:700;color:#8a6400}',
    P + ' .hol .nm{font-weight:700}',
    P + ' a.hol{color:inherit;text-decoration:none}', P + ' a.hol:hover{border-color:var(--navy-100);background:var(--navy-50)}',
    P + ' .wish{display:inline-block;margin-top:6px;font-size:12px;font-weight:600;color:var(--navy);text-decoration:none}', P + ' .wish:hover{text-decoration:underline}',
    P + ' .hol .left{font-size:12px;font-weight:700;color:var(--navy);background:var(--navy-50);padding:3px 9px;border-radius:999px;white-space:nowrap;font-variant-numeric:tabular-nums}',
    P + ' .wipbox{display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px;padding:18px 10px;border:1px dashed var(--navy-100);border-radius:12px;color:var(--g600)}',
    P + ' .wipbox b{font-size:15px;color:var(--g900)}',
    P + ' .soon-tag{background:var(--yellow-50);color:#8a6400;font-weight:700;font-size:11px;padding:2px 9px;border-radius:999px}',
    P + ' .rx{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}',
    P + ' .pc{position:relative;padding-right:46px}',
    P + ' .rxadd{position:absolute;top:8px;right:8px;z-index:4}',
    P + ' .rxbtn{all:unset;cursor:pointer;width:32px;height:32px;border-radius:9px;display:grid;place-items:center;color:var(--g500);transition:background .12s,color .12s}',
    P + ' .rxbtn:hover,' + P + ' .rxadd.open .rxbtn,' + P + ' .rxadd:hover .rxbtn{background:var(--app-bg);color:var(--navy)}',
    P + ' .rxbtn:focus-visible{outline:3px solid var(--yellow)}',
    P + ' .rxpick{position:absolute;right:0;top:100%;display:none;gap:2px;padding:4px;margin-top:2px;background:var(--surface);border:1px solid var(--line);border-radius:999px;box-shadow:0 10px 26px rgba(17,24,39,.16)}',
    P + ' .rxpick::before{content:"";position:absolute;left:0;right:0;top:-8px;height:8px}',
    P + ' .rxadd:hover .rxpick,' + P + ' .rxadd:focus-within .rxpick,' + P + ' .rxadd.open .rxpick{display:flex}',
    P + ' .rxadd.rest:not(.open) .rxpick{display:none}',
    P + ' .rxpick button{all:unset;cursor:pointer;width:36px;height:36px;border-radius:50%;display:grid;place-items:center;font-size:20px;line-height:1;transition:transform .12s,background .12s}',
    P + ' .rxpick button:hover{transform:translateY(-2px) scale(1.25);background:var(--app-bg)}',
    P + ' .rxpick button[aria-pressed="true"]{background:var(--pink-50)}',
    P + ' .rxpick button:focus-visible{outline:3px solid var(--yellow)}',
    P + ' .rb{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line);background:var(--surface);border-radius:999px;padding:3px 10px 3px 7px;font-size:13px;line-height:1.5;position:relative;transition:transform .12s}',
    P + ' .rb .c{font-size:12px;font-weight:700;color:var(--g600);font-variant-numeric:tabular-nums;min-width:1ch}',
    P + ' .rb[aria-pressed="true"]{background:var(--pink-50);border-color:var(--pink)}',
    P + ' .rb[aria-pressed="true"] .c{color:#b3246a}',
    P + ' .rb:hover{transform:translateY(-1px)}',
    P + ' .rb:focus-visible{outline:3px solid var(--yellow)}',
    P + ' .rb[aria-busy="true"]{opacity:.6;cursor:progress}',
    P + ' .rb.pop{animation:ech-pop .35s ease}',
    '@keyframes ech-pop{40%{transform:scale(1.3)}}',
    // Neo trai o cam xuc (khong canh giua): o nam sat mep trai the, canh giua thi nua tip lot ra ngoai
    // .stage (overflow:auto) va bi cat (PO 01/10). Dai qua 240px thi xuong dong, khong keo dai ra.
    P + ' .tip{position:absolute;bottom:calc(100% + 6px);left:0;background:var(--g900);color:#fff;font-size:11.5px;line-height:1.4;padding:6px 9px;border-radius:7px;width:max-content;max-width:240px;white-space:normal;pointer-events:none;opacity:0;transition:opacity .12s;z-index:5}',
    P + ' .rb:hover .tip,' + P + ' .rb:focus-visible .tip{opacity:1}',
    P + ' .nw{display:flex;flex-direction:column;gap:5px;padding:12px 14px;border:1px solid var(--line);border-radius:12px}',
    P + ' .nw.first{border-color:var(--navy-100);background:linear-gradient(180deg,var(--navy-50),var(--surface) 70%)}',
    P + ' .nw .meta{display:flex;align-items:center;gap:8px;font-size:11.5px;color:var(--g500)}',
    P + ' .nw .tg{font-size:10.5px;font-weight:800;letter-spacing:.4px;text-transform:uppercase;padding:2px 8px;border-radius:999px}',
    P + ' .tg.pol{background:var(--navy-50);color:var(--navy)}' + P + ' .tg.mod{background:var(--green-50);color:#047857}' + P + ' .tg.inf{background:var(--yellow-50);color:#8a6400}',
    '@media (max-width:760px){' + P + ' .poster{min-height:min(46vh,340px)}' + P + ' .pbar{padding:10px 16px;flex-wrap:wrap}}',
    P + ' .nw .tt{font-weight:800;font-size:15px;line-height:1.35}',
    P + ' .nw.first .tt{font-size:16.5px}',
    P + ' .nw .ex{font-size:12.5px;color:var(--g600);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}',
    P + ' .nw .body{font-size:13px;color:var(--g700);overflow-wrap:anywhere}',
    P + ' .nw .body img{max-width:100%;height:auto}',
    P + ' .nw .acts{display:flex;gap:16px;flex-wrap:wrap}',
    P + ' .poster{position:relative;flex:1 1 auto;min-height:320px;background:#0f1535;overflow:hidden}',
    P + ' .poster .bg{position:absolute;inset:-24px;width:calc(100% + 48px);height:calc(100% + 48px);object-fit:cover;filter:blur(22px) brightness(.6);transform:scale(1.05)}',
    P + ' .poster .pimg{position:absolute;inset:0;display:grid;place-items:center;cursor:zoom-in}',
    P + ' .poster .pimg.go{cursor:pointer}',
    P + ' .poster .pimg img{max-width:100%;max-height:100%;object-fit:contain;display:block;box-shadow:0 10px 30px rgba(0,0,0,.35)}',
    P + ' .pbar{display:flex;align-items:center;gap:10px;padding:12px 22px;border-top:1px solid var(--line);min-width:0}',
    P + ' .pbar b{flex:1;min-width:0;font-size:14.5px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    P + ' .pbar .tg{font-size:10.5px;font-weight:800;letter-spacing:.4px;text-transform:uppercase;padding:2px 8px;border-radius:999px;white-space:nowrap}',
    P + ' .pbar a{all:unset;cursor:pointer;flex:none;background:var(--navy);color:#fff;font-weight:700;font-size:12.5px;padding:7px 14px;border-radius:9px}',
    P + ' .pbar a:focus-visible{outline:3px solid var(--yellow);outline-offset:2px}',
    P + ' .nw a,' + P + ' .nw .more{all:unset;cursor:pointer;align-self:flex-start;font-weight:700;font-size:12.5px;color:var(--navy);text-decoration:none}',
    P + ' .nw a:hover,' + P + ' .nw .more:hover{text-decoration:underline}',
    P + ' .nw a:focus-visible,' + P + ' .nw .more:focus-visible{outline:3px solid var(--yellow);outline-offset:2px;border-radius:4px}',
    P + ' .df{display:flex;align-items:center;gap:12px;padding:11px 18px 11px 22px;border-top:1px solid var(--line)}',
    P + ' .df label{flex:1;display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--g600);cursor:pointer;margin:0;font-weight:400}',
    P + ' .df input{width:16px;height:16px;margin:0;accent-color:var(--navy)}',
    P + ' .df .pg{font-size:12px;color:var(--g500);font-variant-numeric:tabular-nums}',
    P + ' .nav{all:unset;cursor:pointer;width:32px;height:32px;border-radius:50%;border:1px solid var(--line);display:grid;place-items:center;font-size:16px;color:var(--g700)}',
    P + ' .nav:focus-visible{outline:3px solid var(--yellow)}',
    P + ' .ok{all:unset;cursor:pointer;background:var(--navy);color:#fff;font-weight:700;font-size:13px;padding:9px 18px;border-radius:9px}',
    P + ' .ok:focus-visible{outline:3px solid var(--yellow);outline-offset:2px}',
    // O "Quay so may man" (module Khao sat, 01/10): khung hieu ung + "Luot quay tiep theo".
    // .stage la flex cot: khong co flex:none thi khung hieu ung bi ep lun va de len danh sach ben duoi.
    P + ' .drw,' + P + ' .drsel,' + P + ' .upn,' + P + ' .drempty{flex:none}',
    P + ' .drsel{display:flex;flex-wrap:wrap;gap:6px;padding:10px 20px 0}',
    P + ' .drsel button{all:unset;cursor:pointer;border:1px solid var(--line);border-radius:999px;padding:3px 12px;font-size:12px;font-weight:700;color:var(--g600)}',
    P + ' .drsel button[aria-pressed="true"]{background:var(--navy);border-color:var(--navy);color:#fff}',
    P + ' .upn{border-top:1px solid var(--line);padding:12px 20px 16px;display:flex;flex-direction:column;gap:8px;background:var(--app-bg)}',
    P + ' .upn-h{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;align-items:center}',
    P + ' .upn-h b{font-size:14px}',
    P + ' .upn-h b span{display:inline-block;margin-left:6px;background:var(--navy-50);color:var(--navy);border-radius:999px;padding:0 8px;font-size:11.5px}',
    P + ' .upn-i{position:relative;display:grid;grid-template-columns:36px 44px minmax(0,1fr) auto;gap:12px;align-items:center;background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--uc);border-radius:12px;padding:7px 12px}',
    // Hop qua dau dong (PO 02/10): tro chuot / cham -> danh sach qua cua luot quay.
    P + ' .upn-i:hover,' + P + ' .upn-i:focus-within{z-index:2}',
    P + ' .ugift{position:relative}',
    P + ' .ugift>button{all:unset;cursor:pointer;position:relative;width:36px;height:36px;border-radius:10px;background:#ffd43b;color:#5c4100;display:grid;place-items:center;box-shadow:0 3px 8px rgba(0,0,0,.14);transition:transform .18s ease}',
    P + ' .ugift>button svg{width:18px;height:18px}',
    P + ' .ugift>button:hover,' + P + ' .ugift.on>button{transform:rotate(-6deg)}',
    P + ' .ugift>button:focus-visible{outline:3px solid var(--navy);outline-offset:2px}',
    P + ' .ugift .cnt{position:absolute;top:-6px;right:-6px;min-width:17px;height:17px;padding:0 4px;border-radius:9px;background:#e8384f;color:#fff;font-size:10.5px;font-weight:700;line-height:17px;text-align:center;font-variant-numeric:tabular-nums}',
    P + ' .ugpop{position:fixed;left:0;top:0;width:250px;max-width:calc(100vw - 60px);background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:0 12px 28px rgba(16,24,40,.2);padding:11px 12px;display:flex;flex-direction:column;gap:7px;opacity:0;visibility:hidden;transform:translateY(-4px);transition:opacity .15s ease,transform .15s ease,visibility .15s;z-index:5;max-height:260px;overflow:auto}',
    P + ' .ugpop::before,' + P + ' .ugpop::after{content:"";position:absolute;left:0;right:0;height:10px}' + P + ' .ugpop::before{top:-10px}' + P + ' .ugpop::after{bottom:-10px}',
    // Popover position:fixed + JS dat toa do (placeGift): .stage la khung cuon overflow:auto, absolute
    // mo len / xuong deu bi khung cat (Hoan 02/10 "bi che mat").
    P + ' .ugift:hover .ugpop,' + P + ' .ugift:focus-within .ugpop,' + P + ' .ugift.on .ugpop{opacity:1;visibility:visible;transform:none}',
    P + ' .ugpop .h{display:flex;align-items:center;gap:6px;font-weight:700;font-size:12.5px;color:#6b4e00}',
    P + ' .ugpop .h span{margin-left:auto;color:var(--g500);font-weight:500}',
    P + ' .ugpop ol{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:5px}',
    P + ' .ugpop li{display:flex;align-items:center;gap:8px;font-size:12.5px}',
    P + ' .ugpop li i{font-style:normal;flex:none;width:19px;height:19px;border-radius:6px;background:#fff4cc;color:#6b4e00;font-size:10.5px;font-weight:700;display:grid;place-items:center}',
    P + ' .ugpop li span{flex:1;min-width:0}' + P + ' .ugpop li b{flex:none;font-variant-numeric:tabular-nums}',
    P + ' .ugpop .w{font-size:11.5px;color:var(--g500);border-top:1px dashed var(--line);padding-top:7px}',
    P + ' .upn-d{border-radius:10px;background:var(--ub);color:var(--uc);display:flex;flex-direction:column;align-items:center;padding:3px 0;line-height:1.1}',
    P + ' .upn-d b{font-size:18px;font-weight:800;font-variant-numeric:tabular-nums}' + P + ' .upn-d small{font-size:10px;font-weight:700;text-transform:uppercase}',
    P + ' .upn-b{min-width:0;display:flex;flex-direction:column}',
    P + ' .upn-b b{font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    P + ' .upn-b small{font-size:11.5px;font-weight:700;color:var(--uc)}',
    P + ' .upn-r{display:flex;align-items:center;gap:10px;flex-wrap:wrap;justify-content:flex-end;font-size:12.5px}',
    P + ' .upn-r .ok{all:unset;color:#047857}' + P + ' .upn-r .todo{color:#b3246a;font-weight:600}' + P + ' .upn-r .wait{color:var(--g500)}',
    P + ' .upn-r a{all:unset;cursor:pointer;border:1px solid var(--line);border-radius:8px;padding:4px 10px;font-weight:700;font-size:12px;color:var(--navy);background:var(--surface)}',
    P + ' .upn-r a:focus-visible{outline:3px solid var(--yellow)}',
    P + ' .upn-left{font-size:11px;font-weight:700;color:var(--g600);background:var(--line);border-radius:999px;padding:2px 8px;white-space:nowrap}',
    P + ' .drempty{padding:18px 20px;display:flex;flex-direction:column;gap:4px}',
    '@media (max-width:760px){',
    P + '{padding:10px 10px 92px}',
    P + ' .upn-i{grid-template-columns:36px 44px minmax(0,1fr)}' + P + ' .upn-r{grid-column:2/-1;justify-content:flex-start}',
    P + ' .dbody{grid-template-columns:1fr;grid-template-rows:auto 1fr}',
    P + ' .thumbs{flex-direction:row;overflow-x:auto;border-right:0;border-bottom:1px solid var(--line);padding:10px}',
    P + ' .th{flex:none;width:130px;height:64px}',
    P + ' .hero{height:130px}' + P + ' .hero .cap h3{font-size:19px}',
    P + ' .content{padding:14px 16px}',
    P + ' .df{flex-wrap:wrap;padding:10px 16px}' + P + ' .df label{flex-basis:100%}',
    '}',
    '@media (prefers-reduced-motion:reduce){' + P + ',' + P + ' *{animation:none!important;transition:none!important}}',
  ].join('\n');

  const injectCss = () => {
    if (document.getElementById(ROOT + '-css')) return;
    const st = document.createElement('style');
    st.id = ROOT + '-css';
    st.textContent = CSS;
    document.head.appendChild(st);
  };

  // ------------------------------------------------------------ ảnh minh hoạ (SVG) -------
  let gidSeq = 0;
  const scene = (k, big) => {
    const s = SCN[k];
    const gid = ROOT + '-g' + (gidSeq += 1);
    let dots = '';
    for (let i = 0; i < (big ? 26 : 9); i += 1) {
      const x = (i * 83) % 400;
      const y = (i * 47) % 170;
      const r = 2 + (i % 3) * 1.6;
      dots += i % 4 === 0
        ? '<rect x="' + x + '" y="' + y + '" width="' + (r * 1.6) + '" height="' + (r * 3) + '" rx="1" fill="' + s.dots[i % 3] + '" opacity=".75" transform="rotate(' + (i * 37) + ' ' + x + ' ' + y + ')"/>'
        : '<circle cx="' + x + '" cy="' + y + '" r="' + r + '" fill="' + s.dots[i % 3] + '" opacity=".6"/>';
    }
    return '<svg viewBox="0 0 400 170" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
      + '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="' + s.g[0] + '"/><stop offset="1" stop-color="' + s.g[1] + '"/></linearGradient></defs>'
      + '<rect width="400" height="170" fill="url(#' + gid + ')"/>'
      + '<circle cx="340" cy="40" r="90" fill="#fff" opacity=".08"/><circle cx="40" cy="170" r="70" fill="#fff" opacity=".07"/>'
      + dots
      + '<text x="330" y="' + (big ? 112 : 110) + '" font-size="' + (big ? 92 : 80) + '" text-anchor="middle">' + s.e + '</text></svg>';
  };
  const cover = (sl, big) => (sl.image
    ? '<img src="' + esc(sl.image) + '" alt="" loading="lazy">'
    : scene(sl.k, big));

  // ------------------------------------------------------------ mảnh nội dung -----------
  const ava = (p, cls) => '<span class="ava ' + (cls || '') + '" style="background:' + COLORS[(p.color || 0) % COLORS.length] + '">' + esc(p.initials || '?') + '</span>';

  // Cam xuc kieu Teams (PO 29/09 16:27): goc tren phai the co MOT nut mat cuoi (+); re chuot /
  // cham -> hien 4 icon de chon. Duoi ten CHI hien cam xuc DA co nguoi tha (icon + so); chua ai
  // tha thi khong hien gi. Bam vao o cam xuc = bat/tat cua minh.
  const SMILE_ADD = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">'
    + '<path d="M20.5 11.5A8.5 8.5 0 1 1 12.5 3"/><path d="M8.5 14.5c.9 1.2 2.1 1.8 3.5 1.8s2.6-.6 3.5-1.8"/><circle cx="9" cy="10" r=".9" fill="currentColor" stroke="none"/>'
    + '<circle cx="15" cy="10" r=".9" fill="currentColor" stroke="none"/><path d="M19 2.5v5M16.5 5h5"/></svg>';
  const rxState = (st, key) => {
    const per = (st.data.reactions || {})[key];
    return per ? EMO.map(([k, e]) => ({ k, e, v: per[k] || { n: 0, names: [], mine: false } })) : null;
  };
  const rxAdd = (st, key) => {
    const all = rxState(st, key);
    if (!all) return '';
    return '<div class="rxadd' + (st.pick === key ? ' open' : '') + '"><button type="button" class="rxbtn" data-rxopen="' + esc(key) + '" aria-label="Thả cảm xúc" aria-haspopup="true" aria-expanded="' + (st.pick === key) + '">' + SMILE_ADD + '</button>'
      + '<div class="rxpick" role="menu">' + all.map((x) => '<button type="button" role="menuitem" aria-pressed="' + (!!x.v.mine) + '" data-rx="' + esc(key) + '|' + x.k + '" aria-label="' + x.e + '">' + x.e + '</button>').join('') + '</div></div>';
  };
  const rxHTML = (st, key) => {
    const all = rxState(st, key);
    const used = (all || []).filter((x) => x.v.n > 0);
    if (!used.length) return '';
    return '<div class="rx">' + used.map(({ k, e, v }) => {
      const who = (v.mine ? ['Bạn'] : []).concat(v.names || []);
      const extra = Math.max(who.length - 5, 0) + Math.max(v.n - who.length, 0);
      const tip = who.slice(0, 5).join(', ') + (extra ? ' +' + extra : '');
      return '<button type="button" class="rb" aria-pressed="' + (!!v.mine) + '" data-rx="' + esc(key) + '|' + k + '" aria-label="' + e + ' ' + v.n + '">'
        + e + '<span class="c">' + v.n + '</span><span class="tip">' + esc(tip) + '</span></button>';
    }).join('') + '</div>';
  };

  // Loi chuc tren Bang tin (04/10/2026): cung khoa voi o cam xuc; so loi chuc do server dem.
  let WISHES = {};
  const wishHTML = (key) => {
    if (!key) return '';
    const n = WISHES[key] || 0;
    return '<a class="wish" href="/bang-tin#m-' + esc(String(key).replace(/:/g, '-')) + '">💬 ' + (n ? n + ' lời chúc trên Bảng tin' : 'Gửi lời chúc trên Bảng tin') + '</a>';
  };
  const person = (st, p, sub) => '<div class="pc">' + (p.key ? rxAdd(st, p.key) : '') + ava(p, 'ring') + '<div class="who"><span class="nm">' + esc(p.name) + '</span>'
    + '<span class="rl">' + esc([p.role, sub].filter(Boolean).join(' · ')) + '</span>' + (p.key ? rxHTML(st, p.key) : '') + wishHTML(p.key) + '</div></div>';

  const linkHTML = (n) => '<a href="' + esc(n.url) + '"' + (/^https?:/i.test(n.url) ? ' target="_blank" rel="noopener"' : '') + '>' + esc(n.link_label || 'Mở →') + '</a>';
  const newsHTML = (st, list) => list.map((n, i) => {
    const open = st.open[n.key];
    let act = '';
    if (n.content_html) act += '<button type="button" class="more" data-more="' + esc(n.key) + '">' + (open ? 'Thu gọn ↑' : 'Xem chi tiết →') + '</button>';
    if (n.url) act += linkHTML(n);
    if (act) act = '<div class="acts">' + act + '</div>';
    return '<div class="nw' + (i ? '' : ' first') + '"><div class="meta"><span class="tg ' + esc(n.tag) + '">' + esc(n.tag_label) + '</span>' + esc(n.date_label) + '</div>'
      + '<div class="tt">' + esc(n.title) + '</div>'
      + (open && n.content_html ? '<div class="body">' + n.content_html + '</div>' : (n.excerpt ? '<div class="ex">' + esc(n.excerpt) + '</div>' : ''))
      + act + '</div>';
  }).join('');

  // ------------------------------------------------------------ các ô --------------------
  const buildSlides = (d) => {
    const out = [];
    WISHES = d.wishes || {};
    const news = d.news || [];
    const bd = d.birthdays || { today: [], soon: [] };
    const nw = d.onboard || [];
    const hol = d.holidays || [];
    const ann = d.anniversaries || [];
    // "Chi anh (hien full)": moi poster MOT o, anh phu kin khung ben phai.
    news.filter((n) => n.poster).forEach((n) => {
      out.push({ k: 'news', t: n.title || n.tag_label, s: n.tag_label + ' · ' + n.date_label, ct: null, image: n.image,
        poster: n, hs: n.tag_label, h: n.title, cnt: '' });
    });
    const texts = news.filter((n) => !n.poster);
    if (texts.length) {
      const tags = [...new Set(texts.map((n) => n.tag_label))];
      out.push({ k: 'news', t: 'Thông báo', s: tags.join(' · '), ct: texts.length, hs: 'Thông báo công ty',
        h: texts[0].title, cnt: texts.length + ' thông báo', image: texts[0].image, image_url: texts[0].image_url || '',
        body: (st) => newsHTML(st, texts) });
    }
    if (bd.today.length || bd.soon.length) {
      const n = bd.today.length;
      const sub = [n ? n + ' hôm nay' : '', bd.soon.length ? bd.soon.length + ' tuần này' : ''].filter(Boolean).join(' · ');
      const names = bd.today.map((p) => given(p));
      const h = n ? 'Chúc mừng sinh nhật ' + (names.length > 1 ? names.slice(0, -1).join(', ') + ' và ' + names[names.length - 1] : names[0]) + '!' : 'Sinh nhật 7 ngày tới';
      out.push({ k: 'bd', t: 'Sinh nhật', s: sub, ct: n || null, hs: 'Sinh nhật', h, cnt: n ? n + ' hôm nay' : bd.soon.length + ' sắp tới',
        body: (st) => (n ? '<div class="eyebrow">Hôm nay · ' + esc(d.date_label.split(', ')[1] ? d.date_label.split(', ')[1].slice(0, 5) : '') + '</div><div class="ppl">' + bd.today.map((p) => person(st, p)).join('') + '</div>' : '')
          + (bd.soon.length ? '<div class="eyebrow">7 ngày tới</div><div class="soonlist">' + bd.soon.map((p) => '<div class="sl"><time>' + esc(p.date) + '</time>' + ava(p) + '<div><b>' + esc(p.name) + '</b> <span class="rl">· ' + esc([p.role, p.weekday].filter(Boolean).join(' · ')) + '</span></div></div>').join('') + '</div>' : '') });
    }
    if (nw.length) {
      const one = nw.length === 1;
      out.push({ k: 'new', t: 'Bạn mới', s: one ? [nw[0].name, nw[0].role.split(' · ').pop()].filter(Boolean).join(' · ') : nw.length + ' bạn mới', ct: nw.length,
        hs: 'Chào bạn mới', h: one ? 'Hôm nay là ngày đầu tiên của ' + nw[0].name : 'Chào ' + nw.length + ' bạn mới hôm nay', cnt: nw.length + ' bạn mới',
        body: (st) => nw.map((p) => '<div class="pc" style="align-items:center">' + rxAdd(st, p.key) + ava(p, 'lg ring') + '<div class="who"><span class="nm" style="font-size:17px">' + esc(p.name) + '</span><span class="rl">' + esc(p.role) + '</span>'
          + (p.intro ? '<p class="intro">' + esc(p.intro) + '</p>' : '') + rxHTML(st, p.key) + wishHTML(p.key) + '</div></div>').join('')
          + '<p class="note">Cả nhà cùng say hi và giúp bạn ấy làm quen nhé.</p>' });
    }
    // Su kien CLB tu Bang tin (04/10/2026) thay o "Sap ra mat". Moi dong la link toi bai su kien.
    const evs = d.events || [];
    if (evs.length) {
      const e0 = evs[0];
      out.push({ k: 'ev', t: 'Sự kiện sắp tới', s: e0.title + ' · ' + (e0.days_left > 0 ? 'còn ' + e0.days_left + ' ngày' : 'hôm nay'), ct: evs.length,
        hs: 'Sự kiện sắp tới', h: (e0.emoji ? e0.emoji + ' ' : '') + e0.title, cnt: evs.length + ' sự kiện',
        body: () => evs.map((x) => '<a class="hol" href="' + esc(x.url) + '"><div class="dd"><b>' + esc(x.day) + '</b><small>' + esc(x.month) + '</small></div><div><div class="nm">'
          + esc((x.emoji ? x.emoji + ' ' : '') + x.title) + '</div><div class="rl">' + esc([x.when, x.place, x.club ? 'CLB ' + x.club : ''].filter(Boolean).join(' · ')) + '</div></div>'
          + (x.going ? '<span class="left">' + x.going + ' tham gia</span>' : '') + '</a>').join('')
          + '<p class="note"><a href="/bang-tin?loc=su-kien">Xem tất cả trên Bảng tin →</a></p>' });
    } else if (d.event_coming_soon) {
      out.push({ k: 'ev', t: 'Sự kiện công ty', s: 'Sắp ra mắt', ct: 'soon', hs: 'Sự kiện công ty', h: 'Lịch sự kiện đang được xây dựng', cnt: 'Sắp ra mắt',
        body: () => '<div class="wipbox"><span class="soon-tag">Sắp ra mắt</span><b>Team building, workshop, tiệc cuối năm…</b><span>Khi HR nhập lịch sự kiện, các sự kiện sắp tới sẽ hiện ở đây kèm ngày giờ và địa điểm.</span></div>' });
    }
    if (hol.length) {
      out.push({ k: 'hol', t: 'Nghỉ lễ sắp tới', s: hol[0].name + ' · còn ' + hol[0].days_left + ' ngày', ct: null, hs: 'Nghỉ lễ sắp tới', h: hol[0].name,
        cnt: hol[0].days_left ? 'Còn ' + hol[0].days_left + ' ngày' : 'Hôm nay',
        body: () => hol.map((x) => '<div class="hol"><div class="dd"><b>' + esc(x.day) + '</b><small>' + esc(x.month) + '</small></div><div><div class="nm">' + esc(x.name) + '</div><div class="rl">'
          + esc(x.date_label + (x.days_off > 1 ? ' · nghỉ ' + x.days_off + ' ngày' : '')) + '</div></div><span class="left">' + (x.days_left ? 'còn ' + x.days_left + ' ngày' : 'hôm nay') + '</span></div>').join('') });
    }
    const dr = d.draws || {};
    const today = dr.draws || [];
    if (today.length || dr.soon) {
      const first = today[0];
      const race = first ? first.mode === 'race' : (dr.upcoming || [])[0] && dr.upcoming[0].mode === 'race';
      const sl = { k: race ? 'race' : 'draw', draw: true, t: race && today.length ? 'Đua về đích' : 'Quay số may mắn',
        s: first ? first.title + ' · ' + hhmm(first.draw_at) : (dr.upcoming.length + ' lượt sắp tới'),
        ct: today.length ? (today.some((x) => x.state !== 'done') ? 'live' : null) : dr.upcoming.length || null };
      // Ngay co quay: o nay dung DAU (PO 01/10 - "dung dau slider trong ngay co quay so").
      if (today.length) out.unshift(sl); else out.push(sl);
    }
    if (ann.length) {
      const one = ann.length === 1;
      out.push({ k: 'ann', t: 'Kỷ niệm gắn bó', s: one ? ann[0].name + ' · ' + ann[0].years + ' năm' : ann.length + ' người', ct: ann.length, hs: 'Kỷ niệm gắn bó',
        h: one ? given(ann[0]) + ' tròn ' + ann[0].years + ' năm cùng eCentric' : ann.length + ' người tròn năm gắn bó hôm nay', cnt: ann.length + ' người',
        body: (st) => ann.map((p) => person(st, p, 'vào công ty ' + p.joined + ' · ' + p.years + ' năm')).join('') });
    }
    return out;
  };

  // ------------------------------------------------------------ quay so (Khao sat) ---------
  const hhmm = (s) => String(s || '').slice(11, 16);
  const ME = {
    holding: (u) => ['ok', '✓ Bạn giữ số ' + u.my_number],
    joined: () => ['ok', '✓ Bạn đã có xe'],
    pick: () => ['todo', 'Đã nộp - chưa chọn số'],
    not_submitted: (u) => ['todo', u.mode === 'race' ? 'Chưa nộp phiếu - chưa có xe' : 'Chưa nộp phiếu'],
    not_open: (u) => ['wait', 'Mở phiếu từ ' + String(u.open_at || '').slice(8, 10) + '/' + String(u.open_at || '').slice(5, 7)],
    closed: () => ['wait', 'Đã đóng phiếu'],
  };
  const GIFT_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="8" width="18" height="13" rx="1"/><path d="M12 8v13M3 12h18M12 8c-2-4-6-4-6-1.5S9 8 12 8zm0 0c2-4 6-4 6-1.5S15 8 12 8z"/></svg>';
  const giftHTML = (u, label) => {
    const list = u.prizes || [];
    let total = 0;
    list.forEach((p) => { total += p.quantity || 0; });
    const rows = list.map((p, i) => '<li><i>' + (i + 1) + '</i><span>' + esc(p.label) + '</span><b>×' + (p.quantity || 0) + '</b></li>').join('');
    return '<div class="ugift"><button type="button" data-ugift aria-label="Quà tặng: ' + esc(u.title) + '">' + GIFT_SVG + (total ? '<span class="cnt">' + total + '</span>' : '') + '</button>'
      + '<div class="ugpop" role="tooltip"><div class="h">' + GIFT_SVG.replace('<svg ', '<svg width="14" height="14" ') + esc(label) + (total ? '<span>' + total + ' phần quà</span>' : '') + '</div>'
      + (rows ? '<ol>' + rows + '</ol>' : '<div class="w">Chưa có danh sách quà.</div>')
      + (u.note ? '<div class="w">' + esc(u.note) + '</div>' : '') + '</div></div>';
  };
  const placeGift = (g) => {
    const b = g.querySelector('button'), p = g.querySelector('.ugpop');
    if (!b || !p) return;
    const r = b.getBoundingClientRect(), w = p.offsetWidth, h = p.offsetHeight;
    const vw = window.innerWidth || document.documentElement.clientWidth, vh = window.innerHeight || document.documentElement.clientHeight;
    const top = (vh - r.bottom >= h + 16 || r.top < h + 16) ? r.bottom + 8 : r.top - h - 8;
    p.style.left = Math.max(8, Math.min(r.left, vw - w - 8)) + 'px';
    p.style.top = Math.max(8, top) + 'px';
  };
  const upcomingHTML = (dr) => {
    const list = dr.upcoming || [];
    if (!list.length) return '';
    return '<div class="upn"><div class="upn-h"><b>Lượt quay tiếp theo<span>' + list.length + '</span></b><span class="note">Nộp phiếu để có số / có xe trước giờ quay</span></div>'
      + list.map((u) => {
        const c = u.mode === 'race' ? ['#0f9f75', '#e7f8f1', 'Đua về đích'] : ['#7b3fe4', '#f1ebfd', 'Số may mắn'];
        const me = (ME[u.me] || ME.closed)(u);
        const cta = u.me === 'not_submitted' ? 'Nộp phiếu' : (u.me === 'pick' ? 'Chọn số' : '');
        const left = u.days_left > 0 ? 'Còn ' + u.days_left + ' ngày' : 'Hôm nay';
        return '<div class="upn-i" style="--uc:' + c[0] + ';--ub:' + c[1] + '">' + giftHTML(u, c[2]) + '<div class="upn-d"><b>' + esc(String(u.draw_at).slice(8, 10)) + '</b><small>Th' + esc(String(u.draw_at).slice(5, 7)) + '</small></div>'
          + '<div class="upn-b"><b>' + esc(u.title) + '</b><small>' + c[2] + ' · ' + esc(hhmm(u.draw_at)) + '</small></div>'
          + '<div class="upn-r"><span class="' + me[0] + '">' + esc(me[1]) + '</span>' + (cta ? '<a href="' + esc(u.url) + '">' + cta + '</a>' : '') + '<span class="upn-left">' + left + '</span></div></div>';
      }).join('') + '</div>';
  };
  const drawStageHTML = (st) => {
    const dr = st.data.draws || {};
    const today = dr.draws || [];
    const pick = Math.min(st.drawPick || 0, Math.max(today.length - 1, 0));
    let h = '';
    if (today.length > 1) {
      h += '<div class="drsel">' + today.map((x, i) => '<button type="button" data-drpick="' + i + '" aria-pressed="' + (i === pick) + '">' + esc(x.title) + ' · ' + esc(hhmm(x.draw_at)) + '</button>').join('') + '</div>';
    }
    h += today.length ? '<div class="drw" data-drmount></div>'
      : '<div class="drempty"><span class="eyebrow">Quay số may mắn</span><b style="font-size:17px">Hôm nay chưa có lượt quay</b><span class="note">Các lượt sắp tới ở dưới - nộp phiếu sớm để có số / có xe.</span></div>';
    return h + upcomingHTML(dr);
  };
  // Lay ban moi cua MOT luot quay (luc toi gio) - API nhe cua module Khao sat: chua chot thi tra
  // ngay ban toi gian, khong tai lai ca popup (ca cong ty cung hoi trong vai phut dang quay).
  const reloadDraw = (name) => {
    const req = window.ecApi && window.ecApi.get ? window.ecApi.get(API_DRAW, { name })
      : fetch('/api/method/' + API_DRAW + '?name=' + encodeURIComponent(name), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))).then((j) => j && j.message);
    return req.then((env) => {
      const d = env && Object.prototype.hasOwnProperty.call(env, 'data') ? env.data : env;
      return d && d.drawn ? d : null;
    });
  };
  const mountDraw = (st) => {
    const el = st.root.querySelector('[data-drmount]');
    if (!el || !window.ECSvyDraw) return;
    const today = (st.data.draws || {}).draws || [];
    const d = today[Math.min(st.drawPick || 0, today.length - 1)];
    window.ECSvyDraw.mount(el, d, { serverNow: st.data.draws.server_now, reload: reloadDraw });
  };

  // ------------------------------------------------------------ popup --------------------
  const thumbHTML = (st, sl, n) => '<button type="button" class="th" role="tab" aria-selected="' + (n === st.i) + '" data-i="' + n + '">'
    + '<span class="img">' + cover(sl, false) + '</span>'
    + '<span class="tx"><span class="tt">' + esc(sl.t) + '</span><span class="ts">' + esc(sl.s) + '</span></span>'
    + (sl.ct === 'soon' ? '<span class="ct soon">Mới</span>' : sl.ct === 'live' ? '<span class="ct">● Hôm nay</span>' : (sl.ct ? '<span class="ct">' + sl.ct + '</span>' : ''))
    + '<span class="prog"><i></i></span></button>';

  const stageHTML = (st, sl) => {
    if (sl.draw) return drawStageHTML(st);
    if (sl.poster) {
      const n = sl.poster;
      // Poster co duong dan -> bam anh di toi dung cho do (PO 01/10: "bam vao hinh cung nen vao cho
      // huong dan"); khong co duong dan thi bam anh mo anh goc nhu cu.
      const go = n.url || n.image;
      const ext = !n.url || /^https?:/i.test(n.url);
      return '<div class="poster"><img class="bg" src="' + esc(n.image) + '" alt="" aria-hidden="true"><a class="pimg' + (n.url ? ' go' : '') + '" href="' + esc(go) + '"'
        + (ext ? ' target="_blank" rel="noopener"' : '') + ' title="' + esc(n.url ? (n.link_label || 'Mở') : 'Mở ảnh gốc') + '"><img src="' + esc(n.image) + '" alt="' + esc(n.title) + '"></a></div>'
        + '<div class="pbar"><span class="tg ' + esc(n.tag) + '">' + esc(n.tag_label) + '</span><b>' + esc(n.title) + '</b>'
        + (n.url ? linkHTML(n) : '') + '</div>';
    }
    // Anh cua thong bao co tich "Bam anh mo link" (Tin noi bo, 01/10) -> bam anh di toi bai.
    const pic = sl.image && sl.image_url
      ? '<a class="hlink" href="' + esc(sl.image_url) + '"' + (/^https?:/i.test(sl.image_url) ? ' target="_blank" rel="noopener"' : '')
        + ' aria-label="' + esc('Mở: ' + (sl.h || '')) + '">' + cover(sl, true) + '</a>'
      : cover(sl, true);
    return '<div class="hero' + (sl.image ? ' photo' : '') + '">' + pic + (sl.cnt ? '<span class="cnt">' + esc(sl.cnt) + '</span>' : '')
      + '<div class="cap"><small>' + esc(sl.hs) + '</small><h3>' + esc(sl.h) + '</h3></div></div>'
      + '<div class="content">' + sl.body(st) + '</div>';
  };

  const render = (st, focus) => {
    const sl = st.slides[st.i];
    const prevMount = st.root.querySelector('[data-drmount]');
    if (prevMount && window.ECSvyDraw) window.ECSvyDraw.unmount(prevMount);
    // Dang o o quay so: khong tu chuyen o (dang dem nguoc / dang quay thi chuyen o la mat hieu ung).
    if (sl.draw) st.manual = true;
    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    st.root.innerHTML = '<div class="dlg' + (st.paused || st.manual || reduce ? ' paused' : '') + '" role="dialog" aria-modal="true" aria-labelledby="' + ROOT + '-title" tabindex="-1">'
      + '<div class="dh"><div class="t"><h2 id="' + ROOT + '-title">Hôm nay ở eCentric</h2><p>' + esc(st.data.date_label) + '</p></div><button type="button" class="x" data-close aria-label="Đóng">×</button></div>'
      + '<div class="dbody"><div class="thumbs" role="tablist" aria-label="Chủ đề">' + st.slides.map((s, n) => thumbHTML(st, s, n)).join('') + '</div>'
      + '<div class="stage" role="tabpanel">' + stageHTML(st, sl) + '</div></div>'
      + '<div class="df"><label><input type="checkbox" data-hide ' + (st.hide ? 'checked' : '') + '> Không hiện lại hôm nay</label>'
      + '<button type="button" class="nav" data-step="-1" aria-label="Mục trước">‹</button><span class="pg">' + (st.i + 1) + ' / ' + st.slides.length + '</span><button type="button" class="nav" data-step="1" aria-label="Mục sau">›</button>'
      + '<button type="button" class="ok" data-close>Đóng</button></div></div>';
    const bar = st.root.querySelector('.th[aria-selected="true"] .prog i');
    if (bar && !reduce && st.slides.length > 1) {
      bar.addEventListener('animationend', () => {
        if (!st.manual && !st.paused) { st.i = (st.i + 1) % st.slides.length; render(st, false); }
      });
    }
    const dlg = st.root.querySelector('.dlg');
    dlg.addEventListener('mouseenter', () => { st.paused = true; dlg.classList.add('paused'); });
    dlg.addEventListener('mouseleave', () => { st.paused = false; if (!st.manual && !reduce) dlg.classList.remove('paused'); });
    // Nguoi dung ban phim / trinh doc man hinh: da vao trong popup thi DUNG tu chuyen o -
    // chuyen o = ve lai popup = mat focus dang dung.
    dlg.addEventListener('focusin', (e) => { if (e.target !== dlg) { st.manual = true; dlg.classList.add('paused'); } });
    if (sl.draw) mountDraw(st);
    if (focus) dlg.focus();
  };

  const go = (st, i) => { st.i = (i + st.slides.length) % st.slides.length; st.manual = true; render(st, false); };

  const post = (method, data) => {
    if (window.ecApi && window.ecApi.post) return window.ecApi.post(method, data);
    const token = (window.frappe && window.frappe.csrf_token) || window.csrf_token || '';
    return fetch('/api/method/' + method, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-Frappe-CSRF-Token': token },
      body: JSON.stringify(data),
    }).then((r) => (r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))).then((j) => j && j.message);
  };

  const react = (st, btn) => {
    if (btn.getAttribute('aria-busy') === 'true') return;
    const [key, kind] = btn.dataset.rx.split('|');
    st.manual = true;
    btn.setAttribute('aria-busy', 'true');
    post(API_REACT, { target: key, kind }).then((res) => {
      if (res && res.target && res.reactions) {
        st.data.reactions = st.data.reactions || {};
        st.data.reactions[res.target] = res.reactions;
      }
      render(st, false);
      // Chon xong thi dong bang chon (nhu Teams) - ke ca khi chuot van dang dung tren nut.
      const add = st.root.querySelector('[data-rxopen="' + key + '"]');
      if (add) { const w = add.parentElement; w.classList.add('rest'); w.addEventListener('mouseleave', () => w.classList.remove('rest'), { once: true }); }
      const again = st.root.querySelector('.rx [data-rx="' + key + '|' + kind + '"]');
      if (again) { again.classList.add('pop'); again.focus(); }
    }).catch((e) => { warn(e); btn.removeAttribute('aria-busy'); });
  };

  let current = null;
  const show = (data, want) => {
    const slides = buildSlides(data);
    if (!slides.length) return null;
    const di = slides.findIndex((x) => x.draw);
    if (current && document.getElementById(ROOT)) {
      // Popup dang mo (vi du toi T-5): cap nhat du lieu + nhay toi o quay so, khong mo popup thu hai.
      current.data = data; current.slides = slides;
      if (want === 'draw' && di >= 0) { current.i = di; current.drawPick = 0; }
      current.i = Math.min(current.i, slides.length - 1);
      render(current, false);
      return current;
    }
    if (document.getElementById(ROOT)) return null;
    injectCss();
    const root = document.createElement('div');
    root.id = ROOT;
    const st = { data, slides, root, i: want === 'draw' && di >= 0 ? di : 0, paused: false, manual: false, hide: !shouldShow(data), open: {}, prevFocus: document.activeElement, drawPick: 0 };
    current = st;
    const close = () => {
      const m = root.querySelector('[data-drmount]');
      if (m && window.ECSvyDraw) window.ECSvyDraw.unmount(m);
      current = null;
      root.remove();
      document.removeEventListener('keydown', onKey, true);
      if (st.prevFocus && st.prevFocus.focus) { try { st.prevFocus.focus(); } catch (e) { /* bỏ qua */ } }
    };
    const onKey = (e) => {
      // Esc chi dong popup khi focus dang o popup / trang - khong dong khi dang go trong eC Mate
      // (nam TREN nen mo, z 1045).
      const t = e.target;
      const here = root.contains(t) || t === document.body || t === document.documentElement || t === document;
      if (e.key === 'Escape') { if (here) close(); return; }
      if (!here) return;
      if (!e.target.closest || !e.target.closest('.thumbs')) return;
      const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
      if (step) { e.preventDefault(); go(st, st.i + step); const t = root.querySelector('[data-i="' + st.i + '"]'); if (t) t.focus(); }
    };
    root.addEventListener('click', (e) => {
      if (e.target === root || (e.target.closest && e.target.closest('[data-close]'))) { close(); return; }
      const o = e.target.closest('[data-rxopen]');
      if (o) { st.manual = true; st.pick = st.pick === o.dataset.rxopen ? null : o.dataset.rxopen; o.parentElement.classList.toggle('open', !!st.pick); o.setAttribute('aria-expanded', String(!!st.pick)); return; }
      const r = e.target.closest('[data-rx]'); if (r) { st.pick = null; react(st, r); return; }
      if (st.pick && !e.target.closest('.rxadd')) { st.pick = null; const op = root.querySelector('.rxadd.open'); if (op) op.classList.remove('open'); }
      const t = e.target.closest('[data-i]'); if (t) { go(st, Number(t.dataset.i)); const f = root.querySelector('[data-i="' + st.i + '"]'); if (f) f.focus(); return; }
      const s = e.target.closest('[data-step]'); if (s) { go(st, st.i + Number(s.dataset.step)); return; }
      const m = e.target.closest('[data-more]'); if (m) { st.open[m.dataset.more] = !st.open[m.dataset.more]; st.manual = true; render(st, false); return; }
      // Hop qua: dien thoai khong co hover -> cham de bat / tat; cham cho khac thi dong.
      const ug = e.target.closest('[data-ugift]');
      root.querySelectorAll('.ugift.on').forEach((x) => { if (!ug || x !== ug.parentElement) x.classList.remove('on'); });
      if (ug) { ug.parentElement.classList.toggle('on'); placeGift(ug.parentElement); return; }
      const dp = e.target.closest('[data-drpick]'); if (dp) { st.drawPick = Number(dp.dataset.drpick); render(st, false); }
    });
    const nearGift = (e) => e.target.closest && e.target.closest('.ugift');
    root.addEventListener('mouseover', (e) => { const g = nearGift(e); if (g) placeGift(g); });
    root.addEventListener('focusin', (e) => { const g = nearGift(e); if (g) placeGift(g); });
    root.addEventListener('scroll', () => { root.querySelectorAll('.ugift.on,.ugift:hover,.ugift:focus-within').forEach(placeGift); }, true);
    root.addEventListener('change', (e) => {
      if (!e.target.hasAttribute('data-hide')) return;
      st.hide = e.target.checked;
      writeHide(st.hide ? { d: data.date, k: data.keys || [] } : null);
    });
    document.addEventListener('keydown', onKey, true);
    document.body.appendChild(root);
    render(st, true);
    return st;
  };

  // Luot quay HOM NAY chua toi T-5: hen gio tu mo popup dung luc (PO 01/10 "luc do se tu popup").
  // Canh theo gio server; realtime `ec_survey_draw` (neu socket song) mo som hon/chinh xac hon.
  const armed = {};
  const arm = (data) => {
    const dr = data && data.draws;
    if (!dr || !dr.timers || !window.ECSvyDraw) return;
    const skew = window.ECSvyDraw._parse(dr.server_now) - Date.now();
    dr.timers.forEach((t) => {
      if (armed[t.name]) return;
      const wait = window.ECSvyDraw._parse(t.open_at) - (Date.now() + skew);
      if (wait <= 0 || wait > 12 * 3600 * 1000) return;
      armed[t.name] = setTimeout(() => { load(true, 'draw'); }, wait + 1500);
    });
  };
  const listenRealtime = () => {
    const rt = window.frappe && window.frappe.realtime;
    const s = rt && rt.socket;
    if (!s || s.__ecDrawBound) return;
    s.__ecDrawBound = true;
    s.on('ec_survey_draw', () => { load(true, 'draw'); });
  };

  const load = (force, want) => {
    const req = window.ecApi && window.ecApi.get
      ? window.ecApi.get(API_GET)
      : fetch('/api/method/' + API_GET, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))).then((j) => j && j.message);
    return req.then((data) => {
      arm(data);
      listenRealtime();
      if (!data || !data.has_content || (!force && !shouldShow(data))) return null;
      return show(data, want);
    }, (e) => { warn(e); return null; });
  };

  const run = () => {
    // Server (Jinja) chưa nói "có nội dung" -> không gọi API thừa.
    const flag = document.querySelector('[data-ec-today]');
    if (!flag || flag.getAttribute('data-ec-today') !== '1') return Promise.resolve(null);
    return load();
  };

  // Nut "🎉 Hom nay" tren dai navy (server ve san khi co noi dung): mo lai popup bat cu luc nao,
  // ke ca da tich "Khong hien lai hom nay" (PO 29/09 16:32).
  document.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('[data-ec-today-open]');
    if (!b || document.getElementById(ROOT)) return;
    e.preventDefault();
    load(true);
  });

  window.EcHomePopup = { run, show, load, buildSlides, shouldShow, HIDE_KEY, upcomingHTML };
  // Chỉ hiện sau khi trang đã vẽ xong và ổn định (không tranh lần vẽ đầu).
  const start = () => setTimeout(run, 400);
  if (document.readyState === 'complete') start();
  else window.addEventListener('load', start, { once: true });
})();
