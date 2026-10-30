# coding=utf-8
"""QPainter renderer for the interactive WaveDrom diagram."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)

from .layout import DiagramLayout, EditTarget
from .model import Selection, WaveDocument
from .skins import Skin, font_for_skin, get_skin
from .wavedrom_render import (
    BRICK_SIZE,
    LABEL_X,
    WAVE_TOP,
)

EDGE_COLOR = QColor("#0041c4")


@dataclass
class CanvasColors:
    accent: QColor = field(default_factory=lambda: QColor("#2563eb"))
    accent_soft: QColor = field(default_factory=lambda: QColor(37, 99, 235, 38))
    hover: QColor = field(default_factory=lambda: QColor(37, 99, 235, 18))
    row_alt: QColor = field(default_factory=lambda: QColor(15, 23, 42, 6))
    gutter: QColor = field(default_factory=lambda: QColor("#f6f7f9"))
    header: QColor = field(default_factory=lambda: QColor("#f6f7f9"))
    border: QColor = field(default_factory=lambda: QColor("#e2e6ec"))
    muted: QColor = field(default_factory=lambda: QColor("#8a93a3"))
    danger: QColor = field(default_factory=lambda: QColor("#e5484d"))
    white: QColor = field(default_factory=lambda: QColor("#ffffff"))
    text: QColor = field(default_factory=lambda: QColor("#111827"))


@dataclass
class DragState:
    active: bool = False
    source_rows: tuple[int, ...] = ()
    target_index: int = 0
    label: str = ""


@dataclass
class PaintState:
    selection: Selection | None = None
    active_cell: tuple[int, int] | None = None
    hover_cell: tuple[int, int] | None = None
    row_selection: tuple[int, ...] | None = None
    drag: DragState = field(default_factory=DragState)
    editing_target: EditTarget | None = None
    focused: bool = True
    show_chrome: bool = True
    show_selection: bool = True
    insert_mode: bool = False
    compact: bool = False

    def row_selected(self, index: int) -> bool:
        return bool(self.row_selection) and index in self.row_selection


class WaveRenderer:
    """Draws a :class:`WaveDocument` using WaveDrom's own skin symbols."""

    def __init__(self, colors: CanvasColors | None = None):
        self.colors = colors or CanvasColors()

    # ------------------------------------------------------------------
    def paint(self, painter: QPainter, layout: DiagramLayout, state: PaintState) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        skin = layout.skin or get_skin(layout.doc.skin_name())
        bg = skin.background
        painter.fillRect(QRectF(0, 0, layout.width, layout.height), bg)
        colors = self._colors_for(skin)

        rows_bottom = layout.rows_top + max(1, len(layout.rows)) * layout.row_height
        if layout.chrome:
            self._paint_chrome_background(painter, layout, colors)
        self._paint_grid(painter, layout, colors, rows_bottom)
        self._paint_head_tail(painter, layout, colors, skin, rows_bottom)
        self._paint_row_backgrounds(painter, layout, colors, state)
        self._paint_waveforms(painter, layout, skin)
        self._paint_gaps(painter, layout, skin)
        if state.show_selection:
            self._paint_selection(painter, layout, state, colors)
        if layout.groups:
            self._paint_groups(painter, layout, skin, colors, state)
        self._paint_names(painter, layout, skin, state)
        self._paint_data_labels(painter, layout, skin, state)
        self._paint_nodes_and_edges(painter, layout, skin, colors)
        if state.insert_mode:
            self._paint_insert_caret(painter, layout, state, colors)
        if layout.chrome:
            self._paint_chrome_foreground(painter, layout, colors, state)
        if state.drag.active:
            self._paint_drag(painter, layout, state.drag, colors)
        if not layout.rows:
            self._paint_empty_state(painter, layout, colors, skin)
        painter.restore()

    # ------------------------------------------------------------------
    def _colors_for(self, skin: Skin) -> CanvasColors:
        colors = CanvasColors()
        colors.accent = self.colors.accent
        colors.accent_soft = self.colors.accent_soft
        colors.hover = self.colors.hover
        if skin.dark:
            colors.gutter = QColor("#25272b")
            colors.header = QColor("#25272b")
            colors.border = QColor("#3a3d44")
            colors.muted = QColor("#9aa1ad")
            colors.text = QColor("#f3f4f6")
            colors.row_alt = QColor(255, 255, 255, 8)
            colors.white = QColor("#1e1e1e")
        else:
            colors.gutter = self.colors.gutter
            colors.header = self.colors.header
            colors.border = self.colors.border
            colors.muted = self.colors.muted
            colors.text = skin.text_color
            colors.row_alt = self.colors.row_alt
            colors.white = QColor("#ffffff")
        return colors

    # ------------------------------------------------------------------
    def _paint_chrome_background(self, painter: QPainter, layout: DiagramLayout, colors: CanvasColors) -> None:
        rows_bottom = layout.rows_top + max(1, len(layout.rows)) * layout.row_height + layout.foot_height
        painter.fillRect(QRectF(0, 0, layout.gutter_width, rows_bottom), colors.gutter)
        painter.fillRect(QRectF(0, 0, layout.width, layout.header_height), colors.header)
        painter.setPen(QPen(colors.border, 1.0))
        painter.drawLine(QPointF(layout.gutter_width, 0), QPointF(layout.gutter_width, rows_bottom))
        painter.drawLine(QPointF(0, layout.header_height), QPointF(layout.width, layout.header_height))
        painter.drawLine(QPointF(0, layout.header_height - 1), QPointF(layout.gutter_width, layout.header_height - 1))

    def _paint_grid(self, painter: QPainter, layout: DiagramLayout, colors: CanvasColors, rows_bottom: float) -> None:
        pen = QPen(colors.border)
        pen.setWidthF(1.0)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        units = max(layout.display_units, 1)
        for unit in range(0, units + 1):
            x = layout.time_grid_x(unit)
            if x > layout.width:
                break
            painter.drawLine(QPointF(x, layout.rows_top), QPointF(x, rows_bottom))
        painter.setPen(QPen(colors.border, 1.0))
        for index in range(len(layout.rows) + 1):
            y = layout.rows_top + index * layout.row_height
            painter.drawLine(QPointF(layout.gutter_width, y), QPointF(layout.width, y))

    def _paint_row_backgrounds(
        self,
        painter: QPainter,
        layout: DiagramLayout,
        colors: CanvasColors,
        state: PaintState,
    ) -> None:
        if not layout.chrome:
            return
        for row in layout.rows:
            if row.index % 2:
                painter.fillRect(
                    QRectF(layout.gutter_width, row.slot_top, layout.width - layout.gutter_width, layout.row_height),
                    colors.row_alt,
                )
            if state.row_selected(row.index):
                painter.fillRect(
                    QRectF(0, row.slot_top, layout.width, layout.row_height),
                    QColor(colors.accent.red(), colors.accent.green(), colors.accent.blue(), 26),
                )
                painter.fillRect(
                    QRectF(0, row.slot_top, 3.0 * layout.zoom, layout.row_height),
                    colors.accent,
                )
            if state.hover_cell and state.hover_cell[0] == row.index:
                painter.fillRect(
                    QRectF(layout.gutter_width, row.slot_top, layout.width - layout.gutter_width, layout.row_height),
                    colors.hover,
                )
                col = state.hover_cell[1]
                if 0 <= col < len(row.row.wave):
                    painter.fillRect(row.char_rect(col, layout.row_height), colors.hover)

    def _paint_waveforms(self, painter: QPainter, layout: DiagramLayout, skin: Skin) -> None:
        painter.save()
        clip = QRectF(
            layout.wave_origin,
            layout.rows_top,
            max(0.0, layout.width - layout.wave_origin),
            max(0.0, layout.foot_height + len(layout.rows) * layout.row_height),
        )
        painter.setClipRect(clip)
        z = layout.zoom
        for row_layout in layout.rows:
            y = row_layout.slot_top + WAVE_TOP * z
            x_base = layout.wave_origin + row_layout.bricks.x_offset * BRICK_SIZE * z
            for index, brick in enumerate(row_layout.bricks.bricks):
                if not brick:
                    continue
                skin.draw_symbol(
                    painter,
                    brick,
                    x_base + index * BRICK_SIZE * z,
                    y,
                    z,
                )
        painter.restore()

    # ------------------------------------------------------------------
    def _paint_gaps(self, painter: QPainter, layout: DiagramLayout, skin: Skin) -> None:
        z = layout.zoom
        hscale = layout.doc.hscale()
        painter.save()
        painter.setClipRect(
            QRectF(
                layout.wave_origin,
                layout.rows_top,
                max(0.0, layout.width - layout.wave_origin),
                len(layout.rows) * layout.row_height,
            )
        )
        for row_layout in layout.rows:
            row = row_layout.row
            wave = row.wave
            if not wave or "|" not in wave:
                continue
            period = max(1, row.period)
            for index, char in enumerate(wave):
                if char != "|":
                    continue
                center = (
                    layout.wave_origin
                    + (hscale * (2 * index * period + period) - 2 * row.phase) * BRICK_SIZE * z
                )
                y = row_layout.slot_top + WAVE_TOP * z
                if skin.has_symbol("gap"):
                    skin.draw_symbol(painter, "gap", center, y, z)
                else:
                    pen = QPen(skin.text_color, max(1.0, z))
                    painter.setPen(pen)
                    painter.drawLine(QPointF(center - 3 * z, y), QPointF(center - 3 * z, y + 20 * z))
                    painter.drawLine(QPointF(center + 3 * z, y), QPointF(center + 3 * z, y + 20 * z))
        # config.gaps vertical separators
        gaps = layout.doc.gaps.strip()
        if gaps:
            scale = layout.time_unit_width
            rows_bottom = layout.rows_top + len(layout.rows) * layout.row_height
            for index, char in enumerate(gaps.split()):
                if char in (".", ""):
                    continue
                center = layout.wave_origin + (index + (0.5 if char.islower() else 0.0)) * scale
                self._paint_gap_mark(painter, center, layout.rows_top, rows_bottom, char, layout, skin)
        painter.restore()

    def _paint_gap_mark(
        self,
        painter: QPainter,
        x: float,
        top: float,
        bottom: float,
        char: str,
        layout: DiagramLayout,
        skin: Skin,
    ) -> None:
        z = layout.zoom
        width = 6 * z if char in "0123|" else 9 * z
        painter.fillRect(
            QRectF(x - width / 2, top, width, bottom - top),
            QColor(skin.background.red(), skin.background.green(), skin.background.blue(), 215),
        )
        pen = QPen(skin.text_color, max(1.0, z))
        painter.setPen(pen)
        if char in "|1":
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        elif char == "2":
            painter.drawLine(QPointF(x - 2 * z, top), QPointF(x - 2 * z, bottom))
            painter.drawLine(QPointF(x + 2 * z, top), QPointF(x + 2 * z, bottom))
        elif char == "3":
            for offset in (-3, 0, 3):
                painter.drawLine(QPointF(x + offset * z, top), QPointF(x + offset * z, bottom))
        else:
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))

    # ------------------------------------------------------------------
    def _paint_selection(
        self,
        painter: QPainter,
        layout: DiagramLayout,
        state: PaintState,
        colors: CanvasColors,
    ) -> None:
        selection = state.selection
        if selection is None:
            return
        sel = selection.normalized()
        painter.save()
        painter.setClipRect(
            QRectF(
                layout.wave_origin,
                layout.rows_top,
                max(0.0, layout.width - layout.wave_origin),
                max(1, len(layout.rows)) * layout.row_height,
            )
        )
        for row_index in range(sel.row0, sel.row1 + 1):
            if row_index < 0 or row_index >= len(layout.rows):
                continue
            row = layout.rows[row_index]
            col0 = max(0, sel.col0)
            col1 = max(col0, sel.col1)
            if col1 < col0:
                continue
            x0 = row.char_x(col0)
            x1 = row.char_x(col1 + 1)
            rect = QRectF(x0, row.slot_top + 1.5 * layout.zoom, x1 - x0, layout.row_height - 3 * layout.zoom)
            painter.fillRect(rect, colors.accent_soft)
            pen = QPen(colors.accent, max(1.0, layout.zoom))
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
            # Cell separators make multi-cell selections easy to read.
            pen = QPen(QColor(colors.accent.red(), colors.accent.green(), colors.accent.blue(), 80), 1.0)
            painter.setPen(pen)
            for col in range(col0 + 1, col1 + 1):
                x = row.char_x(col)
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        painter.restore()

        if state.active_cell:
            row_index, col = state.active_cell
            if 0 <= row_index < len(layout.rows):
                row = layout.rows[row_index]
                if 0 <= col <= layout.max_column():
                    rect = row.char_rect(col, layout.row_height).adjusted(1, 1, -1, -1)
                    pen = QPen(colors.accent, max(1.5, 2.0 * layout.zoom))
                    painter.setPen(pen)
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRoundedRect(rect, 3 * layout.zoom, 3 * layout.zoom)

    # ------------------------------------------------------------------
    def _paint_groups(
        self,
        painter: QPainter,
        layout: DiagramLayout,
        skin: Skin,
        colors: CanvasColors,
        state: PaintState,
    ) -> None:
        """Draw WaveDrom signal groups: a rounded bracket plus a rotated name."""
        z = layout.zoom
        font = font_for_skin(skin, 0.74 * z)
        painter.save()
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        info = QColor("#5b8def") if skin.dark else QColor("#0041c4")
        selected_rows = set(state.row_selection or ())
        for group in layout.groups:
            rows = range(group.span.start, group.span.end + 1)
            selected = bool(selected_rows) and all(index in selected_rows for index in rows)
            color = colors.accent if selected else info
            x = group.x
            top = group.top
            bottom = group.bottom
            radius = max(2.0, 5.0 * z)
            path = QPainterPath()
            path.moveTo(x, top)
            path.cubicTo(x - radius * 0.6, top, x - radius, top + radius * 0.5, x - radius, top + radius)
            path.lineTo(x - radius, max(top + radius, bottom - radius))
            path.cubicTo(x - radius, bottom - radius * 0.5, x - radius * 0.6, bottom, x, bottom)
            if selected:
                painter.fillRect(
                    QRectF(x - radius - 2 * z, top, radius + 3 * z, max(1.0, bottom - top)),
                    QColor(colors.accent.red(), colors.accent.green(), colors.accent.blue(), 36),
                )
            pen = QPen(color, max(1.0, 1.15 * z))
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
            name = group.name
            if not name:
                continue
            painter.save()
            painter.translate(group.name_x, (top + bottom) / 2.0)
            painter.rotate(-90)
            # WaveDrom renders the full group name.  Only extremely long names
            # are elided so that adjacent groups remain distinguishable.
            max_width = max(200.0 * z, bottom - top)
            if metrics.horizontalAdvance(name) > max_width:
                text = metrics.elidedText(name, Qt.ElideRight, int(max_width))
            else:
                text = name
            width = metrics.horizontalAdvance(text) + 4.0 * z
            painter.setPen(QPen(color if selected else skin.name_color))
            painter.drawText(
                QRectF(-width / 2.0, -metrics.height() / 2.0, width, metrics.height()),
                int(Qt.AlignCenter | Qt.TextSingleLine),
                text,
            )
            painter.restore()
        painter.restore()

    # ------------------------------------------------------------------
    def _paint_insert_caret(
        self,
        painter: QPainter,
        layout: DiagramLayout,
        state: PaintState,
        colors: CanvasColors,
    ) -> None:
        """Show where insert mode will push the next waveform character."""
        if state.active_cell is None:
            return
        row_index, col = state.active_cell
        if row_index < 0 or row_index >= len(layout.rows):
            return
        rows = [row_index]
        if state.selection is not None:
            sel = state.selection.normalized()
            rows = [
                index
                for index in range(sel.row0, sel.row1 + 1)
                if 0 <= index < len(layout.rows)
            ]
        elif state.row_selection:
            rows = [index for index in state.row_selection if 0 <= index < len(layout.rows)]
        if not rows:
            return
        z = layout.zoom
        painter.save()
        painter.setClipRect(
            QRectF(
                layout.wave_origin,
                layout.rows_top,
                max(0.0, layout.width - layout.wave_origin),
                max(1, len(layout.rows)) * layout.row_height,
            )
        )
        top = layout.rows[rows[0]].slot_top + 2.0 * z
        bottom = layout.rows[rows[-1]].slot_top + layout.row_height - 2.0 * z
        accent = colors.accent
        band = QColor(accent.red(), accent.green(), accent.blue(), 34)
        painter.setPen(Qt.NoPen)
        painter.setBrush(band)
        for index in rows:
            row = layout.rows[index]
            x = row.char_x(col)
            painter.fillRect(
                QRectF(x, row.slot_top + 1.5 * z, row.char_width, layout.row_height - 3.0 * z),
                band,
            )
        x = layout.rows[rows[0]].char_x(col)
        pen = QPen(accent, max(1.5, 2.0 * z))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        # Small I-beam caps make the insertion column obvious even on clocks.
        cap = max(3.0, 4.0 * z)
        painter.drawLine(QPointF(x - cap, top), QPointF(x + cap, top))
        painter.drawLine(QPointF(x - cap, bottom), QPointF(x + cap, bottom))
        painter.setBrush(accent)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(x, top), max(1.5, 2.0 * z), max(1.5, 2.0 * z))
        painter.restore()

    # ------------------------------------------------------------------
    def _paint_names(
        self,
        painter: QPainter,
        layout: DiagramLayout,
        skin: Skin,
        state: PaintState,
    ) -> None:
        font = layout.name_font or font_for_skin(skin, layout.zoom)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        z = layout.zoom
        for row_layout in layout.rows:
            row = row_layout.row
            text = row.name
            color = skin.name_color
            if not text:
                if not layout.placeholder or not row.shows_placeholder_name:
                    # Bare ``{}`` spacer lanes and node-only lanes stay blank.
                    if layout.chrome:
                        self._paint_handle(
                            painter,
                            row_layout.handle_x,
                            row_layout.slot_top + layout.row_height / 2,
                            z,
                            skin,
                        )
                    continue
                text = "signal"
                color = QColor(skin.muted_color)
            painter.setPen(QPen(color))
            rect = QRectF(
                row_layout.name_rect.left(),
                row_layout.slot_top + 3 * z,
                max(20.0, layout.wave_origin - row_layout.name_rect.left() - 8 * z),
                layout.row_height - 6 * z,
            )
            flags = int(Qt.AlignRight | Qt.AlignVCenter | Qt.TextSingleLine)
            painter.drawText(rect, flags, metrics.elidedText(text, Qt.ElideMiddle, int(rect.width())))
            # A small move handle at a fixed position, so long names never
            # shift the drag affordance.
            if layout.chrome:
                self._paint_handle(
                    painter,
                    row_layout.handle_x,
                    row_layout.slot_top + layout.row_height / 2,
                    z,
                    skin,
                )

    def _paint_handle(self, painter: QPainter, x: float, y: float, z: float, skin: Skin) -> None:
        color = QColor(skin.muted_color)
        color.setAlpha(130)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        radius = 1.15 * z
        for row in (-1, 0, 1):
            for col in (0, 1):
                painter.drawEllipse(QPointF(x + col * 4.0 * z, y + row * 4.5 * z), radius, radius)

    # ------------------------------------------------------------------
    def _paint_data_labels(
        self,
        painter: QPainter,
        layout: DiagramLayout,
        skin: Skin,
        state: PaintState,
    ) -> None:
        font = layout.data_font or font_for_skin(skin, layout.zoom)
        painter.setFont(font)
        z = layout.zoom
        for row_layout in layout.rows:
            for target in row_layout.data_targets:
                if target.text:
                    painter.setPen(QPen(skin.text_color))
                    rect = target.rect.adjusted(2 * z, 0, -2 * z, 0)
                    painter.drawText(
                        rect,
                        int(Qt.AlignCenter | Qt.TextSingleLine),
                        target.text,
                    )
                elif layout.placeholder:
                    rect = target.rect
                    pen = QPen(QColor(skin.muted_color.red(), skin.muted_color.green(), skin.muted_color.blue(), 150))
                    pen.setStyle(Qt.DashLine)
                    painter.setPen(pen)
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRoundedRect(rect.adjusted(3 * z, 1 * z, -3 * z, -1 * z), 4 * z, 4 * z)
                    painter.setPen(QPen(QColor(skin.muted_color.red(), skin.muted_color.green(), skin.muted_color.blue(), 180)))
                    painter.drawText(rect, int(Qt.AlignCenter | Qt.TextSingleLine), "data")

    # ------------------------------------------------------------------
    def _paint_nodes_and_edges(
        self,
        painter: QPainter,
        layout: DiagramLayout,
        skin: Skin,
        colors: CanvasColors,
    ) -> None:
        nodes = self._node_positions(layout)
        if not nodes:
            return
        painter.save()
        painter.setClipRect(
            QRectF(
                layout.wave_origin,
                layout.rows_top,
                max(0.0, layout.width - layout.wave_origin),
                max(1, len(layout.rows)) * layout.row_height,
            )
        )
        self._paint_edges(painter, layout, nodes, colors)
        font = font_for_skin(skin, layout.zoom * 0.82)
        painter.setFont(font)
        for name, (point, is_lower) in nodes.items():
            if not is_lower:
                continue
            painter.setPen(QPen(skin.text_color))
            painter.setBrush(Qt.NoBrush)
            rect = QRectF(point.x() - 8 * layout.zoom, point.y() - 16 * layout.zoom, 16 * layout.zoom, 14 * layout.zoom)
            painter.drawText(rect, int(Qt.AlignCenter), name)
        painter.restore()

    def _node_positions(self, layout: DiagramLayout) -> dict[str, tuple[QPointF, bool]]:
        nodes: dict[str, tuple[QPointF, bool]] = {}
        hscale = layout.doc.hscale()
        z = layout.zoom
        for row in layout.rows:
            for col, char in enumerate(row.row.node):
                if char == "." or char.isspace() or not char:
                    continue
                period = max(1, row.row.period)
                x = layout.wave_origin + (
                    BRICK_SIZE * (2 * col * period * hscale - 2 * row.row.phase) + LABEL_X
                ) * z
                y = row.slot_top + (WAVE_TOP + 10) * z
                nodes.setdefault(char, (QPointF(x, y), char.islower()))
        return nodes

    def _paint_edges(
        self,
        painter: QPainter,
        layout: DiagramLayout,
        nodes: dict[str, tuple[QPointF, bool]],
        colors: CanvasColors,
    ) -> None:
        z = layout.zoom
        for edge in layout.doc.edges:
            if not isinstance(edge, str):
                continue
            parts = edge.strip().split(" ", 1)
            if not parts:
                continue
            head = parts[0]
            label = parts[1] if len(parts) > 1 else ""
            if len(head) < 2:
                continue
            start_name, end_name = head[0], head[-1]
            shape = head[1:-1] or "-"
            if start_name not in nodes or end_name not in nodes:
                continue
            start = nodes[start_name][0]
            end = nodes[end_name][0]
            path, label_point = _edge_path(start, end, shape)
            arrow_start = "<" in shape
            arrow_end = ">" in shape
            tee = shape == "+"
            pen_color = EDGE_COLOR
            pen = QPen(pen_color, max(1.0, z))
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
            if arrow_end:
                _draw_arrowhead(painter, path, end, pen_color, z, at_start=False)
            if arrow_start:
                _draw_arrowhead(painter, path, start, pen_color, z, at_start=True)
            if tee:
                _draw_tee(painter, end, pen_color, z)
                _draw_tee(painter, start, pen_color, z)
            if label:
                self._paint_edge_label(painter, layout, label_point, label, colors, z)

    def _paint_edge_label(
        self,
        painter: QPainter,
        layout: DiagramLayout,
        point: QPointF,
        text: str,
        colors: CanvasColors,
        z: float,
    ) -> None:
        font = font_for_skin(get_skin(layout.doc.skin_name()), 0.78 * z)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        width = metrics.horizontalAdvance(text) + 8 * z
        height = metrics.height() + 2 * z
        rect = QRectF(point.x() - width / 2, point.y() - height / 2, width, height)
        painter.setPen(QPen(colors.border, max(0.5, 0.7 * z)))
        painter.setBrush(QColor(colors.white.red(), colors.white.green(), colors.white.blue(), 235))
        painter.drawRoundedRect(rect, 3 * z, 3 * z)
        painter.setPen(QPen(layout.skin.text_color if layout.skin else colors.text))
        painter.drawText(rect, int(Qt.AlignCenter | Qt.TextSingleLine), text)

    # ------------------------------------------------------------------
    def _paint_head_tail(
        self,
        painter: QPainter,
        layout: DiagramLayout,
        colors: CanvasColors,
        skin: Skin,
        rows_bottom: float,
    ) -> None:
        z = layout.zoom
        head = layout.doc.head
        foot = layout.doc.foot
        font = font_for_skin(skin, 0.9 * z)
        painter.setFont(font)
        if head:
            text = _text_value(head.get("text"))
            if text:
                painter.setPen(QPen(skin.text_color))
                baseline = layout.header_height + 17 * z
                painter.drawText(
                    QRectF(layout.wave_origin, baseline - 14 * z, layout.width - layout.wave_origin, 20 * z),
                    int(Qt.AlignHCenter | Qt.AlignVCenter),
                    text,
                )
        if foot:
            text = _text_value(foot.get("text"))
            if text:
                baseline = rows_bottom + (18 * z if _has_ticks(foot) else 0) + 18 * z
                painter.setPen(QPen(skin.text_color))
                painter.drawText(
                    QRectF(layout.wave_origin, baseline - 14 * z, layout.width - layout.wave_origin, 20 * z),
                    int(Qt.AlignHCenter | Qt.AlignVCenter),
                    text,
                )
        small = font_for_skin(skin, 0.76 * z)
        painter.setFont(small)
        painter.setPen(QPen(colors.muted))
        if _has_ticks(head):
            labels = layout.tick_labels(head)
            for x, text in labels:
                painter.drawText(
                    QRectF(x - 24 * z, layout.header_height + (22 * z if _text_value(head.get("text")) else 0), 48 * z, 15 * z),
                    int(Qt.AlignHCenter | Qt.AlignVCenter),
                    text,
                )
        if _has_ticks(foot):
            labels = layout.tick_labels(foot)
            for x, text in labels:
                painter.drawText(
                    QRectF(x - 24 * z, rows_bottom + 2 * z, 48 * z, 15 * z),
                    int(Qt.AlignHCenter | Qt.AlignVCenter),
                    text,
                )

    # ------------------------------------------------------------------
    def _paint_chrome_foreground(
        self,
        painter: QPainter,
        layout: DiagramLayout,
        colors: CanvasColors,
        state: PaintState,
    ) -> None:
        z = layout.zoom
        # Time ruler.
        font = font_for_skin(get_skin(layout.doc.skin_name()), 0.72 * z)
        painter.setFont(font)
        painter.setPen(QPen(colors.muted))
        units = layout.display_units
        step = 1
        if layout.time_unit_width < 30:
            step = max(1, int(math.ceil(30 / max(1.0, layout.time_unit_width))))
        for unit in range(0, units + 1, step):
            x = layout.time_grid_x(unit)
            if x > layout.width - 2:
                break
            painter.drawText(
                QRectF(x - 20 * z, layout.header_height - 18 * z, 40 * z, 14 * z),
                int(Qt.AlignHCenter | Qt.AlignBottom),
                str(unit),
            )
        # Row numbers and drag handles.
        row_font = font_for_skin(get_skin(layout.doc.skin_name()), 0.70 * z)
        painter.setFont(row_font)
        for row in layout.rows:
            painter.setPen(QPen(colors.muted))
            painter.drawText(
                QRectF(4 * z, row.slot_top, 28 * z, layout.row_height),
                int(Qt.AlignLeft | Qt.AlignVCenter),
                str(row.index + 1),
            )
        # A subtle resize/edge affordance.
        painter.setPen(QPen(colors.border, 1.0))
        painter.drawLine(
            QPointF(layout.gutter_width - 4 * z, layout.rows_top),
            QPointF(layout.gutter_width - 4 * z, layout.rows_top + len(layout.rows) * layout.row_height),
        )

    # ------------------------------------------------------------------
    def _paint_drag(
        self,
        painter: QPainter,
        layout: DiagramLayout,
        drag: DragState,
        colors: CanvasColors,
    ) -> None:
        z = layout.zoom
        y = layout.rows_top + drag.target_index * layout.row_height
        painter.save()
        pen = QPen(colors.accent, max(2.0, 2.4 * z))
        painter.setPen(pen)
        painter.drawLine(QPointF(0, y), QPointF(layout.width, y))
        painter.setBrush(colors.accent)
        painter.setPen(Qt.NoPen)
        triangle = QPolygonF(
            [QPointF(0, y - 5 * z), QPointF(7 * z, y), QPointF(0, y + 5 * z)]
        )
        painter.drawPolygon(triangle)
        if drag.source_rows:
            for index in drag.source_rows:
                if 0 <= index < len(layout.rows):
                    row = layout.rows[index]
                    painter.fillRect(
                        QRectF(0, row.slot_top, layout.width, layout.row_height),
                        QColor(colors.accent.red(), colors.accent.green(), colors.accent.blue(), 16),
                    )
        if drag.label:
            font = font_for_skin(get_skin(layout.doc.skin_name()), 0.82 * z)
            painter.setFont(font)
            metrics = QFontMetricsF(font)
            width = metrics.horizontalAdvance(drag.label) + 18 * z
            height = metrics.height() + 8 * z
            rect = QRectF(min(layout.width - width - 10 * z, 20 * z), max(0, y - height - 5 * z), width, height)
            painter.setBrush(QColor(colors.accent.red(), colors.accent.green(), colors.accent.blue(), 232))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, 5 * z, 5 * z)
            painter.setPen(QPen(QColor("#ffffff")))
            painter.drawText(rect, int(Qt.AlignCenter | Qt.TextSingleLine), drag.label)
        painter.restore()

    def _paint_empty_state(
        self,
        painter: QPainter,
        layout: DiagramLayout,
        colors: CanvasColors,
        skin: Skin,
    ) -> None:
        font = font_for_skin(skin, 1.0 * layout.zoom)
        painter.setFont(font)
        painter.setPen(QPen(colors.muted))
        painter.drawText(
            QRectF(layout.wave_origin, layout.rows_top, layout.width - layout.wave_origin, layout.row_height * 2),
            int(Qt.AlignHCenter | Qt.AlignVCenter),
            "No signals · press Insert to add one",
        )


