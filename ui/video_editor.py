import os
import json
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTextEdit, QComboBox, QFileDialog, QScrollArea,
    QFrame, QSlider, QDialog, QDialogButtonBox, QDateTimeEdit,
    QMessageBox, QSizePolicy, QListWidget, QListWidgetItem, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QDateTime
from PyQt6.QtGui import QPixmap

import db.database as db
import scheduler.task_scheduler as task_scheduler

try:
    from PIL import Image
    import subprocess
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def get_video_info(file_path: str) -> dict:
    """Extract duration, width, height from video using ffprobe."""
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
    """Extract a frame from video at given time using ffmpeg."""
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


class ScheduleDialog(QDialog):
    def __init__(self, video_id: int, parent=None):
        super().__init__(parent)
        self.video_id = video_id
        self.setWindowTitle("Запланировать публикацию")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Аккаунт:"))
        self.account_combo = QComboBox()
        self._load_accounts()
        layout.addWidget(self.account_combo)

        layout.addWidget(QLabel("Дата и время публикации:"))
        self.dt_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.dt_edit.setCalendarPopup(True)
        self.dt_edit.setMinimumDateTime(QDateTime.currentDateTime())
        layout.addWidget(self.dt_edit)

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

    def _accept(self):
        if self.account_combo.count() == 0:
            QMessageBox.warning(self, "Нет аккаунтов",
                                "Сначала подключите YouTube аккаунт в разделе 'Аккаунты'.")
            return
        self.accept()

    def get_result(self):
        account_id = self.account_combo.currentData()
        dt = self.dt_edit.dateTime().toPyDateTime()
        return account_id, dt


class VideoEditorDialog(QDialog):
    def __init__(self, video_id: int = None, parent=None):
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

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # File picker
        file_row = QHBoxLayout()
        self.file_label = QLabel("Файл не выбран")
        self.file_label.setStyleSheet("color: gray;")
        file_row.addWidget(self.file_label, 1)
        pick_btn = QPushButton("Выбрать видео")
        pick_btn.clicked.connect(self._pick_file)
        file_row.addWidget(pick_btn)
        layout.addLayout(file_row)

        # Type badge
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

        # Thumbnail
        thumb_label = QLabel("Превью:")
        layout.addWidget(thumb_label)
        thumb_row = QHBoxLayout()
        self.thumb_preview = QLabel()
        self.thumb_preview.setFixedSize(160, 90)
        self.thumb_preview.setStyleSheet("background: #1a1a1a; border: 1px solid #2c2c2c; border-radius: 6px; color: #505050;")
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

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать видео", "",
            "Видео (*.mp4 *.mov *.avi *.mkv *.webm)"
        )
        if not path:
            return
        self._video_path = path
        self.file_label.setText(os.path.basename(path))
        self.file_label.setStyleSheet("")

        info = get_video_info(path)
        self._video_duration = info["duration"]
        w, h = info["width"], info["height"]

        is_vertical = h > w if w and h else False
        is_short = is_vertical and self._video_duration <= 60
        if is_short:
            self.type_label.setText("Shorts")
            self.type_label.setStyleSheet("color: #ff0000; font-weight: bold;")
        else:
            self.type_label.setText("Обычное видео")
            self.type_label.setStyleSheet("color: #333; font-weight: bold;")

        if self._video_duration > 0:
            self.frame_slider.setEnabled(True)
            self.frame_slider.setValue(0)
            self._preview_frame(0)

    def _on_frame_slider(self, value: int):
        if self._video_path and self._video_duration > 0:
            t = (value / 100) * self._video_duration
            self._preview_frame(t)

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
            self, "Выбрать превью", "",
            "Изображения (*.jpg *.jpeg *.png)"
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
        t = video["video_type"]
        if t == "short":
            self.type_label.setText("Shorts")
            self.type_label.setStyleSheet("color: #ff0000; font-weight: bold;")
        else:
            self.type_label.setText("Обычное видео")
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

        is_short = (self.type_label.text() == "Shorts")
        video_type = "short" if is_short else "regular"

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


class VideoLibraryWidget(QWidget):
    post_scheduled = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

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

        self.list_widget = QListWidget()
        self.list_widget.setSpacing(2)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        edit_btn = QPushButton("Редактировать")
        edit_btn.clicked.connect(self._edit_video)
        schedule_btn = QPushButton("Запланировать")
        schedule_btn.setStyleSheet(
            "background: #e53935; color: white; border: none; "
            "padding: 7px 16px; border-radius: 7px; font-weight: 600;"
        )
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
            badge = "[S] " if v["video_type"] == "short" else "     "
            item = QListWidgetItem(f"{badge}{v['title']}  |  {v['file_path']}")
            item.setData(Qt.ItemDataRole.UserRole, v["id"])
            self.list_widget.addItem(item)

    def _selected_id(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.information(self, "Выбор", "Выберите видео из списка.")
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _add_video(self):
        dlg = VideoEditorDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _edit_video(self):
        vid = self._selected_id()
        if vid is None:
            return
        dlg = VideoEditorDialog(video_id=vid, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _schedule_video(self):
        vid = self._selected_id()
        if vid is None:
            return
        dlg = ScheduleDialog(video_id=vid, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            account_id, dt = dlg.get_result()
            post_id = db.add_scheduled_post(vid, account_id, dt.isoformat())
            task_scheduler.schedule_post(post_id, dt)
            self.post_scheduled.emit()
            QMessageBox.information(self, "Запланировано",
                                    f"Публикация запланирована на {dt.strftime('%d.%m.%Y %H:%M')}")

    def _delete_video(self):
        vid = self._selected_id()
        if vid is None:
            return
        reply = QMessageBox.question(
            self, "Удалить видео",
            "Удалить видео из библиотеки? Все запланированные посты тоже будут удалены.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            db.delete_video(vid)
            self.refresh()
