# coding=utf-8
"""Geometry and hit-testing for the interactive waveform canvas."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QFont, QFontMetricsF

from .model import GroupSpan, SignalRow, WaveDocument
from .skins import Skin, font_for_skin
from .wavedrom_render import (
    BRICK_SIZE,
    LABEL_X,
    ROW_HEIGHT,
    WAVE_TOP,
    BrickLayout,
    lane_layout,
)

GROUP_LEVEL_WIDTH = 26.0  # px per nesting level: bracket + rotated group name
MAX_SELECTION_COLUMNS = 512


@dataclass(frozen=True)
class DataTarget:
    row: int
    marker_index: int
    data_index: int
    rect: QRectF
    center: QPointF
    text: str
    segment_width: float

    @property
    def is_empty(self) -> bool:
        return not self.text


@dataclass(frozen=True)
class EditTarget:
    kind: str  # "name" or "data"
    row: int
    data_index: int
    rect: QRectF
    text: str
    label: str

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.kind, self.row, self.data_index)


@dataclass
class GroupLayout:
    """Rendered geometry of one signal group bracket."""

    span: GroupSpan
    x: float
    top: float
    bottom: float
    name_x: float
    name_rect: QRectF
    selected: bool = False

    @property
    def name(self) -> str:
        value = self.span.group.name
        if isinstance(value, (list, tuple)):
            return _label_text(value)
        return self.span.group.display_name


@dataclass
class RowLayout:
    index: int
    row: SignalRow
    slot_top: float
    bricks: BrickLayout
    name_rect: QRectF
    data_targets: list[DataTarget]
    row_rect: QRectF
    char_width: float
    char_x0: float
    depth: int = 0
    handle_x: float = 0.0

    def char_at_x(self, x: float) -> int:
        if self.char_width <= 0:
            return 0
        rel = x - self.char_x0
        index = int(math.floor(rel / self.char_width))
        return max(0, index)

    def char_x(self, index: int) -> float:
        return self.char_x0 + index * self.char_width

    def char_rect(self, index: int, row_height: float) -> QRectF:
        return QRectF(
            self.char_x(index),
            self.slot_top + 2.0,
            self.char_width,
            max(8.0, row_height - 4.0),
        )

    def data_target_at(self, x: float, tolerance: float = 6.0) -> DataTarget | None:
        if not self.data_targets:
            return None
        for target in self.data_targets:
            if target.rect.adjusted(-tolerance, 0, tolerance, 0).contains(QPointF(x, target.center.y())):
                return target
        # Closest marker: allows double-clicking anywhere on a bus segment.
        return min(self.data_targets, key=lambda target: abs(target.center.x() - x))


@dataclass
class DiagramLayout:
    doc: WaveDocument
    zoom: float = 1.0
    skin: Skin | None = None
    chrome: bool = True
    placeholder: bool = True
    extra_units: int = 0

    # computed
    width: float = 0.0
    height: float = 0.0
    wave_origin: float = 0.0
    gutter_width: float = 0.0
    header_height: float = 0.0
    rows_top: float = 0.0
    row_height: float = 0.0
    time_unit_width: float = 0.0
    time_units: int = 0
    display_units: int = 0
    head_height: float = 0.0
    foot_height: float = 0.0
    rows: list[RowLayout] = field(default_factory=list)
    groups: list[GroupLayout] = field(default_factory=list)
    group_column_width: float = 0.0
    group_origin: float = 0.0
    group_level_width: float = 0.0
    max_depth: int = 0
    row_no_width: float = 0.0
    name_font: QFont | None = None
    data_font: QFont | None = None
    name_metrics: QFontMetricsF | None = None
    data_metrics: QFontMetricsF | None = None
    char_width_base: float = 0.0

    def __post_init__(self) -> None:
        if self.skin is None:
            from .skins import get_skin

            self.skin = get_skin(self.doc.skin_name())
        self.zoom = max(0.35, min(4.0, float(self.zoom)))
        self.extra_units = max(0, int(self.extra_units))
        self.name_font = font_for_skin(self.skin, self.zoom)
        self.data_font = font_for_skin(self.skin, self.zoom)
        self.name_metrics = QFontMetricsF(self.name_font)
        self.data_metrics = QFontMetricsF(self.data_font)
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        doc = self.doc
        hscale = doc.hscale()
        z = self.zoom
        self.time_unit_width = 40.0 * hscale * z
        self.row_height = ROW_HEIGHT * z
        self.char_width_base = self.time_unit_width
        self.group_level_width = GROUP_LEVEL_WIDTH * z

        spans = doc.group_spans()
        self.max_depth = max((span.depth + 1 for span in spans), default=0)
        self.row_no_width = 34.0 * z if self.chrome else 0.0
        self.group_origin = self.row_no_width + 6.0 * z
        self.group_column_width = (
            (self.max_depth * self.group_level_width + 10.0 * z) if self.max_depth else 0.0
        )

        # Measure the widest name.
        max_name = 0.0
        for row in doc.rows:
            text = row.name
            if not text and self.placeholder and row.shows_placeholder_name:
                text = "signal"
            max_name = max(max_name, self.name_metrics.horizontalAdvance(text))
        drag_width = 16.0 * z if self.chrome else 0.0
        name_pad = 22.0 * z
        chrome_width = self.row_no_width + self.group_column_width + drag_width + name_pad
        self.gutter_width = max(110.0 * z, chrome_width + max_name)
        if not self.chrome:
            self.gutter_width = max(
                70.0 * z, self.group_column_width + max_name + name_pad
            )
        self.wave_origin = self.gutter_width

        head = doc.head
        foot = doc.foot
        head_text = _label_text(head.get("text"))
        foot_text = _label_text(foot.get("text"))
        self.header_height = 30.0 * z if self.chrome else 0.0
        self.head_height = (22.0 * z if head_text else 0.0) + (
            18.0 * z if _has_ticks(head) else 0.0
        )
        self.foot_height = (18.0 * z if _has_ticks(foot) else 0.0) + (
            24.0 * z if foot_text else 0.0
        )
        self.rows_top = self.header_height + self.head_height

        # Build rows.
        self.rows = []
        max_bricks = 1
        max_time = 0.0
        for index, row in enumerate(doc.rows):
            bricks = lane_layout(row, hscale)
            max_bricks = max(max_bricks, len(bricks.bricks))
            max_time = max(max_time, len(bricks.bricks) / (2.0 * hscale))
            slot_top = self.rows_top + index * self.row_height
            char_width = self.time_unit_width * max(1, bricks.period)
            char_x0 = self.wave_origin + bricks.x_offset * BRICK_SIZE * z
            name_right = self.wave_origin - 8.0 * z
            name_left = self.row_no_width + self.group_column_width + drag_width
            name_rect = QRectF(
                name_left,
                slot_top + 3.0 * z,
                max(24.0 * z, name_right - name_left),
                self.row_height - 6.0 * z,
            )
            handle_x = name_left - 6.0 * z if self.chrome else 0.0
            row_layout = RowLayout(
                index=index,
                row=row,
                slot_top=slot_top,
                bricks=bricks,
                name_rect=name_rect,
                data_targets=[],
                row_rect=QRectF(0, slot_top, 0, self.row_height),
                char_width=char_width,
                char_x0=char_x0,
                depth=doc.group_depth(index),
                handle_x=max(self.row_no_width + 4.0 * z, handle_x),
            )
            row_layout.data_targets = self._data_targets(row_layout)
            self.rows.append(row_layout)

        self.time_units = max(1, int(math.ceil(max_time)))
        self.display_units = self.time_units + (2 if self.chrome else 0) + self.extra_units
        wave_width = (max_bricks * BRICK_SIZE + BRICK_SIZE) * z
        time_width = self.time_unit_width * (self.display_units + 0.5)
        content_width = max(wave_width, time_width)
        self.width = self.wave_origin + content_width + 24.0 * z
        for row in self.rows:
            row.row_rect.setWidth(self.width)
        self.height = (
            self.rows_top
            + max(1, len(self.rows)) * self.row_height
            + self.foot_height
            + 18.0 * z
        )
        self.groups = self._build_groups(spans)

    def _build_groups(self, spans: list[GroupSpan]) -> list[GroupLayout]:
        z = self.zoom
        groups: list[GroupLayout] = []
        for span in spans:
            if span.start >= len(self.rows) or span.end >= len(self.rows):
                continue
            top = self.rows[span.start].slot_top + 4.0 * z
            bottom = self.rows[span.end].slot_top + self.row_height - 4.0 * z
            x = self.group_origin + (span.depth + 1) * self.group_level_width
            # The rotated label sits in its own column left of the bracket so
            # the bracket can never cover it, whatever the group name is.
            name_x = x - 17.0 * z
            name_rect = QRectF(name_x - 9.0 * z, top, 18.0 * z, max(10.0, bottom - top))
            groups.append(
                GroupLayout(
                    span=span,
                    x=x,
                    top=top,
                    bottom=bottom,
                    name_x=name_x,
                    name_rect=name_rect,
                )
            )
        return groups

    def _data_targets(self, row_layout: RowLayout) -> list[DataTarget]:
        layout = row_layout.bricks
        targets: list[DataTarget] = []
        if not layout.markers:
            return targets
        z = self.zoom
        runs = _bus_runs(layout.bricks)
        data = self.doc.row(row_layout.index)
        items = data.data_items() if data else []
        for marker_index, marker in enumerate(layout.markers):
            run = _run_for_marker(runs, marker)
            if run is None:
                run_left, run_right = marker - 1, marker + 1
            else:
                run_left, run_right = run
            segment_width = max(40.0 * z, (run_right - run_left) * BRICK_SIZE * z)
            center_x = (
                self.wave_origin
                + (layout.x_offset + marker) * BRICK_SIZE * z
                + LABEL_X * z
            )
            center_y = row_layout.slot_top + (WAVE_TOP + 10.0) * z
            data_index = layout.unseen_markers + marker_index
            text = items[data_index] if 0 <= data_index < len(items) else ""
            text_width = self.data_metrics.horizontalAdvance(text) if text else 0.0
            width = max(segment_width, text_width + 12.0 * z)
            rect = QRectF(
                center_x - width / 2.0,
                center_y - 10.0 * z,
                width,
                20.0 * z,
            )
            targets.append(
                DataTarget(
                    row=row_layout.index,
                    marker_index=marker_index,
                    data_index=data_index,
                    rect=rect,
                    center=QPointF(center_x, center_y),
                    text=text,
                    segment_width=segment_width,
                )
            )
        return targets

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------
    def row_index_at(self, y: float, *, allow_clamp: bool = True) -> int | None:
        if not self.rows:
            return None
        rel = y - self.rows_top
        if rel < 0 or rel >= len(self.rows) * self.row_height:
            if not allow_clamp:
                return None
            if rel < 0:
                return 0
            return len(self.rows) - 1
        return int(rel // self.row_height)

    def row_at(self, y: float) -> RowLayout | None:
        index = self.row_index_at(y)
        if index is None:
            return None
        return self.rows[index]

    def is_wave_area(self, x: float) -> bool:
        return x >= self.wave_origin - 2.0

    def is_name_area(self, x: float, y: float) -> bool:
        row = self.row_at(y)
        return row is not None and x < self.wave_origin - 2.0 and x >= row.name_rect.left()

    def is_group_area(self, x: float, y: float) -> bool:
        return (
            self.max_depth > 0
            and self.row_no_width - 2 <= x < self.row_no_width + self.group_column_width
            and self.row_at(y) is not None
        )

    def group_at(self, x: float, y: float) -> GroupLayout | None:
        """Innermost group under a point in the group gutter."""
        row = self.row_at(y)
        if row is None:
            return None
        candidates = [
            group
            for group in self.groups
            if group.span.start <= row.index <= group.span.end
        ]
        if not candidates:
            return None
        # Clicking the bracket or its rotated name selects the nearest group;
        # nested groups have their brackets further to the right.
        bias = 4.0 * self.zoom
        return min(candidates, key=lambda group: (abs(group.x - (x + bias)), -group.span.depth))

    def cell_at(self, x: float, y: float) -> tuple[int, int] | None:
        row = self.row_at(y)
        if row is None or x < self.wave_origin:
            return None
        col = row.char_at_x(x)
        if col >= len(row.row.wave):
            return None
        return row.index, col

    def char_at(self, x: float, y: float) -> tuple[int, int] | None:
        """Like :meth:`cell_at` but clamps to the row's last cell."""
        row = self.row_at(y)
        if row is None:
            return None
        col = row.char_at_x(x)
        if row.row.wave:
            col = min(col, len(row.row.wave) - 1)
        return row.index, max(0, col)

    def insertion_index(self, y: float) -> int:
        rel = y - self.rows_top
        index = int(round(rel / self.row_height)) if self.row_height else 0
        return max(0, min(index, len(self.rows)))

    def max_column(self) -> int:
        """Highest selectable column (empty cycles to the right included)."""
        return max(MAX_SELECTION_COLUMNS, self.display_units + 8)

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------
    def char_rect(self, row_index: int, col: int, *, clamp: bool = True) -> QRectF | None:
        if row_index < 0 or row_index >= len(self.rows):
            return None
        row = self.rows[row_index]
        if clamp and row.row.wave:
            col = max(0, min(col, len(row.row.wave) - 1))
        col = max(0, min(col, self.max_column()))
        return row.char_rect(col, self.row_height)

    def selection_rect(self, selection) -> QRectF | None:
        if selection is None:
            return None
        row0, col0, row1, col1 = selection
        if row0 > row1:
            row0, row1 = row1, row0
        if col0 > col1:
            col0, col1 = col1, col0
        row0 = max(0, min(row0, len(self.rows) - 1))
        row1 = max(0, min(row1, len(self.rows) - 1))
        if row0 > row1:
            return None
        x0 = self.rows[row0].char_x(col0)
        x1 = self.rows[row0].char_x(col1 + 1)
        # Use the widest cell width among the selected rows for the union.
        for index in range(row0, row1 + 1):
            row = self.rows[index]
            x0 = min(x0, row.char_x(col0))
            x1 = max(x1, row.char_x(col1 + 1))
        y0 = self.rows[row0].slot_top
        y1 = self.rows[row1].slot_top + self.row_height
        return QRectF(x0, y0, max(1.0, x1 - x0), max(1.0, y1 - y0))

    def edit_targets(self) -> list[EditTarget]:
        targets: list[EditTarget] = []
        for row_layout in self.rows:
            name_label = row_layout.row.name or ("" if not self.placeholder else "(unnamed)")
            name_width = max(90.0 * self.zoom, row_layout.name_rect.width())
            name_rect = QRectF(
                row_layout.name_rect.right() - name_width,
                row_layout.slot_top + 2.0 * self.zoom,
                name_width,
                24.0 * self.zoom,
            )
            targets.append(
                EditTarget(
                    kind="name",
                    row=row_layout.index,
                    data_index=-1,
                    rect=name_rect,
                    text=row_layout.row.name,
                    label=name_label,
                )
            )
            for target in sorted(row_layout.data_targets, key=lambda item: item.center.x()):
                rect = QRectF(
                    target.center.x() - max(target.segment_width, 70.0 * self.zoom) / 2.0,
                    target.center.y() - 11.0 * self.zoom,
                    max(target.segment_width, 70.0 * self.zoom),
                    22.0 * self.zoom,
                )
                targets.append(
                    EditTarget(
                        kind="data",
                        row=row_layout.index,
                        data_index=target.data_index,
                        rect=rect,
                        text=target.text,
                        label=target.text or "(empty data)",
                    )
                )
        return targets

    def target_by_key(self, kind: str, row: int, data_index: int = -1) -> EditTarget | None:
        for target in self.edit_targets():
            if target.kind == kind and target.row == row and target.data_index == data_index:
                return target
        return None

    def next_target(self, current: EditTarget | None, delta: int = 1) -> EditTarget | None:
        targets = self.edit_targets()
        if not targets:
            return None
        if current is None:
            return targets[0] if delta >= 0 else targets[-1]
        index = None
        for i, target in enumerate(targets):
            if target.key == current.key:
                index = i
                break
        if index is None:
            return targets[0]
        index = max(0, min(index + delta, len(targets) - 1))
        return targets[index]

    def next_target_of_kind(self, current: EditTarget | None, kind: str, delta: int = 1) -> EditTarget | None:
        """Next edit target of ``kind`` in document order, wrapping around."""
        targets = self.edit_targets()
        if not targets:
            return None
        same = [target for target in targets if target.kind == kind] or targets
        if current is None:
            return same[0]
        order = {id(target): index for index, target in enumerate(targets)}
        position = order.get(id(current))
        if position is None:
            for index, target in enumerate(targets):
                if target.key == current.key:
                    position = index
                    break
        if position is None:
            return same[0] if delta > 0 else same[-1]
        if delta > 0:
            later = [target for target in same if order[id(target)] > position]
            return later[0] if later else same[0]
        earlier = [target for target in same if order[id(target)] < position]
        return earlier[-1] if earlier else same[-1]

    def data_target(self, row_index: int, x: float) -> DataTarget | None:
        if row_index < 0 or row_index >= len(self.rows):
            return None
        return self.rows[row_index].data_target_at(x, tolerance=4.0 * self.zoom)

    def target_at(self, x: float, y: float, *, kind: str | None = None) -> EditTarget | None:
        row = self.row_at(y)
        if row is None:
            return None
        if x < self.wave_origin:
            if kind in (None, "name"):
                # Allow clicking anywhere in the name gutter.
                for target in self.edit_targets():
                    if target.row == row.index and target.kind == "name":
                        return target
            return None
        data = self.data_target(row.index, x)
        if data is not None and kind in (None, "data"):
            for target in self.edit_targets():
                if target.row == row.index and target.kind == "data" and target.data_index == data.data_index:
                    return target
        return None

    # ------------------------------------------------------------------
    def tick_labels(self, head_foot: dict) -> list[tuple[float, str]]:
        return _tick_labels(head_foot, self.time_units, self.time_unit_width, self.wave_origin)

    def time_grid_x(self, unit: int) -> float:
        return self.wave_origin + unit * self.time_unit_width


