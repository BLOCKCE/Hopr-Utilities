# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'Dialog1.ui'
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
from PySide6.QtWidgets import (QApplication, QDialog, QGridLayout, QLabel,
    QSizePolicy, QWidget, QPushButton)

class Ui_UpdateDialog(object):
    def setupUi(self, Dialog):
        if not Dialog.objectName():
            Dialog.setObjectName(u"UpdateDialog")
        Dialog.resize(300, 120)
        self.gridLayout = QGridLayout(Dialog)
        self.gridLayout.setObjectName(u"gridLayout")

        self.label_title = QLabel(Dialog)
        self.label_title.setObjectName(u"label_title")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Maximum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_title.sizePolicy().hasHeightForWidth())
        self.label_title.setSizePolicy(sizePolicy)
        self.label_title.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gridLayout.addWidget(self.label_title, 0, 0, 1, 2)

        self.label_body = QLabel(Dialog)
        self.label_body.setObjectName(u"label_body")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Maximum)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.label_body.sizePolicy().hasHeightForWidth())
        self.label_body.setSizePolicy(sizePolicy2)
        self.label_body.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.label_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_body.setWordWrap(True)
        self.gridLayout.addWidget(self.label_body, 1, 0, 1, 2)

        self.btn_yes = QPushButton(Dialog)
        self.btn_yes.setObjectName(u"btn_yes")
        self.gridLayout.addWidget(self.btn_yes, 2, 0, 1, 1)

        self.btn_no = QPushButton(Dialog)
        self.btn_no.setObjectName(u"btn_no")
        self.gridLayout.addWidget(self.btn_no, 2, 1, 1, 1)

        self.retranslateUi(Dialog)
        QMetaObject.connectSlotsByName(Dialog)
    # setupUi

    def retranslateUi(self, Dialog):
        Dialog.setWindowTitle(QCoreApplication.translate("UpdateDialog", u"Update Available", None))
        self.label_title.setText("")
        self.label_body.setText("")
        self.btn_yes.setText(QCoreApplication.translate("UpdateDialog", u"Yes", None))
        self.btn_no.setText(QCoreApplication.translate("UpdateDialog", u"No", None))
    # retranslateUi