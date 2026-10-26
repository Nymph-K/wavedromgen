# coding=utf-8
"""WaveDrom skin loading and QPainter symbol drawing.

The skin data in ``resources/skins.json`` is generated from the official
WaveDrom skins (MIT licensed).  It contains the exact 20x20 SVG symbols that
WaveDrom uses for every waveform transition, so our Qt renderer can reproduce
the original diagrams without depending on a browser or SVG rasteriser.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen

from .svgpath import PathOp, parse_path

_RESOURCE = Path(__file__).resolve().parent / "resources" / "skins.json"


@dataclass(frozen=True)
class Symbol:
    paths: tuple[tuple[QPainterPath, dict[str, str]], ...] = ()
    rects: tuple[tuple[QRectF, dict[str, str]], ...] = ()


def _parse_style(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not text:
        return result
    for part in text.split(";"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            result[key] = value
    return result


def _to_path(ops: list[PathOp]) -> QPainterPath:
    path = QPainterPath()
    for op in ops:
        vals = op.values
        if op.kind == "M":
            path.moveTo(vals[0], vals[1])
        elif op.kind == "L":
            path.lineTo(vals[0], vals[1])
        elif op.kind == "C":
            path.cubicTo(vals[0], vals[1], vals[2], vals[3], vals[4], vals[5])
        elif op.kind == "Q":
            path.quadTo(vals[0], vals[1], vals[2], vals[3])
        elif op.kind == "A":
            path.lineTo(vals[5], vals[6])
        elif op.kind == "Z":
            path.closeSubpath()
    return path


def _color(value: str | None, fallback: QColor | None = None) -> QColor | None:
    if value is None:
        return fallback
    value = value.strip()
    if value in ("none", "transparent"):
        return None
    color = QColor(value)
    if not color.isValid():
        if value == "white":
            color = QColor("#ffffff")
        elif value == "black":
            color = QColor("#000000")
        else:
            return fallback
    return color


def _num(value: str | None, fallback: float) -> float:
    if value is None:
        return fallback
    try:
        return float(str(value).replace("px", "").strip())
    except ValueError:
        return fallback


class Skin:
    def __init__(self, name: str, data: dict):
        self.name = name
        self._classes: dict[str, dict[str, str]] = data.get("classes", {})
        self._base: dict[str, str] = data.get("base", {})
        self._symbols_raw: dict[str, list[dict]] = data.get("symbols", {})
        self.socket = data.get("socket", {"width": 20, "height": 20, "x": 6, "y": 15})
        self._symbols: dict[str, Symbol] = {}
        for symbol_id, items in self._symbols_raw.items():
            paths: list[tuple[QPainterPath, dict[str, str]]] = []
            rects: list[tuple[QRectF, dict[str, str]]] = []
            for item in items:
                style = _parse_style(item.get("style") or "")
                if "d" in item:
                    try:
                        path = _to_path(parse_path(item["d"]))
                    except ValueError:
                        continue
                    paths.append((path, {**(self._classes.get(item.get("cls") or "", {})), **style}))
                elif "rect" in item:
                    rect = item["rect"]
                    rects.append(
                        (
                            QRectF(
                                _num(rect.get("x"), 0.0),
                                _num(rect.get("y"), 0.0),
                                _num(rect.get("width"), 0.0),
                                _num(rect.get("height"), 0.0),
                            ),
                            style,
                        )
                    )
            self._symbols[symbol_id] = Symbol(tuple(paths), tuple(rects))
        self.background = self._background_color()
        self.text_color = self._text_color()
        self.name_color = _color(self._classes.get("info", {}).get("fill"), QColor("#0041c4")) or QColor("#0041c4")
        self.muted_color = _color(self._classes.get("muted", {}).get("fill"), QColor("#888888")) or QColor("#888888")

    def _background_color(self) -> QColor:
        if self.name == "dark":
            return QColor("#1e1e1e")
        return QColor("#ffffff")

    def _text_color(self) -> QColor:
        fill = _color(self._base.get("fill"))
        return fill or QColor("#000000")

    @property
    def dark(self) -> bool:
        return self.background.lightness() < 128

    def has_symbol(self, symbol_id: str) -> bool:
        return symbol_id in self._symbols

    def draw_symbol(self, painter: QPainter, symbol_id: str, x: float, y: float, scale: float) -> bool:
        symbol = self._symbols.get(symbol_id)
        if symbol is None:
            return False
        painter.save()
        painter.translate(x, y)
        painter.scale(scale, scale)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for path, style in symbol.paths:
            self._apply_style(painter, style)
            painter.drawPath(path)
        for rect, style in symbol.rects:
            self._apply_style(painter, style)
            painter.drawRect(rect)
        painter.restore()
        return True

    def _apply_style(self, painter: QPainter, style: dict[str, str]) -> None:
        fill = _color(style.get("fill"), QColor(0, 0, 0, 0))
        if fill is None or fill.alpha() == 0:
            painter.setBrush(Qt.NoBrush)
        else:
            fill = QColor(fill)
            opacity = _num(style.get("fill-opacity"), 1.0)
            fill.setAlphaF(max(0.0, min(1.0, opacity)))
            painter.setBrush(QBrush(fill))

        stroke = _color(style.get("stroke"))
        if stroke is None:
            painter.setPen(Qt.NoPen)
            return
        pen = QPen(stroke)
        pen.setWidthF(max(0.1, _num(style.get("stroke-width"), 1.0)))
        pen.setCapStyle(Qt.RoundCap if style.get("stroke-linecap") == "round" else Qt.SquareCap)
        join = style.get("stroke-linejoin", "miter")
        pen.setJoinStyle(Qt.RoundJoin if join == "round" else (Qt.BevelJoin if join == "bevel" else Qt.MiterJoin))
        opacity = _num(style.get("stroke-opacity"), 1.0)
        if "color" in style and stroke.alpha() == 255:
            pass
        stroke_color = QColor(stroke)
        stroke_color.setAlphaF(max(0.0, min(1.0, stroke.alphaF() * opacity)))
        pen.setColor(stroke_color)
        dash = style.get("stroke-dasharray")
        if dash and dash.strip() not in ("none", "0"):
            values = [float(v) for v in dash.replace(",", " ").split() if _is_number(v)]
            if values:
                pen.setDashPattern([max(0.1, v) for v in values])
        painter.setPen(pen)


def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


@lru_cache(maxsize=1)
def _load_all() -> dict[str, dict]:
    try:
        with _RESOURCE.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=16)
def get_skin(name: str | None) -> Skin:
    data = _load_all()
    if name not in data:
        name = "default" if "default" in data else next(iter(data), "default")
    return Skin(name or "default", data.get(name, {}))


def available_skins() -> list[str]:
    return sorted(_load_all().keys())


def font_for_skin(skin: Skin, scale: float = 1.0, *, bold: bool = False) -> QFont:
    font = QFont("Segoe UI")
    font.setPixelSize(max(8, int(round(13 * scale))))
    font.setBold(bold)
    font.setHintingPreference(QFont.PreferFullHinting)
    return font


def palette_for_skin(skin: Skin) -> dict[str, QColor]:
    return {
        "background": skin.background,
        "text": skin.text_color,
        "name": skin.name_color,
        "muted": skin.muted_color,
        "grid": QColor(skin.text_color.red(), skin.text_color.green(), skin.text_color.blue(), 38),
    }
