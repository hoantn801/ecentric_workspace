"""PM hotfix 23 (27/11/2026) - project colour keys, ONE place.

The backend only hands out a KEY; the frontend owns the hex values (PMR.projectColor(key)).

Resolution order (color_for):
  1. Project.ec_color (Custom Field, Select) when it holds a valid key - set by the project's
     manager / a PM leader via projects.set_color.
  2. The project's department: DEPT_COLORS (matched on the department name without the
     company suffix, case-insensitive, so "Service - EC" == "Service").
  3. Department not mapped yet -> a stable hash of its normalised name picks a key (the same
     department always gets the same colour, no config needed for a new department).
  4. No department -> NO_DEPT_COLOR.

Add a department: one line in DEPT_COLORS. Add a palette colour: PALETTE_KEYS here + the
Custom Field options (fixtures/custom_field.json Project-ec_color) + PMR.projectColor.
"""

import hashlib

import frappe

PALETTE_KEYS = ("navy", "violet", "sky", "teal", "green", "amber", "rose", "slate")
COLOR_FIELD = "ec_color"
NO_DEPT_COLOR = "slate"

# Department name (without " - <company abbr>") -> palette key. PO 27/11/2026.
DEPT_COLORS = {
    "E-commerce Operation": "navy",
    "Service": "violet",
    "Production": "rose",
    "Operation & Data & System": "teal",
}


def _norm_dept(dept):
    """'E-commerce Operation - EC' -> 'e-commerce operation'. Only the LAST ' - ' segment is
    treated as the company abbreviation (Frappe appends it on Department.name)."""
    s = (dept or "").strip()
    if " - " in s:
        s = s.rsplit(" - ", 1)[0]
    return s.strip().lower()


_DEPT_NORM = {_norm_dept(k): v for k, v in DEPT_COLORS.items()}


def valid_key(key):
    return (key or "") in PALETTE_KEYS


def hashed_key(text):
    """Stable (process-independent, unlike hash()) palette key for any text."""
    digest = hashlib.md5((text or "").encode("utf-8")).hexdigest()
    return PALETTE_KEYS[int(digest[:8], 16) % len(PALETTE_KEYS)]


def dept_color(dept):
    n = _norm_dept(dept)
    if not n:
        return NO_DEPT_COLOR
    return _DEPT_NORM.get(n) or hashed_key(n)


def color_for(project_row):
    """project_row: dict-like with ec_color (optional) and ec_department."""
    row = project_row or {}
    own = row.get(COLOR_FIELD)
    if valid_key(own):
        return own
    return dept_color(row.get("ec_department"))


def has_color_field():
    """False until the Project.ec_color Custom Field is installed (fixture sync). Callers then
    fall back to the department colour and set_color refuses with a clear message."""
    try:
        return bool(frappe.get_meta("Project").has_field(COLOR_FIELD))
    except Exception:
        return False


def colors_for_projects(names):
    """{project name: key} for a batch of projects (one query). Unknown names are skipped."""
    names = sorted({n for n in (names or []) if n})
    if not names:
        return {}
    fields = ["name", "ec_department"] + ([COLOR_FIELD] if has_color_field() else [])
    return {p["name"]: color_for(p)
            for p in frappe.get_all("Project", filters={"name": ["in", names]}, fields=fields,
                                    limit_page_length=0)}
