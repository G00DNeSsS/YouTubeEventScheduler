from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QProgressBar, QHeaderView,
    QMessageBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor

import db.database as db
import scheduler.task_scheduler as task_scheduler
from api.youtube_uploader import upload_video

STATUS_COLORS = {
    "pending": "#1a73e8",
    "uploading": "#f9a825",
    "done": "#2e7d32",
    "failed": "#c62828",
}

STATUS_LABELS = {
    "pending": "Ожидает",
    "uploading": "Загружается...",
    "done": "Опубликовано",
    "failed": "Ошибка",
}


class UploadThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, post_id: int):
        super().__init__()
        self.post_id = post_id

    def run(self):
        try:
            db.update_post_status(self.post_id, "uploading")
            url = upload_video(self.post_id, progress_callback=lambda p: self.progress.emit(p))
            self.finished.emit(url)
        except Exception as e:
            db.update_post_status(self.post_id, "failed", error_message=str(e))
            self.error.emit(str(e))


class UploadQueueWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._threads = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QHBoxLayout()
        header.addWidget(QLabel("<h2>Очередь загрузок</h2>"))
        header.addStretch()
        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Видео", "Аккаунт", "Дата публикации", "Статус", "Ссылка", "Прогресс"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        upload_now_btn = QPushButton("Загрузить сейчас")
        upload_now_btn.setStyleSheet("background: #1a73e8; color: white; padding: 6px 14px;")
        upload_now_btn.clicked.connect(self._upload_now)

        retry_btn = QPushButton("Повторить")
        retry_btn.clicked.connect(self._retry_post)

        delete_btn = QPushButton("Удалить из очереди")
        delete_btn.setStyleSheet("color: #c62828;")
        delete_btn.clicked.connect(self._delete_post)

        btn_row.addWidget(upload_now_btn)
        btn_row.addWidget(retry_btn)
        btn_row.addStretch()
        btn_row.addWidget(delete_btn)
        layout.addLayout(btn_row)

    def refresh(self):
        posts = db.get_scheduled_posts()
        self.table.setRowCount(len(posts))

        for row, post in enumerate(posts):
            status = post["status"]
            color = STATUS_COLORS.get(status, "#666")
            label = STATUS_LABELS.get(status, status)

            dt_str = post["scheduled_at"][:16].replace("T", " ")

            self.table.setItem(row, 0, QTableWidgetItem(post["title"]))
            self.table.setItem(row, 1, QTableWidgetItem(post["account_name"]))
            self.table.setItem(row, 2, QTableWidgetItem(dt_str))

            status_item = QTableWidgetItem(label)
            status_item.setForeground(QColor(color))
            self.table.setItem(row, 3, status_item)

            url = post["post_url"] or ""
            self.table.setItem(row, 4, QTableWidgetItem(url))

            # Progress bar
            if status == "uploading" and post["id"] in self._threads:
                bar = QProgressBar()
                bar.setRange(0, 100)
                self.table.setCellWidget(row, 5, bar)
            else:
                pct = 100 if status == "done" else 0
                bar = QProgressBar()
                bar.setRange(0, 100)
                bar.setValue(pct)
                self.table.setCellWidget(row, 5, bar)

            for col in range(5):
                item = self.table.item(row, col)
                if item:
                    item.setData(Qt.ItemDataRole.UserRole, post["id"])

        self.table.resizeRowsToContents()

    def _selected_post_id(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Выбор", "Выберите строку из таблицы.")
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _upload_now(self):
        post_id = self._selected_post_id()
        if post_id is None:
            return
        posts = db.get_scheduled_posts()
        post = next((p for p in posts if p["id"] == post_id), None)
        if post and post["status"] in ("done", "uploading"):
            QMessageBox.warning(self, "Нельзя", "Пост уже загружается или опубликован.")
            return
        self._start_upload(post_id)

    def _retry_post(self):
        post_id = self._selected_post_id()
        if post_id is None:
            return
        db.update_post_status(post_id, "pending")
        self._start_upload(post_id)

    def _start_upload(self, post_id: int):
        thread = UploadThread(post_id)
        self._threads[post_id] = thread

        row = self._find_row(post_id)

        def on_progress(pct):
            if row >= 0:
                bar = self.table.cellWidget(row, 5)
                if isinstance(bar, QProgressBar):
                    bar.setValue(pct)

        def on_done(url):
            self._threads.pop(post_id, None)
            self.refresh()

        def on_error(err):
            self._threads.pop(post_id, None)
            self.refresh()
            QMessageBox.critical(self, "Ошибка загрузки", err)

        thread.progress.connect(on_progress)
        thread.finished.connect(on_done)
        thread.error.connect(on_error)
        thread.start()
        self.refresh()

    def _find_row(self, post_id: int) -> int:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == post_id:
                return row
        return -1

    def _delete_post(self):
        post_id = self._selected_post_id()
        if post_id is None:
            return
        reply = QMessageBox.question(
            self, "Удалить", "Удалить пост из очереди?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            task_scheduler.cancel_post(post_id)
            db.delete_scheduled_post(post_id)
            self.refresh()
