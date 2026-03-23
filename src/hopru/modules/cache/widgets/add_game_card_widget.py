from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QSizePolicy, QGridLayout, QFrame
)
from PySide6.QtGui import QFont, Qt


class AddGameCardWidget(QWidget):
    """A card-shaped button that sits last in the presets grid.

    Matches the 175×225 footprint of GameCardWidget so it blends into the
    grid, but renders as a dashed-border "+" placeholder instead of showing
    game data.
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AddGameCardWidget")

        # Match GameCardWidget size constraints exactly
        self.setMinimumSize(175, 225)
        self.setMaximumSize(16777215, 225)
        sp = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setSizePolicy(sp)

        outer = QGridLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setVerticalSpacing(0)

        self.frame = QFrame(self)
        self.frame.setObjectName("frame")
        self.frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame.setFrameShadow(QFrame.Shadow.Raised)
        self.frame.setStyleSheet(
            "QWidget#AddGameCardWidget QFrame#frame {"
            "  border: 2px dashed #666;"
            "  border-radius: 4px;"
            "}"
            "QWidget#AddGameCardWidget QFrame#frame:hover {"
            "  background-color: rgba(255, 255, 255, 0.15);"
            "}"
        )

        inner = QVBoxLayout(self.frame)
        inner.setSpacing(4)
        inner.setContentsMargins(6, 6, 6, 6)

        inner.addStretch(1)

        plus_lbl = QLabel("+", self.frame)
        f = QFont()
        f.setPointSize(32)
        f.setBold(True)
        plus_lbl.setFont(f)
        plus_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus_lbl.setStyleSheet("background: transparent;")
        inner.addWidget(plus_lbl)

        text_lbl = QLabel("Add custom\ngame dump", self.frame)
        text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_lbl.setStyleSheet("background: transparent;")
        inner.addWidget(text_lbl)

        inner.addStretch(1)

        outer.addWidget(self.frame, 0, 0, 1, 1)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.pos())
            if child and child.inherits("QPushButton"):
                return super().mousePressEvent(event)
            self.clicked.emit()
        return super().mousePressEvent(event)
