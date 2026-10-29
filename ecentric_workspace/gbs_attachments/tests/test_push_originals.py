# Copyright (c) 2026, eCentric and contributors
"""gbs_attachments: ke hoach + service, khong can bench / mang.

Su co 29/10/2026: boxme auto-reject moi file dinh kem dang link SharePoint.
Bo test khoa 3 dieu:
  1. Link SharePoint ben boxme LUON bi go, file goc cua EC duoc up thay.
  2. Chay lai khong up trung (idempotent theo ten file).
  3. Khong bao gio xoa file do nguoi boxme tu dinh kem.
"""

import sys
import types
import unittest

try:  # may dev khong cai requests van chay duoc bo test (moi HTTP deu duoc gia lap)
    import requests  # noqa: F401
except ImportError:
    sys.modules["requests"] = types.ModuleType("requests")

from ecentric_workspace.gbs_attachments import domain
from ecentric_workspace.gbs_attachments.application.push_service import PushOriginalsService

SP1 = "https://boxmeglobal.sharepoint.com/:b:/g/AAA?e=x#Email%20confirm.pdf"
SP2 = "https://boxmeglobal.sharepoint.com/:i:/g/BBB?e=y#Budget.png"


class PlanTest(unittest.TestCase):
    def test_sharepoint_links_always_deleted_and_originals_uploaded(self):
        files = [{"name": "f1", "file_name": "Email confirm.pdf", "file_url": SP1, "owner": "api@ec"}]
        p = domain.plan(["Email confirm.pdf"], files, resync=False, api_user="api@ec")
        self.assertEqual(p["delete"], ["f1"])
        self.assertEqual(p["upload"], ["Email confirm.pdf"])

    def test_existing_original_is_kept(self):
        files = [{"name": "f2", "file_name": "Budget.png", "file_url": "/private/files/Budget.png", "owner": "api@ec"}]
        p = domain.plan(["Budget.png"], files, resync=False, api_user="api@ec")
        self.assertEqual((p["upload"], p["delete"], p["keep"]), ([], [], ["Budget.png"]))

    def test_resync_replaces_only_our_own_files(self):
        files = [{"name": "ours", "file_name": "a.pdf", "file_url": "/private/files/a.pdf", "owner": "api@ec"},
                 {"name": "theirs", "file_name": "note.pdf", "file_url": "/private/files/note.pdf", "owner": "thuy@boxme"}]
        p = domain.plan(["a.pdf"], files, resync=True, api_user="api@ec")
        self.assertEqual(p["delete"], ["ours"])
        self.assertEqual(p["upload"], ["a.pdf"])

    def test_boxme_users_files_never_deleted_without_resync(self):
        files = [{"name": "theirs", "file_name": "x.pdf", "file_url": "/files/x.pdf", "owner": "thuy@boxme"}]
        self.assertEqual(domain.plan([], files, resync=False, api_user="api@ec")["delete"], [])

    def test_fragment_name_and_split(self):
        self.assertEqual(domain.fragment_name(SP1), "Email confirm.pdf")
        self.assertEqual(domain.split_attachment_urls(SP1 + " , ," + SP2), [SP1, SP2])


class FakeRepo:
    def __init__(self, doc, local=()):
        self.doc, self.saved, self.local = doc, [], set(local)
        self.copies = []

    def local_copy_names(self, doctype, name):
        return set(self.local)

    def save_local_copy(self, doctype, name, fname, data):
        self.copies.append((doctype, name, fname, data))
        self.local.add(fname)

    def load(self, doctype, name):
        return dict(self.doc)

    def local_file_bytes(self, url):
        return url.rsplit("/", 1)[-1], b"LOCAL"

    def save_result(self, doctype, name, fields, event):
        self.saved.append((fields, event))


class FakeGraph:
    def __init__(self, fail=()):
        self.fail, self.downloads = set(fail), []

    def app_token(self):
        return "T"

    def resolve(self, url, token):
        name = domain.fragment_name(url)
        if name in self.fail:
            raise Exception("HTTP 403")
        return {"drive_id": "d", "item_id": name, "name": name, "size": 10}

    def download(self, item, token):
        self.downloads.append(item["name"])
        return b"BYTES"


class FakeBoxme:
    def __init__(self, files, state="Rejected"):
        self.files, self.uploaded, self.deleted = list(files), [], []
        self.state, self.actions = state, []

    def workflow_state(self, dt, dn):
        return self.state

    def apply_workflow(self, dt, dn, action):
        self.actions.append(action)
        self.state = {"Resubmit": "Draft", "Submit for Approval": "Pending Revenue Verifier",
                      "Submit": "Chờ Kiểm duyệt"}[action]
        return self.state

    def api_user(self):
        return "api@ec"

    def list_files(self, dt, dn):
        return list(self.files)

    def upload(self, dt, dn, fname, data):
        self.uploaded.append((dt, dn, fname, data))
        self.files.append({"name": "n" + fname, "file_name": fname, "file_url": "/private/files/" + fname, "owner": "api@ec"})
        return "/private/files/" + fname

    def delete(self, fid):
        self.deleted.append(fid)
        self.files = [f for f in self.files if f["name"] != fid]


