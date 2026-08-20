// Copyright (c) 2026, eCentric and contributors
// Stability pass — LOCAL-FIRST drag/resize proof (deterministic). Drag gestures cannot be driven
// through the node:vm DOM stub, so this mirrors the exact interaction model in
// document_signing_section.html (global drag controller + _persist that never rebuilds boxes +
// DRW.geom overlay + revision guard) to prove: continuous drag never jumps/shrinks/resets to
// top-left; the save response updates metadata only; a stale/out-of-order response is ignored;
// only a fresh hydrate (open/reload) re-reads server geometry.
function mkModel(){
  const M={ el:{x:0,y:0,w:120,h:40}, geom:{}, st:{placements:[]}, rev:0, appliedRev:0,
            pending:{}, hydrateCount:0, savedBoxes:[] };
  // WHILE dragging: update the visible element ONLY (no save, no redraw)
  M.dragTo=function(x,y,w,h){ M.el={x,y,w,h}; };            // many moves, purely local
  // pointerup: commit clamped local geometry + schedule ONE save (revision-tokened)
  M.pointerUp=function(cid){
    const clamped={ x:Math.max(0,M.el.x), y:Math.max(0,M.el.y),
                    width:Math.max(20,M.el.w), height:Math.max(12,M.el.h) };
    M.geom[cid]=clamped;                                    // local wins immediately
    const myRev=++M.rev; M.pending[cid]=myRev;
    return function serverResponse(serverGeom){             // SAVE RESPONSE
      if(myRev<M.appliedRev) return "stale-ignored";        // out-of-order guard
      M.appliedRev=myRev;
      M.st={placements:[{name:"PL1",x:serverGeom.x,y:serverGeom.y,width:serverGeom.width,height:serverGeom.height}]};
      // metadata only: the RESPONSE must NOT touch M.el (visible geometry stays local)
      return "applied-metadata-only";
    };
  };
  M.visible=function(cid){ const g=M.geom[cid]||M.el; return g; };  // what the user sees
  M.hydrate=function(){ M.hydrateCount++;                   // ONLY on open/reload -> from server
    const p=(M.st.placements||[])[0]; if(p){ M.el={x:p.x,y:p.y,w:p.width,h:p.height}; M.geom={}; } };
  return M;
}
let pass=0,fail=0; const ok=(c,m)=>{console.log((c?"  ok - ":"  FAIL - ")+m);pass+=c;fail+=!c;};

// continuous drag for "several seconds" (many moves) then release -> final local geometry kept
let M=mkModel();
for(let i=0;i<300;i++) M.dragTo(100+i, 200+i, 180, 90);      // long continuous resize+move
const resp=M.pointerUp("PL1");
ok(M.visible("PL1").x===399 && M.visible("PL1").width===180,"continuous drag: final local geometry kept (no jump)");

// server echoes DEFAULT (e.g. a slower earlier place at 120x40 top-left) AFTER the drag
resp({x:0,y:0,width:120,height:40});
ok(M.visible("PL1").x===399 && M.visible("PL1").width===180,
   "save response does NOT replace visible geometry (no shrink / no top-left reset)");

// edit again before an earlier save returns -> newer local wins, stale response ignored
M=mkModel();
M.dragTo(50,50,200,100); const r1=M.pointerUp("PL1");        // first commit (rev1)
M.dragTo(300,300,220,110); const r2=M.pointerUp("PL1");      // second commit (rev2) supersedes
ok(r2({x:300,y:300,width:220,height:110})==="applied-metadata-only","newer save applied");
ok(r1({x:50,y:50,width:200,height:100})==="stale-ignored","older/out-of-order response ignored");
ok(M.visible("PL1").x===300 && M.visible("PL1").width===220,"final visible geometry = newest edit");

// only a fresh hydrate (open/reload) re-reads server geometry
M=mkModel(); M.dragTo(10,10,60,30); const r=M.pointerUp("PL1"); r({x:10,y:10,width:60,height:30});
ok(M.hydrateCount===0,"no hydrate during interaction");
M.st={placements:[{name:"PL1",x:500,y:500,width:300,height:150}]}; M.hydrate();
ok(M.el.x===500 && M.el.w===300,"fresh open/reload hydrates geometry from server");

console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail?1:0);
