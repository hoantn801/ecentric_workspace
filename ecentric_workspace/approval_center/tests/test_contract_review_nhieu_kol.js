/* Creator cong ty / ho KD nhieu KOL tren /approvals/contract-review (jsdom), PO 27/11/2026:
 *   node ecentric_workspace/approval_center/tests/test_contract_review_nhieu_kol.js <repo>
 * Khoa:
 *  - Phieu KOL chon creator cong ty co danh sach KOL: hien o chon KOL (chi dong dang dung), tich thi ban nhap
 *    chi mang kol_ref (server chup lai); creator ca nhan / khong co KOL thi khong hien.
 *  - Form sua creator: them / xoa dong KOL, gui ec_cr_kols kem `name` dong cu; khong doi thi khong gui.
 *  - Chi tiet phieu: dong "KOL / kenh" liet ke KOL da chup.
 */
const {JSDOM}=require("jsdom"); const fs=require("fs"); const path=require("path");
const REPO=process.argv[2]||path.join(__dirname,"..","..","..");
const html=fs.readFileSync(path.join(REPO,"ecentric_workspace/approval_center/features/contract_review/ui/main_section.html"),"utf8");
const KOLT="KOL/KOC / Creator (EC)";
const CTY={name:"SUP-1",supplier_name:"Cty Media A",ec_cr_type:"Công ty",misa_label:"KH1",can_see_pii:true,tax_id:"0312345678",ec_bank_account_no:"001",ec_bank_name:"VCB",
  kols:[{name:"K1",kol_name:"Bé A",tiktok_id:"bea",disabled:0},{name:"K2",kol_name:"Bé B",tiktok_id:"beb",disabled:0},{name:"K3",kol_name:"Bé C",tiktok_id:"bec",disabled:1}]};
const boot={tabs:{},context:{user:"vy@e.c",employee_name:"Vy",department:"E-commerce - EC"},
  form_options:{brands:[{value:"FCV",label:"FCV"}],departments:[{value:"E-commerce - EC",label:"E-commerce"}],contract_types:[KOLT],request_kinds:["New"],
    request_types:["Template from EC / Mẫu theo khung EC"],esign_flows:[],esign_flows_with_partner:[],esign_flow_defaults:[],esign_partner_sign_types:[],
    kol_service_types:["Livestream"],kol_platforms:["TikTok"],kol_payment_schedules:["Thanh toán sau nghiệm thu"],kol_advance_percents:["30"]}};
const calls=[]; const c={}; let failed=0;
function chk(k,v){ c[k]=!!v; if(!v) failed++; }
function done(){ Object.keys(c).forEach(k=>console.log((c[k]?"PASS":"FAIL")+" - "+k)); console.log(failed?"SOME_FAIL":"ALL_PASS"); process.exit(failed?1:0); }
const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://x/approvals/contract-review"});
const w=dom.window;
w.frappe={call:function(o){ calls.push(o);
  if(/get_bootstrap/.test(o.method)) return Promise.resolve({message:boot});
  if(/kol_get_creator$/.test(o.method)) return Promise.resolve({message:JSON.parse(JSON.stringify(CTY))});
  if(/kol_list_templates/.test(o.method)) return Promise.resolve({message:{rows:[]}});
  if(/kol_update_creator/.test(o.method)) return Promise.resolve({message:{name:"SUP-1"}});
  return Promise.resolve({message:{}}); }};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
