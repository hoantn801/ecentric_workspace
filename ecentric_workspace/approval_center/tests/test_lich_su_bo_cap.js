/* Lich su phieu: dong "tu dong bo cap" (engine.submit skip_level_nos) - QC 27/11/2026, EC-CTR-2026-00150.
 *   node ecentric_workspace/approval_center/tests/test_lich_su_bo_cap.js <repo>
 * Khoa: dong cu (actor = nguoi gui, "(level 4 - ...)" cuoi comment) va dong moi (Administrator + level_no) deu hien
 * "Tu dong bo qua cap nay · Cap 4 · ... · He thong", xep vao cho cua cap 4; "Duyet thay" va bo cap khac giu nguyen.
 */
const {JSDOM}=require("jsdom"); const fs=require("fs"); const path=require("path");
const REPO=process.argv[2]||path.join(__dirname,"..","..","..");
const src=fs.readFileSync(path.join(REPO,"ecentric_workspace/public/js/ec_approval_ui.bundle.js"),"utf8");
const dom=new JSDOM("<body></body>",{runScripts:"outside-only"}); dom.window.eval(src); const U=dom.window.EcApprovalUI;
const c={}; let failed=0; function chk(k,v){ c[k]=!!v; if(!v) failed++; }
const R="Cấp Nhân sự chỉ dành cho hợp đồng lao động.";
const old=[{seq:1,action:"Submitted",actor:"thien.vo@ecentric.vn"},
  {seq:2,action:"Skipped",actor:"thien.vo@ecentric.vn",comment:R+" (level 4 - HR & C&B Review)"},
  {seq:3,action:"Approved",actor:"a@ec",level_no:1,level_name:"Department Manager Review"},
  {seq:4,action:"Approved",actor:"b@ec",level_no:2,level_name:"Finance Team Review"},
  {seq:5,action:"Approved",actor:"c@ec",level_no:3,level_name:"Head of Finance Review"},
  {seq:6,action:"Approved",actor:"d@ec",level_no:5,level_name:"CEO Review"}];
const p=U.timelineItemParts(old[1]);
chk("dong cu: nhan Tu dong bo qua", p.label==="Tự động bỏ qua cấp này");
chk("dong cu: nguoi thuc hien la He thong", p.actor==="Hệ thống");
chk("dong cu: cap 4 doc tu comment", p.level==="Cấp 4 · HR & C&B Review");
chk("dong cu: comment chi con ly do", p.comment===R);
chk("xep vao giua cap 3 va cap 5", U.orderTimeline(old).map(a=>a.seq).join(",")==="1,3,4,5,2,6");
chk("phieu moi duyet cap 1: dong bo cap 4 xuong sau cap 1", U.orderTimeline(old.slice(0,3)).map(a=>a.seq).join(",")==="1,3,2");
chk("chua ai duyet: giu nguyen cho", U.orderTimeline(old.slice(0,2)).map(a=>a.seq).join(",")==="1,2");
const nw={seq:2,action:"Skipped",actor:"Administrator",level_no:4,level_name:"HR & C&B Review",comment:R};
const q=U.timelineItemParts(nw);
chk("dong moi: He thong + cap 4 + ly do", q.actor==="Hệ thống"&&q.level==="Cấp 4 · HR & C&B Review"&&q.comment===R&&q.label==="Tự động bỏ qua cấp này");
const ov=U.timelineItemParts({action:"Skipped",actor:"admin@ec",level_no:2,comment:"Admin override approved by z@ec"});
chk("duyet thay giu nhan rieng", ov.label==="Duyệt thay: bỏ lượt người duyệt");
const human=U.timelineItemParts({action:"Skipped",actor:"x@ec",level_no:2,comment:"Bỏ qua vì vắng"});
chk("bo cap do nguoi (khong phai he thong) giu ten nguoi", human.actor==="x@ec"&&human.label!=="Tự động bỏ qua cấp này");
const late=[{seq:1,action:"Submitted",actor:"u"},{seq:2,action:"Approved",actor:"a",level_no:1},{seq:3,action:"Approved",actor:"b",level_no:2},
  {seq:4,action:"Skipped",actor:"Administrator",level_no:3,comment:"Skipped: this approver also approves at a later level"},{seq:5,action:"Approved",actor:"c",level_no:4}];
chk("dong bo cap ghi dung luc (p266) khong bi keo len", U.orderTimeline(late).map(a=>a.seq).join(",")==="1,2,3,4,5");
const late2=[{seq:1,action:"Submitted",actor:"u"},{seq:2,action:"Approved",actor:"a",level_no:1},{seq:3,action:"Restarted",actor:"u"},
  {seq:4,action:"Skipped",actor:"Administrator",level_no:2,comment:"x"}];
chk("dong bo cap o cuoi giu nguyen", U.orderTimeline(late2).map(a=>a.seq).join(",")==="1,2,3,4");
const h=U.timelineHTML(old);
chk("HTML: dong bo cap khong ghi ten nguoi gui", (h.match(/thien\.vo/g)||[]).length===1);
chk("HTML: cap 4 dung sau cap 3", h.indexOf("Head of Finance Review")<h.indexOf("HR &amp; C&amp;B Review")&&h.indexOf("HR &amp; C&amp;B Review")<h.indexOf("CEO Review"));
Object.keys(c).forEach(k=>console.log((c[k]?"PASS":"FAIL")+" - "+k)); console.log(failed?"SOME_FAIL":"ALL_PASS"); process.exit(failed?1:0);