def _bus_runs(bricks: Iterable[str]) -> list[tuple[int, int, float]]:
    runs: list[tuple[int, int, float]] = []
    start: int | None = None
    for index, brick in enumerate(list(bricks) + ["__end__"]):
        is_bus = brick.startswith("vvv-")
        if is_bus and start is None:
            start = index
        elif not is_bus and start is not None:
            runs.append((start, index, (start + index) / 2.0))
            start = None
    return runs


def _run_for_marker(runs: list[tuple[int, int, float]], marker: float) -> tuple[float, float] | None:
    for start, end, _center in runs:
        if start - 0.5 <= marker <= end + 0.5:
            return float(start), float(end)
    return None


def _label_text(value) -> str:
    return _label_text_raw(value).strip()


def _label_text_raw(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        if not value:
            return ""
        if isinstance(value[0], str):
            return "".join(_label_text_raw(item) for item in value[1:])
        return "".join(_label_text_raw(item) for item in value)
    if isinstance(value, dict):
        return ""
    return str(value)


def _has_ticks(section: dict) -> bool:
    if not isinstance(section, dict):
        return False
    return any(section.get(key) is not None for key in ("tick", "tock"))


def _tick_labels(section: dict, units: int, unit_width: float, origin: float) -> list[tuple[float, str]]:
    if not isinstance(section, dict):
        return []
    labels: list[tuple[float, str]] = []
    every = section.get("every", 1)
    try:
        every = max(1, int(every))
    except (TypeError, ValueError):
        every = 1
    for key, offset in (("tick", 0.0), ("tock", 0.5)):
        value = section.get(key)
        if value is None:
            continue
        values = _tick_values(value, units)
        for index in range(0, min(len(values), units + 1)):
            if index % every:
                continue
            x = origin + (index + offset) * unit_width
            labels.append((x, str(values[index])))
    return labels


def _tick_values(value, units: int) -> list:
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, (int, float)):
        return [index + value for index in range(units + 1)]
    if isinstance(value, str):
        parts = value.strip().split()
        if not parts:
            return []
        value = parts
    if isinstance(value, (list, tuple)):
        if not value:
            return []
        if len(value) == 1:
            try:
                offset = float(value[0])
                return [index + offset for index in range(units + 1)]
            except (TypeError, ValueError):
                return [str(v) for v in value]
        if len(value) == 2:
            try:
                offset, step = float(value[0]), float(value[1])
                decimals = len(str(value[1]).split(".")[1]) if "." in str(value[1]) else 0
                return [f"{(step * index + offset * step):.{decimals}f}" for index in range(units + 1)]
            except (TypeError, ValueError):
                return [str(v) for v in value]
    return [str(v) for v in value]