# ----------------------------------------------------------------------
# Edge geometry helpers
# ----------------------------------------------------------------------
def _edge_path(start: QPointF, end: QPointF, shape: str) -> tuple[QPainterPath, QPointF]:
    dx = end.x() - start.x()
    path = QPainterPath()
    label = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
    if shape in ("~", "~>", "<~>", "~-"):
        if shape in ("~", "~>", "<~>"):
            path.moveTo(start)
            path.cubicTo(start.x() + 0.7 * dx, start.y(), start.x() + 0.3 * dx, end.y(), end.x(), end.y())
        else:  # ~-
            path.moveTo(start)
            path.cubicTo(start.x(), start.y(), start.x() + 0.3 * dx, end.y(), end.x(), end.y())
            label = QPointF(start.x() + 0.25 * dx, (start.y() + end.y()) / 2)
    elif shape in ("-~", "-~>", "<-~>"):
        path.moveTo(start)
        path.cubicTo(start.x() + 0.7 * dx, start.y(), end.x(), end.y(), end.x(), end.y())
        label = QPointF(start.x() + 0.75 * dx, (start.y() + end.y()) / 2)
    elif shape in ("-|", "-|>", "<-|>"):
        path.moveTo(start)
        path.lineTo(end.x(), start.y())
        path.lineTo(end.x(), end.y())
        if shape in ("-|", "<-|>"):
            label = QPointF(end.x(), (start.y() + end.y()) / 2)
    elif shape in ("|-", "|->"):
        path.moveTo(start)
        path.lineTo(start.x(), end.y())
        path.lineTo(end.x(), end.y())
        if shape == "|-":
            label = QPointF(start.x(), (start.y() + end.y()) / 2)
    elif shape in ("-|-", "-|->", "<-|->"):
        path.moveTo(start)
        path.lineTo(start.x() + dx / 2, start.y())
        path.lineTo(start.x() + dx / 2, end.y())
        path.lineTo(end.x(), end.y())
    else:
        path.moveTo(start)
        path.lineTo(end)
    return path, label


