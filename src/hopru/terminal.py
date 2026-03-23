# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'terminal.ui'
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
from PySide6.QtWidgets import (QApplication, QLabel, QPlainTextEdit, QSizePolicy,
    QVBoxLayout, QWidget)

class Ui_Form(object):
    def setupUi(self, Form):
        if not Form.objectName():
            Form.setObjectName(u"Form")
        Form.resize(400, 300)
        self.verticalLayout = QVBoxLayout(Form)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(Form)
        self.label.setObjectName(u"label")

        self.verticalLayout.addWidget(self.label)

        self.label_2 = QLabel(Form)
        self.label_2.setObjectName(u"label_2")

        self.verticalLayout.addWidget(self.label_2)

        self.OutputTerminal = QPlainTextEdit(Form)
        self.OutputTerminal.setObjectName(u"OutputTerminal")
        font = QFont()
        font.setFamilies([u"Terminal"])
        font.setBold(True)
        self.OutputTerminal.setFont(font)
        self.OutputTerminal.setUndoRedoEnabled(False)
        self.OutputTerminal.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.OutputTerminal.setReadOnly(True)

        self.verticalLayout.addWidget(self.OutputTerminal)


        self.retranslateUi(Form)

        QMetaObject.connectSlotsByName(Form)
    # setupUi

    def retranslateUi(self, Form):
        Form.setWindowTitle(QCoreApplication.translate("Form", u"Form", None))
        self.label.setText(QCoreApplication.translate("Form", u"Hi I print things :P", None))
        self.label_2.setText(QCoreApplication.translate("Form", u"Time wasted with this program open:", None))
    # retranslateUi

