# coding=utf-8
"""Theme definitions and application stylesheet."""
from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Theme:
    name: str
    dark: bool
    background: QColor
    surface: QColor
    surface_alt: QColor
    border: QColor
    text: QColor
    muted: QColor
    accent: QColor
    accent_hover: QColor
    accent_soft: QColor
    success: QColor
    warning: QColor
    danger: QColor
    selection: QColor
    editor_bg: QColor
    editor_line: QColor
    editor_gutter: QColor
    editor_comment: QColor
    editor_key: QColor
    editor_string: QColor
    editor_number: QColor
    editor_keyword: QColor
    editor_punct: QColor

    @property
    def accent_rgb(self) -> tuple[int, int, int]:
        return (self.accent.red(), self.accent.green(), self.accent.blue())


def _c(value: str) -> QColor:
    return QColor(value)


LIGHT = Theme(
    name="light",
    dark=False,
    background=_c("#f4f6f9"),
    surface=_c("#ffffff"),
    surface_alt=_c("#eef2f7"),
    border=_c("#dfe4eb"),
    text=_c("#111827"),
    muted=_c("#667085"),
    accent=_c("#2563eb"),
    accent_hover=_c("#1d4ed8"),
    accent_soft=_c("#e8f0ff"),
    success=_c("#15803d"),
    warning=_c("#b45309"),
    danger=_c("#dc2626"),
    selection=_c("#cfe1ff"),
    editor_bg=_c("#ffffff"),
    editor_line=_c("#f6f8fb"),
    editor_gutter=_c("#f8fafc"),
    editor_comment=_c("#8a94a6"),
    editor_key=_c("#1d4ed8"),
    editor_string=_c("#0f766e"),
    editor_number=_c("#b45309"),
    editor_keyword=_c("#7c3aed"),
    editor_punct=_c("#64748b"),
)

DARK = Theme(
    name="dark",
    dark=True,
    background=_c("#14161a"),
    surface=_c("#1d2026"),
    surface_alt=_c("#262a31"),
    border=_c("#333842"),
    text=_c("#eef1f5"),
    muted=_c("#9aa3b2"),
    accent=_c("#4d9fff"),
    accent_hover=_c("#74b4ff"),
    accent_soft=_c("#1e3048"),
    success=_c("#4ade80"),
    warning=_c("#fbbf24"),
    danger=_c("#f87171"),
    selection=_c("#264a75"),
    editor_bg=_c("#1a1d22"),
    editor_line=_c("#20242b"),
    editor_gutter=_c("#181b20"),
    editor_comment=_c("#7d8798"),
    editor_key=_c("#7cb7ff"),
    editor_string=_c("#7dd3a8"),
    editor_number=_c("#f0b072"),
    editor_keyword=_c("#c4a7ff"),
    editor_punct=_c("#a7b1c2"),
)


def system_is_dark() -> bool:
    if os.name == "nt":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
        except Exception:
            pass
    palette = QApplication.palette()
    return palette.color(QPalette.Window).lightness() < 128


def resolve_theme(name: str) -> Theme:
    if name == "dark":
        return DARK
    if name == "light":
        return LIGHT
    return DARK if system_is_dark() else LIGHT


def ui_font() -> QFont:
    font = QFont("Segoe UI")
    font.setPointSizeF(9.5)
    font.setHintingPreference(QFont.PreferFullHinting)
    return font


def mono_font(size: float = 10.5) -> QFont:
    from PySide6.QtGui import QFontDatabase

    families = set(QFontDatabase.families())
    family = next(
        (name for name in ("Cascadia Mono", "Cascadia Code", "JetBrains Mono", "Consolas", "Courier New") if name in families),
        "Courier New",
    )
    font = QFont(family)
    font.setStyleHint(QFont.Monospace)
    font.setFixedPitch(True)
    font.setPointSizeF(size)
    font.setHintingPreference(QFont.PreferFullHinting)
    return font


