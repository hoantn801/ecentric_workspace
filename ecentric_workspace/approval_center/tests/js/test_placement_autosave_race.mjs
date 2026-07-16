// Copyright (c) 2026, eCentric and contributors
// Phase C autosave RACE-SAFETY proof (deterministic). Mirrors the exact token/cancel guard
// logic in document_signing_section.html (_persist / delete / _cancelPending) to prove:
// A move->delete-before-debounce stays deleted (no recreate); B rapid edits -> newest wins;
// C out-of-order response -> newest state kept; D close/switch cancels pending / discards stale.
function mkEngine(){
  const E={pending:{},appliedRev:{},rev:0,docToken:0,applied:[]};
  E.cancelAll=function(){ for(const k in E.pending){ if(E.pending[k].timer) E.pending[k].timer.canceled=true; }
    E.pending={}; E.appliedRev={}; E.docToken++; };
  E.persist=function(cid){
    const pend=E.pending[cid]||(E.pending[cid]={});
    if(pend.timer) pend.timer.canceled=true;                 // newer edit supersedes older debounce (clearTimeout)
    if(pend.deleted) return null;                            // never recreate a deleted box
    const myRev=++E.rev, myToken=E.docToken; pend.rev=myRev;
    const t={canceled:false, fire:function(){
      if(t.canceled) return null;                            // debounce was cancelled before firing
      return function response(){                            // simulate the async save response
        if(myToken!==E.docToken) return "stale-token";       // drawer closed / switched
        if(E.pending[cid] && E.pending[cid].deleted) return "deleted";
        if(myRev<(E.appliedRev[cid]||0)) return "out-of-order";
        E.appliedRev[cid]=myRev; E.applied.push({cid,rev:myRev}); return "applied";
      };
    }};
    pend.timer=t; return t;
  };
  E.del=function(cid){                                        // delete cancels pending save for THIS box first
    const pend=E.pending[cid]||(E.pending[cid]={});
    if(pend.timer) pend.timer.canceled=true;
    pend.deleted=true; pend.rev=++E.rev;
  };
  return E;
}
let pass=0,fail=0; const ok=(c,m)=>{console.log((c?"  ok - ":"  FAIL - ")+m);pass+=c;fail+=!c;};

// A. move -> delete before the debounce fires -> box stays deleted, no save applied
let E=mkEngine(); let tMove=E.persist("PL1"); E.del("PL1");
ok(tMove.fire()===null,"A: pending move save is cancelled by delete (never fires)");
ok(E.pending["PL1"].deleted===true && E.applied.length===0,"A: box remains deleted, not recreated");

// B. move A -> move B quickly (same box) -> only B persists, coordinates B win
E=mkEngine(); let tA=E.persist("PL1"); let tB=E.persist("PL1");
ok(tA.canceled===true,"B: earlier debounce superseded");
ok(tB.fire()()==="applied","B: newest edit persists");
ok(tA.fire()===null,"B: older edit never fires -> final state is B");

// C. two dispatched saves; OLD response arrives AFTER NEW response -> newest kept
E=mkEngine(); let t1=E.persist("PL1"); let r1=t1.fire();      // t1 dispatched (in-flight)
let t2=E.persist("PL1"); let r2=t2.fire();                    // t2 dispatched
ok(r2()==="applied","C: newer response applied");
ok(r1()==="out-of-order","C: older response arriving later is discarded (UI keeps newest)");

// D. close drawer with a pending (not-yet-fired) save -> cancelled, no stale mutation
E=mkEngine(); let tp=E.persist("PL1"); E.cancelAll();
ok(tp.fire()===null,"D: pending save cancelled on close (no dispatch)");
// D2. a save already dispatched before close -> its late response is discarded by token
E=mkEngine(); let td=E.persist("PL1"); let rd=td.fire(); E.cancelAll();
ok(rd()==="stale-token","D: late response after close is discarded (no stale mutation)");

console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail?1:0);
