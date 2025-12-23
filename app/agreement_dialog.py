"""
agreement_dialog.py
初回起動時の規約同意ダイアログ
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
)
from PySide6.QtCore import Qt

from app.settings import set_agreed


class AgreementDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("利用規約の確認")
        self.setFixedSize(480, 360)

        layout = QVBoxLayout(self)

        text = QLabel(
            "このツールは Booth 購入済み商品の\n"
            "管理・整理を補助するための非公式ツールです。\n\n"
            "・商品データの自動ダウンロードは行いません\n"
            "・操作は必ずユーザー自身の判断で行ってください\n"
            "・Booth の利用規約を遵守してください\n\n"
            "同意されない場合、このアプリは使用できません。"
        )
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignLeft)
        layout.addWidget(text)

        btn_layout = QHBoxLayout()

        decline = QPushButton("同意しない")
        decline.clicked.connect(self.reject)

        agree = QPushButton("同意する")
        agree.clicked.connect(self.on_agree)

        btn_layout.addStretch()
        btn_layout.addWidget(decline)
        btn_layout.addWidget(agree)

        layout.addLayout(btn_layout)

    def on_agree(self):
        set_agreed()
        self.accept()
