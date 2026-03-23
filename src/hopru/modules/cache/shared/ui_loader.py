"""UI loading helpers."""

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader


def load_ui(path, parent=None):
    loader = QUiLoader()
    f = QFile(path)
    f.open(QFile.ReadOnly)
    ui = loader.load(f, parent)
    f.close()
    return ui
