"""Guard (16/10/2026 hotfix): inserting a helper between `@frappe.whitelist()` and its function
silently moved the decorator -> schedule.viewable_users lost its whitelist (Lich lam viec could not
list colleagues) and the private helper became a public endpoint. AST check over pm/api/*.py."""
import ast, os, unittest

API = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "api"))
MUST = {"schedule.py": {"week", "viewable_users", "today", "rsvp", "reschedule", "place", "move", "remove", "confirm"},
        "comments.py": {"add", "upload", "list", "pin"},
        "pm_inbox.py": {"received", "given", "coordinate", "request_deadline", "answer_deadline",
                        "withdraw_deadline", "nudge", "close_parent"}}


def whitelisted(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = set()
    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            for d in n.decorator_list:
                f = d.func if isinstance(d, ast.Call) else d
                if isinstance(f, ast.Attribute) and f.attr == "whitelist":
                    out.add(n.name)
    return out


class T(unittest.TestCase):
    def test_no_private_function_is_whitelisted(self):
        bad = []
        for fn in sorted(os.listdir(API)):
            if fn.endswith(".py"):
                bad += ["%s:%s" % (fn, n) for n in whitelisted(os.path.join(API, fn)) if n.startswith("_")]
        self.assertEqual(bad, [])

    def test_required_endpoints_whitelisted(self):
        for fn, names in MUST.items():
            missing = names - whitelisted(os.path.join(API, fn))
            self.assertEqual(missing, set(), fn)


if __name__ == "__main__":
    unittest.main()
