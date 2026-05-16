import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from db.database import init_db
from ui.main_window import MainWindow


def main():
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName("AutoDropVideo")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")

    app.setStyleSheet("""
        * { font-family: 'Segoe UI', 'Inter', Arial, sans-serif; }
        QWidget { background-color: #141414; color: #d8d8d8; font-size: 13px; }
        QDialog { background-color: #141414; }
        QMainWindow { background-color: #141414; }

        QPushButton {
            background-color: #242424;
            color: #b8b8b8;
            border: 1px solid #2c2c2c;
            border-radius: 7px;
            padding: 7px 16px;
            font-size: 13px;
        }
        QPushButton:hover { background-color: #2a2a2a; color: #e0e0e0; border-color: #383838; }
        QPushButton:pressed { background-color: #1c1c1c; }
        QPushButton:disabled { color: #404040; border-color: #202020; }

        QLineEdit, QTextEdit, QPlainTextEdit {
            background-color: #1c1c1c;
            color: #d8d8d8;
            border: 1px solid #2c2c2c;
            border-radius: 7px;
            padding: 7px 10px;
            selection-background-color: #c62828;
            selection-color: white;
        }
        QLineEdit:focus, QTextEdit:focus { border-color: #e53935; }

        QComboBox {
            background-color: #1c1c1c;
            color: #d8d8d8;
            border: 1px solid #2c2c2c;
            border-radius: 7px;
            padding: 7px 10px;
            min-height: 18px;
        }
        QComboBox:focus { border-color: #e53935; }
        QComboBox::drop-down { border: none; width: 18px; }
        QComboBox QAbstractItemView {
            background-color: #1c1c1c;
            border: 1px solid #2c2c2c;
            color: #d8d8d8;
            selection-background-color: #c62828;
            selection-color: white;
            outline: none;
        }

        QSpinBox, QDateTimeEdit {
            background-color: #1c1c1c;
            color: #d8d8d8;
            border: 1px solid #2c2c2c;
            border-radius: 7px;
            padding: 6px 10px;
        }
        QSpinBox:focus, QDateTimeEdit:focus { border-color: #e53935; }
        QDateTimeEdit::drop-down { border: none; width: 18px; }
        QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { background: transparent; border: none; }

        QTableWidget {
            background-color: #181818;
            gridline-color: #202020;
            border: 1px solid #202020;
            border-radius: 8px;
            color: #d8d8d8;
            alternate-background-color: #1a1a1a;
        }
        QTableWidget::item { padding: 9px 12px; border: none; }
        QTableWidget::item:selected { background-color: #2a1515; color: white; }
        QHeaderView { background-color: #181818; }
        QHeaderView::section {
            background-color: #181818;
            color: #555;
            padding: 10px 12px;
            border: none;
            border-bottom: 1px solid #202020;
            font-weight: 600;
            font-size: 11px;
            letter-spacing: 0.5px;
        }

        QListWidget {
            background-color: #181818;
            border: 1px solid #202020;
            border-radius: 8px;
            color: #d8d8d8;
            outline: none;
        }
        QListWidget::item { padding: 10px 14px; border-bottom: 1px solid #1e1e1e; }
        QListWidget::item:selected { background-color: #2a1515; color: white; }
        QListWidget::item:hover { background-color: #1e1e1e; }

        QScrollBar:vertical { background: transparent; width: 6px; }
        QScrollBar::handle:vertical { background: #2c2c2c; border-radius: 3px; min-height: 30px; }
        QScrollBar::handle:vertical:hover { background: #3c3c3c; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar:horizontal { background: transparent; height: 6px; }
        QScrollBar::handle:horizontal { background: #2c2c2c; border-radius: 3px; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

        QProgressBar {
            background-color: #202020;
            border: none;
            border-radius: 3px;
            max-height: 5px;
            color: transparent;
        }
        QProgressBar::chunk { background-color: #e53935; border-radius: 3px; }

        QSlider::groove:horizontal { background: #242424; height: 4px; border-radius: 2px; }
        QSlider::handle:horizontal {
            background: #e53935;
            width: 14px; height: 14px;
            border-radius: 7px; margin: -5px 0;
        }
        QSlider::sub-page:horizontal { background: #e53935; border-radius: 2px; }

        QCalendarWidget QAbstractItemView {
            background-color: #181818;
            color: #d8d8d8;
            selection-background-color: #c62828;
            selection-color: white;
        }
        QCalendarWidget QWidget { background-color: #1c1c1c; color: #d8d8d8; }
        QCalendarWidget QToolButton {
            background: transparent; color: #d8d8d8;
            border: none; border-radius: 5px; padding: 4px 8px;
        }
        QCalendarWidget QToolButton:hover { background: #242424; }
        QCalendarWidget QSpinBox {
            background: #1c1c1c; color: #d8d8d8; border: 1px solid #2c2c2c;
        }
        QCalendarWidget QAbstractItemView:disabled { color: #3a3a3a; }
        QCalendarWidget QWidget#qt_calendar_navigationbar { background-color: #1c1c1c; }

        QToolTip {
            background-color: #1c1c1c; color: #d8d8d8;
            border: 1px solid #2c2c2c; padding: 4px 8px; border-radius: 4px;
        }
        QMessageBox { background-color: #141414; }
        QMessageBox QLabel { color: #d8d8d8; }
        QDialogButtonBox QPushButton { min-width: 80px; }
        QLabel { background: transparent; }
    """)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
