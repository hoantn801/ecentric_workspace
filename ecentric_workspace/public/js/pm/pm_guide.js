/* pm_guide.js — Hướng dẫn /pm (Quản lý công việc). Asset tĩnh, tải khi mở #guide (pm_app.html showGuide).
 * Một global duy nhất: window.PMGuide.render(container, {head}). Không gọi server.
 * Màu vai trò dùng xuyên suốt: người nhận = xanh lá, người giao = navy, hệ thống = xám, trưởng nhóm / trưởng phòng = cam.
 * Ảnh: /assets/ecentric_workspace/images/pm_guide/<key>.jpg (giao diện thật, dữ liệu minh hoạ). Sửa nội dung: chỉ sửa file này. */
(function (root) {
"use strict";
if (root.PMGuide) return;
var IMG = "/assets/ecentric_workspace/images/pm_guide/";
var ROLE = { n: "Người nhận", g: "Người giao", s: "Hệ thống", l: "Trưởng nhóm / phòng" };

function ic(id) { return '<svg class="pmg-i" aria-hidden="true"><use href="#' + id + '"/></svg>'; }
function role(r, label) { return '<span class="pmg-r pmg-r-' + r + '">' + (label || ROLE[r]) + "</span>"; }
function st(cls, label) { return '<span class="pmg-st pmg-' + cls + '">' + label + "</span>"; }
function b(t) { return "<b>" + t + "</b>"; }
/* Các bước: mỗi phần tử là chuỗi, hoặc [vai trò, nội dung] để tô màu người làm bước đó. */
function steps(arr) {
  return '<ol class="pmg-steps">' + arr.map(function (x) {
    return Array.isArray(x) ? '<li class="pmg-li-' + x[0] + '">' + role(x[0]) + " " + x[1] + "</li>" : "<li>" + x + "</li>";
  }).join("") + "</ol>";
}
function tip(html, warn) { return '<div class="' + (warn ? "pmg-warn" : "pmg-tip") + '">' + ic(warn ? "p-alert" : "p-info") + "<span>" + html + "</span></div>"; }
function shot(key, cap) {
  return '<figure class="pmg-shot" data-shot="' + key + '"><img src="' + IMG + key + '.jpg" alt="' + cap.replace(/"/g, "") + '" loading="lazy">' +
    "<figcaption>" + cap + "</figcaption></figure>";
}
function table(head, rows) {
  return '<div class="pmg-tw"><table class="pmg-tb"><thead><tr>' + head.map(function (h) { return "<th>" + h + "</th>"; }).join("") + "</tr></thead><tbody>" +
    rows.map(function (r) { return "<tr>" + r.map(function (c) { return "<td>" + c + "</td>"; }).join("") + "</tr>"; }).join("") + "</tbody></table></div>";
}
/* Sơ đồ làn (thay cho Mermaid, vẽ bằng HTML để không tải thư viện ngoài):
 * roles = thứ tự làn, list = [[vai trò, nội dung], ...] theo thứ tự thời gian. Màn hẹp: tự thành danh sách dọc. */
function lanes(title, roles, list) {
  var n = list.length, h = '<div class="pmg-flowbox"><div class="pmg-flow-t">' + ic("p-gantt") + title + "</div>";
  h += '<div class="pmg-lanes" style="grid-template-columns:132px repeat(' + n + ',minmax(118px,1fr))">';
  roles.forEach(function (r) {
    h += '<div class="pmg-lane-h pmg-r-' + r + '">' + ROLE[r] + "</div>";
    list.forEach(function (s, i) {
      h += '<div class="pmg-cell pmg-cell-' + r + '">' + (s[0] === r ? '<div class="pmg-node pmg-node-' + r + '"><span>' + (i + 1) + "</span>" + s[1] + "</div>" : "") + "</div>";
    });
  });
  h += '</div><ol class="pmg-lanes-m">' + list.map(function (s) { return "<li>" + role(s[0]) + " " + s[1] + "</li>"; }).join("") + "</ol></div>";
  return h;
}
function sec(id, n, title, who, inner) {
  return '<section class="pmg-sec" id="' + id + '"><h2><span class="pmg-n">' + n + "</span>" + title + "</h2>" +
    '<p class="pmg-who">' + who + "</p>" + inner + "</section>";
}

var TOC = [
  ["pmg-s1", "Công việc gồm những gì"], ["pmg-s2", "Khi được giao việc"], ["pmg-s3", "Xin dời hạn"],
  ["pmg-s4", "Làm việc và bấm Xong"], ["pmg-s5", "Ghi giờ"], ["pmg-s6", "Giao việc cho người khác"],
  ["pmg-s7", "Theo dõi việc đã giao"], ["pmg-s8", "Trưởng nhóm và trưởng phòng"], ["pmg-s9", "Ai được làm gì"], ["pmg-s10", "Câu hỏi thường gặp"]
];

function content() {
  var h = "";
  /* Bạn là ai */
  h += '<div class="pmg-pick">' +
    '<a class="pmg-card pmg-card-n" href="#" data-pmg-jump="pmg-s2">' + role("n", "Tôi nhận việc") + "<b>Mục 2 → 5</b><span>Nhận việc, xin dời hạn, làm và bấm Xong, ghi giờ.</span></a>" +
    '<a class="pmg-card pmg-card-g" href="#" data-pmg-jump="pmg-s6">' + role("g", "Tôi giao việc") + "<b>Mục 6 → 7</b><span>Giao cho một hay nhiều người, theo dõi ai xong, duyệt và đóng việc.</span></a>" +
    '<a class="pmg-card pmg-card-l" href="#" data-pmg-jump="pmg-s8">' + role("l", "Tôi là trưởng nhóm / phòng") + "<b>Mục 8 → 9</b><span>Điều phối cả nhóm, xem lịch nhân viên, quyền sửa việc.</span></a>" +
    "</div>" +
    '<div class="pmg-legend-roles">Màu trong hướng dẫn: ' + role("n") + role("g") + role("s") + role("l") + " cho biết <b>ai</b> làm bước đó.</div>";

  /* 1 */
  h += sec("pmg-s1", 1, "Công việc gồm những gì", "Ai cũng đọc",
    '<div class="pmg-two">' + shot("menu", "Menu trái của Công việc") +
    '<div><ol class="pmg-menu-l">' +
      "<li>" + b("Việc của tôi") + ": mọi việc bạn đang phải làm, xếp theo hạn. Mở mỗi sáng là đủ.</li>" +
      "<li>" + b("Được giao cho tôi") + ": chỉ những gì <b>cần bạn trả lời</b>: nhận việc, việc mới giao, kết quả xin dời hạn. Có số đỏ là có việc chờ bạn.</li>" +
      "<li>" + b("Tôi đã giao") + ": việc bạn giao cho người khác, ai xong ai chưa.</li>" +
      "<li>" + b("Lịch làm việc") + ": xếp việc vào giờ trong tuần, xem lịch họp Outlook.</li>" +
      "<li>" + b("+ Giao việc") + ": tạo việc cho mình hoặc giao cho người khác.</li>" +
      "<li>Nhóm " + b("Quản lý") + " (Điều phối, Dự án, Tất cả việc, Timesheet) dành cho trưởng nhóm và người theo dõi dự án.</li>" +
    "</ol></div></div>" +
    "<h3>Một việc có 4 trạng thái</h3>" +
    '<div class="pmg-states">' +
      "<div>" + st("s0", "Chưa làm") + "<br>Mới tạo, chưa bắt đầu.</div>" +
      "<div>" + st("s1", "Đang làm") + "<br>Đã bắt đầu làm.</div>" +
      "<div>" + st("s2", "Chờ duyệt") + "<br>Đã làm xong, chờ người giao kiểm tra.</div>" +
      "<div>" + st("s3", "Xong") + "<br>Hoàn tất.</div>" +
      "<div>" + st("s4", "Đã huỷ") + "<br>Chỉ quản lý huỷ được. Mặc định ẩn.</div></div>");

  /* 2 */
  h += sec("pmg-s2", 2, "Khi được giao việc", role("n") + " Dành cho người nhận việc",
    "<p>Có người giao việc cho bạn: bạn nhận " + b("tin Teams") + " kèm đường link. Bấm link, hoặc vào " + b("Được giao cho tôi") + ", là thấy ai giao, hạn khi nào.</p>" +
    shot("received", "Được giao cho tôi: việc cần trả lời, việc mới giao chưa mở, các lần xin dời hạn của bạn") +
    "<h3>Có hai kiểu được giao</h3>" +
    table(["Kiểu", "Bạn thấy gì", "Bạn làm gì"], [
      [b("Cần bạn đồng ý") + "<br><small>(mặc định khi giao cho người khác)</small>", "Việc nằm ở <b>Được giao cho tôi → Cần bạn trả lời</b>.", "Bấm <b>Nhận việc</b>, <b>Đề xuất hạn khác</b>, hoặc <b>Từ chối</b> (ghi lý do)."],
      [b("Giao thẳng"), "Việc vào thẳng <b>Việc của tôi</b>. Không có nút từ chối.", "Làm luôn. Hạn không hợp lý thì <b>Xin dời hạn</b> (mục 3)."]]) +
    lanes("Luồng giao thẳng", ["g", "s", "n"], [
      ["g", "Giao việc (tắt <b>Cần người nhận đồng ý</b>)"], ["s", "Gửi tin Teams, việc vào <b>Việc của tôi</b>"],
      ["n", "Làm: <b>Đang làm</b> → <b>Xong</b>"], ["s", "Báo người giao việc đã xong"]]) +
    lanes("Luồng “Cần bạn đồng ý”", ["g", "s", "n"], [
      ["g", "Giao việc, bật <b>Cần người nhận đồng ý</b>"], ["s", "Gửi tin Teams cho người nhận"],
      ["n", "Nhận việc / Đề xuất hạn khác / Từ chối"], ["s", "Báo lại người giao"],
      ["g", "Nếu là đề xuất hạn: <b>Đồng ý</b> hoặc giữ hạn"]]) +
    "<h3>Mở một việc</h3>" +
    shot("task_sheet_receiver", "Chi tiết việc: trái là việc, phải là Bình luận") +
    steps([
      ["n", "Dưới tên việc luôn ghi <b>ai giao cho bạn</b> và ngày giao."],
      ["n", "Thanh trạng thái: bấm <b>Đang làm</b> khi bắt đầu, <b>Xong</b> khi xong."],
      ["n", "Các tab: <b>Việc con</b>, <b>Các bước</b>, <b>Thời gian</b>, <b>Lịch sử</b>."],
      ["n", "Cột phải là <b>Bình luận</b>: hỏi lại, báo tiến độ, gửi file. Ghi chú quan trọng được <b>ghim</b> lên đầu, nền vàng."]]));

  /* 3 */
  h += sec("pmg-s3", 3, "Xin dời hạn", role("n") + " gửi đề xuất · " + role("g") + " trả lời",
    steps([
      ["n", "Mở việc, bấm <b>Xin dời hạn</b> ngay cạnh hạn."],
      ["n", "Chọn ngày mới (các nút gợi ý, hoặc <b>Chọn ngày…</b>), ghi ngắn lý do, bấm <b>Gửi đề xuất</b>."],
      ["g", "Nhận tin Teams. Đề xuất hiện ở đầu trang <b>Tôi đã giao</b>: bấm <b>Đồng ý</b> hoặc <b>Giữ hạn cũ</b>."],
      ["n", "Xem kết quả ở <b>Được giao cho tôi → Xin dời hạn của bạn</b>. Đồng ý thì hạn tự cập nhật."]]) +
    shot("deadline_form", "Form Xin dời hạn ngay trong việc") +
    lanes("Luồng xin dời hạn", ["n", "s", "g"], [
      ["n", "Xin dời hạn + lý do"], ["s", "Báo người giao qua Teams"], ["g", "Đồng ý / Giữ hạn cũ"], ["s", "Báo kết quả"], ["n", "Hạn mới tự cập nhật"]]) +
    tip("Trong lúc chờ, <b>hạn cũ vẫn giữ</b>. Bạn làm xong trước khi người giao trả lời thì cứ bấm Xong: đề xuất <b>tự rút</b>."));

  /* 4 */
  h += sec("pmg-s4", 4, "Làm việc và bấm Xong", role("n") + " Dành cho người nhận việc",
    steps([
      ["n", "Bắt đầu thì bấm " + st("s1", "Đang làm") + "."],
      ["n", "Việc có <b>Các bước</b> thì tích từng bước khi làm xong."],
      ["n", "Việc lớn thì chia <b>Việc con</b>: tab Việc con, gõ tên rồi Enter. Bấm vòng tròn người nhận để giao luôn, bấm nút tròn bên trái để đánh Xong."],
      ["n", "Làm xong bấm <b>Xong</b>. Bấm nhầm thì chọn <b>Hoàn tác</b> trên thông báo."]]) +
    shot("done_toast", "Sau khi bấm Xong: có nút Ghi giờ (không bắt buộc) và Hoàn tác") +
    "<h3>Khi nút là “Gửi kiểm tra” thay vì “Xong”</h3>" +
    "<p>Người giao đã bật <b>Cần tôi kiểm tra trước khi xong</b>.</p>" +
    lanes("Luồng cần kiểm tra", ["n", "s", "g"], [
      ["n", "Bấm <b>Gửi kiểm tra</b>"], ["s", "Việc sang " + st("s2", "Chờ duyệt") + ", báo người giao"], ["g", "<b>Đóng việc</b> hoặc <b>Trả lại</b>"], ["n", "Bị trả lại thì sửa rồi gửi lại"]]) +
    tip("<b>Không bấm Xong được?</b> Còn <b>bước bắt buộc</b> chưa tích, hoặc còn <b>việc con</b> chưa xong. Hệ thống ghi rõ lý do.", true));

  /* 5 */
  h += sec("pmg-s5", 5, "Ghi giờ", "Ai cần ghi giờ làm việc",
    "<p>Có 4 chỗ ghi giờ. Ghi ở đâu cũng cộng về một chỗ, xem tổng ở <b>Timesheet</b>.</p>" +
    table(["Ở đâu", "Dùng khi"], [
      [b("Tab Thời gian trong việc"), "Bấm giờ, hoặc ghi tay số giờ kèm việc đã làm. <b>Dùng chỗ này là chính.</b>"],
      [b("Nút Ghi giờ sau khi bấm Xong"), "Ghi nhanh ngay lúc vừa xong."],
      [b("Đồng hồ trên thanh trên cùng"), "Đang bấm giờ thì đồng hồ hiện ở đó, bấm Dừng là tự ghi."],
      [b("Lịch làm việc"), "Xác nhận các khối giờ đã xếp trong tuần."]]) +
    shot("time_tab", "Tab Thời gian: bấm giờ hoặc + Ghi giờ"));

  /* 6 */
  h += sec("pmg-s6", 6, "Giao việc cho người khác", role("g") + " Dành cho người giao · cũng dùng để tạo việc cho chính mình",
    steps([
      ["g", "Bấm <b>+ Giao việc</b> trên menu."],
      ["g", "Điền <b>tên việc</b> (bắt buộc), chọn <b>người nhận</b>, <b>hạn</b> và <b>dự án</b> (gõ để tìm)."],
      ["g", "Bật các tuỳ chọn cần thiết (bảng dưới), rồi bấm nút xanh ở góc dưới."],
      ["s", "Người nhận nhận tin Teams. Bạn vẫn ở màn đang làm."]]) +
    shot("new_task_sheet", "Form Giao việc") +
    table(["Tuỳ chọn", "Khi nào bật"], [
      [b("Cần người nhận đồng ý"), "<b>Bật sẵn.</b> Người nhận xác nhận trước khi làm. Tắt đi nếu muốn giao thẳng. Giao cho chính mình thì tự bỏ qua."],
      [b("Mỗi người một việc riêng"), "Giao cùng một việc cho nhiều người, ai cũng phải làm (ví dụ báo cáo tháng). Mỗi người có việc con riêng, bạn thấy ai xong ai chưa."],
      [b("Tự đóng khi mọi người xong"), "Tắt (mặc định): mọi người xong thì việc sang Chờ duyệt để bạn kiểm tra. Bật: tự đóng luôn."],
      [b("Cần tôi kiểm tra trước khi xong"), "Bạn muốn duyệt kết quả. Người nhận bấm Gửi kiểm tra thay vì Xong."],
      [b("Lặp lại"), "Việc định kỳ (ví dụ ngày 7 hằng tháng). Hệ thống tự giao lại cho cùng người."],
      [b("Theo dõi (CC)"), "Người cần nắm việc nhưng không phải làm. <b>Tự thêm</b> trưởng phòng của người nhận khi bạn giao cho người <b>phòng khác</b> (bỏ được). Giao cho chính trưởng phòng thì không CC lên trên."]]) +
    tip("<b>Giao cho cả trưởng phòng lẫn nhân viên của họ?</b> Form sẽ gợi ý <b>chuyển trưởng phòng sang Theo dõi</b>: nhân viên làm, trưởng phòng nắm tiến độ, không ai phải bấm Xong thay ai.") +
    tip("<b>Báo cáo hằng tháng cho cả nhóm:</b> chọn cả nhóm, bật <b>Mỗi người một việc</b> và <b>Lặp lại</b>. Từ tháng sau hệ thống tự giao, bạn không phải tạo tay."));

  /* 7 */
  h += sec("pmg-s7", 7, "Theo dõi việc đã giao", role("g") + " Dành cho người giao",
    shot("given", "Tôi đã giao: tiến độ từng người, đề xuất dời hạn ở đầu trang") +
    steps([
      ["g", "Mỗi dòng là một lần giao. Thanh màu: <span class=\"pmg-c-done\">xanh</span> xong, <span class=\"pmg-c-run\">navy</span> đang làm, <span class=\"pmg-c-late\">đỏ</span> trễ."],
      ["g", "<b>Nhắc</b> từng người, hoặc <b>Nhắc N người</b> chưa xong. Tin nhắc đi qua Teams."],
      ["g", "Đề xuất dời hạn hiện ở đầu trang: <b>Đồng ý</b> hoặc <b>Giữ hạn cũ</b>."],
      ["g", "Việc sang " + st("s2", "Chờ duyệt") + ": kiểm tra rồi <b>Đóng việc</b>, hoặc <b>Trả lại</b> người cần sửa."],
      ["g", "Việc lặp lại xem ở tab <b>Lặp lại</b>: tạm dừng hoặc chạy lại."],
      ["l", "Việc bạn được CC nằm ở tab <b>Tôi theo dõi</b>: xem tiến độ, mở việc, bình luận. Bạn nhận tin khi được CC, khi việc xong và khi trễ hạn."]]) +
    lanes("Luồng “Mỗi người một việc”", ["g", "s", "n"], [
      ["g", "Giao cho cả nhóm, bật <b>Mỗi người một việc</b>"], ["s", "Tạo việc con cho từng người, gửi Teams"],
      ["n", "Mỗi người làm và bấm Xong phần của mình"], ["s", "Người cuối xong: việc chung sang Chờ duyệt"],
      ["g", "<b>Đóng việc</b> hoặc trả lại một người"]]));

  /* 8 */
  h += sec("pmg-s8", 8, "Trưởng nhóm và trưởng phòng", role("l") + " Leader, trưởng phòng, người theo dõi dự án",
    table(["Màn", "Dùng để"], [
      [b("Điều phối"), "Mở đầu ngày: việc đang mở, trễ hạn, chưa có người nhận. Mục <b>Cần xử lý</b> có nút làm ngay: Nhắc, Giao, Đặt hạn."],
      [b("Dự án"), "Tiến độ từng dự án, số việc trễ và chưa giao. Bấm vào dự án để xem việc, Kanban, Gantt."],
      [b("Tất cả việc"), "Mọi việc bạn được xem. Lọc nhanh <b>Trễ hạn / Chưa có người / Hạn tuần này</b>. Đổi kiểu xem: Danh sách, Kanban, Theo hạn, Gantt."],
      [b("Lịch làm việc"), "Trưởng phòng chọn tên nhân viên để xem lịch tuần: thấy <b>tên việc và tên cuộc họp</b> (họp riêng tư hiện “Họp riêng”). Đồng nghiệp chỉ thấy “Bận”."]]) +
    shot("coordinate", "Điều phối: số liệu cả nhóm, việc cần xử lý, theo người, theo dự án") +
    shot("all_work", "Tất cả việc: lọc, nhóm theo dự án, đổi kiểu xem"));

  /* 9 */
  h += sec("pmg-s9", 9, "Ai được làm gì", "Ai cũng nên biết",
    "<p>Xem được một việc <b>không</b> có nghĩa là sửa được. Người chỉ xem mở việc sẽ thấy dòng <b>Chỉ xem</b>, nhưng vẫn bình luận được.</p>" +
    table(["Việc cần làm", role("n"), role("g"), role("l"), "Người khác xem được"], [
      ["Đổi trạng thái, bấm Xong", "✓", "✓", "✓", "—"],
      ["Đổi hạn", "Xin dời hạn", "✓", "✓", "—"],
      ["Thêm người nhận, việc con, các bước", "✓", "✓", "✓", "—"],
      ["Bình luận, ghim ghi chú", "✓", "✓", "✓", "✓"],
      ["Thêm / bỏ người theo dõi (CC)", "✓", "✓", "✓", "Tự theo dõi"],
      ["Huỷ việc", "—", "—", "Quản trị PM", "—"]]) +
    "<p class=\"pmg-note\">Trưởng phòng ở đây là trưởng phòng của <b>người nhận</b> việc. Quản lý dự án và quản trị PM có quyền như người giao.</p>");

  /* 10 */
  h += sec("pmg-s10", 10, "Câu hỏi thường gặp", "Ai cũng đọc",
    table(["Câu hỏi", "Trả lời"], [
      ["“Việc của tôi” khác “Được giao cho tôi” thế nào?", "<b>Việc của tôi</b> là toàn bộ việc bạn đang làm. <b>Được giao cho tôi</b> chỉ chứa những gì cần bạn <b>trả lời</b>."],
      ["Không muốn nhận một việc giao thẳng?", "Giao thẳng không có nút từ chối. Hãy <b>Xin dời hạn</b>, hoặc viết ở <b>Bình luận</b> để trao đổi với người giao."],
      ["Bấm Xong nhầm?", "Chọn <b>Hoàn tác</b> trên thông báo, hoặc mở việc đổi lại trạng thái."],
      ["Việc chung chưa đóng dù mọi người đã xong?", "Việc sang Chờ duyệt để người giao kiểm tra. Không cần kiểm tra thì khi giao bật <b>Tự đóng khi mọi người xong</b>."],
      ["Được CC thì phải làm gì?", "Không phải bấm Xong. Bạn chỉ theo dõi: xem ở <b>Tôi đã giao → Tôi theo dõi</b>, bình luận khi cần. Không muốn theo dõi nữa thì bấm × cạnh tên mình trong việc."],
      ["Muốn giao thêm người cho việc đã Xong?", "Chuyển việc về <b>Đang làm</b> trước, rồi thêm người."],
      ["Có bắt buộc ghi giờ không?", "Tuỳ quy định của nhóm. Hệ thống không bắt buộc."],
      ["Việc nhật ký cá nhân (worklog) đi đâu?", "Mặc định ẩn khỏi các màn Công việc và không tính vào số đếm. Bấm <b>Hiện</b> ở dòng “Đang ẩn …” để xem."]]));
  return h;
}

function render(c, o) {
  o = o || {};
  var head = typeof o.head === "function" ? o.head("Hướng dẫn quản lý công việc", "Chọn vai trò của bạn bên dưới để đọc đúng phần cần. Mỗi mục khoảng 1 phút.") : "";
  c.innerHTML = head + '<div class="pmg"><nav class="pmg-toc" aria-label="Mục lục"><b>Mục lục</b>' +
    TOC.map(function (t, i) { return '<button type="button" data-pmg-jump="' + t[0] + '"><span>' + (i + 1) + "</span>" + t[1] + "</button>"; }).join("") +
    '</nav><div class="pmg-main">' + content() + "</div></div>";
  Array.prototype.forEach.call(c.querySelectorAll("[data-pmg-jump]"), function (x) {
    x.onclick = function (e) {
      if (e && e.preventDefault) e.preventDefault();
      var t = document.getElementById(x.getAttribute("data-pmg-jump"));
      if (t && t.scrollIntoView) t.scrollIntoView({ behavior: "auto", block: "start" }); /* auto: smooth bị nuốt sau hash-nav SPA */
    };
  });
  /* ảnh lỗi (chưa deploy asset) -> ẩn khung ảnh thay vì hiện icon vỡ */
  Array.prototype.forEach.call(c.querySelectorAll(".pmg-shot img"), function (im) {
    im.onerror = function () { var f = im.parentNode; if (f) f.classList.add("pmg-shot-off"); };
  });
}

root.PMGuide = { render: render, _keys: ["menu", "received", "task_sheet_receiver", "deadline_form", "done_toast", "time_tab", "new_task_sheet", "given", "coordinate", "all_work"] };
})(window);
