from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QStackedWidget, QLabel, QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QIcon, QAction

from ui.video_editor import VideoLibraryWidget
from ui.calendar_widget import CalendarWidget
from ui.upload_queue import UploadQueueWidget
from ui.account_manager import AccountManagerWidget
import scheduler.task_scheduler as task_scheduler


class SchedulerSignals(QObject):
    post_status_changed = pyqtSignal(int, str, str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoDropVideo")
        self.setMinimumSize(1100, 700)

        self._signals = SchedulerSignals()
        self._signals.post_status_changed.connect(self._on_post_status)

        task_scheduler.set_status_callback(self._scheduler_callback)
        task_scheduler.start()

        self._setup_tray()
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = self._build_sidebar()
        root_layout.addWidget(sidebar)

        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack, 1)

        self.library_widget = VideoLibraryWidget()
        self.calendar_widget = CalendarWidget()
        self.queue_widget = UploadQueueWidget()
        self.accounts_widget = AccountManagerWidget()

        self.stack.addWidget(self.library_widget)
        self.stack.addWidget(self.calendar_widget)
        self.stack.addWidget(self.queue_widget)
        self.stack.addWidget(self.accounts_widget)

        self.library_widget.post_scheduled.connect(self._on_post_scheduled)
        self.calendar_widget.post_scheduled.connect(self._on_post_scheduled)

        self._switch_page(0)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(180)
        sidebar.setObjectName("Sidebar")
        sidebar.setStyleSheet("""
            #Sidebar { background-color: #1a1a2e; }
            QPushButton {
                background: transparent;
                color: #a0a0b0;
                border: none;
                text-align: left;
                padding: 12px 20px;
                font-size: 14px;
                border-radius: 0;
            }
            QPushButton:hover { background-color: #16213e; color: white; }
            QPushButton[active="true"] {
                background-color: #0f3460;
                color: white;
                border-left: 3px solid #e94560;
            }
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel("AutoDrop\nVideo")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: white; font-size: 16px; font-weight: bold; padding: 20px 10px;")
        layout.addWidget(title)

        self._nav_buttons = []
        nav_items = [
            ("Библиотека", 0),
            ("Календарь", 1),
            ("Очередь", 2),
            ("Аккаунты", 3),
        ]
        for label, idx in nav_items:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, i=idx: self._switch_page(i))
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()
        return sidebar

    def _switch_page(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setProperty("active", i == index)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if index == 1:
            self.calendar_widget.refresh()
        elif index == 2:
            self.queue_widget.refresh()

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("AutoDropVideo")
        tray_menu = QMenu()
        show_action = QAction("Открыть", self)
        show_action.triggered.connect(self.show)
        quit_action = QAction("Выйти", self)
        quit_action.triggered.connect(self._quit)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        self.tray.setContextMenu(tray_menu)
        self.tray.show()

    def _scheduler_callback(self, post_id: int, status: str, message: str = ""):
        self._signals.post_status_changed.emit(post_id, status, message)

    def _on_post_status(self, post_id: int, status: str, message: str):
        self.queue_widget.refresh()
        self.calendar_widget.refresh()

        if status == "done":
            self.tray.showMessage(
                "Видео опубликовано",
                f"Пост #{post_id} успешно загружен на YouTube",
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )
        elif status == "failed":
            self.tray.showMessage(
                "Ошибка загрузки",
                f"Пост #{post_id}: {message}",
                QSystemTrayIcon.MessageIcon.Critical,
                6000,
            )

    def _on_post_scheduled(self):
        self.calendar_widget.refresh()
        self.queue_widget.refresh()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "AutoDropVideo",
            "Приложение продолжает работу в фоне",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _quit(self):
        task_scheduler.shutdown()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()
