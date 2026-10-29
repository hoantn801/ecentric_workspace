# Copyright (c) 2026, eCentric and contributors
"""Thao tac File ben boxme (team.boxme.asia) bang khoa API trong GBS Settings."""

import base64
import json

import requests

from ecentric_workspace.gbs_attachments import constants as C


class BoxmeFileError(Exception):
    """Boxme tu choi thao tac file (message khong chua khoa)."""


class BoxmeFiles:
    def __init__(self, base, key, secret, http=requests):
        self.base = base.rstrip("/")
        self._auth = {"Authorization": "token " + key + ":" + secret, "Accept": "application/json"}
        self.http = http

    @classmethod
    def from_settings(cls):
        from ecentric_workspace.gbs_comment_proxy import _get_gbs_credentials
        base, key, secret = _get_gbs_credentials()
        return cls(base, key, secret)

    def _ok(self, r, what):
        if r.status_code >= 400:
            raise BoxmeFileError(what + ": HTTP " + str(r.status_code) + " " + (r.text or "")[:200])
        return r

    def api_user(self):
        r = self._ok(self.http.get(self.base + "/api/method/frappe.auth.get_logged_user",
                                   headers=self._auth, timeout=(C.CONNECT_TIMEOUT, 30)), "whoami")
        return (r.json() or {}).get("message") or ""

    def list_files(self, doctype, docname):
        params = {
            "fields": json.dumps(["name", "file_name", "file_url", "owner"]),
            "filters": json.dumps([["attached_to_doctype", "=", doctype],
                                   ["attached_to_name", "=", docname]]),
            "limit_page_length": 500,
        }
        r = self._ok(self.http.get(self.base + "/api/resource/File", headers=self._auth,
                                   params=params, timeout=(C.CONNECT_TIMEOUT, 60)), "list")
        return (r.json() or {}).get("data") or []

    def upload(self, doctype, docname, filename, data):
        """POST /api/resource/File voi noi dung base64 (`decode: 1`).

        Cung endpoint ma gbs_add_attachment (v5) va Step 2 cu da dung thanh cong tren
        phieu boxme dang trong workflow; chi khac la gui bytes that thay vi file_url.
        is_private=1: nguoi boxme co quyen doc phieu van mo duoc, nguoi ngoai thi khong.
        """
        payload = {
            "file_name": filename,
            "content": base64.b64encode(data).decode("ascii"),
            "decode": 1,
            "attached_to_doctype": doctype,
            "attached_to_name": docname,
            "is_private": 1,
        }
        headers = dict(self._auth, **{"Content-Type": "application/json"})
        r = self._ok(self.http.post(self.base + "/api/resource/File", headers=headers,
                                    data=json.dumps(payload), timeout=(C.CONNECT_TIMEOUT, C.READ_TIMEOUT)),
                     "upload " + filename)
        url = ((r.json() or {}).get("data") or {}).get("file_url") or ""
        if not url:
            raise BoxmeFileError("upload " + filename + ": boxme khong tra file_url")
        return url

    def workflow_state(self, doctype, docname):
        r = self._ok(self.http.get(self.base + "/api/resource/" + requests.utils.quote(doctype) + "/" + requests.utils.quote(docname, safe=""),
                                   headers=self._auth, timeout=(C.CONNECT_TIMEOUT, 30)), "state " + docname)
        return ((r.json() or {}).get("data") or {}).get("workflow_state") or ""

    def apply_workflow(self, doctype, docname, action):
        """frappe.model.workflow.apply_workflow ben boxme; tra workflow_state moi."""
        r = self._ok(self.http.post(self.base + "/api/method/frappe.model.workflow.apply_workflow",
                                    headers=self._auth, timeout=(C.CONNECT_TIMEOUT, 60),
                                    data={"doc": json.dumps({"doctype": doctype, "name": docname}), "action": action}),
                     action + " " + docname)
        return ((r.json() or {}).get("message") or {}).get("workflow_state") or ""

    def delete(self, file_id):
        r = self.http.delete(self.base + "/api/resource/File/" + requests.utils.quote(file_id, safe=""),
                             headers=self._auth, timeout=(C.CONNECT_TIMEOUT, 60))
        if r.status_code == 404:
            return
        self._ok(r, "delete " + file_id)
