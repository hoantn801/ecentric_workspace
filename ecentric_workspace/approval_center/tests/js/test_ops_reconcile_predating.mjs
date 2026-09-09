// Copyright (c) 2026, eCentric and contributors
// Nút "Đối soát — chấp nhận chữ ký ký trước lệnh" trên trang vận hành ký số.
//
// BỐI CẢNH (09/09/2026). Người duyệt (HOF/CEO) quen mở mail của SCTS rồi ký thẳng trên cổng
// TRƯỚC khi họ bấm Duyệt trên ERP. Chữ ký là thật, nhưng mốc thời gian `signed_after` của ERP
// từ chối nó và chân ký nằm Manual Review. Nút "Đối soát" cũ KHÔNG truyền cờ chấp nhận
// (mặc định TẮT, có chủ đích), nên bấm vào vẫn bị từ chối — chỉ script chạy tay mới bật được.
//
// Nút này BỎ một lớp bảo vệ, nên bộ test không kiểm "có nút hay không" mà kiểm ba điều:
//   1. Bấm nút phải gửi ĐÚNG cờ và ĐÚNG lý do người nhập — nuốt mất một trong hai là hỏng.
//   2. Không nhập lý do (hoặc quá ngắn) thì KHÔNG gửi gì cả — không phải "gửi rồi máy chủ chặn".
//   3. Nút "Đối soát" thường KHÔNG được vô tình mang cờ theo.
// Chạy THẬT hàm `run` của trang, không dò chuỗi: đổi tên hàm/biến vẫn bắt được lỗi thật.
import fs from "fs";
import vm from "vm";
import { fileURLToPath } from "url";
import path from "path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
function find(rel, name) {
  for (const r of ["../../", "../../../"]) {
    const p = path.join(HERE, r, rel, name);
    if (fs.existsSync(p)) return p;
  }
  throw new Error(name + " not found");
}
const OPS = find("../platform/esign/ui", "ops_page.html");
const SRC = fs.readFileSync(OPS, "utf8")
  .match(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/)[1];

let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };

// --- cắt đúng những mảnh cần, rồi chạy thật -------------------------------------------
function slice(from, to) {
  const i = SRC.indexOf(from), j = SRC.indexOf(to, i);
  if (i < 0 || j < 0) throw new Error("khong cat duoc: " + from);
  return SRC.slice(i, j);
}
const CODE = slice("var ACTION_LABEL = {", "function actionsHtml")
           + slice("function run(btn) {", "\n  function wire()");

function harness(answers) {
  const calls = [], msgs = [];
  const ctx = {
    console,
    // `call` trả về promise TREO: `run` có chuỗi .then(...) nhưng ta chỉ cần biết nó gọi
    // gì. Treo luôn thì không phải giả nốt load()/msg() phía sau.
    call: (method, args, type) => { calls.push({ method, args, type }); return new Promise(() => {}); },
    msg: (text, kind) => msgs.push({ text, kind }),
    esc: (s) => String(s == null ? "" : s),
    window: {
      confirm: () => answers.confirm !== false,
      prompt: () => (answers.prompt === undefined ? "" : answers.prompt),
    },
  };
  vm.createContext(ctx);
  vm.runInContext(CODE + "\n;this.run = run; this.ACTION_LABEL = ACTION_LABEL; this.ACTION_WHY = ACTION_WHY;", ctx);
  return { ctx, calls, msgs };
}

function btn(act, name) {
  const a = { "data-act": act, "data-name": name, "data-doc": "", "data-dt": "", "data-label": act };
  return { getAttribute: (k) => (k in a ? a[k] : null) };
}

const LY_DO = "Da mo cong SCTS: Vinh ky luc 08/09 23:48, dung tai lieu.";

// 1. Bấm nút -> gửi đúng cờ + đúng lý do
{
  console.log("Bấm nút: gửi đúng cờ và đúng lý do");
  const h = harness({ prompt: LY_DO });
  h.ctx.run(btn("reconcile_predating", "EC-DSR-2026-00080"));
  ok(h.calls.length === 1, "gọi đúng một lần");
  const c = h.calls[0] || { args: {} };
  ok(c.method === "reconcile_signature_request", "gọi đúng endpoint (không tạo endpoint song song)");
  ok(c.type === "POST", "POST — GET tự rollback trong Frappe");
  ok(c.args.dsr_name === "EC-DSR-2026-00080", "đúng chân ký");
  ok(String(c.args.accept_predating) === "1", "CÓ truyền cờ chấp nhận — thiếu nó thì nút vô dụng");
  ok(c.args.reason === LY_DO, "lý do đi NGUYÊN VĂN xuống máy chủ, không bị nuốt");
}

// 2. Không có lý do -> KHÔNG gửi gì
{
  console.log("Thiếu lý do: chặn tại chỗ, không gửi");
  for (const bad of ["", "   ", "ok", "ngan qua", null]) {
    const h = harness({ prompt: bad });
    h.ctx.run(btn("reconcile_predating", "EC-DSR-2026-00080"));
    ok(h.calls.length === 0, "lý do " + JSON.stringify(bad) + " -> không gửi gì");
    ok(h.msgs.some((m) => m.kind === "err"), "và có báo lỗi cho người bấm");
  }
  // Đúng ngưỡng thì PHẢI qua — nếu không thì phép kiểm ở trên chỉ đang chặn tất.
  const h2 = harness({ prompt: "1234567890" });
  h2.ctx.run(btn("reconcile_predating", "x"));
  ok(h2.calls.length === 1, "đúng 10 ký tự thì qua");
}

// 3. Bấm Hủy ở hộp xác nhận -> không gửi
{
  console.log("Hủy ở hộp xác nhận");
  const h = harness({ confirm: false, prompt: LY_DO });
  h.ctx.run(btn("reconcile_predating", "x"));
  ok(h.calls.length === 0, "không gửi gì");
}

// 4. Nút "Đối soát" thường KHÔNG mang cờ theo
{
  console.log("Đối soát thường: tuyệt đối không kèm cờ");
  const h = harness({ prompt: LY_DO });
  h.ctx.run(btn("reconcile", "EC-DSR-2026-00080"));
  ok(h.calls.length === 1, "vẫn gọi");
  const a = (h.calls[0] || { args: {} }).args;
  ok(!("accept_predating" in a), "KHÔNG có cờ — đường thường phải y hệt trước");
  ok(!("reason" in a), "và không hỏi lý do");
}

// 5. Người bấm phải được cho biết mình đang bỏ cái gì
{
  console.log("Hộp xác nhận nói rõ đánh đổi");
  const h = harness({ prompt: LY_DO });
  const why = h.ctx.ACTION_WHY.reconcile_predating || "";
  ok(/TRƯỚC/.test(why), "nói rõ tình huống: ký trước lệnh");
  ok(/thời gian/.test(why), "nói rõ bỏ phép kiểm nào");
  ok(/Sai người|sai tài liệu|Sai tài liệu/.test(why), "nói rõ cái gì VẪN bị từ chối");
  ok(/lý do/i.test(why), "báo trước là phải nêu lý do");
  ok((h.ctx.ACTION_LABEL.reconcile_predating || "").length > 0, "có nhãn riêng, không dùng lại nhãn Đối soát");
  ok(h.ctx.ACTION_LABEL.reconcile_predating !== h.ctx.ACTION_LABEL.reconcile,
     "nhãn phải KHÁC nút thường — hai việc khác nhau");
}

console.log(pass + " đạt, " + fail + " hỏng");
process.exit(fail ? 1 : 0);
