from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCalendarWidget,
    QLabel, QListWidget, QListWidgetItem, QPushButton,
    QDialog, QDialogButtonBox, QDateTimeEdit, QComboBox,
    QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QDate, QDateTime, pyqtSignal
from PyQt6.QtGui import QTextCharFormat, QColor, QBrush

import db.database as db
import scheduler.task_scheduler as task_scheduler

STATUS_COLORS = {
    "pending": "#1a73e8",
    "uploading": "#f9a825",
    "done": "#2e7d32",
    "failed": "#c62828",
}

STATUS_LABELS = {
    "pending": "Ожидает",
    "uploading": "Загружается",
    "done": "Опубликовано",
    "failed": "Ошибка",
}


class RescheduleDialog(QDialog):
    def __init__(self, post_id: int, current_dt: str, parent=None):
        super().__init__(parent)
        self.post_id = post_id
        self.setWindowTitle("Перенести публикацию")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Новая дата и время:"))

        dt = QDateTime.fromString(current_dt[:16], "yyyy-MM-ddTHH:mm")
        if not dt.isValid():
            dt = QDateTime.currentDateTime()
        self.dt_edit = QDateTimeEdit(dt)
        self.dt_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.dt_edit.setCalendarPopup(True)
        self.dt_edit.setMinimumDateTime(QDateTime.currentDateTime())
        layout.addWidget(self.dt_edit)

        layout.addWidget(QLabel("Аккаунт:"))
        self.account_combo = QComboBox()
        for acc in db.get_accounts():
            self.account_combo.addItem(acc["account_name"], acc["id"])
        layout.addWidget(self.account_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_result(self):
        return self.dt_edit.dateTime().toPyDateTime()


class CalendarWidget(QWidget):
    post_scheduled = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title_lbl = QLabel("Календарь публикаций")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #f0f0f0;")
        layout.addWidget(title_lbl)

        content = QHBoxLayout()

        left = QVBoxLayout()
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(False)
        self.calendar.setMinimumWidth(380)
        self.calendar.clicked.connect(self._on_date_clicked)
        left.addWidget(self.calendar)

        legend = QHBoxLayout()
        for status, color in STATUS_COLORS.items():
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 16px;")
            legend.addWidget(dot)
            legend.addWidget(QLabel(STATUS_LABELS[status]))
            legend.addSpacing(10)
        legend.addStretch()
        left.addLayout(legend)

        content.addLayout(left)

        right = QVBoxLayout()
        day_lbl = QLabel("События на выбранный день")
        day_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #505050; letter-spacing: 0.3px;")
        right.addWidget(day_lbl)
        self.posts_list = QListWidget()
        self.posts_list.setMinimumWidth(340)
        right.addWidget(self.posts_list)

        post_btns = QHBoxLayout()
        reschedule_btn = QPushButton("Перенести")
        reschedule_btn.clicked.connect(self._reschedule_post)
        delete_btn = QPushButton("Удалить")
        delete_btn.setStyleSheet("color: #ef5350; border-color: #2c2c2c;")
        delete_btn.clicked.connect(self._delete_post)
        post_btns.addWidget(reschedule_btn)
        post_btns.addStretch()
        post_btns.addWidget(delete_btn)
        right.addLayout(post_btns)

        content.addLayout(right)
        layout.addLayout(content)

    def refresh(self):
        self._mark_calendar_dates()
        self._load_day_posts(self.calendar.selectedDate())

    def _mark_calendar_dates(self):
        default_fmt = QTextCharFormat()
        self.calendar.setDateTextFormat(QDate(), default_fmt)

        dates = db.get_dates_with_posts()
        for d_str in dates:
            try:
                qdate = QDate.fromString(d_str, "yyyy-MM-dd")
                fmt = QTextCharFormat()
                fmt.setBackground(QBrush(QColor("#2a1515")))
                fmt.setForeground(QBrush(QColor("#ef5350")))
                fmt.setFontWeight(700)
                self.calendar.setDateTextFormat(qdate, fmt)
            except Exception:
                pass

    def _on_date_clicked(self, qdate: QDate):
        self._load_day_posts(qdate)

    def _load_day_posts(self, qdate: QDate):
        self.posts_list.clear()
        date_str = qdate.toString("yyyy-MM-dd")
        posts = db.get_posts_for_date(date_str)
        for post in posts:
            status = post["status"]
            color = STATUS_COLORS.get(status, "#666")
            label = STATUS_LABELS.get(status, status)
            time_str = post["scheduled_at"][11:16]
            text = f"[{time_str}] {post['title']}  —  {post['account_name']}  ({label})"
            item = QListWidgetItem(text)
            item.setForeground(QColor(color))
            item.setData(Qt.ItemDataRole.UserRole, dict(post))
            self.posts_list.addItem(item)

    def _selected_post(self):
        item = self.posts_list.currentItem()
        if not item:
            QMessageBox.information(self, "Выбор", "Выберите событие из списка.")
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _reschedule_post(self):
        post = self._selected_post()
        if not post:
            return
        if post["status"] in ("done", "uploading"):
            QMessageBox.warning(self, "Нельзя перенести",
                                "Нельзя перенести уже опубликованный или загружаемый пост.")
            return
        dlg = RescheduleDialog(post["id"], post["scheduled_at"], parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_dt = dlg.get_result()
            db.reschedule_post(post["id"], new_dt.isoformat())
            task_scheduler.cancel_post(post["id"])
            task_scheduler.schedule_post(post["id"], new_dt)
            self.refresh()
            self.post_scheduled.emit()

    def _delete_post(self):
        post = self._selected_post()
        if not post:
            return
        reply = QMessageBox.question(
            self, "Удалить пост",
            "Удалить запланированную публикацию?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            task_scheduler.cancel_post(post["id"])
            db.delete_scheduled_post(post["id"])
            self.refresh()
