# Copyright (c) 2026, eCentric and contributors
"""Anh nho cua tung live (OBS / dien thoai): file private ghi de tai cho, khong tao ban ghi File.
Chi doc qua API co kiem quyen (monitor_thumb), khong co duong dan /private/files cong khai cho anh nay."""
import os
import re

from ecentric_workspace.ai_tools.features.ai_live import constants as C

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


class ThumbRepository:
    def _dir(self):
        import frappe
        d = frappe.get_site_path("private", "files", C.THUMB_DIR)
        os.makedirs(d, exist_ok=True)
        return d

    def _path(self, key, kind, ext):
        return os.path.join(self._dir(), "%s_%s.%s" % (_SAFE.sub("_", key), kind, ext))

    def save(self, key, kind, data, ext):
        """Ghi de nguyen tu (file tam roi doi ten). Xoa ban khac duoi (jpg/png) cua cung o."""
        path = self._path(key, kind, ext)
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
        other = self._path(key, kind, "png" if ext == "jpg" else "jpg")
        if os.path.exists(other):
            os.remove(other)

    def read(self, key, kind):
        """(bytes, mime) hoac None."""
        for ext, mime in (("jpg", "image/jpeg"), ("png", "image/png")):
            path = self._path(key, kind, ext)
            if os.path.exists(path):
                with open(path, "rb") as fh:
                    return fh.read(), mime
        return None
