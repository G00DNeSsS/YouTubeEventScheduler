import os
import json
import tempfile
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTextEdit, QComboBox, QFileDialog, QScrollArea,
    QFrame, QSlider, QDialog, QDialogButtonBox, QDateTimeEdit,
    QMessageBox, QSizePolicy, QListWidget, QListWidgetItem, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QInputDialog,
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
                return {
                    "width": stream.get("width", 0),
                    "height": stream.get("height", 0),
                    "duration": float(stream.get("duration", 0)),
                }
    except Exception:
        pass
    return {"width": 0, "height": 0, "duration": 0}


_TEMP_FRAME = os.path.join(tempfile.gettempdir(), "_adv_preview_frame.jpg")


def extract_frame(video_path: str, time_sec: float, out_path: str) -> bool:
    try:
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(time_sec), "-i", video_path,
             "-frames:v", "1", "-q:v", "2", out_path],
            capture_output=True, timeout=15
        )
        return os.path.exists(out_path)
    except FileNotFoundError:
        return False  # ffmpeg not in PATH
    except Exception:
        return False


def _is_short(width: int, height: int, duration: float) -> bool:
    return bool(width and height and height > width and duration <= 60)


# ---------------------------------------------------------------------------
# SchedulePickerDialog — video selector + scheduling config in one place
# ---------------------------------------------------------------------------

