"""theme.py — ダークテーマ(DCCツール風)"""
from PySide6.QtWidgets import QApplication

ACCENT = "#4aa3ff"

STYLE = f"""
* {{ font-family: "Yu Gothic UI", "Meiryo UI", sans-serif; font-size: 12px; }}
QMainWindow, QDialog {{ background: #2b2b2f; }}
QWidget {{ background: #2b2b2f; color: #d8d8dc; }}
QDockWidget::title {{ background: #232326; padding: 5px 8px;
    border-bottom: 1px solid #1b1b1e; }}
QGroupBox {{ border: 1px solid #3c3c42; border-radius: 6px;
    margin-top: 10px; padding: 8px 6px 6px 6px; background: #303034; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px;
    color: #9fc2ea; }}
QLabel {{ background: transparent; }}
QPushButton {{ background: #3d3d44; border: 1px solid #55555e;
    border-radius: 4px; padding: 4px 12px; }}
QPushButton:hover {{ background: #4a4a53; border-color: {ACCENT}; }}
QPushButton:pressed, QPushButton:checked {{ background: {ACCENT};
    color: #101014; }}
QToolBar {{ background: #232326; border: 0; spacing: 4px; padding: 4px; }}
QToolButton {{ background: transparent; border-radius: 4px; padding: 4px 8px; }}
QToolButton:hover {{ background: #3d3d44; }}
QToolButton:checked {{ background: {ACCENT}; color: #101014; }}
QSlider::groove:horizontal {{ height: 4px; background: #45454c;
    border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 12px; margin: -5px 0;
    border-radius: 6px; background: #c3c3cc; }}
QSlider::handle:horizontal:hover {{ background: {ACCENT}; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit {{ background: #232327;
    border: 1px solid #4a4a52; border-radius: 4px; padding: 2px 6px; }}
QComboBox QAbstractItemView {{ background: #232327;
    selection-background-color: {ACCENT}; }}
QListWidget {{ background: #232327; border: 1px solid #3c3c42;
    border-radius: 4px; }}
QListWidget::item {{ padding: 5px 8px; }}
QListWidget::item:selected {{ background: {ACCENT}; color: #101014;
    border-radius: 3px; }}
QScrollArea {{ border: 0; }}
QScrollBar:vertical {{ background: #2b2b2f; width: 10px; }}
QScrollBar::handle:vertical {{ background: #4a4a52; border-radius: 5px;
    min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QStatusBar {{ background: #232326; color: #9a9aa2; }}
QMenuBar {{ background: #232326; }}
QMenuBar::item:selected {{ background: #3d3d44; }}
QMenu {{ background: #2f2f34; border: 1px solid #4a4a52; }}
QMenu::item:selected {{ background: {ACCENT}; color: #101014; }}
QProgressDialog {{ background: #2b2b2f; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border-radius: 3px;
    border: 1px solid #55555e; background: #232327; }}
QCheckBox::indicator:checked {{ background: {ACCENT};
    border-color: {ACCENT}; }}
"""


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
