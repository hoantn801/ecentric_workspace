/* Nut "Chuyen cho ke toan khac" (27/11/2026, chi Lien) tren /approvals/contract-review (jsdom):
 *   node ecentric_workspace/approval_center/tests/test_contract_review_chuyen_ke_toan.js <repo>
 * Nut chi hien khi server tra extra.handover; khong hien khi dang cho cong ky (esign_wait thay ca khoi hanh dong).
 */
const {JSDOM}=require("jsdom"); const fs=require("fs"); const path=require("path");
const REPO=process.argv[2]||path.join(__dirname,"..","..","..");
const html=fs.readFileSync(path.join(REPO,"ecentric_workspace/approval_center/features/contract_review/ui/main_section.html"),"utf8");
const c={}; let failed=0; function chk(k,v){ c[k]=!!v; if(!v) failed++; }
const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://x/approvals/contract-review"});
const w=dom.window; const calls=[];
w.frappe={call:function(o){ calls.push(o); if(/get_bootstrap/.test(o.method)) return Promise.resolve({message:{tabs:{},context:{user:"lien@ec"},form_options:{}}});
  if(/handover_step/.test(o.method)) return Promise.resolve({message:{to:o.args.new_user}}); return Promise.resolve({message:{}}); }};
(async function(){
  let t=0; while(!w.ContractReview){ if(t++>160){ console.log("not ready"); process.exit(1);} await new Promise(r=>setTimeout(r,25)); }
  const CR=w.ContractReview;
  const base={capabilities:{can_approve:true,can_reject:true},approval:{approval_status:"Pending"},business:{name:"CR-1"}};
  const ho={level:"Finance Team Review",level_label:"Finance Team duyệt",level_no:2,from:["lien@ec"],candidates:[{user:"kt1@ec",full_name:"Kế toán Một"}]};
  chk("khong co extra.handover: khong co nut", CR.actionPanelHTML(Object.assign({extra:{}},base)).indexOf('data-act="handover"')<0);
  chk("co extra.handover: co nut", CR.actionPanelHTML(Object.assign({extra:{handover:ho}},base)).indexOf('data-act="handover"')>0);
  chk("dang cho cong ky: khong co nut", CR.actionPanelHTML(Object.assign({extra:{handover:ho,esign_wait:{status:"Verifying"}}},base)).indexOf('data-act="handover"')<0);
  Object.keys(c).forEach(k=>console.log((c[k]?"PASS":"FAIL")+" - "+k)); console.log(failed?"SOME_FAIL":"ALL_PASS"); process.exit(failed?1:0);
})();
