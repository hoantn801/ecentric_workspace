# Copyright (c) 2026, eCentric and contributors
"""Nao cua Khay: mot cau -> MOT hanh dong, va khong bao gio doan thay nguoi dung.

    python3 ecentric_workspace/platform/ai/tests/test_khay.py

Nap MA NGUON THAT (config, dialects, gateway, khay_intent, khay) bang exec voi `frappe` +
`requests` gia; than phan hoi Gemini la hinh dang SSE that (xem test_gateway).
"""
import datetime
import json
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AI = os.path.dirname(HERE)
TODAY = datetime.date(2026, 9, 28)          # Thu Hai
TYPES = ["Annual Leave", "Compensatory Off", "Leave Without Pay", "Sick Leave"]


def sse(obj):
    cand = {"content": {"role": "model", "parts": [{"text": json.dumps(obj, ensure_ascii=False)}]},
            "finishReason": "STOP"}
    return "data: " + json.dumps({"candidates": [cand]}, ensure_ascii=False) + "\n\n"


CATALOG = [
    {"approval_code": "PAYMENT_REQUEST", "approval_title": "Payment Request", "card_status": "Active",
     "route": "/approvals/payment-request", "description": "Đề nghị thanh toán cho nhà cung cấp"},
    {"approval_code": "PURCHASE_REQUEST", "approval_title": "Purchase Request", "card_status": "Active",
     "route": "approvals/purchase-request", "description": "Đề nghị mua hàng"},
    # Form nghi cua Approval Center KHONG dung - xin nghi di Leave Application goc.
    {"approval_code": "LEAVE_REQUEST", "approval_title": "Leave", "card_status": "Active",
     "route": "/approvals/leave", "description": ""},
    # Chua mo (Coming Soon): the co trong danh sach nhung khong co route.
    {"approval_code": "OFFER_REQUEST", "approval_title": "Offer Request", "card_status": "Coming Soon",
     "route": None, "description": ""},
    # Coming Soon nhung CO route (dung nhu NEW_STAFF_PREPARATION tren site 29/09).
    {"approval_code": "NEW_STAFF_PREPARATION", "approval_title": "New Staff Preparation",
     "card_status": "Coming Soon", "route": "/approvals/new-staff-preparation", "description": ""},
    # Khong co trong registry -> may AI dien ho khong chay duoc.
    {"approval_code": "ANNUAL_BUDGET", "approval_title": "Annual Budget", "card_status": "Active",
     "route": "/approvals/annual", "description": ""},
]


def as_chat(sse_text):
    """SSE Gemini -> than THAT cua luong OpenAI ben Kie (probe 28/09)."""
    first = json.loads(sse_text.split("data: ", 1)[1].split("\n", 1)[0])
    text = first["candidates"][0]["content"]["parts"][0]["text"]
    return json.dumps({"choices": [{"finish_reason": "stop", "index": 0,
                                    "message": {"content": text, "role": "assistant"}}],
                       "object": "chat.completion"})


