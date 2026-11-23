# Copyright (c) 2026, eCentric and contributors
"""Khao sat ca nhan - luat THUAN: chuan hoa nguoi xem, khoa chong giao trung, ai xem duoc gi.

QUYEN XEM KET QUA (Hoan chot 22-23/11/2026):
  * role nam trong `viewer_roles` cua lan giao (vd "HR", "EC CnB")      -> xem DU;
  * token "LM" + nguoi xem la quan ly truc tiep HIEN TAI cua nguoi tra loi -> xem phan
    "LM xem duoc" (cau trong `lm_hidden_items` cua mau bi an);
  * System Manager                                                    -> xem du;
  * con lai (ke ca chinh nguoi tra loi qua duong nay)                  -> khong.
Khao sat nghi viec (Agent C goi voi nguoi_xem_role="HR") -> LM KHONG xem duoc.
"""
import hashlib
import json

from ecentric_workspace.surveys import constants as C

FULL = "full"
LM = "lm"


def chuan_hoa_nguoi_xem(nguoi_xem_role):
    """str ("HR, EC CnB, LM" / xuong dong) hoac list -> tuple role, giu thu tu, bo trung/rong."""
    if nguoi_xem_role is None:
        items = []
    elif isinstance(nguoi_xem_role, str):
        items = nguoi_xem_role.replace("\n", ",").split(",")
    else:
        items = list(nguoi_xem_role)
    out = []
    for r in items:
        r = str(r or "").strip()
        if r and r not in out:
            out.append(r)
    return tuple(out)


def doc_danh_sach(text):
    """Small Text (moi dong mot gia tri) / JSON list -> list."""
    if not text:
        return []
    if isinstance(text, (list, tuple)):
        return [str(x) for x in text if str(x).strip()]
    s = str(text).strip()
    if s.startswith("["):
        try:
            return [str(x) for x in json.loads(s) if str(x).strip()]
        except ValueError:
            return []
    return [x.strip() for x in s.replace(",", "\n").split("\n") if x.strip()]


def khoa_giao(user, ma_mau, ngu_canh):
    """Khoa chong giao trung. Ngu canh co "khoa" thi dung no; khong thi bam JSON da sap xep -
    goi lai voi cung (user, ma_mau, ngu_canh) KHONG BAO GIO tao lan giao thu hai."""
    ngu_canh = ngu_canh or {}
    if isinstance(ngu_canh, dict) and ngu_canh.get("khoa"):
        tail = str(ngu_canh["khoa"])
    else:
        tail = hashlib.sha1(json.dumps(ngu_canh, sort_keys=True, ensure_ascii=False,
                                       default=str).encode("utf-8")).hexdigest()[:16]
    return ("%s|%s|%s" % (user, ma_mau, tail))[:140]


def quyen_xem(viewer, viewer_roles, assignment_roles, respondent, respondent_manager, is_admin):
    """FULL / LM / None - xem docstring module."""
    if not viewer or viewer == "Guest":
        return None
    if is_admin:
        return FULL
    roles = set(chuan_hoa_nguoi_xem(assignment_roles))
    if set(viewer_roles or ()) & (roles - {C.VIEWER_LM}):
        return FULL
    if C.VIEWER_LM in roles and respondent_manager and viewer == respondent_manager \
            and viewer != respondent:
        return LM
    return None


def an_voi_lm(questions, answers, hidden_ids):
    """(cau hoi con lai, cau tra loi con lai, so cau bi an) cho nguoi xem kieu LM."""
    hidden = set(hidden_ids or ())
    qs = [q for q in questions if q.get("id") not in hidden]
    ans = {k: v for k, v in (answers or {}).items() if k not in hidden}
    return qs, ans, len([q for q in questions if q.get("id") in hidden])
