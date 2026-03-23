"""Stupid stupid stipod thijngs"""

from __future__ import annotations

import sys
import io
from PySide6.QtCore import QtMsgType, qInstallMessageHandler


_installed = False
_prev_handler = None

# patters we want to silently drop
_SUPPRESSED = (
    "Slot 'Main::' not found",
)


# stderr filter
class _FilteredStderr:
    """Wraps sys.stderr and drops lines matching _SUPPRESSED."""

    def __init__(self, wrapped):
        self._wrapped = wrapped

    def __getattr__(self, name):
        return getattr(self._wrapped, name)

    def write(self, text: str) -> int:
        if text and any(pat in text for pat in _SUPPRESSED):
            return len(text)
        return self._wrapped.write(text)

    def writelines(self, lines):
        filtered = [l for l in lines if not any(
            pat in l for pat in _SUPPRESSED)]
        if filtered:
            self._wrapped.writelines(filtered)


# Qt message handler
def _handler(msg_type: QtMsgType, context, message: str) -> None:
    if message and any(pat in message for pat in _SUPPRESSED):
        return
    if _prev_handler is not None:
        _prev_handler(msg_type, context, message)


# public entry point
def install_qt_message_filter() -> None:
    """Call once at startup (idempotent)."""
    global _installed, _prev_handler
    if _installed:
        return

    # 1. Intercept Qt's own C++ message handler.
    _prev_handler = qInstallMessageHandler(_handler)

    # 2. Intercept PySide6's Python-level stderr prints.
    if not isinstance(sys.stderr, _FilteredStderr):
        sys.stderr = _FilteredStderr(sys.stderr)

    _installed = True