def _draw_arrowhead(
    painter: QPainter,
    path: QPainterPath,
    point: QPointF,
    color: QColor,
    z: float,
    *,
    at_start: bool,
) -> None:
    if path.isEmpty():
        return
    # Find a nearby point on the path to derive the tangent.
    if at_start:
        near = path.pointAtPercent(0.06)
        direction = point - near
    else:
        near = path.pointAtPercent(0.94)
        direction = point - near
    length = math.hypot(direction.x(), direction.y())
    if length < 1e-6:
        return
    ux, uy = direction.x() / length, direction.y() / length
    size = 8.0 * max(1.0, z)
    width = 3.6 * max(1.0, z)
    base = QPointF(point.x() - ux * size, point.y() - uy * size)
    left = QPointF(base.x() - uy * width, base.y() + ux * width)
    right = QPointF(base.x() + uy * width, base.y() - ux * width)
    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF([point, left, right]))
    painter.restore()


def _draw_tee(painter: QPainter, point: QPointF, color: QColor, z: float) -> None:
    painter.save()
    painter.setPen(QPen(color, max(1.0, 1.5 * z)))
    painter.drawLine(
        QPointF(point.x() - 6 * z, point.y() - 4 * z),
        QPointF(point.x() + 6 * z, point.y() + 4 * z),
    )
    painter.drawLine(
        QPointF(point.x() - 6 * z, point.y() + 4 * z),
        QPointF(point.x() + 6 * z, point.y() - 4 * z),
    )
    painter.restore()


def _text_value(value) -> str:
    return _text_value_raw(value).strip()


def _text_value_raw(value) -> str:
    """Flatten WaveDrom JSONML text without losing inner spaces."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return "".join(_text_value_raw(item) for item in value[1:])
    if isinstance(value, dict):
        return ""
    return str(value)


def _has_ticks(section: dict) -> bool:
    return isinstance(section, dict) and ("tick" in section or "tock" in section)


def pixmap_for_document(
    doc: WaveDocument,
    *,
    zoom: float = 1.5,
    background: QColor | None = None,
):
    """Render a standalone diagram (used by export and clipboard)."""
    from PySide6.QtGui import QImage

    skin = get_skin(doc.skin_name())
    layout = DiagramLayout(doc, zoom=zoom, skin=skin, chrome=False, placeholder=False)
    image = QImage(
        max(1, int(math.ceil(layout.width))),
        max(1, int(math.ceil(layout.height))),
        QImage.Format_ARGB32_Premultiplied,
    )
    image.fill(background or skin.background)
    painter = QPainter(image)
    WaveRenderer().paint(
        painter,
        layout,
        PaintState(
            show_chrome=False,
            show_selection=False,
            focused=False,
        ),
    )
    painter.end()
    return image, layout