def make(doc, boxme, graph=None, local=()):
    repo = FakeRepo(doc, local)
    svc = PushOriginalsService(repo=repo, graph=graph or FakeGraph(), boxme_factory=lambda: boxme,
                               now=lambda: "2026-10-29 12:00:00", user=lambda: "hoan")
    return svc, repo


class ServiceTest(unittest.TestCase):
    DOC = {"name": "GBS-SO-1", "gbs_doc_name": "SAL-ORD-1", "attachment_url": SP1 + "," + SP2,
           "resubmit_count": 0, "attachments_pushed_count": 0}

    def test_happy_path_replaces_links_with_originals(self):
        box = FakeBoxme([{"name": "l1", "file_name": "Email confirm.pdf", "file_url": SP1, "owner": "api@ec"}])
        svc, repo = make(self.DOC, box)
        res = svc.execute("GBS Sales Order", "GBS-SO-1", reason="test")
        self.assertEqual(box.deleted, ["l1"])
        self.assertEqual([u[2] for u in box.uploaded], ["Email confirm.pdf", "Budget.png"])
        self.assertEqual(box.uploaded[0][:2], ("Sales Order", "SAL-ORD-1"))
        fields, event = repo.saved[-1]
        self.assertEqual(fields["attachments_synced"], 1)
        self.assertEqual(fields["attachments_sync_count"], 2)
        self.assertEqual(event["event"], "attachments_original_push")
        self.assertEqual(res["errors"], [])

    def test_second_run_uploads_nothing(self):
        box = FakeBoxme([])
        svc, _ = make(self.DOC, box)
        svc.execute("GBS Sales Order", "GBS-SO-1")
        svc.execute("GBS Sales Order", "GBS-SO-1")
        self.assertEqual(len(box.uploaded), 2)

    def test_one_bad_file_does_not_block_others_and_marks_unsynced(self):
        box = FakeBoxme([])
        svc, repo = make(self.DOC, box, FakeGraph(fail={"Budget.png"}))
        res = svc.execute("GBS Sales Order", "GBS-SO-1")
        self.assertEqual([u[2] for u in box.uploaded], ["Email confirm.pdf"])
        self.assertEqual(len(res["errors"]), 1)
        self.assertEqual(repo.saved[-1][0]["attachments_synced"], 0)

    def test_dry_run_writes_nothing(self):
        box = FakeBoxme([{"name": "l1", "file_name": "x", "file_url": SP1, "owner": "api@ec"}])
        graph = FakeGraph()
        svc, repo = make(self.DOC, box, graph)
        res = svc.execute("GBS Purchase Order", "GBS-SO-1", dry_run=True)
        self.assertEqual((box.uploaded, box.deleted, repo.saved, graph.downloads), ([], [], [], []))
        self.assertEqual(res["plan"]["delete"], ["l1"])

    def test_resync_bumps_pushed_count(self):
        doc = dict(self.DOC, resubmit_count=2, attachments_pushed_count=1)
        box = FakeBoxme([{"name": "old", "file_name": "Email confirm.pdf", "file_url": "/private/files/old.pdf", "owner": "api@ec"}])
        svc, repo = make(doc, box)
        svc.execute("GBS Sales Order", "GBS-SO-1")
        self.assertEqual(box.deleted, ["old"])
        self.assertEqual(repo.saved[-1][0]["attachments_pushed_count"], 2)

    def test_no_boxme_doc_yet_is_skipped(self):
        svc, repo = make(dict(self.DOC, gbs_doc_name=""), FakeBoxme([]))
        self.assertIn("skipped", svc.execute("GBS Sales Order", "GBS-SO-1"))
        self.assertEqual(repo.saved, [])

    def test_unsupported_doctype_rejected(self):
        svc, _ = make(self.DOC, FakeBoxme([]))
        with self.assertRaises(ValueError):
            svc.execute("Sales Order", "X")

    def test_keeps_private_copy_on_ec_and_downloads_once(self):
        box = FakeBoxme([])
        graph = FakeGraph()
        svc, repo = make(self.DOC, box, graph)
        svc.execute("GBS Sales Order", "GBS-SO-1")
        self.assertEqual([c[2] for c in repo.copies], ["Email confirm.pdf", "Budget.png"])
        self.assertEqual(repo.copies[0][:2], ("GBS Sales Order", "GBS-SO-1"))
        self.assertEqual(graph.downloads, ["Email confirm.pdf", "Budget.png"], "moi file chi tai 1 lan")

    def test_copy_only_when_boxme_already_has_original(self):
        box = FakeBoxme([{"name": "f", "file_name": "Budget.png", "file_url": "/private/files/b.png", "owner": "x"}])
        svc, repo = make(self.DOC, box, local={"Email confirm.pdf"})
        res = svc.execute("GBS Sales Order", "GBS-SO-1")
        self.assertEqual([u[2] for u in box.uploaded], ["Email confirm.pdf"])
        self.assertEqual([c[2] for c in repo.copies], ["Budget.png"])
        self.assertEqual(res["errors"], [])

    def test_ec_copy_failure_does_not_mark_boxme_unsynced(self):
        box = FakeBoxme([])
        svc, repo = make(self.DOC, box)

        def boom(*a):
            raise Exception("file qua lon")
        repo.save_local_copy = boom
        svc.execute("GBS Sales Order", "GBS-SO-1")
        self.assertEqual(repo.saved[-1][0]["attachments_synced"], 1)
        self.assertIn("ban sao EC", repo.saved[-1][0]["attachments_sync_error"])