class SchedulePickerDialog(QDialog):
    def __init__(self, preselected_ids: list = None, parent=None):
        super().__init__(parent)
        self._preselected = set(preselected_ids or [])
        self._all_videos = []
        self.setWindowTitle("Запланировать публикацию")
        self.setMinimumSize(900, 560)
        self._build_ui()
        self._load_videos()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Content row ──────────────────────────────────────────────────────
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        # Left panel — video picker
        left = QWidget()
        left.setObjectName("PickerLeft")
        left.setStyleSheet("#PickerLeft { background: #1a1a1a; border-right: 1px solid #202020; }")
        left.setFixedWidth(400)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 16, 16, 14)
        ll.setSpacing(10)

        hdr = QHBoxLayout()
        lbl = QLabel("Видео")
        lbl.setStyleSheet("font-size: 14px; font-weight: 600; color: #d0d0d0;")
        hdr.addWidget(lbl)
        hdr.addStretch()
        self._count_lbl = QLabel("Выбрано: 0")
        self._count_lbl.setStyleSheet("color: #444; font-size: 11px;")
        hdr.addWidget(self._count_lbl)
        ll.addLayout(hdr)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Поиск по названию...")
        self._search.textChanged.connect(self._filter)
        ll.addWidget(self._search)

        self._list = QListWidget()
        self._list.setSpacing(1)
        self._list.itemChanged.connect(self._on_check)
        ll.addWidget(self._list)

        tog = QHBoxLayout()
        all_btn = QPushButton("Выбрать все")
        all_btn.clicked.connect(self._check_all)
        none_btn = QPushButton("Снять все")
        none_btn.clicked.connect(self._uncheck_all)
        tog.addWidget(all_btn)
        tog.addWidget(none_btn)
        tog.addStretch()
        ll.addLayout(tog)

        content.addWidget(left)

        # Right panel — settings
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(22, 16, 22, 14)
        rl.setSpacing(12)

        rtitle = QLabel("Настройки публикации")
        rtitle.setStyleSheet("font-size: 14px; font-weight: 600; color: #d0d0d0;")
        rl.addWidget(rtitle)

        rl.addWidget(QLabel("Аккаунт:"))
        self.account_combo = QComboBox()
        self._load_accounts()
        rl.addWidget(self.account_combo)

        rl.addWidget(QLabel("Дата первой публикации:"))
        self.dt_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.dt_edit.setCalendarPopup(True)
        self.dt_edit.setMinimumDateTime(QDateTime.currentDateTime())
        rl.addWidget(self.dt_edit)

        irow = QHBoxLayout()
        irow.addWidget(QLabel("Интервал:"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 168)
        self.interval_spin.setValue(24)
        self.interval_spin.setSuffix(" ч")
        self.interval_spin.setFixedWidth(110)
        irow.addWidget(self.interval_spin)
        irow.addStretch()
        rl.addLayout(irow)

        sep_lbl = QLabel("РАСПИСАНИЕ")
        sep_lbl.setStyleSheet(
            "color: #2e2e2e; font-size: 10px; font-weight: 700; letter-spacing: 2px;"
        )
        rl.addWidget(sep_lbl)

        self.preview_lbl = QLabel("Выберите видео и дату")
        self.preview_lbl.setStyleSheet(
            "color: #505050; font-size: 12px; padding: 10px 14px; "
            "background: #1a1a1a; border-radius: 8px;"
        )
        self.preview_lbl.setWordWrap(True)
        self.preview_lbl.setMinimumHeight(130)
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        rl.addWidget(self.preview_lbl)
        rl.addStretch()

        content.addWidget(right, 1)
        root.addLayout(content, 1)

        self.dt_edit.dateTimeChanged.connect(self._update_preview)
        self.interval_spin.valueChanged.connect(self._update_preview)

        # ── Button bar ───────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #1e1e1e; border: none; max-height: 1px;")
        root.addWidget(sep)

        bar = QWidget()
        bar.setStyleSheet("background: #141414;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(20, 10, 20, 14)

        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)

        self.ok_btn = QPushButton("Запланировать")
        self.ok_btn.setStyleSheet(
            "background: #e53935; color: white; border: none; "
            "padding: 8px 22px; border-radius: 7px; font-weight: 600;"
        )
        self.ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_btn.setEnabled(False)
        self.ok_btn.clicked.connect(self._accept)

        bl.addStretch()
        bl.addWidget(cancel_btn)
        bl.addWidget(self.ok_btn)
        root.addWidget(bar)

    # ── data helpers ─────────────────────────────────────────────────────────

    def _load_accounts(self):
        for acc in db.get_accounts():
            self.account_combo.addItem(acc["account_name"], acc["id"])

    def _load_videos(self):
        self._all_videos = list(db.get_videos())
        self._render(self._all_videos)

    def _render(self, videos: list):
        self._list.blockSignals(True)
        self._list.clear()
        for v in videos:
            badge = "Shorts" if v["video_type"] == "short" else "Видео"
            item = QListWidgetItem(f"[{badge}]  {v['title']}")
            item.setData(Qt.ItemDataRole.UserRole, v["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = v["id"] in self._preselected
            item.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
            if v["video_type"] == "short":
                item.setForeground(QColor("#ef5350"))
            self._list.addItem(item)
        self._list.blockSignals(False)
        self._refresh_state()

    def _filter(self, text: str):
        self._preselected = self._checked_ids()
        txt = text.lower()
        filtered = (
            [v for v in self._all_videos if txt in v["title"].lower()]
            if txt else self._all_videos
        )
        self._render(filtered)

    def _on_check(self):
        self._preselected = self._checked_ids()
        self._refresh_state()

    def _checked_ids(self) -> set:
        ids = set()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                ids.add(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _check_all(self):
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Checked)
        self._list.blockSignals(False)
        self._preselected = self._checked_ids()
        self._refresh_state()

    def _uncheck_all(self):
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._list.blockSignals(False)
        self._preselected = set()
        self._refresh_state()

    def _refresh_state(self):
        n = len(self._preselected)
        self._count_lbl.setText(f"Выбрано: {n}")
        has_acc = self.account_combo.count() > 0
        self.ok_btn.setEnabled(n > 0 and has_acc)
        word = "видео" if n % 10 != 1 or n % 100 == 11 else "видео"
        self.ok_btn.setText(f"Запланировать {n} {word}")
        self._update_preview()

    def _update_preview(self):
        ordered = self._ordered_checked()
        if not ordered:
            self.preview_lbl.setText("Выберите видео и дату")
            return
        dt = self.dt_edit.dateTime().toPyDateTime()
        interval_h = self.interval_spin.value()
        title_map = {v["id"]: v["title"] for v in self._all_videos}
        lines = []
        for i, vid_id in enumerate(ordered[:6]):
            t = dt + timedelta(hours=interval_h * i)
            title = title_map.get(vid_id, "?")
            short_t = (title[:30] + "…") if len(title) > 30 else title
            lines.append(f"{t.strftime('%d.%m  %H:%M')}  —  {short_t}")
        if len(ordered) > 6:
            lines.append(f"... ещё {len(ordered) - 6}")
        self.preview_lbl.setText("\n".join(lines))

    def _ordered_checked(self) -> list:
        result = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    def _accept(self):
        if self.account_combo.count() == 0:
            QMessageBox.warning(self, "Нет аккаунтов",
                                "Сначала подключите YouTube аккаунт в разделе «Аккаунты».")
            return
        self.accept()

    def get_result(self) -> list:
        account_id = self.account_combo.currentData()
        dt = self.dt_edit.dateTime().toPyDateTime()
        interval_h = self.interval_spin.value()
        return [
            (vid_id, account_id, dt + timedelta(hours=interval_h * i))
            for i, vid_id in enumerate(self._ordered_checked())
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
        self.setMinimumSize(600, 620)
        self._build_ui()

        if video_id:
            self._load_video(video_id)
        elif file_path:
            self._apply_file(file_path)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll, 1)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 8)
        layout.setSpacing(10)

        file_row = QHBoxLayout()
        self.file_label = QLabel("Файл не выбран")
        self.file_label.setStyleSheet("color: #505050;")
        self.file_label.setWordWrap(True)
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

        title_hdr = QHBoxLayout()
        title_lbl = QLabel("Заголовок")
        title_lbl.setStyleSheet("font-weight: 600;")
        title_hdr.addWidget(title_lbl)
        title_hdr.addStretch()
        self.title_counter = QLabel("0 / 100")
        self.title_counter.setStyleSheet("color: #383838; font-size: 11px;")
        title_hdr.addWidget(self.title_counter)
        layout.addLayout(title_hdr)

        self.title_edit = QLineEdit()
        self.title_edit.setMaxLength(100)
        self.title_edit.setPlaceholderText("Название видео...")
        self.title_edit.setMinimumHeight(36)
        self.title_edit.textChanged.connect(self._on_title_changed)
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
        layout.addStretch()

        btn_sep = QFrame()
        btn_sep.setFrameShape(QFrame.Shape.HLine)
        btn_sep.setStyleSheet("background: #1e1e1e; border: none; max-height: 1px;")
        outer.addWidget(btn_sep)

        btn_wrapper = QWidget()
        btn_wrapper.setStyleSheet("background: #141414;")
        btn_layout = QHBoxLayout(btn_wrapper)
        btn_layout.setContentsMargins(20, 10, 20, 14)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        btn_layout.addWidget(buttons)
        outer.addWidget(btn_wrapper)

    def _on_title_changed(self, text: str):
        n = len(text)
        self.title_counter.setText(f"{n} / 100")
        color = "#ef5350" if n >= 90 else "#f59e0b" if n >= 70 else "#383838"
        self.title_counter.setStyleSheet(f"color: {color}; font-size: 11px;")

    def _apply_file(self, path: str):
        self._video_path = path
        self.file_label.setText(os.path.basename(path))
        self.file_label.setStyleSheet("")

        info = get_video_info(path)
        self._video_duration = info["duration"]
        short = _is_short(info["width"], info["height"], self._video_duration)
        self.type_label.setText("Shorts" if short else "Обычное видео")
        self.type_label.setStyleSheet(
            "color: #ef5350; font-weight: bold;" if short else "font-weight: bold;"
        )
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
        if not self._video_path or not os.path.exists(self._video_path):
            return
        tmp = _TEMP_FRAME
        if extract_frame(self._video_path, time_sec, tmp):
            self._temp_thumb = tmp
            pix = QPixmap(tmp).scaled(
                160, 90, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.thumb_preview.setPixmap(pix)
        else:
            self.thumb_preview.setText("ffmpeg не найден")

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
        short = video["video_type"] == "short"
        self.type_label.setText("Shorts" if short else "Обычное видео")
        self.type_label.setStyleSheet(
            "color: #ef5350; font-weight: bold;" if short else "font-weight: bold;"
        )
        if video["thumbnail_path"] and os.path.exists(video["thumbnail_path"]):
            self.thumbnail_path = video["thumbnail_path"]
            pix = QPixmap(video["thumbnail_path"]).scaled(
                160, 90, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.thumb_preview.setPixmap(pix)
        if self._video_duration > 0 and os.path.exists(self._video_path or ""):
            self.frame_slider.setEnabled(True)
            self._preview_frame(0)  # load initial frame preview

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
        files_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #505050; letter-spacing: 0.3px;"
        )
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
        self.table.setFixedHeight(min(len(self._paths) * 38 + 42, 260))

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
        sep.setStyleSheet(
            "color: #303030; font-size: 10px; font-weight: 700; letter-spacing: 2px;"
        )
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
        layout.setSpacing(10)

        # Header
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

        # Toolbar: search + sort
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Поиск по названию...")
        self._search_edit.textChanged.connect(self.refresh)
        toolbar.addWidget(self._search_edit, 1)

        self._sort_combo = QComboBox()
        self._sort_combo.addItems([
            "Дата (новые)",
            "Дата (старые)",
            "Название A → Z",
            "Название Z → A",
            "Shorts сначала",
            "Видео сначала",
        ])
        self._sort_combo.setFixedWidth(160)
        self._sort_combo.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(self._sort_combo)

        layout.addLayout(toolbar)

        # Video list
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(2)
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list_widget.itemDoubleClicked.connect(self._quick_rename)
        layout.addWidget(self.list_widget)

        # Hint
        hint = QLabel("Двойной клик — переименовать  ·  Ctrl/Shift+Click — выбрать несколько")
        hint.setStyleSheet("color: #2e2e2e; font-size: 11px;")
        layout.addWidget(hint)

        # Action buttons
        btn_row = QHBoxLayout()
        edit_btn = QPushButton("Редактировать")
        edit_btn.setToolTip("Редактировать одно выбранное видео")
        edit_btn.clicked.connect(self._edit_video)

        schedule_btn = QPushButton("Запланировать...")
        schedule_btn.setStyleSheet(
            "background: #e53935; color: white; border: none; "
            "padding: 7px 16px; border-radius: 7px; font-weight: 600;"
        )
        schedule_btn.setToolTip("Открыть диалог выбора видео для планирования")
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
        videos = list(db.get_videos())

        # Filter
        search = self._search_edit.text().lower().strip()
        if search:
            videos = [v for v in videos if search in v["title"].lower()]

        # Sort
        idx = self._sort_combo.currentIndex()
        if idx == 1:    # старые
            videos = list(reversed(videos))
        elif idx == 2:  # A→Z
            videos.sort(key=lambda v: v["title"].lower())
        elif idx == 3:  # Z→A
            videos.sort(key=lambda v: v["title"].lower(), reverse=True)
        elif idx == 4:  # Shorts сначала
            videos.sort(key=lambda v: (v["video_type"] != "short", v["title"].lower()))
        elif idx == 5:  # Видео сначала
            videos.sort(key=lambda v: (v["video_type"] == "short", v["title"].lower()))

        self.list_widget.clear()
        for v in videos:
            badge = "Shorts" if v["video_type"] == "short" else "Видео"
            item = QListWidgetItem(f"[{badge}]  {v['title']}")
            item.setData(Qt.ItemDataRole.UserRole, v["id"])
            item.setData(Qt.ItemDataRole.UserRole + 1, v["title"])
            if v["video_type"] == "short":
                item.setForeground(QColor("#ef5350"))
            self.list_widget.addItem(item)

    def _quick_rename(self, item: QListWidgetItem):
        vid_id = item.data(Qt.ItemDataRole.UserRole)
        old_title = item.data(Qt.ItemDataRole.UserRole + 1)
        new_title, ok = QInputDialog.getText(
            self, "Переименовать", "Заголовок:", text=old_title
        )
        if ok and new_title.strip():
            db.update_video_title(vid_id, new_title.strip())
            self.refresh()

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
        dlg = (
            VideoEditorDialog(file_path=paths[0], parent=self)
            if len(paths) == 1
            else BatchAddDialog(paths, parent=self)
        )
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
        preselected = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.list_widget.selectedItems()
        ]
        dlg = SchedulePickerDialog(preselected_ids=preselected, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            schedule = dlg.get_result()
            for vid_id, account_id, dt in schedule:
                post_id = db.add_scheduled_post(vid_id, account_id, dt.isoformat())
                task_scheduler.schedule_post(post_id, dt)
            self.post_scheduled.emit()
            n = len(schedule)
            first_dt = schedule[0][2]
            msg = (
                f"Запланировано {n} видео.\nПервое: {first_dt.strftime('%d.%m.%Y %H:%M')}"
                if n > 1 else
                f"Публикация запланирована на {first_dt.strftime('%d.%m.%Y %H:%M')}"
            )
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