class Env(object):
    def __init__(self, roles=("EC Khay Pilot",), conf=None, employee=True, reply=None,
                 catalog=None):
        self.calls, self.logs = [], []
        self.reply = reply
        env = self
        fk = types.ModuleType("frappe")

        class PermissionError(Exception):
            pass
        fk.PermissionError = PermissionError
        fk.conf = dict(conf or {})
        fk.session = types.SimpleNamespace(user="nv@ecentric.vn")
        fk.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
        fk.get_roles = lambda user=None: list(roles)
        fk._ = lambda s: s
        fk.log_error = lambda **k: env.logs.append(k.get("title"))
        fk.parse_json = lambda s: json.loads(s)
        fk.cache = lambda: types.SimpleNamespace(get_value=lambda k: None,
                                                 set_value=lambda *a, **k: None,
                                                 delete_value=lambda k: None)

        class _DB(object):
            def get_single_value(self, dt, f):
                return {"ec_kie_api_key": "K", "ec_llm_model_kie": "gemini-3-8-flash",
                        "ec_llm_model_kie_fallback": "gemini-3-8-flash-openai"}.get(f, "")

            def get_value(self, dt, filters, fields=None, as_dict=False):
                if dt == "Employee":
                    return {"name": "HR-EMP-1", "employee_name": "Tran Van Hoan"} if employee else None
                return "Hoan"
        fk.db = _DB()
        fk.get_all = lambda dt, **k: [types.SimpleNamespace(name=t) for t in TYPES]
        meta = types.SimpleNamespace(get_field=lambda f: types.SimpleNamespace(label="Nhãn " + f))
        fk.get_meta = lambda dt: meta
        utils = types.ModuleType("frappe.utils")
        utils.nowdate = lambda: TODAY.isoformat()
        utils.getdate = lambda s: datetime.date.fromisoformat(s)
        pw = types.ModuleType("frappe.utils.password")
        pw.get_decrypted_password = lambda *a, **k: "K"
        utils.password = pw
        fk.utils = utils
        rq = types.ModuleType("requests")

        def post(url, json=None, timeout=None, headers=None):
            env.calls.append({"url": url, "body": json, "timeout": timeout})
            status, body = env.reply if env.reply else (200, '{"code":500,"msg":"x"}')
            if "/v1/chat/completions" in url and body.startswith("data:"):
                body = as_chat(body)      # cung noi dung, hinh dang luong OpenAI cua Kie
            return types.SimpleNamespace(status_code=status, content=body.encode("utf-8"))
        rq.post = post
        sys.modules.update({"frappe": fk, "frappe.utils": utils, "frappe.utils.password": pw,
                            "requests": rq})
        for pkg in ("ecentric_workspace", "ecentric_workspace.platform",
                    "ecentric_workspace.platform.ai", "ecentric_workspace.approval_center",
                    "ecentric_workspace.approval_center.shared"):
            sys.modules[pkg] = types.ModuleType(pkg)
        reg = types.ModuleType("ecentric_workspace.approval_center.shared.registry")
        reg.get_definition = lambda code: types.SimpleNamespace(
            business_doctype="EC " + code, editable_fields=("payee", "payment_amount"))
        reg.APPROVAL_DEFINITIONS = {c: 1 for c in (
            "PAYMENT_REQUEST", "PURCHASE_REQUEST", "LEAVE_REQUEST", "OFFER_REQUEST", "RESIGNATION",
            "NEW_STAFF_PREPARATION")}
        sys.modules["ecentric_workspace.approval_center.shared.registry"] = reg
        cat = types.ModuleType("ecentric_workspace.approval_center.shared.catalog_api")
        env.catalog = CATALOG if catalog is None else catalog
        cat.list_catalog = lambda: {"types": env.catalog}
        sys.modules["ecentric_workspace.approval_center.shared.catalog_api"] = cat
        sys.modules["ecentric_workspace.approval_center.shared"].catalog_api = cat
        self.mod = {}
        for name in ("config", "dialects", "health", "gateway", "khay_intent", "khay"):
            full = "ecentric_workspace.platform.ai." + name
            m = types.ModuleType(full)
            m.__file__ = os.path.join(AI, name + ".py")
            sys.modules[full] = m
            setattr(sys.modules["ecentric_workspace.platform.ai"], name, m)
            with open(m.__file__, encoding="utf-8") as fh:
                exec(compile(fh.read(), m.__file__, "exec"), m.__dict__)
            self.mod[name] = m
        self.k, self.b = self.mod["khay"], self.mod["khay_intent"]


B = Env().b


class Lich(unittest.TestCase):
    def test_thu_dung(self):
        cal = B.calendar(TODAY, 8)
        self.assertEqual(cal[0], "2026-09-28 (Thứ Hai) - hôm nay")
        self.assertEqual(cal[1], "2026-09-29 (Thứ Ba) - ngày mai")
        self.assertEqual(cal[4], "2026-10-02 (Thứ Sáu)")

    def test_prompt_co_lich_loai_nghi_tep(self):
        p = B.build_prompt("nghi mai", TODAY, TYPES, page="/viec-cua-toi", file_names=["hd.pdf"])
        for s in ("2026-10-02 (Thứ Sáu)", "Annual Leave, Compensatory Off", "/viec-cua-toi",
                  "VUA THA 1 TEP: hd.pdf", "nghi mai"):
            self.assertIn(s, p)


