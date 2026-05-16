import os
import json
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTextEdit, QComboBox, QFileDialog, QScrollArea,
    QFrame, QSlider, QDialog, QDialogButtonBox, QDateTimeEdit,
    QMessageBox, QSizePolicy, QListWidget, QListWidgetItem, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal, QDateTime
from PyQt6.QtGui import QPixmap, QColor

import db.database as db
import scheduler.task_scheduler as task_scheduler

try:
    from PIL import Image
    import subprocess
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def get_video_info(file_path: str) -> dict:
    try:
        import subprocess, json as _json
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", file_path],
            capture_output=True, text=True, timeout=10
        )
        data = _json.loads(result.stdout)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                w = stream.get("width", 0)
                h = stream.get("height", 0)
                dur = float(stream.get("duration", 0))
                return {"width": w, "height": h, "duration": dur}
    except Exception:
        pass
    return {"width": 0, "height": 0, "duration": 0}


def extract_frame(video_path: str, time_sec: float, out_path: str) -> bool:
    try:
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(time_sec), "-i", video_path,
             "-frames:v", "1", "-q:v", "2", out_path],
            capture_output=True, timeout=15
        )
        return os.path.exists(out_path)
    except Exception:
        return False


def _is_short(width: int, height: int, duration: float) -> bool:
    return bool(width and height and height > width and duration <= 60)


# ---------------------------------------------------------------------------
# ScheduleDialog — handles single and batch scheduling
# ---------------------------------------------------------------------------

class ScheduleDialog(QDialog):
    def __init__(self, video_ids: list, parent=None):
        super().__init__(parent)
        self._video_ids = video_ids
        n = len(video_ids)
        self.setWindowTitle(f"Запланировать {n} видео" if n > 1 else "Запланировать публикацию")
        self.setMinimumWidth(430)
        self._build_ui(n)

    def _build_ui(self, n: int):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Аккаунт:"))
        self.account_combo = QComboBox()
        self._load_accounts()
        layout.addWidget(self.account_combo)

        layout.addWidget(QLabel("Дата и время первой публикации:"))
        self.dt_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.dt_edit.setCalendarPopup(True)
        self.dt_edit.setMinimumDateTime(QDateTime.currentDateTime())
        layout.addWidget(self.dt_edit)

        self.interval_spin = None
        self.preview_label = None

        if n > 1:
            interval_row = QHBoxLayout()
            interval_row.addWidget(QLabel("Интервал между публикациями:"))
            self.interval_spin = QSpinBox()
            self.interval_spin.setRange(1, 168)
            self.interval_spin.setValue(24)
            self.interval_spin.setSuffix(" ч")
            self.interval_spin.setFixedWidth(100)
            interval_row.addWidget(self.interval_spin)
            interval_row.addStretch()
            layout.addLayout(interval_row)

            self.preview_label = QLabel()
            self.preview_label.setStyleSheet(
                "color: #606060; font-size: 12px; padding: 10px 12px; "
                "background: #1a1a1a; border-radius: 7px; line-height: 1.6;"
            )
            self.preview_label.setWordWrap(True)
            layout.addWidget(self.preview_label)

            self.dt_edit.dateTimeChanged.connect(self._update_preview)
            self.interval_spin.valueChanged.connect(self._update_preview)
            self._update_preview()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_accounts(self):
        self.account_combo.clear()
        self._accounts = db.get_accounts()
        for acc in self._accounts:
            self.account_combo.addItem(acc["account_name"], acc["id"])

    def _update_preview(self):
        if not self.preview_label:
            return
        dt = self.dt_edit.dateTime().toPyDateTime()
        interval_h = self.interval_spin.value()
        lines = []
        for i, _ in enumerate(self._video_ids[:5]):
            t = dt + timedelta(hours=interval_h * i)
            lines.append(f"Видео {i + 1}:  {t.strftime('%d.%m.%Y  %H:%M')}")
        if len(self._video_ids) > 5:
            lines.append(f"... ещё {len(self._video_ids) - 5} видео")
        self.preview_label.setText("\n".join(lines))

    def _accept(self):
        if self.account_combo.count() == 0:
            QMessageBox.warning(self, "Нет аккаунтов",
                                "Сначала подключите YouTube аккаунт в разделе «Аккаунты».")
            return
        self.accept()

    def get_result(self) -> list:
        account_id = self.account_combo.currentData()
        dt = self.dt_edit.dateTime().toPyDateTime()
        interval_h = self.interval_spin.value() if self.interval_spin else 0
        return [
            (vid_id, account_id, dt + timedelta(hours=interval_h * i))
            for i, vid_id in enumerate(self._video_ids)
        ]


