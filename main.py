"""Entry point do Cadastro Auto."""
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

import database as db
from gui.main_window import MainWindow
from gui.styles import STYLE


def main() -> int:
    db.init_db()

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Segoe UI", 10))

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
