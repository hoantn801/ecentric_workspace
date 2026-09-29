# Copyright (c) 2026, eCentric and contributors
"""Suc khoe tung model - "status 24h" cua RIENG minh (Hoan yeu cau 28/09).

Kie co trang theo doi ti le thanh cong (bieu do 24h tren kie.ai/<model>), nhung endpoint
`api.kie.ai/api/v1/monitor/success-rate` doi token DANG NHAP WEB, khong nhan khoa API
(probe 28/09: 401 ca khi co khoa). Nen minh tu dem:

  * moi lan cong AI goi model -> ghi (thoi diem, ok, ms);
  * cron 10 phut ping moi model trong chuoi bang mot cau cuc ngan -> dem ca luc vang nguoi;
  * ti le thanh cong trong CUA_SO gan nhat < NGUONG (30%) -> cong AI BO QUA model do,
    chuyen sang model ke. Du lieu it hon MIN_MAU lan thi chua ket luan (coi nhu song).

Cua so 60 phut chu khong phai 24h: Kie sap theo dot vai chuc phut (28/09), dem 24h thi
mot dot sap sang som keo ti le ca ngay xuong va model song lai van bi bo qua.
"""
import time

import frappe

KEY = "ec_ai_health::%s"
WINDOW_SECONDS = 3600
MAX_SAMPLES = 30
MIN_SAMPLES = 4
THRESHOLD = 0.30
PING_TIMEOUT = 30


def trim(samples, now, window=WINDOW_SECONDS, cap=MAX_SAMPLES):
    """PURE. Bo mau cu hon cua so, giu toi da `cap` mau moi nhat."""
    keep = [s for s in (samples or []) if isinstance(s, (list, tuple)) and len(s) >= 2
            and now - float(s[0]) <= window]
    return keep[-cap:]


def summarize(samples, min_samples=MIN_SAMPLES):
    """PURE. -> (ti_le hoac None khi chua du mau, so_mau, ms_trung_vi_cua_lan_ok)."""
    n = len(samples or [])
    if n < min_samples:
        rate = None
    else:
        rate = sum(1 for s in samples if s[1]) / float(n)
    oks = sorted(int(s[2]) for s in (samples or []) if s[1] and len(s) > 2)
    med = oks[len(oks) // 2] if oks else 0
    return rate, n, med


def is_unhealthy_rate(rate, threshold=THRESHOLD):
    """PURE. Chua du mau (None) thi KHONG bi coi la hong."""
    return rate is not None and rate < threshold


def _get(model):
    try:
        return frappe.cache().get_value(KEY % model) or []
    except Exception:
        return []


def record(model, ok, ms=0, now=None):
    """Ghi mot mau. Khong bao gio nem - suc khoe la thu phu, khong duoc lam hong lan goi."""
    if not model:
        return
    now = float(now or time.time())
    try:
        samples = trim(_get(model), now)
        samples.append([now, 1 if ok else 0, int(ms or 0)])
        frappe.cache().set_value(KEY % model, samples[-MAX_SAMPLES:],
                                 expires_in_sec=WINDOW_SECONDS * 2)
    except Exception:
        pass


def stats(model, now=None):
    return summarize(trim(_get(model), float(now or time.time())))


def unhealthy(model):
    return is_unhealthy_rate(stats(model)[0])


def ping_models():
    """Cron 10 phut: goi moi model trong chuoi mot cau ngan, song song, ghi suc khoe.

    Chi doc/ghi cache. Tat cung cong AI (`ec_ai_disabled`) hoac thieu khoa thi khong lam gi.
    Chi phi: ~60 token vao x 5 model x 144 lan/ngay - vai xu mot ngay.
    """
    import concurrent.futures as cf
    from ecentric_workspace.platform.ai import config, dialects, gateway
    if config.disabled():
        return {}
    key = config.api_key()
    if not key:
        return {}
    models = []
    for m in config.chain(True):
        if dialects.dialect_of(m) and m not in models:
            models.append(m)
    request = {"prompt": "Tra loi dung mot chu: ok", "system": None, "schema": None,
               "files": [], "history": None, "json_mode": False,
               "opts": {"temperature": 0, "max_tokens": 16, "effort": "none"}}
    out = {}
    with cf.ThreadPoolExecutor(max_workers=max(1, len(models))) as ex:
        futs = {ex.submit(gateway.timed_try, m, key, request, PING_TIMEOUT): m for m in models}
        for f in cf.as_completed(futs):
            r = f.result()
            out[r["model"]] = r
    for m, r in out.items():            # ghi cache o luong chinh, khong o luong phu
        record(m, not r["error"], r["ms"])
    return {m: ("ok %dms" % r["ms"]) if not r["error"] else r["error"][:120]
            for m, r in out.items()}
