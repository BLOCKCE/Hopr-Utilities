"""Custom item delegates used by the cache module."""

from PySide6.QtWidgets import QStyledItemDelegate, QStyle


class NoFocusDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.state &= ~QStyle.State_HasFocus
        super().paint(painter, option, index)


class HoverDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hover_row = -1

    def paint(self, painter, option, index):
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QStyle

        option.state &= ~QStyle.State_HasFocus

        if index.row() == self.hover_row and not (option.state & QStyle.State_Selected):
            painter.save()
            painter.fillRect(option.rect, QColor("#3d3d3d"))
            painter.restore()

        super().paint(painter, option, index)