class KiemKetQua(unittest.TestCase):
    def test_nghi_mai_ca_ngay(self):
        r = B.normalize({"action": "leave", "reply": "Ok", "leave_type": "annual leave",
                         "from_date": "2026-09-29", "to_date": "2026-09-29",
                         "reason": "viec gia dinh"}, TYPES, TODAY)
        self.assertEqual(r["action"], "leave")
        self.assertEqual(r["leave"], {"leave_type": "Annual Leave", "from_date": "2026-09-29",
                                      "to_date": "2026-09-29", "half_day": 0, "half_day_date": "",
                                      "half_day_part": "", "reason": "viec gia dinh",
                                      "past": False})

    def test_loai_bia_thi_hoi_lai_khong_doan(self):
        r = B.normalize({"action": "leave", "reply": "x", "leave_type": "Phep nam",
                         "from_date": "2026-09-29"}, TYPES, TODAY)
        self.assertEqual(r["action"], "clarify")
        self.assertEqual(r["options"], TYPES[:4])
        self.assertNotIn("leave", r)

    def test_thieu_ngay_thi_hoi(self):
        r = B.normalize({"action": "leave", "reply": "x", "leave_type": "Sick Leave"}, TYPES, TODAY)
        self.assertEqual((r["action"], r["reply"]), ("clarify", "Bạn muốn nghỉ ngày nào?"))

    def test_ngay_nguoc_thi_hoi(self):
        r = B.normalize({"action": "leave", "reply": "x", "leave_type": "Sick Leave",
                         "from_date": "2026-10-02", "to_date": "2026-10-01"}, TYPES, TODAY)
        self.assertEqual(r["action"], "clarify")

    def test_nua_ngay_chi_khi_mot_ngay_va_ghi_buoi(self):
        r = B.normalize({"action": "leave", "reply": "x", "leave_type": "Annual Leave",
                         "from_date": "2026-10-02", "half_day": True,
                         "half_day_part": "afternoon", "reason": "kham rang"}, TYPES, TODAY)
        lv = r["leave"]
        self.assertEqual((lv["half_day"], lv["half_day_date"], lv["reason"]),
                         (1, "2026-10-02", "(Buổi chiều) kham rang"))
        r = B.normalize({"action": "leave", "reply": "x", "leave_type": "Annual Leave",
                         "from_date": "2026-10-01", "to_date": "2026-10-02", "half_day": True},
                        TYPES, TODAY)
        self.assertEqual(r["leave"]["half_day"], 0, "nhieu ngay thi khong co nua ngay")

    def test_ngay_qua_khu_danh_dau(self):
        r = B.normalize({"action": "leave", "reply": "x", "leave_type": "Sick Leave",
                         "from_date": "2026-09-25"}, TYPES, TODAY)
        self.assertTrue(r["leave"]["past"])

    def test_hanh_dong_la_thi_hoi_lai(self):
        r = B.normalize({"action": "delete_everything", "reply": ""}, TYPES, TODAY)
        self.assertEqual(r["action"], "clarify")
        self.assertTrue(r["reply"])

    def test_lua_chon_cat_gon(self):
        r = B.normalize({"action": "clarify", "reply": "?", "options": ["a", "a", "b", "", "c",
                                                                          "d", "e"]}, TYPES, TODAY)
        self.assertEqual(r["options"], ["a", "b", "c", "d"])

    def test_tro_chuyen_tra_loi_thang_khong_tra_cuu(self):
        r = B.normalize({"action": "answer", "reply": "Chào bạn!", "needs_data": False}, TYPES, TODAY)
        self.assertEqual((r["action"], r["needs_data"], r["reply"]), ("answer", False, "Chào bạn!"))

    def test_can_so_lieu_hoac_reply_rong_thi_tra_cuu(self):
        r = B.normalize({"action": "answer", "reply": "", "needs_data": False}, TYPES, TODAY)
        self.assertTrue(r["needs_data"], "reply rong thi khong duoc hien mot cau rong")
        r = B.normalize({"action": "answer", "reply": "x", "needs_data": True}, TYPES, TODAY)
        self.assertTrue(r["needs_data"])

    def test_ten_tro_ly_trong_loi_dan(self):
        self.assertIn("Ban la eCentric AI,", B.system("eCentric AI"))
        self.assertNotIn("{name}", B.system("eCentric AI"))

    def test_lich_su(self):
        h = B.parse_history(json.dumps([{"role": "user", "text": "hi"}, {"role": "x", "text": " "},
                                        {"role": "bot", "text": "chao"}]))
        self.assertEqual(h, [{"role": "user", "text": "hi"}, {"role": "model", "text": "chao"}])


