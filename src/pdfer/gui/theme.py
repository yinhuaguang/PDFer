"""界面主题。

刻意保持克制：用 Fusion 风格打底 + 少量 QSS 微调，
不引入任何图片资源，这样打包体积最小、也不会出现高分屏模糊。
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

ACCENT = "#2563eb"
ACCENT_HOVER = "#1d4ed8"
BORDER = "#d9dce3"
TEXT_MUTED = "#6b7280"

_QSS = f"""
QWidget {{
    color: #1f2430;
}}
QMainWindow, QDialog {{
    background: #f6f7f9;
}}
QLabel#hint {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QLabel#sectionTitle {{
    font-size: 14px;
    font-weight: 500;
    padding-bottom: 2px;
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px 12px 10px 12px;
    background: #ffffff;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #374151;
    font-weight: 500;
}}
QPushButton {{
    background: #ffffff;
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 14px;
    min-height: 20px;
}}
QPushButton:hover {{
    background: #f0f4ff;
    border-color: #b9c6e8;
}}
QPushButton:pressed {{
    background: #e3ebfd;
}}
QPushButton:disabled {{
    color: #a8adb8;
    background: #f3f4f6;
    border-color: #e5e7eb;
}}
QPushButton#primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: #ffffff;
    font-weight: 500;
    padding: 6px 20px;
}}
QPushButton#primary:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#primary:disabled {{
    background: #b9c6e8;
    border-color: #b9c6e8;
    color: #f0f4ff;
}}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextBrowser {{
    background: #ffffff;
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: #c7d9f8;
}}
QLineEdit:read-only {{
    background: #fafbfc;
    color: #4b5563;
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    background: #f3f4f6;
    color: #a8adb8;
}}
QListWidget, QTreeWidget {{
    background: #ffffff;
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    border-radius: 6px;
    padding: 4px 6px;
    margin: 1px;
}}
QListWidget::item:selected {{
    background: #dbe7fd;
    color: #12243f;
}}
QListWidget#sidebar {{
    background: transparent;
    border: none;
    font-size: 13px;
    padding: 6px;
}}
QListWidget#sidebar::item {{
    padding: 9px 12px;
    border-radius: 8px;
}}
QListWidget#sidebar::item:selected {{
    background: #dbe7fd;
    color: #14315c;
    font-weight: 500;
}}
QListWidget#sidebar::item:hover:!selected {{
    background: #eef1f6;
}}
QListWidget#pageGrid {{
    border-radius: 8px;
    padding: 8px;
}}
QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: #ffffff;
    height: 14px;
    text-align: center;
    font-size: 11px;
    color: #4b5563;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 5px;
}}
QRadioButton, QCheckBox {{
    spacing: 6px;
}}
QStatusBar {{
    background: #ffffff;
    border-top: 1px solid {BORDER};
}}
QStatusBar::item {{
    border: none;
}}
QMenuBar {{
    background: #ffffff;
    border-bottom: 1px solid {BORDER};
}}
QMenuBar::item:selected {{
    background: #dbe7fd;
    border-radius: 4px;
}}
QMenu {{
    background: #ffffff;
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: #dbe7fd;
}}
QToolTip {{
    background: #1f2430;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
}}
"""


def pick_ui_font() -> QFont:
    """挑选一个能正确显示中文的界面字体。"""
    if sys.platform == "win32":
        candidates = ["Microsoft YaHei UI", "微软雅黑", "Microsoft YaHei", "Segoe UI"]
    elif sys.platform == "darwin":
        candidates = ["PingFang SC", "Helvetica Neue"]
    else:
        candidates = ["Noto Sans CJK SC", "WenQuanYi Micro Hei", "DejaVu Sans"]

    from PySide6.QtGui import QFontDatabase

    families = set(QFontDatabase.families())
    for name in candidates:
        if name in families:
            return QFont(name, 9)
    return QFont()


def apply_theme(app: QApplication) -> None:
    """应用全局主题。需在创建主窗口之前调用。"""
    app.setStyle("Fusion")
    font = pick_ui_font()
    if font.family():
        app.setFont(font)
    app.setStyleSheet(_QSS)
