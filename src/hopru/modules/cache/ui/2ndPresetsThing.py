# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file '2ndPresetsThing.ui'
##
## Created by: Qt User Interface Compiler version 6.10.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QAbstractScrollArea, QApplication, QFrame, QHeaderView,
    QPushButton, QSizePolicy, QSplitter, QTreeView,
    QVBoxLayout, QWidget)

class Ui_Form(object):
    def setupUi(self, Form):
        if not Form.objectName():
            Form.setObjectName(u"Form")
        Form.resize(400, 300)
        self.verticalLayout = QVBoxLayout(Form)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Form)
        self.splitter.setObjectName(u"splitter")
        self.splitter.setOrientation(Qt.Orientation.Horizontal)
        self.treeView = QTreeView(self.splitter)
        self.treeView.setObjectName(u"treeView")
        self.treeView.setStyleSheet(u"QTreeView {\n"
"    background-color: #2d2d2d;\n"
"    color: #e0e0e0;\n"
"    border: 1px solid #3c3c3c;\n"
"    outline: none;\n"
"    border-radius: 0px;\n"
"    show-decoration-selected: 1;\n"
"}\n"
"\n"
"QTreeView::item {\n"
"    padding: 2px 8px;\n"
"    border: none;\n"
"    border-radius: 0px;\n"
"    border-right: 1px solid #3c3c3c;\n"
"}\n"
"\n"
"QTreeView::item:hover {\n"
"    background-color: #3d3d3d;\n"
"    border-radius: 0px;\n"
"}\n"
"\n"
"QTreeView::item:selected {\n"
"    background-color: #404040;\n"
"    color: #e0e0e0;\n"
"    border-radius: 0px;\n"
"}\n"
"\n"
"QTreeView::item:selected:active {\n"
"    background-color: #404040;\n"
"    border-radius: 0px;\n"
"}\n"
"\n"
"QTreeView::item:selected:!active {\n"
"    background-color: #404040;\n"
"    border-radius: 0px;\n"
"}\n"
"\n"
"QHeaderView::section {\n"
"    background-color: #1e1e1e;\n"
"    color: #e0e0e0;\n"
"    padding: 3px 8px;\n"
"    border: none;\n"
"    border-right: 1px solid #3c3c3c;\n"
"    border-bottom: 1px solid #3c3c3"
                        "c;\n"
"    font-weight: bold;\n"
"    text-align: left;\n"
"    border-radius: 0px;\n"
"}\n"
"\n"
"QHeaderView::section:hover {\n"
"    background-color: #252525;\n"
"}")
        self.treeView.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.treeView.setAutoScroll(False)
        self.splitter.addWidget(self.treeView)
        self.PreviewFrame2 = QFrame(self.splitter)
        self.PreviewFrame2.setObjectName(u"PreviewFrame2")
        self.PreviewFrame2.setMinimumSize(QSize(125, 0))
        palette = QPalette()
        brush = QBrush(QColor(45, 45, 45, 0))
        brush.setStyle(Qt.BrushStyle.SolidPattern)
        palette.setBrush(QPalette.ColorGroup.Active, QPalette.ColorRole.Base, brush)
        palette.setBrush(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Base, brush)
        self.PreviewFrame2.setPalette(palette)
        self.PreviewFrame2.setFrameShape(QFrame.Shape.StyledPanel)
        self.splitter.addWidget(self.PreviewFrame2)

        self.verticalLayout.addWidget(self.splitter)

        self.pushButton = QPushButton(Form)
        self.pushButton.setObjectName(u"pushButton")

        self.verticalLayout.addWidget(self.pushButton)


        self.retranslateUi(Form)

        QMetaObject.connectSlotsByName(Form)
    # setupUi

    def retranslateUi(self, Form):
        Form.setWindowTitle(QCoreApplication.translate("Form", u"Form", None))
        self.pushButton.setText(QCoreApplication.translate("Form", u"Import Selected", None))
    # retranslateUi

