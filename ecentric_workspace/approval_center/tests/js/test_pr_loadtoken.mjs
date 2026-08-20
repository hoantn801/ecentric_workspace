// Copyright (c) 2026, eCentric and contributors
// Stability pass ISSUE 4 — PR identity LOAD-TOKEN proof (deterministic). Mirrors the exact guard
// in document_signing_section.html load(): a load captures (tok, name); on resolve it renders only
// if `tok===_loadTok && pr()===name`. Identity change bumps _loadTok, so a late/slow response from
// the PREVIOUS request can never repopulate the new page.
function mkView(){
  const V={ _loadTok:0, _curPr:null, cur:null, rendered:null };
  V.pr=()=>V.cur;
  V.load=function(){                                         // returns the deferred "server resolve"
    const name=V.pr(); const tok=++V._loadTok; V._curPr=name;
    if(!name){ V.rendered="__unsaved__"; return ()=>{}; }
    return function resolve(docsForName){                    // async response arrives later
      if(tok!==V._loadTok || V.pr()!==name) return "discarded-stale";
      V.rendered=docsForName; return "rendered";
    };
  };
  V.navigate=function(id){ V.cur=id; V._loadTok++; };        // _checkIdentity bumps the token immediately
  return V;
}
let pass=0,fail=0; const ok=(c,m)=>{console.log((c?"  ok - ":"  FAIL - ")+m);pass+=c;fail+=!c;};

// load A, then navigate to a NEW request before A's response returns
let V=mkView(); V.cur="A";
const respA=V.load();                                        // in-flight load for A
V.navigate(null);                                            // -> "Tạo mới" (identity change bumps token)
const loadNew=V.load();                                      // new page load (no id -> unsaved)
ok(V.rendered==="__unsaved__","new-request page rendered as unsaved");
ok(respA({docs:"A-docs"})==="discarded-stale","late response from A is discarded (token stale)");
ok(V.rendered==="__unsaved__","A documents never rendered into the new page");

// load A, navigate to B, B resolves, then A's late response must not overwrite B
V=mkView(); V.cur="A"; const rA=V.load();
V.navigate("B"); const rB=V.load();
ok(rB({docs:"B-docs"}).valueOf()==="rendered" && V.rendered.docs==="B-docs","B rendered");
ok(rA({docs:"A-docs"})==="discarded-stale" && V.rendered.docs==="B-docs","late A does not overwrite B");

console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail?1:0);
