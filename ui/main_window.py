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
        from PyQt6.QtWidgets import QFrame
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setObjectName("Sidebar")
        sidebar.setStyleSheet("""
            #Sidebar {
                background-color: #0e0e0e;
                border-right: 1px solid #1c1c1c;
            }
            #Sidebar QPushButton {
                background: transparent;
                color: #505050;
                border: none;
                border-left: 3px solid transparent;
                border-radius: 0;
                text-align: left;
                padding: 12px 20px;
                font-size: 13px;
                font-weight: 500;
                letter-spacing: 0.2px;
            }
            #Sidebar QPushButton:hover {
                background-color: #181818;
                color: #b0b0b0;
                border-left: 3px solid transparent;
            }
            #Sidebar QPushButton[active="true"] {
                background-color: #1a1a1a;
                color: #ef5350;
                border-left: 3px solid #e53935;
            }
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo area
        logo_widget = QWidget()
        logo_widget.setStyleSheet("background: transparent;")
        logo_layout = QVBoxLayout(logo_widget)
        logo_layout.setContentsMargins(0, 28, 0, 22)
        logo_layout.setSpacing(3)

        icon_lbl = QLabel("▶")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("color: #e53935; font-size: 22px; background: transparent;")
        logo_layout.addWidget(icon_lbl)

        name_lbl = QLabel("AutoDrop")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet(
            "color: #f0f0f0; font-size: 15px; font-weight: 700; "
            "letter-spacing: 1px; background: transparent;"
        )
        logo_layout.addWidget(name_lbl)

        sub_lbl = QLabel("VIDEO")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setStyleSheet(
            "color: #383838; font-size: 9px; letter-spacing: 4px; background: transparent;"
        )
        logo_layout.addWidget(sub_lbl)
        layout.addWidget(logo_widget)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background: #1c1c1c; border: none; max-height: 1px; margin: 0;")
        layout.addWidget(divider)
        layout.addSpacing(10)

        # Nav section label
        nav_label = QLabel("НАВИГАЦИЯ")
        nav_label.setStyleSheet(
            "color: #2e2e2e; font-size: 9px; font-weight: 700; "
            "letter-spacing: 2px; padding: 0 20px 6px 20px; background: transparent;"
        )
        layout.addWidget(nav_label)

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

        ver_lbl = QLabel("v 1.0.0")
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver_lbl.setStyleSheet(
            "color: #252525; font-size: 10px; padding: 12px; background: transparent;"
        )
        layout.addWidget(ver_lbl)

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
