# Copyright (c) 2026, eCentric and contributors
"""Goi eVoice API (may GPU van phong) qua Cloudflare Tunnel. Chi noi nay biet duong dan / header cua eVoice.

Loi mang, may tat, tunnel 502/530, Cloudflare 524 (qua 100 s) -> EVoiceDown (thu lai sau duoc).
Loi eVoice tra ve ({"detail": ...} voi 4xx) -> EVoiceHttpError (khong thu lai, bao nguoi dung)."""
DOWN_STATUSES = {502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527, 530}
MAX_AUDIO_BYTES = 200 * 1024 * 1024
USER_AGENT = "eCentric-ERP-AiVoice/1.0"


class EVoiceDown(Exception):
    """May giong doc khong ket noi duoc / khong tra loi kip - thu lai sau."""

    def __init__(self, message="", timeout=False):
        super().__init__(message)
        self.timeout = timeout


class EVoiceHttpError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class EVoiceClient:
    def __init__(self, base_url, token, timeout=30, session=None):
        self.base = str(base_url or "").rstrip("/")
        self.token = token or ""
        self.timeout = timeout
        self._session = session

    # ------------------------------------------------------------------ tho ---
    def _s(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def _req(self, method, path, json_body=None, timeout=None, stream=False):
        import requests
        headers = {"Authorization": "Bearer %s" % self.token, "User-Agent": USER_AGENT, "Accept": "application/json"}
        try:
            r = self._s().request(method, self.base + path, json=json_body, headers=headers,
                                  timeout=timeout or self.timeout, stream=stream, allow_redirects=False)
        except requests.Timeout as e:
            raise EVoiceDown("timeout: %s" % e, timeout=True)
        except requests.RequestException as e:
            raise EVoiceDown(str(e))
        if r.status_code in DOWN_STATUSES:
            msg = "HTTP %s" % r.status_code
            r.close()
            raise EVoiceDown(msg, timeout=r.status_code == 524)
        if r.status_code >= 300:
            detail = _detail(r)
            r.close()
            raise EVoiceHttpError(r.status_code, detail)
        return r

    def _json(self, method, path, json_body=None, timeout=None):
        r = self._req(method, path, json_body=json_body, timeout=timeout)
        try:
            return r.json()
        except ValueError:
            raise EVoiceDown("tra ve khong phai JSON (HTTP %s)" % r.status_code)

    def _bytes(self, path, limit=MAX_AUDIO_BYTES, timeout=None):
        r = self._req("GET", path, timeout=timeout or max(self.timeout, 120), stream=True)
        buf, n = [], 0
        try:
            for chunk in r.iter_content(64 * 1024):
                n += len(chunk)
                if n > limit:
                    raise EVoiceHttpError(413, "File quá lớn")
                buf.append(chunk)
        except EVoiceHttpError:
            raise
        except Exception as e:  # noqa: BLE001 - dut giua chung = may / mang hong
            raise EVoiceDown("tai file dut giua chung: %s" % e)
        finally:
            r.close()
        return b"".join(buf), (r.headers.get("Content-Type") or "").split(";")[0].strip()

    # ------------------------------------------------------------------ API ---
    def health(self):
        return self._json("GET", "/health")

    def voices(self):
        return list((self._json("GET", "/v1/voices") or {}).get("voices") or [])

    def brands(self):
        return list((self._json("GET", "/v1/brands") or {}).get("brands") or [])

    def create_job(self, payload):
        return self._json("POST", "/v1/jobs", json_body=payload)

    def get_job(self, job_id):
        return self._json("GET", "/v1/jobs/%s" % _seg(job_id))

    def delete_job(self, job_id):
        return self._json("DELETE", "/v1/jobs/%s" % _seg(job_id))

    def job_audio(self, job_id):
        return self._bytes("/v1/jobs/%s/audio" % _seg(job_id))

    def voice_sample(self, voice_id):
        return self._bytes("/v1/voices/%s/sample" % _seg(voice_id), limit=30 * 1024 * 1024)

    def create_voice(self, payload, timeout):
        return self._json("POST", "/v1/voices", json_body=payload, timeout=timeout)

    def delete_voice(self, voice_id):
        return self._json("DELETE", "/v1/voices/%s" % _seg(voice_id))


def _seg(v):
    """Id tu may / tu DB: chi cho chu, so, - _ . (khong cho / ? # va doan "." ".." di vao duong dan)."""
    s = str(v or "")
    if not s or s.strip(".") == "" or not all((c.isascii() and c.isalnum()) or c in "-_." for c in s):
        raise EVoiceHttpError(400, "Mã không hợp lệ")
    return s


def _detail(r):
    try:
        d = r.json()
        if isinstance(d, dict) and d.get("detail"):
            return str(d["detail"])[:500]
    except ValueError:
        pass
    try:
        txt = (r.text or "").strip()
    except Exception:  # noqa: BLE001
        txt = ""
    if txt.startswith("<"):
        return "HTTP %s" % r.status_code
    return (txt[:300] or "HTTP %s" % r.status_code)

