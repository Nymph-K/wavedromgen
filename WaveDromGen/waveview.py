# coding=utf-8
"""Interactive waveform canvas."""
from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QLineEdit, QScrollArea, QWidget

from .layout import DiagramLayout, EditTarget, GroupLayout
from .model import Selection, WaveDocument
from .renderer import CanvasColors, DragState, PaintState, WaveRenderer
from .skins import get_skin
from .wavedrom_render import sanitize_wave_char

# Inline editor commit codes: sign selects the direction, magnitude the field
# kind (1 = data label, 2 = signal name, 0 = plain focus loss).
COMMIT_FOCUS_OUT = 0
COMMIT_NEXT_DATA = 1
COMMIT_NEXT_NAME = 2


class InlineEditor(QLineEdit):
    """Small editor that commits on Enter/Tab and cancels on Escape."""

    commitRequested = Signal(int)
    cancelRequested = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("InlineEdit")
        self.setFrame(False)
        self.setAttribute(Qt.WA_MacShowFocusRect, False)
        self._closing = False
        self.setStyleSheet(
            "QLineEdit#InlineEdit {"
            " background: #fff8d8;"
            " border: 2px solid #f59e0b;"
            " border-radius: 4px;"
            " padding: 1px 5px;"
            " selection-background-color: #f59e0b;"
            " selection-color: #111827;"
            " color: #111827;"
            "}"
        )

    def close_silently(self) -> None:
        self._closing = True
        self.hide()

    def event(self, event) -> bool:
        # QWidget consumes Tab for focus traversal before keyPressEvent, so
        # intercept it here to implement "commit and edit the next data label".
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            delta = 1 if event.key() == Qt.Key_Tab else -1
            self.commitRequested.emit(delta * COMMIT_NEXT_DATA)
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            delta = -1 if event.modifiers() & Qt.ShiftModifier else 1
            self.commitRequested.emit(delta * COMMIT_NEXT_NAME)
            event.accept()
            return
        if key == Qt.Key_Escape:
            self.cancelRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        if not self._closing and self.isVisible():
            self.commitRequested.emit(COMMIT_FOCUS_OUT)


