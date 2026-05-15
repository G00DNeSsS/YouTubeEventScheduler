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
        QWidget { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; }
        QPushButton {
            padding: 6px 14px;
            border: 1px solid #ccc;
            border-radius: 4px;
            background: #f8f8f8;
        }
        QPushButton:hover { background: #e8e8e8; }
        QPushButton:pressed { background: #d0d0d0; }
        QLineEdit, QTextEdit, QComboBox {
            border: 1px solid #ccc;
            border-radius: 4px;
            padding: 5px 8px;
            background: white;
        }
        QLineEdit:focus, QTextEdit:focus { border-color: #1a73e8; }
        QTableWidget { gridline-color: #e0e0e0; }
        QHeaderView::section {
            background: #f5f5f5;
            padding: 6px;
            border: none;
            border-bottom: 1px solid #ddd;
            font-weight: bold;
        }
    """)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
