// Trang chu, dai hero: thay o "KPI QUY" bang %SLA thang nay CUA CHINH nguoi dang
// dang nhap. Du lieu: ecentric_workspace.sla.controllers.api.my_board.
// ES5, noi chuoi (khong template literal), khong token Jinja.
//
// VI SAO THAY CHU KHONG THEM MOT O MOI. O "KPI QUY" dang hien "0% - Chua co du
// lieu" va da hien nhu vay tu lau: no khong do gi ca. Mot con so 0% dung mai o
// cho de nhin nhat trang chu day nguoi ta toi mot ket luan sai ("he thong hong")
// va lam cac o ben canh mat gia tri theo. Thay bang mot con so co that thi ca
// dai hero noi that.
//
// KHONG TU TINH GI. Ti le va mau so deu lay nguyen tu `my_board` - dung endpoint
// ma trang /sla dung. Neu o day tu cong tru thi se co ngay trang chu va trang
// /sla noi hai con so khac nhau ve cung mot nguoi, va luc do ca hai deu vo
// nghia.
//
// HONG THI TRA LAI NGUYEN TRANG. Snapshot lai HTML goc cua o truoc khi cham
// vao; goi API loi -> dan lai. Mot o nua voi ("SLA THANG 9" ma khong co so) con
// te hon o cu.
(function () {
  'use strict';
  if (window._ecSlaCardInstalled) return;
  window._ecSlaCardInstalled = true;

  var ROUTE = '/sla';
  var METHOD = '/api/method/ecentric_workspace.sla.controllers.api.my_board';
  var MARK = 'data-ec-sla-card';

  // Ba muc mau, chu so huu chot 17/09: tu 90% tro len xanh, 70-90% cam, duoi
  // 70% do. Nguong doc tu tren xuong, muc dau tien khop thi dung.
  //
  // BA MA MAU NAY LA BA MA CUA TRANG /sla (--green #15803D, --amber #B45309,
  // --red #B91C1C). Co y: mot nguoi thay o cam tren trang chu roi bam vao se
  // thay dung mau do tren con so lon cua trang /sla. Hai mau khac nhau cho cung
  // mot tinh trang se lam nguoi ta tuong day la hai thu do khac nhau.
  //
  // Chu TRANG tren ca ba nen: do tuong phan lan luot 5.0 : 5.0 : 6.5 - deu qua
  // nguong AA cho chu thuong. Day la ly do dung sac dam cua tung mau chu khong
  // dung sac tuoi: nen cam tuoi (#F5A524) chi cho 2.1 va chu trang tren do gan
  // nhu khong doc duoc.
  var TONES = [
    [90, 'linear-gradient(135deg,#15803D 0%,#14532D 100%)'],
    [70, 'linear-gradient(135deg,#B45309 0%,#7C2D12 100%)'],
    [0,  'linear-gradient(135deg,#B91C1C 0%,#7F1D1D 100%)']
  ];

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function findCard() {
    var cards = document.querySelectorAll('.stat-card');
    for (var i = 0; i < cards.length; i++) {
      if (cards[i].getAttribute(MARK)) return cards[i];
      var lab = cards[i].querySelector('.stat-label');
      var t = ((lab && lab.textContent) || '').toUpperCase();
      // Nhan dang theo NHAN chu khong theo vi tri hay lop mau: vi tri doi khi
      // ai do them mot o, con lop `s-green` co the dung o cho khac. Khong tim
      // thay thi khong lam gi - tot hon la ghi de nham mot o khac.
      if (t.indexOf('KPI') >= 0) return cards[i];
    }
    return null;
  }

  function monthLabel(period) {
    var m = /^(\d{4})-(\d{2})$/.exec(String(period || ''));
    if (!m) return 'SLA THÁNG NÀY';
    return 'SLA THÁNG ' + String(parseInt(m[2], 10));
  }

  function setTone(card, rate) {
    // "Chua du mau" KHONG to mau: chua do duoc khong phai la mot tinh trang tot
    // hay xau, va to no thanh do se bien mot nguoi moi vao lam thanh nguoi dang
    // bi canh bao.
    if (rate == null) return;
    var g = null;
    for (var i = 0; i < TONES.length; i++) {
      if (rate >= TONES[i][0]) { g = TONES[i][1]; break; }
    }
    if (!g) return;
    // Cac o trong dai hero co mot vach mau 3px o mep trai (`.stat-card::before`,
    // mau lay tu lop `s-green`/`s-yellow`/...). Khi o nay da co nen gradient thi
    // vach do vua thua vua SAI MAU - mot so cham 70% se co nen do kem mot vach
    // xanh la. Khong sua duoc bang style inline nen cam mot quy tac nho, dung
    // mot lan.
    if (!document.getElementById('ec-sla-card-css')) {
      var st = document.createElement('style');
      st.id = 'ec-sla-card-css';
      st.textContent = '.stat-card[' + MARK + ']::before{display:none !important;}';
      document.head.appendChild(st);
    }
    // Dat dau ngay o day chu khong doi `makeClickable` chay truoc: quy tac tren
    // an theo thuoc tinh nay, va mot lan ai do doi thu tu hai loi goi trong
    // `render` se lam vach mau hien lai ma khong co gi bao.
    if (!card.getAttribute(MARK)) card.setAttribute(MARK, 'toned');
    card.style.background = g;
    card.style.borderColor = 'rgba(255,255,255,.22)';
    var lab = card.querySelector('.stat-label');
    var val = card.querySelector('.stat-value');
    var unit = card.querySelector('.unit');
    if (lab) lab.style.color = 'rgba(255,255,255,.85)';
    if (val) val.style.color = '#fff';
    if (unit) unit.style.color = 'rgba(255,255,255,.75)';
  }

  function paint(card, labelText, valueText, unitText, title) {
    var lab = card.querySelector('.stat-label');
    var val = card.querySelector('.stat-value');
    if (!lab || !val) return false;
    lab.textContent = labelText;
    // Dung dung cau truc cua cac o ben canh: so lon la text node, don vi nam
    // trong <span class="unit">. Viet khac di thi o nay se lech font so voi
    // ba o con lai ngay canh no.
    val.innerHTML = esc(valueText) + (unitText
      ? '<span class="unit">' + esc(unitText) + '</span>' : '');
    if (title) card.setAttribute('title', title);
    return true;
  }

  function makeClickable(card) {
    if (card.getAttribute(MARK) === 'linked') return;
    card.setAttribute(MARK, 'linked');
    card.style.cursor = 'pointer';
    card.setAttribute('role', 'link');
    card.setAttribute('tabindex', '0');
    card.addEventListener('click', function () { window.location.href = ROUTE; });
    card.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        window.location.href = ROUTE;
      }
    });
  }

  function fetchBoard() {
    return fetch(METHOD, {
      method: 'POST', credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': (window.frappe && window.frappe.csrf_token) || ''
      },
      body: JSON.stringify({})
    }).then(function (r) { return r.json(); })
      .then(function (d) {
        var env = d && d.message;
        if (!env || env.success === false || !env.data) {
          throw new Error((env && env.message) || 'khong lay duoc bang diem');
        }
        return env.data;
      });
  }

  function render(card, board) {
    var o = board.overall || {};
    var label = monthLabel(board.period);
    if (o.rate == null) {
      paint(card, label, '—', 'chưa đủ mẫu',
            'Mới có ' + (o.scored || 0) + ' đầu việc được chấm trong tháng — '
            + 'chưa đủ để ra tỉ lệ. Bấm để xem chi tiết.');
    } else {
      paint(card, label, o.rate + '%', o.ontime + '/' + o.scored,
            o.ontime + ' đúng hạn / ' + o.scored + ' đầu việc được chấm. '
            + 'Bấm để xem chi tiết.');
      setTone(card, o.rate);
    }
    makeClickable(card);
  }

  function load() {
    var card = findCard();
    if (!card) return;                       // khong co o nay tren trang -> thoi
    var original = card.innerHTML;
    var originalTitle = card.getAttribute('title');
    // Chup ca thuoc tinh `style` cua chinh o: `setTone` ghi nen va mau chu vao
    // day, nen dan lai innerHTML thoi la chua du - o se giu nen gradient voi
    // noi dung cu "KPI QUY 0%".
    var originalStyle = card.getAttribute('style');
    // Doi nhan NGAY: de nguyen "KPI QUY 0%" trong luc doi mang la de nguoi ta
    // doc dung cai con so sai ma ca lo nay sinh ra de xoa.
    paint(card, monthLabel(null), '…', '');
    fetchBoard().then(function (board) {
      render(card, board);
    }).catch(function (e) {
      card.innerHTML = original;
      if (originalTitle == null) card.removeAttribute('title');
      else card.setAttribute('title', originalTitle);
      if (originalStyle == null) card.removeAttribute('style');
      else card.setAttribute('style', originalStyle);
      if (window.console) console.warn('[ec-sla-card]', e);
    });
  }

  function init() {
    // Dai hero duoc mot script khac cua trang chu dung lai va DI CHUYEN cac o
    // vao `.ec2-chips` sau khi tai. Nen doi o xuat hien thay vi chay mot lan
    // roi bo cuoc - va co nguong bo cuoc that (8 giay) de khong quay vo han.
    var tries = 0;
    var iv = setInterval(function () {
      if (findCard()) { clearInterval(iv); load(); return; }
      if (++tries > 40) clearInterval(iv);
    }, 200);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
