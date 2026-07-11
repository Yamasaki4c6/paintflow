"""app.py — エントリポイント"""
import sys

from PySide6.QtWidgets import QApplication

from studio import theme
from studio.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Paintflow Studio")
    theme.apply(app)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
