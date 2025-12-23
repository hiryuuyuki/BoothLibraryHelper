"""
about_dialog.py
About（このアプリについて）ダイアログ
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt

from app.version import DISPLAY_VERSION
from app.constants import NOTICE_TEXT


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("About BoothLibraryHelper")
        self.setFixedSize(420, 320)

        layout = QVBoxLayout(self)

        title = QLabel(DISPLAY_VERSION)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel(
            "BoothLibraryHelper は Booth 購入済み商品の\n"
            "管理・整理を補助するための非公式ツールです。\n\n"
            "※ 商品データの自動ダウンロードは行いません。\n"
            "※ 操作は必ずユーザー自身の判断で行ってください。\n"
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        notice = QLabel(NOTICE_TEXT)
        notice.setWordWrap(True)
        notice.setStyleSheet("color: #aa0000;")
        layout.addWidget(notice)

        footer = QLabel(
            "This tool is NOT affiliated with Booth.\n"
            "Use at your own responsibility."
        )
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("font-size: 10px; color: gray;")
        layout.addWidget(footer)

        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
