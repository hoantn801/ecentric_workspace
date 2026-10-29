# Copyright (c) 2026, eCentric and contributors
"""Use-case: dua file GOC cua mot phieu GBS len boxme, go link SharePoint ben boxme,
va giu MOT BAN SAO private ngay tren site EC (doi chieu doc lap voi SharePoint -
thu vien nam tren tenant boxmeglobal; Hoan chot 29/10/2026).

Idempotent: chay lai chi up / chep file con thieu (theo ten). Moi file loi rieng.
"""

from ecentric_workspace.gbs_attachments import constants as C
from ecentric_workspace.gbs_attachments import domain


class PushOriginalsService:
    def __init__(self, repo=None, graph=None, boxme_factory=None, now=None, user=None):
        if repo is None:
            from ecentric_workspace.gbs_attachments.infrastructure import repository as repo
        if graph is None:
            from ecentric_workspace.gbs_attachments.infrastructure import graph
        if boxme_factory is None:
            from ecentric_workspace.gbs_attachments.infrastructure.boxme import BoxmeFiles
            boxme_factory = BoxmeFiles.from_settings
        if now is None or user is None:
            import frappe
            now = now or frappe.utils.now
            user = user or (lambda: frappe.session.user)
        self.repo, self.graph, self.boxme_factory = repo, graph, boxme_factory
        self.now, self.user = now, user
        self._token = None

    # ------------------------------------------------------------------ public
    def execute(self, doctype, name, reason="", dry_run=False):
        if doctype not in C.BOXME_DOCTYPE:
            raise ValueError("doctype khong ho tro: " + str(doctype))
        doc = self.repo.load(doctype, name)
        if not doc:
            raise ValueError("khong thay phieu " + name)
        target = doc.get("gbs_doc_name") or ""
        if not target:
            return {"skipped": "chua co phieu boxme"}
        resync = int(doc.get("resubmit_count") or 0) > int(doc.get("attachments_pushed_count") or 0)
        sources, errors = self._sources(doc.get("attachment_url"))
        box = self.boxme_factory()
        bdt = C.BOXME_DOCTYPE[doctype]
        p = domain.plan([s["name"] for s in sources], box.list_files(bdt, target), resync,
                        box.api_user() if resync else "")
        have_local = self.repo.local_copy_names(doctype, name)
        copy = [s["name"] for s in sources if s["kind"] == "sharepoint" and s["name"] not in have_local]
        result = {"target": target, "resync": resync, "plan": p, "sources": len(sources),
                  "local_copy": copy, "uploaded": [], "copied": [], "deleted": 0, "errors": errors}
        if dry_run:
            result["files"] = [{"name": s["name"], "size": s.get("size", 0), "kind": s["kind"]} for s in sources]
            return result
        self._delete(box, p["delete"], result)
        for src in sources:
            if src["name"] in p["upload"] or src["name"] in copy:
                self._handle(doctype, name, box, bdt, target, src, src["name"] in p["upload"],
                             src["name"] in copy, result)
        self._record(doctype, name, doc, result, reason)
        return result

    # ----------------------------------------------------------------- private
    def _sources(self, raw):
        """attachment_url -> [{name, kind, url, item?}] ; loi phan giai ghi rieng tung file."""
        out, errors, seen = [], [], set()
        for url in domain.split_attachment_urls(raw):
            try:
                if domain.is_local_file_url(url):
                    src = {"name": url.rsplit("/", 1)[-1], "kind": "local", "url": url}
                elif domain.is_sharepoint_url(url):
                    self._token = self._token or self.graph.app_token()
                    item = self.graph.resolve(url, self._token)
                    src = {"name": item.get("name") or domain.fragment_name(url) or "attachment",
                           "kind": "sharepoint", "url": url, "item": item, "size": item.get("size", 0)}
                else:
                    errors.append("bo qua url la: " + url[:80])
                    continue
                if src["name"] not in seen:
                    seen.add(src["name"])
                    out.append(src)
            except Exception as e:
                errors.append((domain.fragment_name(url) or url[-40:]) + ": " + str(e)[:200])
        return out, errors

    def _delete(self, box, ids, result):
        for fid in ids:
            try:
                box.delete(fid)
                result["deleted"] += 1
            except Exception as e:
                result["errors"].append("xoa " + str(fid) + ": " + str(e)[:160])

    def _handle(self, doctype, name, box, bdt, target, src, to_boxme, to_local, result):
        """Tai 1 lan, dung cho ca boxme lan ban sao EC."""
        try:
            if src["kind"] == "local":
                fname, data = self.repo.local_file_bytes(src["url"])
            else:
                fname = src["name"]
                data = self.graph.download(src["item"], self._token or self.graph.app_token())
        except Exception as e:
            result["errors"].append(src["name"] + ": " + str(e)[:200])
            return
        if to_boxme:
            try:
                box.upload(bdt, target, fname, data)
                result["uploaded"].append(fname)
            except Exception as e:
                result["errors"].append(fname + ": " + str(e)[:200])
        if to_local:
            try:
                self.repo.save_local_copy(doctype, name, fname, data)
                result["copied"].append(fname)
            except Exception as e:
                result["errors"].append("ban sao EC " + fname + ": " + str(e)[:160])

    def _record(self, doctype, name, doc, result, reason):
        boxme_errs = [e for e in result["errors"] if not e.startswith("ban sao EC ")]
        fields = {
            "attachments_sync_count": len(result["uploaded"]) + len(result["plan"]["keep"]),
            "attachments_sync_error": "; ".join(result["errors"])[:1000],
            "attachments_last_sync": self.now(),
            "attachments_synced": 0 if boxme_errs else 1,
        }
        if result["resync"]:
            fields["attachments_pushed_count"] = int(doc.get("resubmit_count") or 0)
        event = {
            "event": C.HISTORY_EVENT, "at": self.now(), "by": self.user(), "reason": reason or "",
            "gbs_doc_name": result["target"], "uploaded": result["uploaded"], "copied_ec": result["copied"],
            "kept": len(result["plan"]["keep"]), "deleted": result["deleted"],
            "errors": result["errors"][:10],
        }
        self.repo.save_result(doctype, name, fields, event)
