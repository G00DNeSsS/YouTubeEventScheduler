import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt

import db.database as db
from auth.youtube_auth import authorize_youtube, credentials_to_dict


class AccountManagerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title_lbl = QLabel("YouTube аккаунты")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #f0f0f0;")
        layout.addWidget(title_lbl)

        info = QLabel(
            "Для подключения аккаунта необходим файл <b>client_secrets.json</b> "
            "от Google Cloud Console (YouTube Data API v3, тип Desktop App).<br>"
            "Положите файл в папку <code>config/</code> рядом с программой."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "color: #707070; padding: 10px 14px; background: #1a1a1a; "
            "border: 1px solid #202020; border-radius: 8px; line-height: 1.5;"
        )
        layout.addWidget(info)

        self.accounts_list = QListWidget()
        layout.addWidget(self.accounts_list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Подключить аккаунт")
        add_btn.setStyleSheet(
            "background: #e53935; color: white; border: none; "
            "padding: 8px 18px; font-size: 13px; border-radius: 7px; font-weight: 600;"
        )
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._connect_account)

        delete_btn = QPushButton("Удалить аккаунт")
        delete_btn.setStyleSheet("color: #ef5350; border-color: #2c2c2c; padding: 8px 12px;")
        delete_btn.clicked.connect(self._delete_account)

        btn_row.addWidget(add_btn)
        btn_row.addStretch()
        btn_row.addWidget(delete_btn)
        layout.addLayout(btn_row)

        layout.addStretch()

    def refresh(self):
        self.accounts_list.clear()
        for acc in db.get_accounts():
            text = f"{acc['account_name']}"
            if acc["channel_id"]:
                text += f"  (ID: {acc['channel_id']})"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, acc["id"])
            self.accounts_list.addItem(item)

        if self.accounts_list.count() == 0:
            placeholder = QListWidgetItem("Нет подключённых аккаунтов")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.accounts_list.addItem(placeholder)

    def _connect_account(self):
        try:
            creds, channel_name, channel_id = authorize_youtube()
            creds_json = json.dumps(credentials_to_dict(creds))
            db.add_account(channel_name, channel_id, creds_json)
            self.refresh()
            QMessageBox.information(
                self, "Аккаунт подключён",
                f"Канал «{channel_name}» успешно подключён."
            )
        except FileNotFoundError as e:
            QMessageBox.critical(self, "Файл не найден", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка авторизации", str(e))

    def _delete_account(self):
        item = self.accounts_list.currentItem()
        if not item or not item.data(Qt.ItemDataRole.UserRole):
            QMessageBox.information(self, "Выбор", "Выберите аккаунт для удаления.")
            return
        acc_id = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Удалить аккаунт",
            "Удалить аккаунт? Все запланированные посты для этого аккаунта тоже будут удалены.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            db.delete_account(acc_id)
            self.refresh()
