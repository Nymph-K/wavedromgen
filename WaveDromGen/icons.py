# coding=utf-8
"""Vector icons generated from tiny inline SVG definitions."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .theme import Theme

# Each entry is the inner content of a 24x24 SVG.  ``{c}`` is replaced with
# the requested foreground colour.
_ICONS: dict[str, str] = {
    "new": '<path d="M6 3h8l4 4v14H6z" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M14 3v4h4" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M9 12h6M12 9v6" stroke="{c}" stroke-width="1.6"/>',
    "open": '<path d="M3 6h6l2 2h10v11H3z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/>',
    "save": '<path d="M4 3h13l3 3v15H4z" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M8 3v6h8V3M8 15h8v6H8z" fill="none" stroke="{c}" stroke-width="1.6"/>',
    "export": '<path d="M12 3v12M8 7l4-4 4 4" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M5 14v6h14v-6" fill="none" stroke="{c}" stroke-width="1.6"/>',
    "import": '<path d="M12 15V3M8 11l4 4 4-4" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M5 14v6h14v-6" fill="none" stroke="{c}" stroke-width="1.6"/>',
    "undo": '<path d="M9 7H5v-4" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M5 7a9 9 0 1 1-1 9" fill="none" stroke="{c}" stroke-width="1.6"/>',
    "redo": '<path d="M15 7h4v-4" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M19 7a9 9 0 1 0 1 9" fill="none" stroke="{c}" stroke-width="1.6"/>',
    "add": '<path d="M12 5v14M5 12h14" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>',
    "insert": '<path d="M5 6h14M5 18h14" stroke="{c}" stroke-width="1.6"/><path d="M12 9v6M9 12h6" stroke="{c}" stroke-width="1.8"/>',
    "delete": '<path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/>',
    "duplicate": '<rect x="8" y="8" width="11" height="11" rx="1.5" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M5 16V5h11" fill="none" stroke="{c}" stroke-width="1.6"/>',
    "copy": '<rect x="8" y="8" width="11" height="11" rx="1.5" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M5 16V5h11" fill="none" stroke="{c}" stroke-width="1.6"/>',
    "cut": '<circle cx="7" cy="18" r="2.2" fill="none" stroke="{c}" stroke-width="1.5"/><circle cx="17" cy="18" r="2.2" fill="none" stroke="{c}" stroke-width="1.5"/><path d="M8.5 16.5L18 4M15.5 16.5L6 4" fill="none" stroke="{c}" stroke-width="1.5"/>',
    "paste": '<path d="M9 4h6v3H9z" fill="none" stroke="{c}" stroke-width="1.5"/><path d="M7 6H5v15h14V6h-2" fill="none" stroke="{c}" stroke-width="1.6"/>',
    "up": '<path d="M12 19V5M6 11l6-6 6 6" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
    "down": '<path d="M12 5v14M6 13l6 6 6-6" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
    "settings": '<circle cx="12" cy="12" r="3" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1" stroke="{c}" stroke-width="1.5"/>',
    "help": '<circle cx="12" cy="12" r="9" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M9.5 9a2.6 2.6 0 1 1 4.3 2c-1.1.8-1.8 1.2-1.8 2.4" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/><circle cx="12" cy="17" r="1" fill="{c}"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M15.5 15.5L21 21" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>',
    "theme": '<circle cx="12" cy="12" r="8" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M12 4a8 8 0 0 1 0 16z" fill="{c}"/>',
    "fit": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/>',
    "zoom_in": '<circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M15.5 15.5L21 21M7.5 10.5h6M10.5 7.5v6" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>',
    "zoom_out": '<circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M15.5 15.5L21 21M7.5 10.5h6" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>',
    "wave": '<path d="M2 12h3V7h4v10h4V7h4v10h3" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/>',
    "editor": '<rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M7 9l3 3-3 3M13 15h4" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>',
    "split_v": '<rect x="3" y="3" width="18" height="18" rx="2" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M3 12h18" stroke="{c}" stroke-width="1.5"/>',
    "split_h": '<rect x="3" y="3" width="18" height="18" rx="2" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M12 3v18" stroke="{c}" stroke-width="1.5"/>',
    "live": '<circle cx="12" cy="12" r="4" fill="{c}"/><path d="M6.5 6.5a8 8 0 0 0 0 11M17.5 6.5a8 8 0 0 1 0 11" fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>',
    "format": '<path d="M4 6h16M4 12h10M4 18h16" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/>',
    "wrap": '<path d="M4 6h16M4 12h12a3 3 0 0 1 0 6h-4M4 18h6" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/><path d="M10 16l-2 2 2 2" fill="none" stroke="{c}" stroke-width="1.5"/>',
    "relation": '<circle cx="6" cy="18" r="2.2" fill="none" stroke="{c}" stroke-width="1.5"/><circle cx="18" cy="6" r="2.2" fill="none" stroke="{c}" stroke-width="1.5"/><path d="M7.5 16.5C9 12 12 9 16.5 7.5" fill="none" stroke="{c}" stroke-width="1.6" stroke-dasharray="2 2"/>',
    "ascii": '<path d="M4 5h16v14H4z" fill="none" stroke="{c}" stroke-width="1.5"/><path d="M8 9l-2 3 2 3M16 9l2 3-2 3M13 8l-2 8" fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>',
    "select": '<path d="M6 3l12 9-5.5 1.2L16 20l-2.5 1-3.5-6.5L6 18z" fill="none" stroke="{c}" stroke-width="1.5" stroke-linejoin="round"/>',
    "clk": '<path d="M3 18V7h5v11h5V7h5v11h3" fill="none" stroke="{c}" stroke-width="1.7" stroke-linejoin="miter"/>',
    "sig": '<path d="M3 17h7V7h11" fill="none" stroke="{c}" stroke-width="1.7" stroke-linejoin="miter"/>',
    "bus": '<path d="M4 8h4l3 4-3 4H4l3-4zM11 8h6l3 4-3 4h-6l3-4zM20 8h1" fill="none" stroke="{c}" stroke-width="1.4"/>',
    "x": '<path d="M4 19L19 4M4 4l15 15M4 19h15" fill="none" stroke="{c}" stroke-width="1.5"/><path d="M4 4v15M4 19h15" fill="none" stroke="{c}" stroke-width="1.1" stroke-dasharray="2 2"/>',
    "z": '<path d="M4 12h16" stroke="{c}" stroke-width="1.6"/><path d="M4 12l4-4M4 12l4 4M20 12l-4-4M20 12l-4 4" fill="none" stroke="{c}" stroke-width="1.3"/>',
    "gap": '<path d="M7 4c4 4-4 8 0 16M17 4c-4 4 4 8 0 16" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>',
    "text": '<path d="M5 5h14M12 5v14M8 19h8" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/>',
    "clear": '<path d="M4 15l6-7 8 6-5 5H7z" fill="none" stroke="{c}" stroke-width="1.5" stroke-linejoin="round"/><path d="M14 20h6M13 8l7 5" fill="none" stroke="{c}" stroke-width="1.4"/>',
    "node": '<circle cx="7" cy="17" r="2" fill="none" stroke="{c}" stroke-width="1.6"/><circle cx="17" cy="7" r="2" fill="none" stroke="{c}" stroke-width="1.6"/><path d="M8.5 15.5L15.5 8.5" stroke="{c}" stroke-width="1.5"/>',
    "columns": '<rect x="3" y="4" width="18" height="16" rx="1.5" fill="none" stroke="{c}" stroke-width="1.5"/><path d="M9 4v16M15 4v16M12 8v8M9 12h6" stroke="{c}" stroke-width="1.1"/>',
    "row_props": '<rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="{c}" stroke-width="1.5"/><path d="M7 9h10M7 13h6M7 17h8" stroke="{c}" stroke-width="1.3" stroke-linecap="round"/>',
    "fit_width": '<path d="M3 6v12M21 6v12M6 12h12M9 9l-3 3 3 3M15 9l3 3-3 3" fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
    "recent": '<circle cx="12" cy="12" r="8.5" fill="none" stroke="{c}" stroke-width="1.5"/><path d="M12 7v5l3 2" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>',
    "check": '<path d="M5 12l5 5L20 7" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
}


def _svg(name: str, color: str) -> bytes:
    body = _ICONS[name]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'{body.replace("{c}", color)}</svg>'
    ).encode("utf-8")


@lru_cache(maxsize=512)
def _pixmap(name: str, color: str, size: int) -> QPixmap:
    svg = QSvgRenderer(_svg(name, color))
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    svg.render(painter, QRectF(0, 0, size * scale, size * scale))
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


def make_icon(name: str, theme: Theme, size: int = 20, *, checked_color: QColor | None = None) -> QIcon:
    if name not in _ICONS:
        return QIcon()
    color = theme.text.name()
    accent = (checked_color or theme.accent).name()
    muted = theme.muted.name()
    icon = QIcon()
    icon.addPixmap(_pixmap(name, color, size), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_pixmap(name, accent, size), QIcon.Normal, QIcon.On)
    icon.addPixmap(_pixmap(name, accent, size), QIcon.Active, QIcon.Off)
    icon.addPixmap(_pixmap(name, muted, size), QIcon.Disabled, QIcon.Off)
    return icon


def has_icon(name: str) -> bool:
    return name in _ICONS
