from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QProgressBar, QHeaderView,
    QMessageBox, QAbstractItemView, QMenu, QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QColor, QAction, QDesktopServices

import db.database as db
import scheduler.task_scheduler as task_scheduler
from api.youtube_uploader import upload_video

STATUS_COLORS = {
    "pending":   "#4f8ef7",
    "uploading": "#f9a825",
    "done":      "#4caf50",
    "failed":    "#ef5350",
}

STATUS_LABELS = {
    "pending":   "Ожидает",
    "uploading": "Загружается...",
    "done":      "Опубликовано",
    "failed":    "Ошибка",
}

URL_COL = 4


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
        title_lbl = QLabel("Очередь загрузок")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #f0f0f0;")
        header.addWidget(title_lbl)
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

        # Clickable URL column
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        layout.addWidget(self.table)

        hint = QLabel("Клик по ссылке — открыть в браузере  ·  ПКМ — скопировать")
        hint.setStyleSheet("color: #2e2e2e; font-size: 11px;")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        upload_now_btn = QPushButton("Загрузить сейчас")
        upload_now_btn.setStyleSheet(
            "background: #e53935; color: white; border: none; "
            "padding: 7px 18px; border-radius: 7px; font-weight: 600;"
        )
        upload_now_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        upload_now_btn.clicked.connect(self._upload_now)

        retry_btn = QPushButton("Повторить")
        retry_btn.clicked.connect(self._retry_post)

        delete_btn = QPushButton("Удалить")
        delete_btn.setStyleSheet("color: #ef5350; border-color: #2c2c2c;")
        delete_btn.clicked.connect(self._delete_post)

        clear_btn = QPushButton("Очистить всё")
        clear_btn.setStyleSheet("color: #ef5350; border-color: #2c2c2c;")
        clear_btn.setToolTip("Удалить все записи из очереди")
        clear_btn.clicked.connect(self._clear_all)

        btn_row.addWidget(upload_now_btn)
        btn_row.addWidget(retry_btn)
        btn_row.addStretch()
        btn_row.addWidget(delete_btn)
        btn_row.addWidget(clear_btn)
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

            # URL cell — styled as link when present
            url = post["post_url"] or ""
            url_item = QTableWidgetItem(url)
            if url:
                url_item.setForeground(QColor("#4fc3f7"))
                url_item.setToolTip("Нажмите чтобы открыть · ПКМ для копирования")
            self.table.setItem(row, URL_COL, url_item)

            # Progress bar
            bar = QProgressBar()
            bar.setRange(0, 100)
            if status == "uploading" and post["id"] in self._threads:
                bar.setValue(0)
            else:
                bar.setValue(100 if status == "done" else 0)
            self.table.setCellWidget(row, 5, bar)

            for col in range(5):
                item = self.table.item(row, col)
                if item:
                    item.setData(Qt.ItemDataRole.UserRole, post["id"])

        self.table.resizeRowsToContents()

    # ── URL interaction ───────────────────────────────────────────────────────

    def _on_cell_clicked(self, row: int, col: int):
        if col != URL_COL:
            return
        item = self.table.item(row, URL_COL)
        if item and item.text():
            QDesktopServices.openUrl(QUrl(item.text()))

    def _show_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        url_item = self.table.item(row, URL_COL)
        url = url_item.text() if url_item else ""
        if not url:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1e1e1e; border: 1px solid #2c2c2c; }"
            "QMenu::item { padding: 6px 20px; color: #d0d0d0; }"
            "QMenu::item:selected { background: #2a2a2a; }"
        )

        open_act = QAction("Открыть в браузере", self)
        open_act.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        menu.addAction(open_act)

        copy_act = QAction("Копировать ссылку", self)
        copy_act.triggered.connect(lambda: QApplication.clipboard().setText(url))
        menu.addAction(copy_act)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ── post actions ─────────────────────────────────────────────────────────

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

    def _clear_all(self):
        posts = db.get_scheduled_posts()
        if not posts:
            QMessageBox.information(self, "Очередь пуста", "В очереди нет записей.")
            return
        uploading = [p for p in posts if p["status"] == "uploading"]
        extra = f"\n\nВнимание: {len(uploading)} видео сейчас загружается." if uploading else ""
        reply = QMessageBox.question(
            self, "Очистить очередь",
            f"Удалить все {len(posts)} записей из очереди?{extra}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            for post in posts:
                task_scheduler.cancel_post(post["id"])
                db.delete_scheduled_post(post["id"])
            self.refresh()

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
