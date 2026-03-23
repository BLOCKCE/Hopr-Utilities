"""Cache finder filter helpers."""

from PySide6.QtCore import Qt

def _parse_size_to_bytes(self, s: str):
    s = s.strip().lower().replace(" ", "")
    mult = 1
    if s.endswith("kb"):
        mult = 1024
        s = s[:-2]
    elif s.endswith("mb"):
        mult = 1024**2
        s = s[:-2]
    elif s.endswith("gb"):
        mult = 1024**3
        s = s[:-2]
    elif s.endswith("b"):
        mult = 1
        s = s[:-1]
    try:
        return float(s) * mult
    except Exception:
        return None

def _build_finder_conditions(self, raw: str):
    if not raw:
        return "", []

    tokens = raw.strip().split()
    conditions = []
    leftovers = []

    for t in tokens:
        tl = t.lower().replace(" ", "")

        # size comparisons
        if tl.startswith("size>") or tl.startswith("size<"):
            op = ">" if ">" in tl else "<"
            val = tl.split(op, 1)[1]
            b = self._parse_size_to_bytes(val)
            if b is None:
                leftovers.append(t)
                continue

            def cond(row, parent, m, op=op, b=b):
                idx = m.index(row, 3, parent)  # Size col
                size_bytes = m.data(idx, Qt.UserRole)
                if size_bytes is None:
                    return False
                return (size_bytes > b) if op == ">" else (size_bytes < b)

            conditions.append(cond)
            continue

        leftovers.append(t)

    return " ".join(leftovers), conditions

def _apply_finder_filters(self):
    # asset type filter from menu
    if self.all_action.isChecked():
        allowed = None
    else:
        allowed = {tid for tid, act in self.type_actions.items()
                   if act.isChecked()}
        if not allowed:
            allowed = set()

    self.proxy.set_type_filter(allowed)

    # search + size conditions
    text = self.finder_search.text() if getattr(self, "finder_search", None) else ""
    leftover, conditions = self._build_finder_conditions(text)

    cols = None
    if hasattr(self, "search_col_actions"):
        selected = [c for c, a in self.search_col_actions.items()
                    if a.isChecked()]
        cols = selected or None

    self.proxy.set_search(leftover, cols=cols, conditions=conditions)