class Endpoint(unittest.TestCase):
    def test_khong_co_role_thi_tat_va_cam(self):
        e = Env(roles=("Employee",))
        self.assertEqual(e.k.boot(), {"enabled": False})
        with self.assertRaises(Exception):
            e.k.intent(message="nghi mai")
        self.assertEqual(e.calls, [])

    def test_cong_tac_tat(self):
        e = Env(conf={"ec_khay_disabled": 1})
        self.assertFalse(e.k.boot()["enabled"])
        e = Env(conf={"ec_ai_disabled": 1})
        self.assertFalse(e.k.boot()["enabled"])

    def test_boot(self):
        e = Env(roles=("EC Khay Pilot", "EC AI Formfill Pilot"))
        b = e.k.boot()
        self.assertEqual((b["enabled"], b["name"], b["first_name"], b["can_leave"], b["can_payment"]),
                         (True, "eC Mate", "Hoan", True, True))

    def test_nghi_phep_di_qua_cong_voi_schema(self):
        e = Env(reply=(200, sse({"action": "leave", "reply": "Soạn xong", "leave_type": "Annual Leave",
                                 "from_date": "2026-09-29", "to_date": "2026-09-29"})))
        r = e.k.intent(message="cho minh nghi mai", history='[{"role":"user","text":"chao"}]',
                       page="/viec-cua-toi")
        self.assertEqual((r["action"], r["leave"]["leave_type"]), ("leave", "Annual Leave"))
        call = e.calls[0]
        body = call["body"]
        self.assertIn("/gemini-3-8-flash-openai/v1/chat/completions", call["url"],
                      "tro chuyen di luong OpenAI: Gemini goc treo 30s o 5/6 lan (do 28/09)")
        self.assertEqual(body["reasoning_effort"], "none", "tat suy nghi: 5-7s thay vi 25s")
        self.assertEqual(body["temperature"], 0)
        self.assertIn('"leave_type"', body["messages"][-1]["content"], "ep dung schema")
        self.assertIn("2026-09-29 (Thứ Ba) - ngày mai", body["messages"][-1]["content"])
        self.assertEqual(body["messages"][1]["content"], "chao", "giu lich su")
        self.assertIn("Ban la eC Mate", body["messages"][0]["content"])
        self.assertLessEqual(call["timeout"][1], 10, "hoi thoai: moi lan thu toi da 10s")
        self.assertEqual(r["model"], "gemini-3-8-flash-openai", "tra ten model de hien 'Tra loi boi'")

    def test_chao_cam_on_tra_loi_ngay_khong_goi_ai(self):
        for msg in ("chào", "Chao ban!", "hello", "cảm ơn nhé", "ok", "Thanks"):
            e = Env()
            r = e.k.intent(message=msg)
            self.assertEqual((r["action"], r["needs_data"], r["model"]), ("answer", False, ""), msg)
            self.assertTrue(r["reply"], msg)
            self.assertEqual(e.calls, [], msg)

    def test_cau_co_viec_that_van_goi_ai(self):
        for msg in ("chào, cho mình nghỉ mai", "ok tạo đề nghị thanh toán", "hi team tuần này sao"):
            self.assertIsNone(B.quick_reply(msg, "eC Mate"), msg)
        self.assertIsNone(B.quick_reply("chào", "eC Mate", has_files=True), "co tep la co viec")

    def test_khong_ho_so_nhan_vien_thi_bao(self):
        e = Env(employee=False, reply=(200, sse({"action": "leave", "reply": "x",
                "leave_type": "Annual Leave", "from_date": "2026-09-29"})))
        r = e.k.intent(message="nghi mai")
        self.assertEqual(r["action"], "notice")
        self.assertIn("hồ sơ nhân viên", r["reply"])

    def test_thanh_toan_can_quyen_ai_dien_ho(self):
        rep = (200, sse({"action": "payment_request", "reply": ""}))     # ten cu van hieu
        e = Env(reply=rep)
        self.assertEqual(e.k.intent(message="tao de nghi TT", files='["hd.pdf"]')["action"], "notice")
        e = Env(roles=("EC Khay Pilot", "EC AI Formfill Pilot"), reply=rep)
        r = e.k.intent(message="tao de nghi TT", files='["hd.pdf"]')
        self.assertEqual((r["action"], r["approval_code"], r["route"], r["approval_title"]),
                         ("approval", "PAYMENT_REQUEST", "/approvals/payment-request",
                          "Payment Request"))
        self.assertEqual(r["labels"]["payee"], "Nhãn payee")
        self.assertIn("đọc tệp", r["reply"])

    def test_moi_form_nguoi_do_tao_duoc(self):
        e = Env(roles=("EC Khay Pilot", "EC AI Formfill Pilot"),
                reply=(200, sse({"action": "approval", "approval_code": "purchase_request",
                                 "reply": ""})))
        r = e.k.intent(message="minh can mua 2 man hinh")
        self.assertEqual((r["action"], r["approval_code"], r["route"]),
                         ("approval", "PURCHASE_REQUEST", "/approvals/purchase-request"),
                         "route thieu '/' dau tren site (booking, contract) duoc sua")
        prompt = e.calls[0]["body"]["messages"][-1]["content"]
        self.assertIn("PURCHASE_REQUEST | Purchase Request | Đề nghị mua hàng", prompt)
        for an in ("LEAVE_REQUEST", "OFFER_REQUEST", "ANNUAL_BUDGET", "NEW_STAFF_PREPARATION"):
            self.assertNotIn(an, prompt, "%s khong duoc dua cho AI" % an)

    def test_form_khong_duoc_tao_thi_hoi_lai_khong_doan(self):
        for code in ("OFFER_REQUEST", "ANNUAL_BUDGET", "LEAVE_REQUEST", "BIA_RA", ""):
            e = Env(roles=("EC Khay Pilot", "EC AI Formfill Pilot"),
                    reply=(200, sse({"action": "approval", "approval_code": code, "reply": "ok"})))
            r = e.k.intent(message="tao phieu")
            self.assertEqual(r["action"], "clarify", code)
            self.assertNotIn("approval_code", r, code)
            self.assertEqual(r["options"], ["Payment Request", "Purchase Request"], code)

    def test_the_bi_an_voi_nguoi_nay_thi_khong_co_trong_danh_sach(self):
        # Visibility theo vai tro/phong ban do list_catalog quyet (chay duoi quyen nguoi goi):
        # form nguoi nay khong thay -> khong nam trong prompt, AI chon cung bi tu choi.
        e = Env(roles=("EC Khay Pilot", "EC AI Formfill Pilot"), catalog=CATALOG[:1],
                reply=(200, sse({"action": "approval", "approval_code": "PURCHASE_REQUEST",
                                 "reply": "ok"})))
        r = e.k.intent(message="mua man hinh")
        self.assertEqual(r["action"], "clarify")
        self.assertNotIn("PURCHASE_REQUEST", e.calls[0]["body"]["messages"][-1]["content"])

    def test_lop_cuoi_server_tu_choi_ma_ngoai_danh_sach(self):
        e = Env(roles=("EC Khay Pilot", "EC AI Formfill Pilot"))
        r = e.k._enrich({"action": "approval", "approval_code": "RESIGNATION", "reply": "x",
                         "options": []}, "nv@ecentric.vn", forms=[])
        self.assertEqual(r["action"], "notice")
        self.assertNotIn("route", r)

    def test_khong_co_form_nao_thi_noi_ro(self):
        e = Env(roles=("EC Khay Pilot", "EC AI Formfill Pilot"), catalog=[],
                reply=(200, sse({"action": "approval", "approval_code": "PAYMENT_REQUEST",
                                 "reply": "ok"})))
        r = e.k.intent(message="tao phieu")
        self.assertEqual(r["action"], "clarify")
        self.assertIn("chưa có loại phiếu", r["reply"])

    def test_ai_hong_thi_bao_ban_khong_nem(self):
        e = Env()
        r = e.k.intent(message="nghi mai")
        self.assertEqual((r["action"], r["reply"]), ("error", e.k.BUSY))

    def test_rong_thi_hoi_khong_goi_ai(self):
        e = Env()
        self.assertEqual(e.k.intent(message="  ")["action"], "clarify")
        self.assertEqual(e.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
