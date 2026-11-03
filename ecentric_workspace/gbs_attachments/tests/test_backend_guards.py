# Copyright (c) 2026, eCentric and contributors
"""Kiem quyen / dau vao cua cac endpoint GBS chay ngoai sandbox - KHONG can bench.

    python -m unittest ecentric_workspace.gbs_attachments.tests.test_backend_guards

QA 03/11/2026 (t1_backend). Khoa 4 dieu:
  1. enqueue_push goi tu Server Script sync (session nguoi duyet) KHONG bi chan vi nguoi
     duyet thieu DocPerm; goi thang tu trinh duyet van phai co quyen doc nhu cu.
  2. proxy_boxme_file khong cho "../" (ke ca dang ma hoa) thoat khoi /private/files/.
  3. fetch_boxme_docinfo chi doc 2 doctype GBS, phieu phai ton tai o EC; chua sang boxme
     thi khong goi mang.
  4. upload_image_to_boxme chi nhan anh raster, chi gan vao Sales/Purchase Order.
"""
import importlib
import sys
import types
import unittest

_SAVED = {}
_NAMES = ("frappe", "requests", "ecentric_workspace.gbs_comment_proxy",
          "ecentric_workspace.gbs_attachments.controllers.api")


class _Throw(Exception):
    pass


def _fake_frappe(state):
    f = types.ModuleType("frappe")
    f.ValidationError = type("ValidationError", (_Throw,), {})
    f.PermissionError = type("PermissionError", (_Throw,), {})
    f.DoesNotExistError = type("DoesNotExistError", (f.ValidationError,), {})

    def throw(msg, exc=None):
        raise (exc or f.ValidationError)(msg)
    f.throw = throw
    f.whitelist = lambda *a, **k: (lambda fn: fn)
    f.flags = types.SimpleNamespace(in_safe_exec=0)
    f.session = types.SimpleNamespace(user="nv@ecentric.vn")
    f.has_permission = lambda dt, ptype="read", doc=None, **k: state["perm"]
    f.only_for = lambda roles: None
    f.enqueue = lambda method, **kw: state["enqueued"].append(kw)
    f.db = types.SimpleNamespace(exists=lambda dt, name=None: (dt, name) in state["docs"])

    class _Doc(dict):
        def get(self, k, d=None):
            return dict.get(self, k, d)
    f.get_doc = lambda dt, name=None: _Doc(state["docs"].get((dt, name)) or {})

    class _Cache:
        def get_value(self, k):
            return state["cache"].get(k)

        def set_value(self, k, v, expires_in_sec=None):
            state["cache"][k] = v

        def delete_value(self, k):
            state["cache"].pop(k, None)
    f.cache = lambda: _Cache()
    f.local = types.SimpleNamespace(response=types.SimpleNamespace())
    return f


class _Resp:
    def __init__(self, body=None, content=b"", headers=None):
        self._body, self.content, self.headers, self.status_code = body or {}, content, headers or {}, 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def _fake_requests(state):
    r = types.ModuleType("requests")
    r.HTTPError = type("HTTPError", (Exception,), {"response": None})
    r.Timeout = type("Timeout", (Exception,), {})

    def get(url, **kw):
        state["http"].append(("GET", url, kw.get("params")))
        return _Resp({"docinfo": {"comments": [{"name": "c1"}]}}, content=b"PNG", headers={"Content-Type": "image/png"})

    def post(url, **kw):
        state["http"].append(("POST", url, kw.get("data")))
        return _Resp({"message": {"file_url": "/private/files/p.png", "file_name": "p.png"}})
    r.get, r.post = get, post
    return r


def setUpModule():
    for n in _NAMES:
        _SAVED[n] = sys.modules.pop(n, None)


def tearDownModule():
    for n in _NAMES:
        sys.modules.pop(n, None)
        if _SAVED.get(n) is not None:
            sys.modules[n] = _SAVED[n]


class _Base(unittest.TestCase):
    def setUp(self):
        self.state = {"perm": False, "enqueued": [], "http": [], "cache": {},
                      "docs": {("GBS Sales Order", "GBS-SO-1"): {"gbs_doc_name": "SAL-ORD-9"},
                               ("GBS Purchase Order", "GBS-PO-2"): {"gbs_doc_name": ""}}}
        for n in _NAMES:
            sys.modules.pop(n, None)
        sys.modules["frappe"] = self.f = _fake_frappe(self.state)
        sys.modules["requests"] = _fake_requests(self.state)
        # import_module (khong dung "from pkg import mod"): attribute cu tren package co the
        # con tro toi module da nap voi frappe gia cua test truoc.
        self.proxy = importlib.import_module("ecentric_workspace.gbs_comment_proxy")
        self.proxy._get_gbs_credentials = lambda: ("https://boxme.test", "k", "s")


