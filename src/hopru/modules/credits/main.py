from PySide6.QtCore import QObject, QEvent, QUrl
from PySide6.QtGui import QPixmap, QCursor, QDesktopServices
from PySide6.QtWidgets import QLabel, QFrame
from PySide6.QtCore import Qt
import resources_rc


class Main(QObject):
    def __init__(self, tab_widget):
        super().__init__(tab_widget)
        self.tab_widget = tab_widget

        d = tab_widget.findChild(QLabel, "DiscordIcon")
        g = tab_widget.findChild(QLabel, "GitHubIcon")

        if d:
            d.setPixmap(QPixmap(":/icons/DiscordIcon.png"))
            d.setScaledContents(True)
        if g:
            g.setPixmap(QPixmap(":/icons/GitHubIcon.png"))
            g.setScaledContents(True)

        discord_frame = tab_widget.findChild(QFrame, "frame")
        github_frame = tab_widget.findChild(QFrame, "frame_2")

        if discord_frame:
            discord_frame.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            discord_frame.installEventFilter(self)
        if github_frame:
            github_frame.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            github_frame.installEventFilter(self)

        self._discord_frame = discord_frame
        self._github_frame = github_frame

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonRelease:
            if obj is self._discord_frame:
                QDesktopServices.openUrl(QUrl("https://discord.gg/J8QxfkUjdU"))
                return True
            if obj is self._github_frame:
                QDesktopServices.openUrl(QUrl("https://github.com/BLOCKCE/Hopr-Utilities"))
                return True
        return super().eventFilter(obj, event)
