"""Qt menu helpers."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu


class StayOpenMenu(QMenu):
    def mouseReleaseEvent(self, event):
        act = self.actionAt(event.pos())

        if act is not None and act.isEnabled() and act.isCheckable() and event.button() == Qt.LeftButton:
            act.setChecked(not act.isChecked())
            event.accept()
            return

        super().mouseReleaseEvent(event)