# ---------------------------------------------------------------------------
# VideoEditorDialog — single video add / edit
# ---------------------------------------------------------------------------

class VideoEditorDialog(QDialog):
    def __init__(self, video_id: int = None, file_path: str = None, parent=None):
        super().__init__(parent)
        self.video_id = video_id
        self.thumbnail_path = None
        self._video_path = None
        self._video_duration = 0
        self._temp_thumb = None

        self.setWindowTitle("Редактор видео" if video_id else "Добавить видео")
        self.setMinimumSize(600, 650)
        self._build_ui()

        if video_id:
            self._load_video(video_id)
        elif file_path:
            self._apply_file(file_path)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        file_row = QHBoxLayout()
        self.file_label = QLabel("Файл не выбран")
        self.file_label.setStyleSheet("color: #505050;")
        file_row.addWidget(self.file_label, 1)
        pick_btn = QPushButton("Выбрать видео")
        pick_btn.clicked.connect(self._pick_file)
        file_row.addWidget(pick_btn)
        layout.addLayout(file_row)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Тип:"))
        self.type_label = QLabel("—")
        self.type_label.setStyleSheet("font-weight: bold;")
        type_row.addWidget(self.type_label)
        type_row.addStretch()
        layout.addLayout(type_row)

        layout.addWidget(QLabel("Заголовок:"))
        self.title_edit = QLineEdit()
        self.title_edit.setMaxLength(100)
        self.title_edit.setPlaceholderText("Максимум 100 символов")
        layout.addWidget(self.title_edit)

        layout.addWidget(QLabel("Описание:"))
        self.desc_edit = QTextEdit()
        self.desc_edit.setMaximumHeight(120)
        self.desc_edit.setPlaceholderText("Описание видео...")
        layout.addWidget(self.desc_edit)

        layout.addWidget(QLabel("Теги (через запятую):"))
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("тег1, тег2, тег3")
        layout.addWidget(self.tags_edit)

        priv_row = QHBoxLayout()
        priv_row.addWidget(QLabel("Приватность:"))
        self.privacy_combo = QComboBox()
        self.privacy_combo.addItems(["Публичное", "Не в списке", "Приватное"])
        priv_row.addWidget(self.privacy_combo)
        priv_row.addStretch()
        layout.addLayout(priv_row)

        layout.addWidget(QLabel("Превью:"))
        thumb_row = QHBoxLayout()
        self.thumb_preview = QLabel()
        self.thumb_preview.setFixedSize(160, 90)
        self.thumb_preview.setStyleSheet(
            "background: #1a1a1a; border: 1px solid #2c2c2c; "
            "border-radius: 6px; color: #505050;"
        )
        self.thumb_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_preview.setText("Нет превью")
        thumb_row.addWidget(self.thumb_preview)

        thumb_btns = QVBoxLayout()
        load_thumb_btn = QPushButton("Загрузить файл")
        load_thumb_btn.clicked.connect(self._pick_thumbnail)
        thumb_btns.addWidget(load_thumb_btn)

        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setRange(0, 100)
        self.frame_slider.setValue(0)
        self.frame_slider.setEnabled(False)
        self.frame_slider.valueChanged.connect(self._on_frame_slider)
        thumb_btns.addWidget(QLabel("Кадр из видео:"))
        thumb_btns.addWidget(self.frame_slider)
        use_frame_btn = QPushButton("Использовать этот кадр")
        use_frame_btn.clicked.connect(self._use_current_frame)
        thumb_btns.addWidget(use_frame_btn)

        thumb_row.addLayout(thumb_btns)
        layout.addLayout(thumb_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply_file(self, path: str):
        self._video_path = path
        self.file_label.setText(os.path.basename(path))
        self.file_label.setStyleSheet("")

        info = get_video_info(path)
        self._video_duration = info["duration"]
        short = _is_short(info["width"], info["height"], self._video_duration)
        if short:
            self.type_label.setText("Shorts")
            self.type_label.setStyleSheet("color: #ef5350; font-weight: bold;")
        else:
            self.type_label.setText("Обычное видео")
            self.type_label.setStyleSheet("font-weight: bold;")

        self.title_edit.setText(os.path.splitext(os.path.basename(path))[0])

        if self._video_duration > 0:
            self.frame_slider.setEnabled(True)
            self.frame_slider.setValue(0)
            self._preview_frame(0)

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать видео", "", "Видео (*.mp4 *.mov *.avi *.mkv *.webm)"
        )
        if path:
            self._apply_file(path)

    def _on_frame_slider(self, value: int):
        if self._video_path and self._video_duration > 0:
            self._preview_frame((value / 100) * self._video_duration)

    def _preview_frame(self, time_sec: float):
        tmp = "/tmp/_adv_preview_frame.jpg"
        if extract_frame(self._video_path, time_sec, tmp):
            self._temp_thumb = tmp
            pix = QPixmap(tmp).scaled(
                160, 90, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.thumb_preview.setPixmap(pix)

    def _use_current_frame(self):
        if self._temp_thumb and os.path.exists(self._temp_thumb):
            import shutil, uuid
            data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
            os.makedirs(data_dir, exist_ok=True)
            dest = os.path.join(data_dir, f"thumb_{uuid.uuid4().hex}.jpg")
            shutil.copy(self._temp_thumb, dest)
            self.thumbnail_path = dest

    def _pick_thumbnail(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать превью", "", "Изображения (*.jpg *.jpeg *.png)"
        )
        if path:
            self.thumbnail_path = path
            pix = QPixmap(path).scaled(
                160, 90, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.thumb_preview.setPixmap(pix)

    def _load_video(self, video_id: int):
        video = db.get_video(video_id)
        if not video:
            return
        self._video_path = video["file_path"]
        self._video_duration = video["duration_seconds"]
        self.file_label.setText(os.path.basename(video["file_path"]))
        self.title_edit.setText(video["title"])
        self.desc_edit.setPlainText(video["description"])
        self.tags_edit.setText(video["tags"])
        privacy_map = {"public": 0, "unlisted": 1, "private": 2}
        self.privacy_combo.setCurrentIndex(privacy_map.get(video["privacy"], 0))
        if video["video_type"] == "short":
            self.type_label.setText("Shorts")
            self.type_label.setStyleSheet("color: #ef5350; font-weight: bold;")
        else:
            self.type_label.setText("Обычное видео")
            self.type_label.setStyleSheet("font-weight: bold;")
        if video["thumbnail_path"] and os.path.exists(video["thumbnail_path"]):
            self.thumbnail_path = video["thumbnail_path"]
            pix = QPixmap(video["thumbnail_path"]).scaled(
                160, 90, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.thumb_preview.setPixmap(pix)
        if self._video_duration > 0:
            self.frame_slider.setEnabled(True)

    def _save(self):
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Ошибка", "Введите заголовок видео.")
            return
        if not self._video_path and not self.video_id:
            QMessageBox.warning(self, "Ошибка", "Выберите файл видео.")
            return

        privacy_values = ["public", "unlisted", "private"]
        privacy = privacy_values[self.privacy_combo.currentIndex()]
        video_type = "short" if self.type_label.text() == "Shorts" else "regular"

        if self.video_id:
            db.update_video(
                self.video_id, title,
                self.desc_edit.toPlainText(),
                self.tags_edit.text(),
                self.thumbnail_path,
                privacy, video_type
            )
        else:
            self.video_id = db.add_video(
                self._video_path, title,
                self.desc_edit.toPlainText(),
                self.tags_edit.text(),
                self.thumbnail_path,
                privacy, video_type,
                self._video_duration
            )
        self.accept()


# ---------------------------------------------------------------------------
# BatchAddDialog — add multiple videos at once
# ---------------------------------------------------------------------------

class BatchAddDialog(QDialog):
    def __init__(self, file_paths: list, parent=None):
        super().__init__(parent)
        self._paths = file_paths
        self.setWindowTitle(f"Добавить видео — {len(file_paths)} файлов")
        self.setMinimumSize(700, 540)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        files_lbl = QLabel(f"Файлы и заголовки  ({len(self._paths)})")
        files_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #505050; letter-spacing: 0.3px;")
        layout.addWidget(files_lbl)

        self.table = QTableWidget(len(self._paths), 3)
        self.table.setHorizontalHeaderLabels(["Файл", "Заголовок", "Тип"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 90)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table_h = min(len(self._paths) * 38 + 42, 260)
        self.table.setFixedHeight(table_h)

        self._title_edits = []
        for row, path in enumerate(self._paths):
            fname = os.path.basename(path)
            stem = os.path.splitext(fname)[0]

            fname_item = QTableWidgetItem(fname)
            fname_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            fname_item.setForeground(QColor("#505050"))
            self.table.setItem(row, 0, fname_item)

            title_edit = QLineEdit(stem)
            title_edit.setMaxLength(100)
            title_edit.setStyleSheet("border-radius: 4px; margin: 2px 3px;")
            self.table.setCellWidget(row, 1, title_edit)
            self._title_edits.append(title_edit)

            info = get_video_info(path)
            short = _is_short(info["width"], info["height"], info["duration"])
            type_item = QTableWidgetItem("Shorts" if short else "Видео")
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            type_item.setForeground(QColor("#ef5350" if short else "#505050"))
            type_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 2, type_item)

        self.table.resizeRowsToContents()
        layout.addWidget(self.table)

        sep = QLabel("ОБЩИЕ НАСТРОЙКИ")
        sep.setStyleSheet("color: #303030; font-size: 10px; font-weight: 700; letter-spacing: 2px;")
        layout.addWidget(sep)

        layout.addWidget(QLabel("Описание:"))
        self.desc_edit = QTextEdit()
        self.desc_edit.setMaximumHeight(80)
        self.desc_edit.setPlaceholderText("Общее описание для всех видео...")
        layout.addWidget(self.desc_edit)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(16)

        tags_col = QVBoxLayout()
        tags_col.setSpacing(4)
        tags_col.addWidget(QLabel("Теги:"))
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("тег1, тег2, тег3")
        tags_col.addWidget(self.tags_edit)
        bottom_row.addLayout(tags_col, 2)

        priv_col = QVBoxLayout()
        priv_col.setSpacing(4)
        priv_col.addWidget(QLabel("Приватность:"))
        self.privacy_combo = QComboBox()
        self.privacy_combo.addItems(["Публичное", "Не в списке", "Приватное"])
        priv_col.addWidget(self.privacy_combo)
        bottom_row.addLayout(priv_col, 1)
        layout.addLayout(bottom_row)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        add_btn = QPushButton(f"Добавить {len(self._paths)} видео")
        add_btn.setStyleSheet(
            "background: #e53935; color: white; border: none; "
            "padding: 8px 20px; border-radius: 7px; font-weight: 600;"
        )
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._save_all)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(add_btn)
        layout.addLayout(btn_row)

    def _save_all(self):
        privacy_values = ["public", "unlisted", "private"]
        privacy = privacy_values[self.privacy_combo.currentIndex()]
        desc = self.desc_edit.toPlainText()
        tags = self.tags_edit.text()

        for row, path in enumerate(self._paths):
            title = self._title_edits[row].text().strip()
            if not title:
                title = os.path.splitext(os.path.basename(path))[0]
            info = get_video_info(path)
            short = _is_short(info["width"], info["height"], info["duration"])
            db.add_video(
                path, title, desc, tags, None,
                privacy, "short" if short else "regular", info["duration"]
            )
        self.accept()


# ---------------------------------------------------------------------------
# VideoLibraryWidget
# ---------------------------------------------------------------------------

class VideoLibraryWidget(QWidget):
    post_scheduled = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title_lbl = QLabel("Библиотека видео")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #f0f0f0;")
        header.addWidget(title_lbl)
        header.addStretch()
        add_btn = QPushButton("+ Добавить видео")
        add_btn.setStyleSheet(
            "background: #e53935; color: white; border: none; "
            "padding: 8px 18px; font-size: 13px; border-radius: 7px; font-weight: 600;"
        )
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add_video)
        header.addWidget(add_btn)
        layout.addLayout(header)

        hint = QLabel("Ctrl+Click / Shift+Click — выбрать несколько")
        hint.setStyleSheet("color: #303030; font-size: 11px;")
        layout.addWidget(hint)

        self.list_widget = QListWidget()
        self.list_widget.setSpacing(2)
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        edit_btn = QPushButton("Редактировать")
        edit_btn.setToolTip("Редактировать одно выбранное видео")
        edit_btn.clicked.connect(self._edit_video)

        schedule_btn = QPushButton("Запланировать")
        schedule_btn.setStyleSheet(
            "background: #e53935; color: white; border: none; "
            "padding: 7px 16px; border-radius: 7px; font-weight: 600;"
        )
        schedule_btn.setToolTip("Запланировать выбранные видео")
        schedule_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        schedule_btn.clicked.connect(self._schedule_video)

        delete_btn = QPushButton("Удалить")
        delete_btn.setStyleSheet("color: #ef5350; border-color: #2c2c2c;")
        delete_btn.clicked.connect(self._delete_video)

        btn_row.addWidget(edit_btn)
        btn_row.addWidget(schedule_btn)
        btn_row.addStretch()
        btn_row.addWidget(delete_btn)
        layout.addLayout(btn_row)

    def refresh(self):
        self.list_widget.clear()
        for v in db.get_videos():
            badge = "Shorts" if v["video_type"] == "short" else "Видео"
            item = QListWidgetItem(f"[{badge}]  {v['title']}   —   {os.path.basename(v['file_path'])}")
            item.setData(Qt.ItemDataRole.UserRole, v["id"])
            if v["video_type"] == "short":
                item.setForeground(QColor("#ef5350"))
            self.list_widget.addItem(item)

    def _selected_ids(self) -> list:
        items = self.list_widget.selectedItems()
        if not items:
            QMessageBox.information(self, "Выбор", "Выберите видео из списка.")
            return []
        return [item.data(Qt.ItemDataRole.UserRole) for item in items]

    def _add_video(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Выбрать видео", "", "Видео (*.mp4 *.mov *.avi *.mkv *.webm)"
        )
        if not paths:
            return
        if len(paths) == 1:
            dlg = VideoEditorDialog(file_path=paths[0], parent=self)
        else:
            dlg = BatchAddDialog(paths, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _edit_video(self):
        items = self.list_widget.selectedItems()
        if len(items) != 1:
            QMessageBox.information(self, "Выбор",
                                    "Выберите ровно одно видео для редактирования.")
            return
        vid = items[0].data(Qt.ItemDataRole.UserRole)
        dlg = VideoEditorDialog(video_id=vid, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _schedule_video(self):
        vids = self._selected_ids()
        if not vids:
            return
        dlg = ScheduleDialog(video_ids=vids, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            schedule = dlg.get_result()
            for vid_id, account_id, dt in schedule:
                post_id = db.add_scheduled_post(vid_id, account_id, dt.isoformat())
                task_scheduler.schedule_post(post_id, dt)
            self.post_scheduled.emit()
            n = len(schedule)
            first_dt = schedule[0][2]
            if n == 1:
                msg = f"Публикация запланирована на {first_dt.strftime('%d.%m.%Y %H:%M')}"
            else:
                msg = (f"Запланировано {n} видео.\n"
                       f"Первое: {first_dt.strftime('%d.%m.%Y %H:%M')}")
            QMessageBox.information(self, "Запланировано", msg)

    def _delete_video(self):
        vids = self._selected_ids()
        if not vids:
            return
        n = len(vids)
        msg = (
            f"Удалить {n} видео из библиотеки?\n"
            "Все запланированные посты тоже будут удалены."
            if n > 1 else
            "Удалить видео из библиотеки?\n"
            "Все запланированные посты тоже будут удалены."
        )
        reply = QMessageBox.question(
            self, "Удалить видео", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            for vid in vids:
                db.delete_video(vid)
            self.refresh()