class WaveCanvas(QWidget):
    documentEdited = Signal(str)
    selectionChanged = Signal()
    cursorInfoChanged = Signal(str)
    contextMenuRequested = Signal(QPoint, int, int)
    ensureVisibleRequested = Signal(QRectF)
    zoomRequested = Signal(float)
    zoomChanged = Signal(float)
    toolChanged = Signal(str)
    editStateChanged = Signal(bool)
    insertModeChanged = Signal(bool)
    waveFocusChanged = Signal(object, int, int)
    groupRenameRequested = Signal(int, int)

    TOOLS = ("select", "clk", "sig", "bus", "x", "z", "gap", "text", "clear", "node")

    def __init__(self, doc: WaveDocument, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAcceptDrops(False)
        self.doc = doc
        self.zoom = 1.0
        self.tool = "select"
        self.auto_advance = True
        self.insert_mode = False
        self.colors = CanvasColors()
        self._renderer = WaveRenderer(self.colors)
        self._extra_units = 0
        self._layout = DiagramLayout(
            doc, zoom=self.zoom, skin=get_skin(doc.skin_name()), chrome=True
        )
        self.selection: Selection | None = None
        self.active_cell: tuple[int, int] | None = (0, 0) if doc.rows else None
        self.hover_cell: tuple[int, int] | None = None
        self._selected_rows: list[int] = []
        self._row_anchor: int | None = None
        self._anchor: tuple[int, int] | None = None
        self._mode = ""
        self._press_pos: QPoint | None = None
        self._press_row: int | None = None
        self._drag = DragState()
        self._drag_started = False
        self._middle_moved = False
        self._last_paint_cell: tuple[int, int] | None = None
        self._editor: InlineEditor | None = None
        self._editing_target: EditTarget | None = None
        self._editing = False
        self._refresh_size()

    # ------------------------------------------------------------------
    # Document / layout
    # ------------------------------------------------------------------
    def set_document(self, doc: WaveDocument, *, reset_view: bool = False) -> None:
        self._close_editor(commit=False)
        self.doc = doc
        if reset_view:
            self.selection = None
            self._selected_rows = []
            self._row_anchor = None
            self.active_cell = (0, 0) if doc.rows else None
            self.hover_cell = None
            self._anchor = None
            self._extra_units = 0
            self.set_insert_mode(False)
        self.refresh()
        self.selectionChanged.emit()

    def refresh(self) -> None:
        if self._editing:
            self._close_editor(commit=False)
        skin = get_skin(self.doc.skin_name())
        self._layout = DiagramLayout(
            self.doc,
            zoom=self.zoom,
            skin=skin,
            chrome=True,
            placeholder=True,
            extra_units=self._extra_units,
        )
        self._clamp_state()
        self._refresh_size()
        self.update()
        self._emit_cursor_info()

    def _refresh_size(self) -> None:
        width = max(320, int(math.ceil(self._layout.width)))
        height = max(120, int(math.ceil(self._layout.height)))
        self.setMinimumSize(width, height)
        if self.size() != QSize(width, height):
            self.resize(width, height)
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        return QSize(int(self._layout.width), int(self._layout.height))

    def set_zoom(self, zoom: float, *, ensure: QPointF | None = None) -> None:
        zoom = max(0.45, min(3.0, float(zoom)))
        if abs(zoom - self.zoom) < 1e-6:
            return
        self.zoom = zoom
        self.refresh()
        self.zoomChanged.emit(self.zoom)

    def set_colors(self, colors: CanvasColors) -> None:
        self.colors = colors
        self._renderer = WaveRenderer(colors)
        self.update()

    def set_auto_advance(self, enabled: bool) -> None:
        self.auto_advance = bool(enabled)

    def set_tool(self, tool: str) -> None:
        if tool not in self.TOOLS:
            tool = "select"
        if self.tool == tool:
            return
        self.tool = tool
        if tool != "select":
            self.set_insert_mode(False)
        self._update_cursor_shape()
        self.toolChanged.emit(tool)
        self._emit_cursor_info()
        self.update()

    def set_insert_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self.insert_mode == enabled:
            return
        self.insert_mode = enabled
        self._update_cursor_shape()
        self.insertModeChanged.emit(enabled)
        self._emit_cursor_info()
        self.update()

    def _update_cursor_shape(self) -> None:
        if self.insert_mode:
            self.setCursor(Qt.IBeamCursor)
        elif self.tool != "select":
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def _clamp_state(self) -> None:
        rows = self.doc.rows
        if not rows:
            self.selection = None
            self._selected_rows = []
            self._row_anchor = None
            self.active_cell = None
            self._anchor = None
            return
        limit = self._layout.max_column() if hasattr(self, "_layout") else 512
        if self.active_cell is not None:
            y = max(0, min(self.active_cell[0], len(rows) - 1))
            x = max(0, min(self.active_cell[1], limit))
            self.active_cell = (y, x)
        if self.selection is not None:
            sel = self.selection.normalized()
            r0 = max(0, min(sel.row0, len(rows) - 1))
            r1 = max(0, min(sel.row1, len(rows) - 1))
            c0 = max(0, min(sel.col0, limit))
            c1 = max(0, min(sel.col1, limit))
            self.selection = Selection(r0, c0, r1, c1)
        if self._selected_rows:
            self._selected_rows = sorted({max(0, min(i, len(rows) - 1)) for i in self._selected_rows})
        if self._row_anchor is not None:
            self._row_anchor = max(0, min(self._row_anchor, len(rows) - 1))
        if self._anchor is not None:
            y = max(0, min(self._anchor[0], len(rows) - 1))
            self._anchor = (y, max(0, min(self._anchor[1], limit)))

    def _grow_view_for(self, column: int) -> None:
        """Widen the canvas so empty cycles on the right stay reachable."""
        needed = int(column) - int(self.doc.time_units) - 1
        if needed <= self._extra_units:
            return
        self._extra_units = min(600, needed + 2)
        self.refresh()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        skin = get_skin(self.doc.skin_name())
        if self.width() > self._layout.width or self.height() > self._layout.height:
            painter.fillRect(self.rect(), skin.background)
        state = PaintState(
            selection=self.selection,
            active_cell=self.active_cell,
            hover_cell=self.hover_cell,
            row_selection=tuple(self._selected_rows),
            drag=self._drag,
            editing_target=self._editing_target,
            focused=self.hasFocus(),
            show_chrome=True,
            show_selection=True,
            insert_mode=self.insert_mode,
        )
        self._renderer.paint(painter, self._layout, state)
        # A subtle card edge separates the diagram from the scroll background.
        pen = QPen(self.colors.border, 1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(
            QRectF(0.5, 0.5, max(0.0, self._layout.width - 1.0), max(0.0, self._layout.height - 1.0))
        )
        painter.end()

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------
    @property
    def row_selection(self) -> tuple[int, int] | None:
        if not self._selected_rows:
            return None
        return (min(self._selected_rows), max(self._selected_rows))

    @row_selection.setter
    def row_selection(self, value) -> None:
        if value is None:
            self._selected_rows = []
            return
        if isinstance(value, int):
            self._selected_rows = [value]
            return
        values = list(value)
        if not values:
            self._selected_rows = []
            return
        if len(values) == 2 and values[1] >= values[0]:
            self._selected_rows = list(range(int(values[0]), int(values[1]) + 1))
        else:
            self._selected_rows = sorted({int(v) for v in values})

    @property
    def row_selection_rows(self) -> list[int]:
        return list(self._selected_rows)

    def set_row_selection(self, rows, *, anchor: int | None = None) -> None:
        values = [rows] if isinstance(rows, int) else list(rows)
        self._selected_rows = sorted({int(value) for value in values})
        if anchor is not None:
            self._row_anchor = anchor
        self.selection = None
        self.update()
        self.selectionChanged.emit()
        self._emit_cursor_info()

    def toggle_row_selection(self, row: int) -> None:
        if row in self._selected_rows:
            self._selected_rows = [i for i in self._selected_rows if i != row]
        else:
            self._selected_rows = sorted(self._selected_rows + [row])
        self._row_anchor = row
        self.selection = None
        self.active_cell = (row, self.active_cell[1] if self.active_cell else 0)
        self.update()
        self.selectionChanged.emit()
        self._emit_cursor_info()

    def _cell_from_pos(self, pos: QPointF, *, clamp: bool = True) -> tuple[int, int] | None:
        row = self._layout.row_at(pos.y())
        if row is None or pos.x() < self._layout.wave_origin:
            return None
        col = row.char_at_x(pos.x())
        if clamp:
            col = max(0, min(col, self._layout.max_column()))
        return row.index, max(0, col)

    def selected_cells(self) -> list[tuple[int, int]]:
        """Every cell in the rectangular selection (empty right cycles too)."""
        if self.selection is not None:
            sel = self.selection.normalized()
            cells: list[tuple[int, int]] = []
            for y in range(sel.row0, sel.row1 + 1):
                if y < 0 or y >= len(self.doc.rows):
                    continue
                for x in range(sel.col0, sel.col1 + 1):
                    cells.append((y, x))
            if cells:
                return cells
        if self.active_cell is not None and self.doc.rows:
            y, x = self.active_cell
            row = self.doc.row(y)
            if row is not None:
                return [(y, max(0, x))]
        return []

    def selected_rows(self) -> list[int]:
        if self._selected_rows:
            return [i for i in self._selected_rows if 0 <= i < len(self.doc.rows)]
        if self.active_cell is not None:
            return [self.active_cell[0]]
        return []

    def selected_group_span(self):
        rows = set(self.selected_rows())
        if not rows:
            return None
        candidates = [
            span
            for span in self.doc.group_spans()
            if set(range(span.start, span.end + 1)) <= rows
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda span: span.depth)

    def group_at(self, x: float, y: float) -> GroupLayout | None:
        return self._layout.group_at(x, y)

    def _set_active(self, row: int, col: int, *, extend: bool = False) -> None:
        rows = self.doc.rows
        if not rows:
            self.selection = None
            self.active_cell = None
            return
        row = max(0, min(row, len(rows) - 1))
        col = max(0, min(col, self._layout.max_column()))
        self.active_cell = (row, col)
        self._selected_rows = []
        self._row_anchor = None
        if extend and self._anchor is not None:
            self.selection = Selection(self._anchor[0], self._anchor[1], row, col).normalized()
        else:
            self._anchor = (row, col)
            self.selection = Selection(row, col, row, col)
        self._emit_cursor_info()
        self.selectionChanged.emit()
        self.update()

    def select_all_cells(self) -> None:
        if not self.doc.rows:
            return
        max_col = max(0, max(len(row.wave) for row in self.doc.rows) - 1)
        self._anchor = (0, 0)
        self.selection = Selection(0, 0, len(self.doc.rows) - 1, max_col)
        self.active_cell = (0, 0)
        self._selected_rows = []
        self.update()
        self.selectionChanged.emit()
        self._emit_cursor_info()

    def clear_selection(self) -> None:
        self.selection = None
        self._selected_rows = []
        self._row_anchor = None
        self._anchor = None
        self.update()
        self.selectionChanged.emit()

    # ------------------------------------------------------------------
    # Mouse handling
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.setFocus(Qt.MouseFocusReason)
        pos = event.position()
        if event.button() == Qt.MiddleButton:
            self._start_middle_gesture(pos)
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            if self._layout.is_group_area(pos.x(), pos.y()):
                group = self._layout.group_at(pos.x(), pos.y())
                if group is not None:
                    self._select_group(group, extend=bool(event.modifiers() & Qt.ShiftModifier))
                    self._mode = "group-press"
                    self._press_pos = QPoint(int(pos.x()), int(pos.y()))
                    self._press_row = group.span.start
                    self._drag_started = False
                    return
            if pos.x() < self._layout.wave_origin:
                row = self._layout.row_at(pos.y())
                if row is None:
                    return
                self.selection = None
                self._anchor = None
                if event.modifiers() & Qt.ShiftModifier and self._row_anchor is not None:
                    a, b = sorted((self._row_anchor, row.index))
                    self._selected_rows = list(range(a, b + 1))
                elif event.modifiers() & Qt.ControlModifier:
                    self.toggle_row_selection(row.index)
                else:
                    self._selected_rows = [row.index]
                    self._row_anchor = row.index
                self.active_cell = (row.index, self.active_cell[1] if self.active_cell else 0)
                self._press_pos = QPoint(int(pos.x()), int(pos.y()))
                self._press_row = row.index
                self._drag_started = False
                self._mode = "row-press"
                self._emit_cursor_info()
                self.selectionChanged.emit()
                self.update()
                return
            cell = self._cell_from_pos(pos)
            if cell is None:
                self.clear_selection()
                return
            if cell[1] > len(self.doc.rows[cell[0]].wave):
                self._grow_view_for(cell[1])
            if self.tool == "select":
                if self.insert_mode:
                    self._set_active(cell[0], cell[1])
                elif event.modifiers() & Qt.ShiftModifier and self._anchor is not None:
                    self._set_active(cell[0], cell[1], extend=True)
                else:
                    self._set_active(cell[0], cell[1])
                self._mode = "selecting"
                self._press_pos = QPoint(int(pos.x()), int(pos.y()))
            else:
                self._apply_tool(cell[0], cell[1], drag=False)
                self._mode = "painting"
                self._last_paint_cell = cell
                self._set_active(cell[0], cell[1])
                self.update()
        super().mousePressEvent(event)

    def _select_group(self, group: GroupLayout, *, extend: bool = False) -> None:
        rows = list(range(group.span.start, group.span.end + 1))
        if extend and self._row_anchor is not None:
            a, b = sorted((self._row_anchor, rows[-1]))
            self._selected_rows = list(range(a, b + 1))
        else:
            self._selected_rows = rows
            self._row_anchor = rows[0]
        self.selection = None
        self._anchor = None
        self.active_cell = (rows[0], self.active_cell[1] if self.active_cell else 0)
        self.update()
        self.selectionChanged.emit()
        self._emit_cursor_info()

    def _toggle_insert_at(self, pos: QPointF) -> None:
        row = self._layout.row_at(pos.y())
        if row is None:
            self.set_insert_mode(False)
            return
        if self.insert_mode:
            self.set_insert_mode(False)
            return
        cell = self._cell_from_pos(pos)
        if cell is None:
            col = self.active_cell[1] if self.active_cell else 0
            row_index = row.index
        else:
            row_index, col = cell
        self.set_insert_mode(False)
        self.set_active_cell(row_index, col)
        if col > len(self.doc.rows[row_index].wave):
            self._grow_view_for(col)
        self.set_insert_mode(True)

    def _start_middle_gesture(self, pos: QPointF) -> None:
        """Middle press: click toggles insert mode, drag selects rows/cells."""
        row = self._layout.row_at(pos.y())
        if row is None:
            self.set_insert_mode(False)
            return
        self._press_pos = QPoint(int(pos.x()), int(pos.y()))
        self._press_row = row.index
        self._middle_moved = False
        if pos.x() < self._layout.wave_origin:
            # Dragging in the gutter selects signal rows.
            if self._selected_rows:
                self._selected_rows = sorted(set(self._selected_rows + [row.index]))
            else:
                self._selected_rows = [row.index]
            self._row_anchor = row.index
            self.selection = None
            self._anchor = None
            self.active_cell = (
                row.index,
                self.active_cell[1] if self.active_cell else 0,
            )
            self._mode = "middle-rows"
            self.update()
            self.selectionChanged.emit()
            self._emit_cursor_info()
            return
        cell = self._cell_from_pos(pos)
        if cell is None:
            return
        self._anchor = cell
        self.active_cell = cell
        self.selection = Selection(cell[0], cell[1], cell[0], cell[1])
        self._selected_rows = []
        self._row_anchor = None
        self._mode = "middle-select"
        self.update()
        self.selectionChanged.emit()
        self._emit_cursor_info()

    def set_active_cell(self, row: int, col: int) -> None:
        if not self.doc.rows:
            return
        row = max(0, min(row, len(self.doc.rows) - 1))
        col = max(0, min(col, self._layout.max_column()))
        self.active_cell = (row, col)
        self.selection = Selection(row, col, row, col)
        self._anchor = (row, col)
        self._selected_rows = []
        self.update()
        self.selectionChanged.emit()
        self._emit_cursor_info()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        cell = self._cell_from_pos(pos)
        if cell != self.hover_cell:
            self.hover_cell = cell
            self._emit_cursor_info()
            self.update()
        if self._mode in ("row-press", "group-press") and self._press_pos is not None and self._press_row is not None:
            if not self._drag_started:
                distance = (event.position() - QPointF(self._press_pos)).manhattanLength()
                if distance > 4:
                    self._drag_started = True
                    rows = self.selected_rows()
                    self._drag = DragState(
                        active=True,
                        source_rows=tuple(rows),
                        target_index=self._layout.insertion_index(event.position().y()),
                        label=f"Move {len(rows)} signal" + ("s" if len(rows) != 1 else ""),
                    )
                    self.setCursor(Qt.ClosedHandCursor)
            if self._drag_started:
                self._drag.target_index = self._layout.insertion_index(event.position().y())
                self.update()
                return
        if self._mode in ("middle-select", "middle-rows"):
            if self._press_pos is not None:
                distance = (event.position() - QPointF(self._press_pos)).manhattanLength()
                if distance > 4:
                    self._middle_moved = True
                    if not self.insert_mode:
                        self.set_insert_mode(True)
            if self._mode == "middle-rows":
                row = self._layout.row_at(pos.y())
                if self._middle_moved and row is not None:
                    anchor = self._row_anchor if self._row_anchor is not None else row.index
                    a, b = sorted((anchor, row.index))
                    self._selected_rows = list(range(a, b + 1))
                    col = self.active_cell[1] if self.active_cell else 0
                    self.selection = Selection(a, col, b, col)
                    self.active_cell = (b, col)
                    self._emit_cursor_info()
                    self.selectionChanged.emit()
                    self.update()
            elif cell is not None and self._anchor is not None and self._middle_moved:
                self.selection = Selection(
                    self._anchor[0], self._anchor[1], cell[0], cell[1]
                ).normalized()
                self.active_cell = cell
                if cell[1] >= self._layout.display_units - 1:
                    self._grow_view_for(cell[1])
                self._ensure_cell_visible(cell[0], cell[1])
                self._emit_cursor_info()
                self.selectionChanged.emit()
                self.update()
        if self._mode == "selecting" and cell is not None:
            if self._anchor is None:
                self._anchor = cell
            if cell[1] >= self._layout.display_units - 1:
                self._grow_view_for(cell[1])
            self.selection = Selection(self._anchor[0], self._anchor[1], cell[0], cell[1]).normalized()
            self.active_cell = cell
            self._ensure_cell_visible(cell[0], cell[1])
            self.selectionChanged.emit()
            self._emit_cursor_info()
            self.update()
        elif self._mode == "painting" and cell is not None:
            if cell != self._last_paint_cell:
                self._apply_tool(cell[0], cell[1], drag=True)
                self._last_paint_cell = cell
                self._set_active(cell[0], cell[1])
        # Cursor feedback.
        if self._drag_started:
            self.setCursor(Qt.ClosedHandCursor)
        elif pos.x() < self._layout.wave_origin:
            if self._layout.is_group_area(pos.x(), pos.y()):
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.SizeVerCursor if self._layout.row_at(pos.y()) else Qt.ArrowCursor)
        elif self.insert_mode:
            self.setCursor(Qt.IBeamCursor)
        elif self.tool == "select":
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setCursor(Qt.CrossCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MiddleButton:
            moved = self._middle_moved
            self._mode = ""
            self._press_pos = None
            self._press_row = None
            self._middle_moved = False
            if moved:
                self.set_insert_mode(True)
            else:
                self._toggle_insert_at(event.position())
            self._update_cursor_shape()
            self.update()
            super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.LeftButton:
            if self._mode in ("row-press", "group-press") and self._drag_started and self._drag.active:
                target = self._drag.target_index
                rows = list(self._drag.source_rows)
                self._drag = DragState()
                self._drag_started = False
                if rows:
                    moved = self.doc.move_rows(rows, target)
                    if moved:
                        self.set_row_selection(moved)
                        self.active_cell = (moved[0], 0)
                        self.selection = None
                        self.refresh()
                        self.documentEdited.emit("move-rows")
                self._update_cursor_shape()
            else:
                self._drag = DragState()
                self._drag_started = False
            self._mode = ""
            self._press_pos = None
            self._press_row = None
            self._last_paint_cell = None
            self.update()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return
        pos = event.position()
        row = self._layout.row_at(pos.y())
        if row is None:
            return
        if self._layout.is_group_area(pos.x(), pos.y()):
            group = self._layout.group_at(pos.x(), pos.y())
            if group is not None:
                self._select_group(group)
                self.groupRenameRequested.emit(group.span.start, group.span.end)
            return
        if pos.x() < self._layout.wave_origin:
            target = self._layout.target_by_key("name", row.index)
            if target:
                self.open_editor(target)
            return
        cell = self._cell_from_pos(pos)
        if cell is not None:
            self._set_active(cell[0], cell[1])
        data = self._layout.data_target(row.index, pos.x())
        if data is not None:
            target = self._layout.target_by_key("data", row.index, data.data_index)
            if target:
                self.open_editor(target)
                return
        # Fall back to the signal name so double-click is never a dead end.
        target = self._layout.target_by_key("name", row.index)
        if target:
            self.open_editor(target)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        pos = event.pos()
        row = self._layout.row_at(pos.y())
        if row is None:
            return
        if self._layout.is_group_area(pos.x(), pos.y()):
            group = self._layout.group_at(pos.x(), pos.y())
            if group is not None:
                self._select_group(group)
        elif pos.x() >= self._layout.wave_origin:
            cell = self._cell_from_pos(QPointF(pos))
            if cell is not None:
                self._set_active(cell[0], cell[1])
            else:
                self._selected_rows = [row.index]
                self._row_anchor = row.index
                self.active_cell = (row.index, 0)
        else:
            if row.index not in self._selected_rows:
                self._selected_rows = [row.index]
                self._row_anchor = row.index
            self.active_cell = (row.index, 0)
        self.update()
        self.selectionChanged.emit()
        self.contextMenuRequested.emit(
            event.globalPos(), row.index, self.active_cell[1] if self.active_cell else 0
        )

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            super().keyPressEvent(event)
            return
        key = event.key()
        text = event.text()
        if key == Qt.Key_Escape:
            if self.insert_mode:
                self.set_insert_mode(False)
            elif self.tool != "select":
                self.set_tool("select")
            else:
                self.clear_selection()
            return
        if key in (Qt.Key_Tab, Qt.Key_Backtab):
            self._open_name_editor(delta=1 if key == Qt.Key_Tab else -1)
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._open_name_editor(delta=0)
            return
        if key == Qt.Key_F2:
            self._open_target_at_active()
            return
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            self._delete_at_cursor(previous=key == Qt.Key_Backspace)
            return
        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_Home, Qt.Key_End):
            self._handle_arrow(key, bool(event.modifiers() & Qt.ShiftModifier))
            return
        if text and len(text) == 1 and self._is_wave_char(text):
            self._type_wave_char(text)
            return
        super().keyPressEvent(event)

    def _is_wave_char(self, text: str) -> bool:
        return sanitize_wave_char(text) is not None

    def _type_wave_char(self, text: str) -> None:
        char = sanitize_wave_char(text)
        if char is None:
            return
        if self.insert_mode and self.active_cell is not None:
            self._insert_at_cursor(char)
            return
        cells = self.selected_cells()
        if not cells and self.doc.rows:
            self.active_cell = (0, 0)
            cells = [(0, 0)]
        if not cells:
            return
        changed = self.doc.apply_wave_chars(cells, char, tag="wave")
        single = len(cells) == 1
        advanced = False
        if single and self.auto_advance:
            # Advance after every typed waveform character, even when it
            # matches the current cell, so repeated states can be entered fast.
            row, col = cells[0]
            next_col = min(col + 1, self._layout.max_column())
            self.active_cell = (row, next_col)
            self.selection = Selection(row, next_col, row, next_col)
            self._anchor = (row, next_col)
            advanced = True
            self._grow_view_for(next_col)
        if changed or advanced:
            self.refresh()
            if changed:
                self.documentEdited.emit("wave")
        self._emit_cursor_info()

    def _insert_targets(self) -> list[int]:
        """Lanes that receive text in insert mode (multi-row selections too)."""
        if self.selection is not None:
            sel = self.selection.normalized()
            rows = [
                index
                for index in range(sel.row0, sel.row1 + 1)
                if 0 <= index < len(self.doc.rows)
            ]
            if rows:
                return rows
        if self._selected_rows:
            return sorted(
                index for index in self._selected_rows if 0 <= index < len(self.doc.rows)
            )
        if self.active_cell is not None and 0 <= self.active_cell[0] < len(self.doc.rows):
            return [self.active_cell[0]]
        return []

    def _insert_at_cursor(self, char: str) -> None:
        rows = self._insert_targets()
        if not rows:
            return
        if self.active_cell is None:
            self.active_cell = (rows[0], 0)
        _, col = self.active_cell
        col = max(0, min(col, self._layout.max_column()))
        self.doc.insert_text_rows(rows, col, char)
        next_col = col + 1
        self._grow_view_for(next_col)
        self.active_cell = (rows[0], next_col)
        self._anchor = (rows[0], next_col)
        self.selection = Selection(rows[0], next_col, rows[-1], next_col)
        self._selected_rows = []
        self.refresh()
        self.documentEdited.emit("insert")
        self._ensure_cell_visible(rows[0], next_col)

    def apply_char(self, char: str) -> None:
        """Apply a waveform character from the toolbar palette."""
        value = sanitize_wave_char(char)
        if value is None:
            return
        if not self.doc.rows:
            return
        self._type_wave_char(value)

    def apply_wave_block(self, text: str) -> int:
        """Paste a rectangular block of waveform characters."""
        lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        while lines and not lines[-1]:
            lines.pop()
        if not lines:
            return 0
        selection = self.selection.normalized() if self.selection is not None else None
        if selection is not None:
            top, left = selection.row0, selection.col0
        elif self.active_cell is not None:
            top, left = self.active_cell
        else:
            return 0
        if len(lines) == 1:
            chars = "".join(
                c for c in lines[0] if sanitize_wave_char(c) is not None
            )
            if not chars:
                return 0
            cells = self.selected_cells()
            if len(cells) <= 1:
                changed = self.doc.apply_wave_block(top, left, chars)
            else:
                changed = self.doc.apply_wave_sequence(cells, chars)
        else:
            changed = self.doc.apply_wave_block(top, left, "\n".join(lines))
        if changed:
            self.refresh()
            self.documentEdited.emit("wave-paste")
        return changed

    def _delete_at_cursor(self, *, previous: bool = False) -> None:
        """Delete the selected cycles (real deletion, not "." replacement)."""
        if not self.doc.rows:
            return
        selection = self.selection.normalized() if self.selection is not None else None
        multi = bool(
            selection is not None
            and (selection.row0 != selection.row1 or selection.col0 != selection.col1)
        )
        if selection is not None and (multi or not previous):
            changed = self.doc.delete_cells(self.selected_cells())
            if changed:
                self.selection = Selection(
                    selection.row0, selection.col0, selection.row1, selection.col0
                )
                self._anchor = (selection.row0, selection.col0)
                self.active_cell = (selection.row0, selection.col0)
                self.refresh()
                self.documentEdited.emit("delete-cells")
                self._emit_cursor_info()
            return
        if self.active_cell is None:
            return
        row, col = self.active_cell
        target = max(0, col - 1) if previous else col
        changed = self.doc.delete_cells([(row, target)])
        if changed:
            self.refresh()
            self.documentEdited.emit("delete-cells")
        if previous:
            self.set_active_cell(row, target)

    def insert_cycles(self, before: bool = True) -> int:
        """Insert one empty cycle before/after the selected block."""
        selection = self.selection
        if selection is None and self.active_cell is not None:
            row, col = self.active_cell
            selection = Selection(row, col, row, col)
        if selection is None:
            return 0
        sel = selection.normalized()
        rows = list(range(sel.row0, sel.row1 + 1))
        column = sel.col0 if before else sel.col1 + 1
        changed = self.doc.insert_cells(rows, column, count=1)
        if changed:
            self._grow_view_for(column + 1)
            self.set_active_cell(sel.row0, column)
            self.selection = Selection(sel.row0, column, sel.row1, column)
            self.refresh()
            self.documentEdited.emit("insert-cells")
            self._emit_cursor_info()
        return changed

    def _handle_arrow(self, key: int, extend: bool) -> None:
        if not self.doc.rows:
            return
        if self.active_cell is None:
            self._set_active(0, 0, extend=extend)
            return
        row, col = self.active_cell
        if key == Qt.Key_Left:
            if col > 0:
                col -= 1
            elif row > 0:
                row -= 1
                col = max(0, len(self.doc.rows[row].wave) - 1)
            else:
                col = 0
        elif key == Qt.Key_Right:
            if col < self._layout.max_column():
                col += 1
                if col >= self._layout.display_units - 1:
                    self._grow_view_for(col)
        elif key == Qt.Key_Up:
            row = max(0, row - 1)
        elif key == Qt.Key_Down:
            row = min(len(self.doc.rows) - 1, row + 1)
        elif key == Qt.Key_Home:
            col = 0
        elif key == Qt.Key_End:
            col = max(0, len(self.doc.rows[row].wave) - 1)
        self._set_active(row, col, extend=extend)
        self._ensure_cell_visible(row, col)

    def _ensure_cell_visible(self, row: int, col: int) -> None:
        rect = self._layout.char_rect(row, col, clamp=False)
        if rect is not None:
            self.ensureVisibleRequested.emit(rect.adjusted(-40, -40, 40, 40))

    # ------------------------------------------------------------------
    # Inline editing
    # ------------------------------------------------------------------
    def _ensure_editor(self) -> InlineEditor:
        if self._editor is not None:
            self._editor.close_silently()
            self._editor.deleteLater()
            self._editor = None
        editor = InlineEditor(self)
        editor.commitRequested.connect(lambda code, e=editor: self._commit_editor(code, editor=e))
        editor.cancelRequested.connect(lambda e=editor: self._cancel_editor(editor=e))
        self._editor = editor
        return editor

    def _open_name_editor(self, delta: int = 0) -> None:
        if self.active_cell is None and self.doc.rows:
            self.active_cell = (0, 0)
        if self.active_cell is None:
            return
        target = self._layout.target_by_key("name", self.active_cell[0])
        if target:
            self.open_editor(target)

    def _open_target_at_active(self) -> None:
        if self.active_cell is None:
            self._open_name_editor()
            return
        row, col = self.active_cell
        row_layout = self._layout.rows[row] if 0 <= row < len(self._layout.rows) else None
        if row_layout is not None:
            data = row_layout.data_target_at(row_layout.char_x(col) + row_layout.char_width / 2)
            if data is not None:
                target = self._layout.target_by_key("data", row, data.data_index)
                if target:
                    self.open_editor(target)
                    return
        self._open_name_editor()

    def open_editor(self, target: EditTarget, *, delta_after: int = 0) -> None:
        if self._editing:
            self._close_editor(commit=True)
        editor = self._ensure_editor()
        editor._closing = False
        self._editing_target = target
        self._editing = True
        self.editStateChanged.emit(True)
        rect = QRectF(target.rect)
        z = self.zoom
        height = max(20.0, min(30.0 * z, rect.height() + 4.0 * z))
        if target.kind == "name":
            available = max(80.0, self._layout.wave_origin - 18.0 * z)
            width = min(max(110.0 * z, rect.width()), available)
            x = self._layout.wave_origin - width - 8.0 * z
            editor.setAlignment(Qt.AlignRight)
        elif target.kind == "data":
            width = max(90.0 * z, min(360.0 * z, rect.width()))
            x = rect.center().x() - width / 2.0
            editor.setAlignment(Qt.AlignCenter)
        elif target.kind == "node":
            width = 34.0 * z
            x = rect.center().x() - width / 2.0
            editor.setAlignment(Qt.AlignCenter)
        else:
            width = max(100.0 * z, rect.width())
            x = rect.x()
            editor.setAlignment(Qt.AlignLeft)
        y = rect.center().y() - height / 2.0
        editor.setGeometry(int(x), int(y), int(width), int(height))
        font = self._layout.name_font if target.kind == "name" else self._layout.data_font
        if font is not None:
            editor.setFont(font)
        editor.setMaxLength(120)
        editor.setText(target.text)
        editor.selectAll()
        editor.show()
        editor.raise_()
        editor.setFocus(Qt.OtherFocusReason)
        editor._closing = False
        self.ensureVisibleRequested.emit(QRectF(x, y, width, height).adjusted(-30, -20, 30, 20))
        self.update()

    def _close_editor(self, *, commit: bool) -> None:
        if not self._editing or self._editor is None:
            self._editing = False
            self._editing_target = None
            return
        editor = self._editor
        target = self._editing_target
        text = editor.text()
        editor.close_silently()
        self._editing = False
        self._editing_target = None
        self.editStateChanged.emit(False)
        if commit and target is not None:
            self._apply_edit(target, text)
        self.setFocus(Qt.OtherFocusReason)
        self.update()

    def _apply_edit(self, target: EditTarget, text: str) -> None:
        changed = False
        if target.kind == "name":
            changed = self.doc.set_name(target.row, text)
        elif target.kind == "data":
            changed = self.doc.set_data_label(target.row, target.data_index, text)
        elif target.kind == "node":
            changed = self.doc.set_node(target.row, target.data_index, text[:1] if text else ".")
            if not changed and text:
                self.cursorInfoChanged.emit("Node labels must be unique")
        if changed:
            self.refresh()
            self.documentEdited.emit(target.kind)

    def _commit_editor(self, code: int, editor: InlineEditor | None = None) -> None:
        if editor is not None and editor is not self._editor:
            return
        if not self._editing or self._editor is None or self._editing_target is None:
            return
        target = self._editing_target
        text = self._editor.text()
        self._editor.close_silently()
        self._editing = False
        self.editStateChanged.emit(False)
        self._editing_target = None
        self._apply_edit(target, text)
        if code:
            # Let the old editor finish delivering its focus events before
            # opening the next inline editor; otherwise Qt can immediately
            # steal focus back and commit the new editor with stale text.
            QTimer.singleShot(0, lambda t=target, c=code: self._advance_editor(t, c))
        else:
            self.setFocus(Qt.OtherFocusReason)
        self.update()

    def _advance_editor(self, old_target: EditTarget, code: int) -> None:
        kind = "name" if abs(code) >= COMMIT_NEXT_NAME else "data"
        delta = 1 if code > 0 else -1
        target = self._layout.next_target_of_kind(old_target, kind, delta)
        if target is None or target.key == old_target.key:
            self.setFocus(Qt.OtherFocusReason)
            self.update()
            return
        self.open_editor(target)

    def _cancel_editor(self, editor: InlineEditor | None = None) -> None:
        if editor is not None and editor is not self._editor:
            return
        if self._editor is not None:
            self._editor.close_silently()
        self._editing = False
        self._editing_target = None
        self.editStateChanged.emit(False)
        self.setFocus(Qt.OtherFocusReason)
        self.update()

    def edit_name_at(self, row: int) -> None:
        target = self._layout.target_by_key("name", row)
        if target:
            self.open_editor(target)

    def edit_data_at(self, row: int, data_index: int) -> None:
        target = self._layout.target_by_key("data", row, data_index)
        if target:
            self.open_editor(target)

    def edit_active(self) -> None:
        self._open_target_at_active()

    def commit_editing(self) -> None:
        """Commit an open inline name/data/node editor (used before save/export)."""
        if self._editing:
            self._commit_editor(0)

    # ------------------------------------------------------------------
    # Tool painting
    # ------------------------------------------------------------------
    def tool_char(self, tool: str) -> str | None:
        return {
            "clk": "p",
            "sig": "1",
            "bus": "=",
            "x": "x",
            "z": "z",
            "gap": "|",
        }.get(tool)

    def _apply_tool(self, row: int, col: int, *, drag: bool) -> None:
        if row < 0 or row >= len(self.doc.rows):
            return
        current = self.doc.rows[row].char_at(col)
        if self.tool == "clear":
            changed = self.doc.clear_cells([(row, col)])
        elif self.tool == "text":
            target = self._layout.data_target(row, self._layout.rows[row].char_x(col))
            if target is not None:
                self.edit_data_at(row, target.data_index)
            else:
                self.edit_name_at(row)
            return
        elif self.tool == "node":
            self._open_node_editor(row, col)
            return
        elif self.tool == "clk":
            if drag:
                new = "p"
            else:
                cycle = {"p": "P", "P": "n", "n": "N", "N": "p"}
                new = cycle.get(current, "p")
            changed = self.doc.apply_wave_chars([(row, col)], new, tag="draw-clk")
        elif self.tool == "sig":
            if drag:
                new = "1"
            else:
                new = "0" if current == "1" else "1"
            changed = self.doc.apply_wave_chars([(row, col)], new, tag="draw-sig")
        elif self.tool in ("bus", "x", "z", "gap"):
            char = self.tool_char(self.tool) or "."
            new = "." if current == char else char
            changed = self.doc.apply_wave_chars([(row, col)], new, tag="draw")
        else:
            changed = 0
        if changed:
            self.refresh()
            self.documentEdited.emit("draw")
            self._set_active(row, col)

    def _open_node_editor(self, row: int, col: int) -> None:
        row_layout = self._layout.rows[row]
        rect = row_layout.char_rect(col, self._layout.row_height)
        rect = QRectF(rect.center().x() - 12 * self.zoom, row_layout.slot_top + 8 * self.zoom, 24 * self.zoom, 22 * self.zoom)
        synthetic = EditTarget(
            kind="node",
            row=row,
            data_index=col,
            rect=rect,
            text=self.doc.rows[row].node[col : col + 1].replace(".", ""),
            label="node",
        )
        self.open_editor(synthetic)

    # ------------------------------------------------------------------
    # Clipboard support / public commands
    # ------------------------------------------------------------------
    def delete_selection(self) -> int:
        """Public command used by the Delete Cycles action and context menu."""
        before = self.doc.snapshot()
        self._delete_at_cursor(previous=False)
        return 0 if self.doc.snapshot() == before else 1

    def apply_wave_text(self, text: str) -> int:
        chars = "".join(c for c in (text or "") if sanitize_wave_char(c) is not None)
        if not chars:
            return 0
        cells = self.selected_cells()
        if not cells:
            return 0
        changed = self.doc.apply_wave_sequence(cells, chars)
        if changed:
            self.refresh()
            self.documentEdited.emit("wave-paste")
        return changed

    def cell_text(self) -> str:
        cells = self.selected_cells()
        if not cells:
            return ""
        rows = sorted({y for y, _ in cells})
        cols = sorted({x for _, x in cells})
        lines = []
        for y in rows:
            row = self.doc.row(y)
            if row is None:
                continue
            lines.append("".join(row.char_at(x) or "." for x in range(min(cols), max(cols) + 1)))
        return "\n".join(lines)

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom * 1.15)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom / 1.15)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def _emit_cursor_info(self) -> None:
        parts: list[str] = []
        if self.active_cell and self.doc.rows:
            row, col = self.active_cell
            if 0 <= row < len(self.doc.rows):
                char = self.doc.rows[row].char_at(col) or "·"
                parts.append(f"R{row + 1} C{col + 1}  [{char}]")
        if self.selection is not None:
            count = self.selection.cell_count(self.doc.rows)
            parts.append(f"sel {count} cell" + ("s" if count != 1 else ""))
        elif self._selected_rows:
            parts.append(
                "rows " + ",".join(str(index + 1) for index in sorted(self._selected_rows)[:6])
                + ("…" if len(self._selected_rows) > 6 else "")
            )
        if self.insert_mode:
            parts.append("INSERT")
        elif self.tool != "select":
            parts.append(self.tool)
        self.cursorInfoChanged.emit("  ·  ".join(parts))
        if not self.hasFocus() or not self.doc.rows:
            return
        rows: list[int] = []
        col0, col1 = -1, -1
        if self.selection is not None:
            sel = self.selection.normalized()
            rows = list(range(sel.row0, sel.row1 + 1))
            col0, col1 = sel.col0, sel.col1
        elif self._selected_rows:
            rows = sorted(self._selected_rows)
        elif self.active_cell is not None:
            rows = [self.active_cell[0]]
        if rows:
            self.waveFocusChanged.emit(rows, col0, col1)


