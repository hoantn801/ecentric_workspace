# Copyright (c) 2026, eCentric and contributors
"""Describe a provider payload WITHOUT reproducing it.

Written to end a specific guessing loop. `POST /api/Workflow/transition` is rejected with a
bare 400 and the suspicion is that `instanceId` must be a WORKFLOW/TASK id while we send the
DOCUMENT id - eContract's own task screen is `view-tasks.html?id=...`, which is not the
document id. Trying candidate values against a NON-IDEMPOTENT write would be reckless, so
instead we read what the provider actually carries.

The whole point is that a diagnostic must never become a data dump. So:
  * `shape_of` returns key names and value TYPES - never a value.
  * `identifiers_of` returns values ONLY for identifier-looking keys holding a GUID-ish
    token. That answers "is instanceId the same thing as the document id?" while amounts,
    names, comments, filenames and timestamps stay out of the response entirely.

No frappe import here on purpose: pure functions, directly testable.
"""
import re

# camelCase is eContract's convention ("workflowInstanceId", "fileId"), so this must NOT
# demand a boundary before "Id" - the first version did, and missed the very field we were
# looking for.
ID_KEY = re.compile(r"(id|ids|guid|uuid)$", re.I)
GUIDISH = re.compile(r"^[0-9a-fA-F-]{8,64}$")

MAX_DEPTH = 4
MAX_IDENTIFIERS = 60


def shape_of(value, depth=0):
    """Key names and value types only. Depth-capped so a deep payload cannot turn this into
    an unbounded response."""
    if depth > MAX_DEPTH:
        return "..."
    if isinstance(value, dict):
        return {k: shape_of(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [shape_of(value[0], depth + 1)] if value else []
    return type(value).__name__


def identifiers_of(value, prefix="", out=None, depth=0):
    """Values of identifier-looking keys, and only when GUID-ish."""
    if out is None:
        out = {}
    if depth > MAX_DEPTH or len(out) >= MAX_IDENTIFIERS:
        return out
    if isinstance(value, dict):
        for k, v in value.items():
            # Tran phai kiem TRONG vong lap: kiem mot lan luc vao ham thi mot dict phang co
            # 200 khoa van di qua het - tuc muc tran khong chan duoc gi.
            if len(out) >= MAX_IDENTIFIERS:
                return out
            path = (prefix + "." + k) if prefix else k
            if isinstance(v, (dict, list)):
                identifiers_of(v, path, out, depth + 1)
            elif ID_KEY.search(k) and isinstance(v, str) and GUIDISH.match(v):
                out[path] = v
    elif isinstance(value, list) and value:
        # MOI phan tu, khong chi phan tu dau.
        #
        # Ban cu chi lay `value[0]`, nen `signers[0].id` la tat ca nhung gi ham nay ke ra
        # tren mot tai lieu co NAM nguoi ky. Dung cai can nhat - bon dinh danh con lai - bi
        # cat mat, va cong cu chan doan tro thanh vo dung dung luc can no nhat: 02/09 mot chan
        # ky ket voi `expected_signer_absent:<id>/of5`, cau hoi duy nhat la "vay nam nguoi do
        # la ai", va endpoint nay tra ve mot nguoi.
        #
        # Cung lop bay da ghi trong so: mot endpoint chan doan RUT GON khien thu can tim
        # "luon khong thay", roi nguoi ta di doan thay vi di doc.
        #
        # Tran MAX_IDENTIFIERS o dau vong lap van giu nguyen, nen mot mang dai khong the lam
        # phinh ket qua; chi la gio no dung tran that thay vi dung so 1.
        for i, item in enumerate(value):
            if len(out) >= MAX_IDENTIFIERS:
                break
            identifiers_of(item, "%s[%d]" % (prefix, i), out, depth + 1)
    return out