class ResubmitTest(unittest.TestCase):
    DOC = {"name": "GBS-SO-1", "status": "Approved", "gbs_doc_name": "SAL-ORD-1",
           "order_type": "Marketing Services"}

    def make(self, doc, box):
        from ecentric_workspace.gbs_attachments.application.resubmit_service import ResubmitAfterFileFixService
        repo = FakeRepo(doc)
        return ResubmitAfterFileFixService(repo=repo, boxme_factory=lambda: box, now=lambda: "t",
                                           user=lambda: "hoan", sleep=lambda s: None), repo

    def test_so_services_resubmit_then_submit_for_approval(self):
        box = FakeBoxme([{"name": "f", "file_name": "a.pdf", "file_url": "/private/files/a.pdf", "owner": "x"}])
        svc, repo = self.make(self.DOC, box)
        res = svc.execute("GBS Sales Order", "GBS-SO-1")
        self.assertEqual(box.actions, ["Resubmit", "Submit for Approval"])
        self.assertEqual(res["to"], "Pending Revenue Verifier")
        self.assertEqual(repo.saved[-1][1]["event"], "gbs_resubmit_after_file_fix")

    def test_po_uses_submit(self):
        box = FakeBoxme([])
        svc, _ = self.make(dict(self.DOC, order_type=None), box)
        svc.execute("GBS Purchase Order", "GBS-PO-1")
        self.assertEqual(box.actions, ["Resubmit", "Submit"])

    def test_refuses_while_sharepoint_link_remains(self):
        box = FakeBoxme([{"name": "l", "file_name": "a", "file_url": SP1, "owner": "x"}])
        svc, repo = self.make(self.DOC, box)
        with self.assertRaises(ValueError):
            svc.execute("GBS Sales Order", "GBS-SO-1")
        self.assertEqual((box.actions, repo.saved), ([], []))

    def test_refuses_when_not_rejected_or_ec_not_approved(self):
        svc, _ = self.make(self.DOC, FakeBoxme([], state="Draft"))
        with self.assertRaises(ValueError):
            svc.execute("GBS Sales Order", "GBS-SO-1")
        svc, _ = self.make(dict(self.DOC, status="Pending"), FakeBoxme([]))
        with self.assertRaises(ValueError):
            svc.execute("GBS Sales Order", "GBS-SO-1")


class _Resp:
    def __init__(self, code, body=None, content=b""):
        self.status_code, self._body, self.content, self.text = code, body or {}, content, str(body)

    def json(self):
        return self._body


class InfraTest(unittest.TestCase):
    def test_resolve_strips_fragment_first(self):
        from ecentric_workspace.gbs_attachments.infrastructure import graph
        seen = []

        class H:
            def get(self, url, **kw):
                seen.append(url)
                return _Resp(200, {"id": "i", "name": "Email confirm.pdf", "size": 5,
                                   "parentReference": {"driveId": "d"}})
        item = graph.resolve(SP1, "T", http=H())
        self.assertEqual(item["name"], "Email confirm.pdf")
        self.assertEqual(seen[0], graph.C.GRAPH + "/shares/" + graph._share_id(domain.strip_fragment(SP1)) + "/driveItem")

    def test_download_refuses_oversize_before_request(self):
        from ecentric_workspace.gbs_attachments.infrastructure import graph

        class H:
            def get(self, *a, **k):
                raise AssertionError("khong duoc goi mang")
        with self.assertRaises(graph.GraphReadError):
            graph.download({"drive_id": "d", "item_id": "i", "size": graph.C.MAX_FILE_BYTES + 1}, "T", http=H())

    def test_boxme_upload_sends_real_bytes_private(self):
        import base64
        import json
        from ecentric_workspace.gbs_attachments.infrastructure.boxme import BoxmeFiles
        sent = {}

        class H:
            def post(self, url, headers=None, data=None, timeout=None):
                sent.update(url=url, body=json.loads(data))
                return _Resp(200, {"data": {"file_url": "/private/files/a.pdf"}})
        BoxmeFiles("https://b", "k", "s", http=H()).upload("Sales Order", "SAL-1", "a.pdf", b"%PDF")
        self.assertTrue(sent["url"].endswith("/api/resource/File"))
        self.assertEqual(base64.b64decode(sent["body"]["content"]), b"%PDF")
        self.assertEqual((sent["body"]["is_private"], sent["body"]["decode"]), (1, 1))
        self.assertNotIn("file_url", sent["body"])


if __name__ == "__main__":
    unittest.main()
