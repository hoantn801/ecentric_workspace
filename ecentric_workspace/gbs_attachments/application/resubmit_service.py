# Copyright (c) 2026, eCentric and contributors
"""Use-case: dua phieu bi GBS tu choi CHI VI file (link SharePoint) quay lai luong duyet
ben boxme, KHONG qua L1 phia EC lan nua (Hoan chot "huong B", 29/10/2026).

Chot chan (tu choi neu sai bat ky dieu nao):
  - phieu EC dang "Approved" (noi dung EC da duyet, khong co ai dang sua)
  - phieu boxme dang "Rejected"
  - ben boxme KHONG con link SharePoint nao (phai chay PushOriginalsService truoc)
Chuoi hanh dong giong Server Script sync (v11/v12):
  SO: Resubmit -> Draft -> "Submit for Approval" (chi don Services; con lai de GBS tu day)
  PO: Resubmit -> Draft -> "Submit"
"""

from ecentric_workspace.gbs_attachments import constants as C
from ecentric_workspace.gbs_attachments import domain


class ResubmitAfterFileFixService:
    def __init__(self, repo=None, boxme_factory=None, now=None, user=None, sleep=None):
        if repo is None:
            from ecentric_workspace.gbs_attachments.infrastructure import repository as repo
        if boxme_factory is None:
            from ecentric_workspace.gbs_attachments.infrastructure.boxme import BoxmeFiles
            boxme_factory = BoxmeFiles.from_settings
        if now is None or user is None:
            import frappe
            now = now or frappe.utils.now
            user = user or (lambda: frappe.session.user)
        if sleep is None:
            import time
            sleep = time.sleep
        self.repo, self.boxme_factory, self.now, self.user, self.sleep = repo, boxme_factory, now, user, sleep

    def execute(self, doctype, name, note=""):
        if doctype not in C.BOXME_DOCTYPE:
            raise ValueError("doctype khong ho tro: " + str(doctype))
        doc = self.repo.load(doctype, name) or {}
        target = doc.get("gbs_doc_name") or ""
        if (doc.get("status") or "") != "Approved" or not target:
            raise ValueError(name + ": phieu EC phai dang Approved va da co phieu boxme")
        box, bdt = self.boxme_factory(), C.BOXME_DOCTYPE[doctype]
        state = box.workflow_state(bdt, target)
        if state.lower() != "rejected":
            raise ValueError(name + ": phieu boxme dang '" + state + "', khong phai Rejected")
        if any(domain.is_sharepoint_url(f.get("file_url")) for f in box.list_files(bdt, target)):
            raise ValueError(name + ": ben boxme con link SharePoint - chay day file goc truoc")
        steps = [box.apply_workflow(bdt, target, C.ACTION_RESUBMIT)]
        self._wait_draft(box, bdt, target)
        nxt = self._next_action(doctype, doc)
        if nxt:
            steps.append(box.apply_workflow(bdt, target, nxt))
        final = steps[-1] or box.workflow_state(bdt, target)
        self.repo.save_result(doctype, name, {"gbs_status": final, "gbs_last_sync": self.now(), "sync_error": ""}, {
            "event": C.RESUBMIT_EVENT, "at": self.now(), "by": self.user(), "gbs_doc_name": target,
            "from": state, "to": final, "actions": [C.ACTION_RESUBMIT] + ([nxt] if nxt else []),
            "note": note or "GBS tu choi vi file link SharePoint; da thay file goc, gui lai khong qua L1 EC"})
        return {"target": target, "from": state, "to": final}

    def _wait_draft(self, box, bdt, target):
        for _ in range(5):
            if box.workflow_state(bdt, target).lower() == "draft":
                return
            self.sleep(1)

    @staticmethod
    def _next_action(doctype, doc):
        if doctype == "GBS Purchase Order":
            return C.ACTION_PO_SUBMIT
        return C.ACTION_SO_SUBMIT if (doc.get("order_type") or "").endswith("Services") else ""
