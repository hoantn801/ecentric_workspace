# Copyright (c) 2026, eCentric and contributors
"""Luat thuan cho Ban quyen AI Live (khong goi DB / Frappe): lam sach du lieu app gui, nhan dien may nhan ban,
gop dau van tay may, trang thai khoa bi mat, dung cay phan phoi. Luat DUYET nam o ec_license_issuer.decide (khong sua)."""
import json
import re

from ecentric_workspace.ai_tools.features.ai_live import license_constants as L

_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩]")


def clean_text(v, n):
    """Chuoi ngan, bo ky tu dieu khien / dao chieu; khong phai chuoi -> ''. KHONG escape (escape luc hien)."""
    if v is None or isinstance(v, (dict, list, bool)):
        return ""
    return _CTRL.sub("", str(v)).strip()[:n]


def _hex(v):
    v = v if isinstance(v, str) else ""
    v = v.strip().lower()
    if v and not L.HEX_RE.match(v):
        raise L.BadPayload("fp")
    return v


def clean_fp(fp):
    if not isinstance(fp, dict):
        raise L.BadPayload("fp")
    macs = fp.get("mac_h") or []
    if not isinstance(macs, list) or len(macs) > L.MAX_MACS:
        raise L.BadPayload("mac_h")
    out = {"guid_h": _hex(fp.get("guid_h")), "disk_h": _hex(fp.get("disk_h")), "mac_h": []}
    for m in macs:
        m = _hex(m)
        if m and m not in out["mac_h"]:
            out["mac_h"].append(m)
    if not out["guid_h"]:
        raise L.BadPayload("guid_h")      # khong co MachineGuid -> khong nhan ra may duoc (same_machine luon False)
    return out


def clean_hw(product, hw):
    hw = (hw if isinstance(hw, str) else "").replace("-", "").strip()
    if product == "evoice":
        hw = hw.lower()
        ok = L.HW24_RE.match(hw)
    else:
        hw = hw.upper()
        ok = L.HW32_RE.match(hw)
    if not ok:
        raise L.BadPayload("hw")
    return hw


def clean_dist(d):
    if not isinstance(d, dict):
        return {}
    return {k: clean_text(d.get(k), L.MAX_DIST_TEXT) for k in L.DIST_KEYS if isinstance(d.get(k), (str, int, float))}


def clean_payload(raw):
    """Body JSON app gui -> dict da kiem kieu. Sai bat ky -> BadPayload."""
    if not isinstance(raw, dict):
        raise L.BadPayload("body")
    product = raw.get("product")
    if product not in L.PRODUCTS:
        raise L.BadPayload("product")
    out = {"product": product, "hw": clean_hw(product, raw.get("hw")), "fp": clean_fp(raw.get("fp")),
           "dist": clean_dist(raw.get("dist"))}
    for k, n in L.TEXT_LIMITS.items():
        out[k] = clean_text(raw.get(k), n)
    return out


def merge_fp(old, new):
    """Dau van tay moi nhat: giu guid_h, ghi lai disk_h neu doi, them card mang moi (toi da MAX_MACS, moi nhat truoc)."""
    old, new = old or {}, new or {}
    macs = list(new.get("mac_h") or [])
    for m in old.get("mac_h") or []:
        if m not in macs:
            macs.append(m)
    return {"guid_h": new.get("guid_h") or old.get("guid_h") or "", "disk_h": new.get("disk_h") or old.get("disk_h") or "",
            "mac_h": macs[:L.MAX_MACS]}


def is_clone(machine, fp, host):
    """Cung guid_h + disk_h nhung card mang khong giao nhau VA ten may khac = may cai tu cung ban Ghost / sao o.
    Chi canh bao (Hoan 17/11), khong tu khoa."""
    mfp = (machine or {}).get("fp") or {}
    if not mfp.get("guid_h") or mfp.get("guid_h") != fp.get("guid_h"):
        return False
    if not mfp.get("disk_h") or mfp.get("disk_h") != fp.get("disk_h"):
        return False
    a, b = set(mfp.get("mac_h") or []), set(fp.get("mac_h") or [])
    if not a or not b or a & b:
        return False
    mh, nh = str((machine or {}).get("host") or "").lower(), str(host or "").lower()
    return bool(mh and nh and mh != nh)


def office_ips(text):
    return tuple(x.strip() for x in re.split(r"[,\s;]+", str(text or "")) if x.strip())


def secret_state(product, raw):
    """'ok' | 'missing' | 'bad' - chi bao co / thieu, khong bao gio tra noi dung khoa."""
    if not raw:
        return "missing"
    try:
        d = json.loads(raw)
    except (TypeError, ValueError):
        return "bad"
    if not isinstance(d, dict) or any(not d.get(k) for k in L.SECRET_KEYS[product]):
        return "bad"
    return "ok"


def parse_secret(raw):
    d = json.loads(raw or "")
    if not isinstance(d, dict):
        raise ValueError("secret")
    return d


def build_tree(dists, machines):
    """Goc -> Goi -> may dau tien -> cac ban chep (theo source_dist + parent_machine).
    dists: [{name, label, kind, first_machine}] ; machines: [{name, source_dist, parent_machine, ...}].
    May khong co goi -> nhanh "Khong co ma goi". May co parent khong cung goi van treo duoi parent (de thay ai chep ai)."""
    by_name = {m["name"]: dict(m, children=[]) for m in machines}
    roots = {d["name"]: dict(d, machines=[]) for d in dists}
    nodist = {"name": "", "label": L.Msg.NO_DIST, "kind": "", "machines": []}
    for m in by_name.values():
        parent = by_name.get(m.get("parent_machine") or "")
        if parent is not None and parent is not m and not _is_descendant(by_name, parent["name"], m["name"]):
            parent["children"].append(m)
            continue
        (roots.get(m.get("source_dist") or "") or nodist)["machines"].append(m)
    out = list(roots.values())
    if nodist["machines"]:
        out.append(nodist)
    return out


def _is_descendant(by_name, start, target):
    """parent_machine tao vong (du lieu loi) -> khong treo, tranh lap vo han."""
    seen, cur = set(), start
    while cur and cur not in seen:
        if cur == target:
            return True
        seen.add(cur)
        cur = (by_name.get(cur) or {}).get("parent_machine") or ""
    return False


def md_escape(text):
    """Chu tu may gui len -> an toan trong the Teams (Adaptive Card doc markdown; MessageCard doc HTML)."""
    t = clean_text(text, 200)
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_{}\[\]()#+!|~])", r"\\\1", t)