class WaveView(QScrollArea):
    """Scrollable host for :class:`WaveCanvas`."""

    def __init__(self, doc: WaveDocument, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("WaveView")
        self.setFrameShape(QScrollArea.NoFrame)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setFocusPolicy(Qt.StrongFocus)
        self.canvas = WaveCanvas(doc, self)
        self.setWidget(self.canvas)
        self.canvas.ensureVisibleRequested.connect(self.ensure_rect_visible)
        self._update_canvas_size()

    def set_document(self, doc: WaveDocument, *, reset_view: bool = False) -> None:
        self.canvas.set_document(doc, reset_view=reset_view)
        self._update_canvas_size()

    def refresh(self) -> None:
        self.canvas.refresh()
        self._update_canvas_size()

    def _update_canvas_size(self) -> None:
        layout = self.canvas._layout
        width = max(int(math.ceil(layout.width)), self.viewport().width())
        height = max(120, int(math.ceil(layout.height)))
        if self.canvas.minimumWidth() != width or self.canvas.minimumHeight() != height:
            self.canvas.setMinimumSize(width, height)
        if self.canvas.size() != QSize(width, height):
            self.canvas.resize(width, height)

    def set_view_background(self, color: QColor) -> None:
        from PySide6.QtGui import QPalette

        for widget in (self, self.viewport()):
            palette = widget.palette()
            palette.setColor(QPalette.Window, color)
            palette.setColor(QPalette.Base, color)
            widget.setPalette(palette)
        self.viewport().setAutoFillBackground(True)
        self.setAutoFillBackground(True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_canvas_size()

    def ensure_rect_visible(self, rect: QRectF) -> None:
        margin = 20
        hbar = self.horizontalScrollBar()
        vbar = self.verticalScrollBar()
        left = int(rect.left()) - margin
        right = int(rect.right()) + margin
        top = int(rect.top()) - margin
        bottom = int(rect.bottom()) + margin
        if left < hbar.value():
            hbar.setValue(max(0, left))
        elif right > hbar.value() + self.viewport().width():
            hbar.setValue(min(hbar.maximum(), right - self.viewport().width()))
        if top < vbar.value():
            vbar.setValue(max(0, top))
        elif bottom > vbar.value() + self.viewport().height():
            vbar.setValue(min(vbar.maximum(), bottom - self.viewport().height()))

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                factor = 1.15 if delta > 0 else 1 / 1.15
                self.canvas.set_zoom(self.canvas.zoom * factor)
                event.accept()
                return
        if event.modifiers() & Qt.ShiftModifier:
            delta = event.angleDelta().y() or event.angleDelta().x()
            if delta:
                self.horizontalScrollBar().setValue(
                    self.horizontalScrollBar().value() - delta
                )
                event.accept()
                return
        super().wheelEvent(event)
