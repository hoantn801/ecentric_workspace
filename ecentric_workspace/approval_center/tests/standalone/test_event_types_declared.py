# Copyright (c) 2026, eCentric and contributors
"""Mọi event_type mà mã nguồn phát ra phải nằm trong danh sách hợp lệ của doctype.

Sự cố 27/08: thêm hai loại sự kiện `HandoverTargeted` / `HandoverPoolFallback` vào code
nhưng quên khai báo trong Select của `EC Digital Signature Event.event_type`. Frappe từ chối
ghi, ngoại lệ lan ra và GIẾT CẢ JOB KÝ — dù phần logic chọn người kế tiếp đã chạy đúng.

Kiểu lỗi này không test đơn vị nào bắt được (stub nào cũng cho ghi), nên chặn bằng cách đối
chiếu trực tiếp mã nguồn với schema.

  python -m unittest ecentric_workspace.approval_center.tests.standalone.test_event_types_declared
"""
import json
import os
import re
import unittest

_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")
_DOCTYPE = os.path.join(_APP, "ecentric_workspace", "approval_center", "doctype",
                        "ec_digital_signature_event", "ec_digital_signature_event.json")


def _declared():
    with open(_DOCTYPE, encoding="utf-8") as fh:
        doc = json.load(fh)
    for field in doc["fields"]:
        if field.get("fieldname") == "event_type":
            return set(field["options"].split("\n"))
    raise AssertionError("khong tim thay field event_type")


def _emitted():
    """Mọi chuỗi truyền vào event_type=... hoặc emit("...") trong package esign."""
    found = set()
    for root, dirs, files in os.walk(_ESIGN):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests")]
        for name in files:
            if not name.endswith(".py"):
                continue
            with open(os.path.join(root, name), encoding="utf-8") as fh:
                src = fh.read()
            found.update(re.findall(r'event_type\s*=\s*"([A-Za-z]+)"', src))
            found.update(re.findall(r'events\.emit\(\s*"([A-Za-z]+)"', src))
            # dang positional: _emit(dsr, user, "BindingValidated")
            found.update(re.findall(r'_emit\([^)]*?"([A-Z][A-Za-z]+)"', src))
    return found


class TestEventTypesDeclared(unittest.TestCase):
    def test_every_emitted_event_type_is_declared(self):
        declared, emitted = _declared(), _emitted()
        missing = sorted(emitted - declared)
        self.assertEqual(missing, [],
                         "event_type phat ra nhung CHUA khai bao trong doctype: %s" % missing)

    def test_the_two_handover_events_are_declared(self):
        declared = _declared()
        for name in ("HandoverTargeted", "HandoverPoolFallback"):
            self.assertIn(name, declared, name)

    def test_scan_actually_finds_events(self):
        """Nếu regex hỏng thì tập rỗng sẽ làm test trên luôn xanh — chốt chặn."""
        emitted = _emitted()
        self.assertGreater(len(emitted), 10, "quet event_type khong ra gi -> regex hong")
        self.assertIn("BindingValidated", emitted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
