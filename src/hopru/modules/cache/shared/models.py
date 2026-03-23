"""Qt proxy models used by the cache module."""

from PySide6.QtCore import Qt, QSortFilterProxyModel


class SortProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_text = ""
        self._search_cols = None
        self._allowed_type_ids = None  # None = all
        # list of callables(row,parent,model)->bool
        self._conditions = []

        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setDynamicSortFilter(False)

    def set_type_filter(self, type_ids_or_none):
        self._allowed_type_ids = type_ids_or_none
        self.invalidateFilter()

    def set_search(self, text: str, cols=None, conditions=None):
        self._search_text = (text or "").strip().lower()
        self._search_cols = cols
        self._conditions = conditions or []
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        m = self.sourceModel()

        # asset type menu filter (Finder Type column = 2)
        if self._allowed_type_ids is not None:
            idx_type = m.index(source_row, 3, source_parent)
            type_id = m.data(idx_type, Qt.UserRole)
            if type_id not in self._allowed_type_ids:
                return False

        # structured conditions
        for cond in self._conditions:
            if not cond(source_row, source_parent, m):
                return False

        # normal substring search
        if not self._search_text:
            return True

        cols = self._search_cols
        if cols is None:
            cols = range(m.columnCount())

        needle = self._search_text
        for c in cols:
            idx = m.index(source_row, c, source_parent)
            val = m.data(idx)
            if val is None:
                continue
            if needle in str(val).lower():
                return True

        return False

    def lessThan(self, left, right):
        col = left.column()
        m = self.sourceModel()

        if col == 0:
            l_check = m.data(left, Qt.CheckStateRole)
            r_check = m.data(right, Qt.CheckStateRole)
            if l_check is not None and r_check is not None:
                return int(l_check) < int(r_check)
            return str(m.data(left) or "") < str(m.data(right) or "")

        if col in (2, 3):
            return str(m.data(left)) < str(m.data(right))

        l = m.data(left, Qt.UserRole)
        r = m.data(right, Qt.UserRole)

        if l is None or r is None:
            return str(m.data(left)) < str(m.data(right))

        return l < r
