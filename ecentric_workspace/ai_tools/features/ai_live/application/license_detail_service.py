# Copyright (c) 2026, eCentric and contributors
"""Trang Ban quyen - ngan chi tiet may (thong tin, app, 50 su kien, may chep tu may nay) + cay phan phoi."""
from ecentric_workspace.ai_tools.features.ai_live import license_constants as L
from ecentric_workspace.ai_tools.features.ai_live.application import _license_deps as D
from ecentric_workspace.ai_tools.features.ai_live.domain import license_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import license_view as V


class LicenseDetailService:
    def __init__(self, settings=None, machines=None, dists=None, events=None):
        self.settings, self.machines = settings or D.settings(), machines or D.machines()
        self.dists, self.events = dists or D.dists(), events or D.events()

    def machine(self, roles, name):
        D.require_admin(roles)
        m = self.machines.get(str(name or "")[:20])
        if not m:
            raise L.LicenseError(L.Msg.NOT_FOUND % name)
        dist = self.dists.get(m.get("source_dist")) if m.get("source_dist") else None
        kids = self.machines.children(m["name"])
        ml = self.machines.labels([m.get("parent_machine")] + [k.get("parent_machine") for k in kids])
        dl = self.dists.labels([m.get("source_dist")])
        row = V.machine_row(m, dl, ml)
        row.update(os=str(m.get("os") or ""), first_ip=str(m.get("first_ip") or ""), note=str(m.get("note") or ""),
                   approved_by=str(m.get("approved_by") or ""), approved_at=str(m.get("approved_at") or ""),
                   block_message=str(m.get("block_message") or ""), clone_host=str(m.get("clone_host") or ""),
                   dist_kind=L.DIST_KIND_LABEL.get((dist or {}).get("kind"), ""))
        return {"machine": row, "installs": [V.install_row(i) for i in m.get("installs") or []],
                "events": [V.event_row(e) for e in self.events.for_machine(m["name"])],
                "children": [V.machine_row(k, dl, ml) for k in kids],
                "log_only": self.settings.get()["log_only"], "default_block": L.Msg.DEFAULT_BLOCK}

    def tree(self, roles, dist=None):
        D.require_admin(roles)
        dist = str(dist or "")[:64]
        rows = self.machines.tree_rows(None if dist in ("", V.NO_DIST) else dist)
        if dist == V.NO_DIST:
            rows = [r for r in rows if not r.get("source_dist")]
        dists = [d for d in self.dists.all() if not dist or d["name"] == dist]
        nodes = [{"name": r["name"], "label": r.get("label") or "", "host": r.get("host") or "", "status": r.get("status"),
                  "source_dist": r.get("source_dist") or "", "parent_machine": r.get("parent_machine") or "",
                  "clone_warning": int(r.get("clone_warning") or 0), "last_seen": str(r.get("last_seen") or "")}
                 for r in rows]
        roots = [{"name": d["name"], "label": d.get("label") or d["name"][:8], "kind": d.get("kind") or "",
                  "kind_label": L.DIST_KIND_LABEL.get(d.get("kind"), ""), "first_machine": d.get("first_machine") or ""}
                 for d in dists]
        return {"tree": R.build_tree(roots, nodes)}
