"""Helpers for safely invoking functions on the main Qt thread."""

from PySide6.QtCore import QObject, Qt, Signal


class _MainThreadInvoker(QObject):
    call = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.call.connect(self._run, Qt.QueuedConnection)

    def _run(self, fn):
        try:
            fn()
        except Exception as e:
            import traceback
            traceback.print_exc()