class EnqueuePushGuard(_Base):
    def api(self):
        return importlib.import_module("ecentric_workspace.gbs_attachments.controllers.api")

    def test_server_script_caller_without_docperm_still_enqueues(self):
        self.f.flags.in_safe_exec = 1
        self.api().enqueue_push("GBS Sales Order", "GBS-SO-1", reason="first_sync")
        self.assertEqual(len(self.state["enqueued"]), 1)
        self.assertEqual(self.state["enqueued"][0]["name"], "GBS-SO-1")

    def test_server_script_caller_needs_existing_doc(self):
        self.f.flags.in_safe_exec = 1
        with self.assertRaises(self.f.DoesNotExistError):
            self.api().enqueue_push("GBS Sales Order", "GBS-SO-404")
        self.assertEqual(self.state["enqueued"], [])

    def test_browser_caller_still_needs_read_permission(self):
        with self.assertRaises(self.f.PermissionError):
            self.api().enqueue_push("GBS Sales Order", "GBS-SO-1")
        self.state["perm"] = True
        self.api().enqueue_push("GBS Sales Order", "GBS-SO-1")
        self.assertEqual(len(self.state["enqueued"]), 1)

    def test_other_doctype_refused_even_from_server_script(self):
        self.f.flags.in_safe_exec = 1
        with self.assertRaises(self.f.ValidationError):
            self.api().enqueue_push("User", "Administrator")


class ProxyPath(_Base):
    def test_safe_paths(self):
        ok = ["/private/files/a.png", "/private/files/a b.png?fid=abc", "/private/files/%C3%A1nh.png",
              "/private/files/..a.png"]
        for p in ok:
            self.assertEqual(self.proxy._safe_private_path(p), p, p)

    def test_traversal_refused(self):
        bad = ["/private/files/../../api/method/frappe.auth.get_logged_user",
               "/private/files/%2e%2e/%2e%2e/api/resource/Customer",
               "/private/files/%252e%252e/%252e%252e/api/resource/Customer",
               "/private/files/..%2f..%2fapi/resource/User",
               "/private/files/..\\..\\api", "/private/files//etc/passwd",
               "/private/files/a\r\nX: y", "/files/a.png", "", None]
        for p in bad:
            self.assertIsNone(self.proxy._safe_private_path(p), p)

    def test_proxy_never_calls_boxme_for_traversal(self):
        with self.assertRaises(_Throw):
            self.proxy.proxy_boxme_file("/private/files/../../api/method/frappe.auth.get_logged_user")
        self.assertEqual(self.state["http"], [])

    def test_proxy_normal_image(self):
        self.proxy.proxy_boxme_file("/private/files/a.png?fid=1")
        self.assertEqual(self.state["http"][0][1], "https://boxme.test/private/files/a.png?fid=1")
        self.assertEqual(self.f.local.response.type, "binary")


class FetchDocinfo(_Base):
    def test_only_gbs_doctypes(self):
        for dt in ("User", "Sales Order", "Customer"):
            with self.assertRaises(_Throw):
                self.proxy.fetch_boxme_docinfo(dt, "X")
        self.assertEqual(self.state["http"], [])

    def test_unknown_local_doc_does_not_fall_back_to_given_name(self):
        with self.assertRaises(self.f.DoesNotExistError):
            self.proxy.fetch_boxme_docinfo("GBS Sales Order", "SAL-ORD-2026-00001")
        self.assertEqual(self.state["http"], [])

    def test_unsynced_doc_returns_empty_without_network(self):
        r = self.proxy.fetch_boxme_docinfo("GBS Purchase Order", "GBS-PO-2")
        self.assertEqual(r["docinfo"], {"comments": [], "workflow_logs": [], "info_logs": []})
        self.assertEqual((r["success"], r["boxme_dtype"]), (True, "Purchase Order"))
        self.assertEqual(self.state["http"], [])

    def test_synced_doc_reads_its_boxme_counterpart(self):
        r = self.proxy.fetch_boxme_docinfo("GBS Sales Order", "GBS-SO-1")
        self.assertEqual(self.state["http"][0][2], {"doctype": "Sales Order", "name": "SAL-ORD-9"})
        self.assertEqual(r["boxme_name"], "SAL-ORD-9")
        self.assertEqual(r["docinfo"]["comments"], [{"name": "c1"}])


class UploadImage(_Base):
    PNG = "data:image/png;base64,iVBORw0KGgo="

    def test_png_ok_and_no_doctype(self):
        r = self.proxy.upload_image_to_boxme(self.PNG, "image.png")
        self.assertTrue(r["success"])
        self.assertNotIn("doctype", self.state["http"][0][2])

    def test_svg_and_html_refused(self):
        for data, fname in (("data:image/svg+xml;base64,PHN2Zz4=", "x.svg"),
                            ("data:text/html;base64,PGI+", "x.html"),
                            ("PGI+", "x.html")):
            with self.assertRaises(_Throw):
                self.proxy.upload_image_to_boxme(data, fname)
        self.assertEqual(self.state["http"], [])

    def test_wrong_extension_renamed_to_real_type(self):
        self.proxy.upload_image_to_boxme(self.PNG, "evil.svg")
        self.assertEqual(self.state["http"], [("POST", "https://boxme.test/api/method/upload_file",
                                               {"is_private": "1", "folder": "Home", "optimize": "0"})])

    def test_only_sales_purchase_order_targets(self):
        with self.assertRaises(_Throw):
            self.proxy.upload_image_to_boxme(self.PNG, "a.png", doctype="Customer", docname="C1")
        self.proxy.upload_image_to_boxme(self.PNG, "a.png", doctype="Sales Order", docname="SAL-1")
        self.assertEqual(self.state["http"][0][2]["doctype"], "Sales Order")


if __name__ == "__main__":
    unittest.main()