(async function(){
  let t=0; while(!(w.ContractReview&&w.document.querySelector('[data-model="contract_type"]'))){ if(t++>160){ console.log("not ready"); process.exit(1);} await wait(25); }
  const doc=w.document, CR=w.ContractReview, K=CR._KOL;
  const ct=doc.querySelector('[data-model="contract_type"]'); ct.value=KOLT; ct.dispatchEvent(new w.Event("change",{bubbles:true}));
  await wait(120);
  chk("chua chon creator: khong co o chon KOL", !doc.querySelector("[data-kolref]"));
  K.pickCreator({name:"SUP-1",supplier_name:"Cty Media A",ec_cr_type:"Công ty",misa_label:"KH1"});
  await wait(200);
  const boxes=[...doc.querySelectorAll("#kol-kols [data-kolref]")];
  chk("tai creator day du roi hien 2 KOL dang dung (bo dong ngung dung)", boxes.map(b=>b.getAttribute("data-kolref")).join(",")==="K1,K2");
  chk("goi kol_get_creator dung ten", calls.some(o=>/kol_get_creator$/.test(o.method)&&o.args.name==="SUP-1"));
  boxes[1].checked=true; boxes[1].dispatchEvent(new w.Event("change",{bubbles:true}));
  chk("tich Be B -> ban nhap chi mang kol_ref", JSON.stringify(CR.state.draft.kol_channels)===JSON.stringify([{kol_ref:"K2"}]));
  // doi sang creator ca nhan: xoa lua chon, khong hien o
  K._full["SUP-9"]={name:"SUP-9",supplier_name:"Chị C",ec_cr_type:"Cá nhân",kols:[]};
  K.pickCreator(K._full["SUP-9"]); await wait(80);
  chk("doi creator: xoa KOL da chon", (CR.state.draft.kol_channels||[]).length===0);
  chk("creator ca nhan: khong co o chon KOL", !doc.querySelector("#kol-kols [data-kolref]"));
  // form sua creator
  const m=K.creatorModal(JSON.parse(JSON.stringify(CTY))); const ov=m.ov;
  chk("form creator cong ty co 3 dong KOL", ov.querySelectorAll("#kc-kols .kc-kol").length===3);
  chk("khong doi gi thi khong gui ec_cr_kols", !("ec_cr_kols" in K.creatorData(ov,true,CTY)));
  ov.querySelector("#kc-kol-add").click();
  const last=ov.querySelector("#kc-kols .kc-kol:last-child");
  last.querySelector('[data-k="kol_name"]').value="Bé D"; last.querySelector('[data-k="tiktok_id"]').value="bed";
  ov.querySelector('#kc-kols .kc-kol [data-kol-del]').click();   // xoa dong K1
  const data=K.creatorData(ov,true,CTY);
  chk("gui ec_cr_kols: giu name dong cu, dong moi khong name", JSON.stringify((data.ec_cr_kols||[]).map(k=>[k.name||"",k.kol_name]))===JSON.stringify([["K2","Bé B"],["K3","Bé C"],["","Bé D"]]));
  chk("dong ngung dung giu trang thai", (data.ec_cr_kols||[])[1]&&data.ec_cr_kols[1].disabled===1);
  const typ=ov.querySelector("#kc-ec_cr_type"); typ.value="Cá nhân"; typ.dispatchEvent(new w.Event("change",{bubbles:true}));
  chk("doi sang ca nhan: an khoi KOL", ov.querySelector("#kc-kols-wrap").style.display==="none");
  chk("khoi KOL an -> gui danh sach rong", JSON.stringify(K.creatorData(ov,true,CTY).ec_cr_kols)==="[]");
  chk("bao thieu ID KOL truoc khi gui", /TikTok ID \/ Shopee ID của KOL X/.test(K.creatorCheck(Object.assign({},CTY,{ec_cr_kols:[{kol_name:"X"}]}),true)));
  // chi tiet
  const det={business:{contract_type:KOLT,creator_name:"Cty Media A",creator_type:"Công ty",kol_channels:[{kol_ref:"K1",kol_name:"Bé A",tiktok_id:"bea"},{kol_ref:"K2",kol_name:"Bé B",tiktok_id:"beb"}]},
    extra:{kol:{acceptances:[],funding:{},calc:[]}},approval:{approval_status:"Pending"}};
  const dh=K.detailHTML(det);
  chk("chi tiet liet ke KOL", dh.indexOf("Bé A (TikTok bea); Bé B (TikTok beb)")>=0);
  chk("phieu khong co KOL: khong co dong KOL", K.detailHTML({business:{contract_type:KOLT,creator_name:"X"},extra:{kol:{acceptances:[],funding:{},calc:[]}},approval:{approval_status:"Pending"}}).indexOf("KOL / kênh")<0);
  done();
})().catch(e=>{ console.log("ERR",e&&e.stack||e); process.exit(1); });