def build_palette(theme: Theme) -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, theme.background)
    palette.setColor(QPalette.WindowText, theme.text)
    palette.setColor(QPalette.Base, theme.surface)
    palette.setColor(QPalette.AlternateBase, theme.surface_alt)
    palette.setColor(QPalette.ToolTipBase, theme.surface)
    palette.setColor(QPalette.ToolTipText, theme.text)
    palette.setColor(QPalette.Text, theme.text)
    palette.setColor(QPalette.Button, theme.surface)
    palette.setColor(QPalette.ButtonText, theme.text)
    palette.setColor(QPalette.BrightText, theme.danger)
    palette.setColor(QPalette.Highlight, theme.accent)
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.PlaceholderText, theme.muted)
    palette.setColor(QPalette.Link, theme.accent)
    palette.setColor(QPalette.Disabled, QPalette.Text, theme.muted)
    palette.setColor(QPalette.Disabled, QPalette.WindowText, theme.muted)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, theme.muted)
    return palette


def build_stylesheet(theme: Theme) -> str:
    t = theme
    return f"""
    * {{
        outline: none;
    }}
    QWidget {{
        color: {t.text.name()};
    }}
    QMainWindow, QDialog {{
        background: {t.background.name()};
    }}
    QMenuBar {{
        background: {t.surface.name()};
        border-bottom: 1px solid {t.border.name()};
        padding: 2px 4px;
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 4px 9px;
        border-radius: 4px;
    }}
    QMenuBar::item:selected {{
        background: {t.accent_soft.name()};
        color: {t.text.name()};
    }}
    QMenu {{
        background: {t.surface.name()};
        border: 1px solid {t.border.name()};
        padding: 5px;
    }}
    QMenu::item {{
        padding: 5px 26px 5px 22px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background: {t.accent_soft.name()};
    }}
    QMenu::item:disabled {{
        color: {t.muted.name()};
    }}
    QMenu::separator {{
        height: 1px;
        background: {t.border.name()};
        margin: 5px 8px;
    }}
    QToolBar {{
        background: {t.surface.name()};
        border: none;
        border-bottom: 1px solid {t.border.name()};
        padding: 5px 7px;
        spacing: 4px;
    }}
    QToolBar#ToolRail {{
        border-bottom: none;
        border-right: 1px solid {t.border.name()};
        padding: 6px 5px;
    }}
    QToolBar::separator {{
        width: 1px;
        background: {t.border.name()};
        margin: 5px 5px;
    }}
    QToolBar#ToolRail::separator {{
        height: 1px;
        width: auto;
        margin: 5px 3px;
    }}
    QToolButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 4px 6px;
        color: {t.text.name()};
    }}
    QToolButton:hover {{
        background: {t.surface_alt.name()};
        border-color: {t.border.name()};
    }}
    QToolButton:pressed {{
        background: {t.accent_soft.name()};
    }}
    QToolButton:checked {{
        background: {t.accent_soft.name()};
        border-color: {t.accent.name()};
    }}
    QToolButton:disabled {{
        color: {t.muted.name()};
    }}
    QToolButton#ToolRailButton {{
        padding: 5px 4px;
        font-size: 8pt;
        min-width: 48px;
    }}
    QPushButton {{
        background: {t.surface.name()};
        border: 1px solid {t.border.name()};
        border-radius: 6px;
        padding: 5px 13px;
    }}
    QPushButton:hover {{
        background: {t.surface_alt.name()};
    }}
    QPushButton:pressed {{
        background: {t.accent_soft.name()};
    }}
    QPushButton:default {{
        background: {t.accent.name()};
        color: #ffffff;
        border-color: {t.accent.name()};
    }}
    QPushButton:disabled {{
        color: {t.muted.name()};
    }}
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QKeySequenceEdit {{
        background: {t.surface.name()};
        border: 1px solid {t.border.name()};
        border-radius: 6px;
        padding: 4px 6px;
        selection-background-color: {t.selection.name()};
        selection-color: {t.text.name()};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {t.accent.name()};
    }}
    QComboBox QAbstractItemView {{
        background: {t.surface.name()};
        border: 1px solid {t.border.name()};
        selection-background-color: {t.accent_soft.name()};
        selection-color: {t.text.name()};
    }}
    QScrollArea {{
        background: {t.background.name()};
        border: none;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 12px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {t.border.name()};
        min-height: 26px;
        border-radius: 4px;
        margin: 1px 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {t.muted.name()};
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 12px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {t.border.name()};
        min-width: 26px;
        border-radius: 4px;
        margin: 2px 1px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {t.muted.name()};
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        width: 0; height: 0;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: transparent;
    }}
    QSplitter::handle {{
        background: {t.background.name()};
    }}
    QSplitter::handle:horizontal {{
        width: 6px;
    }}
    QSplitter::handle:vertical {{
        height: 6px;
    }}
    QSplitter::handle:hover {{
        background: {t.accent_soft.name()};
    }}
    QStatusBar {{
        background: {t.surface.name()};
        border-top: 1px solid {t.border.name()};
        color: {t.muted.name()};
        padding: 1px 4px;
    }}
    QStatusBar::item {{
        border: none;
    }}
    QStatusBar QLabel {{
        color: {t.muted.name()};
        padding: 0 5px;
    }}
    QToolTip {{
        background: {t.surface.name()};
        color: {t.text.name()};
        border: 1px solid {t.border.name()};
        padding: 5px 7px;
    }}
    QLabel#SectionTitle {{
        font-size: 11pt;
        font-weight: 600;
    }}
    QLabel#Muted {{
        color: {t.muted.name()};
    }}
    QLabel#Badge {{
        background: {t.accent_soft.name()};
        color: {t.accent.name()};
        border-radius: 5px;
        padding: 2px 7px;
        font-size: 8.5pt;
    }}
    QLabel#ErrorBanner {{
        background: rgba(220, 38, 38, 0.10);
        color: {t.danger.name()};
        border: 1px solid rgba(220, 38, 38, 0.30);
        border-radius: 5px;
        padding: 4px 8px;
    }}
    QWidget#EditorHeader {{
        background: {t.surface.name()};
        border-bottom: 1px solid {t.border.name()};
    }}
    QWidget#FindBar {{
        background: {t.surface.name()};
        border-bottom: 1px solid {t.border.name()};
    }}
    QFrame#Card {{
        background: {t.surface.name()};
        border: 1px solid {t.border.name()};
        border-radius: 8px;
    }}
    QTabWidget::pane {{
        border: 1px solid {t.border.name()};
        border-radius: 6px;
        background: {t.surface.name()};
        top: -1px;
    }}
    QTabBar#DocumentTabs {{
        background: {t.surface.name()};
        border-bottom: 1px solid {t.border.name()};
        qproperty-drawBase: 0;
    }}
    QTabBar#DocumentTabs::tab {{
        padding: 5px 12px;
        margin: 3px 2px 0 2px;
        border: 1px solid transparent;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        color: {t.muted.name()};
        font-size: 9pt;
    }}
    QTabBar#DocumentTabs::tab:selected {{
        background: {t.background.name()};
        border-color: {t.border.name()};
        border-bottom-color: {t.background.name()};
        color: {t.text.name()};
    }}
    QTabBar#DocumentTabs::tab:hover {{
        color: {t.text.name()};
    }}
    QTabBar::tab {{
        background: transparent;
        padding: 6px 14px;
        border: 1px solid transparent;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        color: {t.muted.name()};
    }}
    QTabBar::tab:selected {{
        background: {t.surface.name()};
        border-color: {t.border.name()};
        border-bottom-color: {t.surface.name()};
        color: {t.text.name()};
    }}
    QTabBar::tab:hover {{
        color: {t.text.name()};
    }}
    QTableWidget, QTreeWidget, QListWidget {{
        background: {t.surface.name()};
        border: 1px solid {t.border.name()};
        border-radius: 6px;
        gridline-color: {t.border.name()};
        selection-background-color: {t.accent_soft.name()};
        selection-color: {t.text.name()};
    }}
    QHeaderView::section {{
        background: {t.surface_alt.name()};
        color: {t.muted.name()};
        border: none;
        border-bottom: 1px solid {t.border.name()};
        padding: 5px 6px;
        font-weight: 600;
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 15px;
        height: 15px;
    }}
    QGroupBox {{
        border: 1px solid {t.border.name()};
        border-radius: 7px;
        margin-top: 8px;
        padding-top: 8px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: {t.muted.name()};
    }}
    QProgressBar {{
        border: 1px solid {t.border.name()};
        border-radius: 5px;
        background: {t.surface_alt.name()};
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {t.accent.name()};
        border-radius: 4px;
    }}
    """


def apply_theme(app: QApplication, theme: Theme, *, mono_size: float = 10.5) -> None:
    app.setStyle("Fusion")
    app.setPalette(build_palette(theme))
    app.setFont(ui_font())
    app.setStyleSheet(build_stylesheet(theme))
    QApplication.setFont(ui_font())
