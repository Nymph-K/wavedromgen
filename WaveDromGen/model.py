# coding=utf-8
"""Document model for WaveDromGen v2.

The model intentionally mirrors WaveJSON closely: opening a file and saving it
again must not lose unknown fields, and the live JSON editor must be able to
round-trip the document exactly (apart from the convenience defaults added to
newly created rows).
"""
from __future__ import annotations

import copy
import json
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .wavedrom_render import (
    clock_extension,
    clock_like,
    data_items,
    expand_raw_waves,
    row_time_units,
    sanitize_wave_char,
)

try:  # optional, enables comments/trailing commas/single quotes in the editor
    import json5  # type: ignore
except Exception:  # pragma: no cover - json5 is optional
    json5 = None


ROW_FIELD_ORDER = ("name", "wave", "node", "data", "phase", "period")
DEFAULT_COLUMNS = 20
MAX_HISTORY = 200

CLOCK_RE = re.compile(r"clk|clock", re.IGNORECASE)


class DocumentError(ValueError):
    """Raised when a WaveJSON document is structurally invalid."""

    def __init__(self, message: str, line: int | None = None, column: int | None = None):
        super().__init__(message)
        self.line = line
        self.column = column


def _as_int(value: Any, fallback: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return fallback
    return number


def _as_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


class SignalRow:
    """One WaveDrom ``signal`` lane."""

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any] | None = None):
        if data is None:
            data = OrderedDict(
                (
                    ("name", "signal"),
                    ("wave", ""),
                    ("node", ""),
                    ("data", ""),
                    ("phase", 0),
                    ("period", 1),
                )
            )
        if not isinstance(data, dict):
            raise DocumentError("each signal must be a JSON object")
        self._data = OrderedDict(data)

    # -- basic values -------------------------------------------------
    @property
    def name(self) -> str:
        value = self._data.get("name", "")
        return "" if value is None else str(value)

    @name.setter
    def name(self, value: str) -> None:
        self._data["name"] = "" if value is None else str(value)

    @property
    def wave(self) -> str:
        value = self._data.get("wave", "")
        return value if isinstance(value, str) else ""

    @wave.setter
    def wave(self, value: str) -> None:
        self._data["wave"] = value

    @property
    def raw_wave(self) -> Any:
        return self._data.get("wave", "")

    @property
    def node(self) -> str:
        value = self._data.get("node", "")
        return value if isinstance(value, str) else ""

    @node.setter
    def node(self, value: str) -> None:
        self._data["node"] = value

    @property
    def data_value(self) -> Any:
        return self._data.get("data", "")

    @property
    def phase(self) -> float:
        return _as_float(self._data.get("phase", 0), 0.0)

    @phase.setter
    def phase(self, value: float) -> None:
        self._data["phase"] = value

    @property
    def period(self) -> int:
        return max(1, _as_int(self._data.get("period", 1), 1))

    @period.setter
    def period(self, value: int) -> None:
        self._data["period"] = max(1, int(value))

    @property
    def has_name(self) -> bool:
        return bool(self.name.strip())

    @property
    def is_clock(self) -> bool:
        return CLOCK_RE.search(self.name) is not None

    @property
    def is_spacer(self) -> bool:
        return not self.wave and not self.name and not self.node and not data_items(self.data_value)

    @property
    def char_count(self) -> int:
        return len(self.wave)

    @property
    def time_units(self) -> float:
        return row_time_units(self, 1)

    # -- data ---------------------------------------------------------
    def data_items(self) -> list[str]:
        return data_items(self.data_value)

    def set_data_items(self, items: Sequence[str]) -> None:
        items = [str(item) for item in items]
        original = self._data.get("data", "")
        if isinstance(original, (list, tuple)):
            self._data["data"] = items
        else:
            self._data["data"] = " ".join(items)

    def set_data_label(self, index: int, value: str) -> None:
        if index < 0:
            return
        items = self.data_items()
        while len(items) <= index:
            items.append("")
        items[index] = value
        self.set_data_items(items)

    # -- geometry helpers --------------------------------------------
    def char_at(self, index: int) -> str:
        wave = self.wave
        return wave[index] if 0 <= index < len(wave) else ""

    def ensure_length(self, length: int, *, fill: str = ".") -> bool:
        """Pad ``wave``/``node`` to at least ``length`` characters."""
        changed = False
        length = max(0, int(length))
        if not isinstance(self.raw_wave, str):
            self._data["wave"] = "0" + "." * max(0, length - 1)
            changed = True
        elif self.wave == "" and length > 0:
            # Painting into an empty lane starts from a defined low level
            # rather than a run of unknown states.
            self._data["wave"] = "0" + "." * (length - 1)
            changed = True
        if len(self.wave) < length:
            self._data["wave"] = self.wave + fill * (length - len(self.wave))
            changed = True
        if len(self.node) < len(self.wave):
            self._data["node"] = self.node + "." * (len(self.wave) - len(self.node))
            changed = True
        return changed

    def set_wave_char(self, index: int, char: str) -> bool:
        char = sanitize_wave_char(char)
        if char is None or index < 0:
            return False
        self.ensure_length(index + 1)
        wave = self.wave
        if index >= len(wave):
            return False
        if wave[index] == char:
            return False
        self._data["wave"] = wave[:index] + char + wave[index + 1:]
        return True

    def clear_range(self, start: int, end: int, char: str = ".") -> bool:
        char = sanitize_wave_char(char) or "."
        changed = False
        for index in range(max(0, start), max(start, end)):
            if self.set_wave_char(index, char):
                changed = True
        return changed

    def set_node_char(self, index: int, char: str) -> bool:
        if index < 0:
            return False
        self.ensure_length(index + 1)
        node = self.node
        char = (char or ".")[0]
        if index < len(node) and node[index] == char:
            return False
        self._data["node"] = node[:index] + char + node[index + 1 :]
        return True

    def extend_clock(self, target_time_units: float) -> bool:
        if not self.is_clock:
            return False
        new_wave = clock_extension(self, target_time_units)
        if not isinstance(new_wave, str) or new_wave == self.wave:
            return False
        self._data["wave"] = new_wave
        if len(self.node) < len(new_wave):
            self._data["node"] = self.node + "." * (len(new_wave) - len(self.node))
        return True

    # -- serialisation ------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        result: OrderedDict[str, Any] = OrderedDict()
        # Keep the familiar WaveDrom field order, then any extra fields.
        for key in ROW_FIELD_ORDER:
            if key in self._data:
                result[key] = copy.deepcopy(self._data[key])
        for key, value in self._data.items():
            if key not in result:
                result[key] = copy.deepcopy(value)
        if "name" not in result:
            result["name"] = ""
        if "wave" not in result:
            result["wave"] = ""
        return dict(result)

    def clone(self) -> "SignalRow":
        return SignalRow(self.to_dict())

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"SignalRow(name={self.name!r}, wave={self.wave!r})"


def _flatten_signal_list(items: list[Any], notes: list[str]) -> list[SignalRow]:
    rows: list[SignalRow] = []
    for item in items:
        if isinstance(item, list):
            if not item:
                continue
            group = item[0] if isinstance(item[0], str) else ""
            if group:
                notes.append(f'Signal group "{group}" was flattened for editing.')
            rows.extend(_flatten_signal_list(list(item[1:]), notes))
        elif isinstance(item, dict):
            rows.append(SignalRow(item))
        elif item is None:
            rows.append(SignalRow({}))
        else:
            notes.append(f"Ignored unsupported signal entry: {item!r}")
    return rows


def _default_document() -> dict[str, Any]:
    cols = DEFAULT_COLUMNS
    return OrderedDict(
        (
            (
                "signal",
                [
                    {
                        "name": "clk",
                        "wave": "p" + "." * (cols - 1),
                        "node": "." * cols,
                        "data": "",
                        "phase": 0,
                        "period": 1,
                    },
                    {
                        "name": "rstn",
                        "wave": "01" + "." * (cols - 2),
                        "node": "." * cols,
                        "data": "",
                        "phase": 0,
                        "period": 1,
                    },
                    {
                        "name": "signal",
                        "wave": "0" + "." * (cols - 1),
                        "node": "." * cols,
                        "data": "",
                        "phase": 0,
                        "period": 1,
                    },
                ],
            ),
            ("edge", []),
            ("config", OrderedDict((("hscale", 1), ("skin", "default")))),
        )
    )


@dataclass
class Selection:
    row0: int
    col0: int
    row1: int
    col1: int

    def normalized(self) -> "Selection":
        return Selection(
            min(self.row0, self.row1),
            min(self.col0, self.col1),
            max(self.row0, self.row1),
            max(self.col0, self.col1),
        )

    def cell_count(self, rows: Sequence[SignalRow] | None = None) -> int:
        sel = self.normalized()
        if rows is None:
            return (sel.row1 - sel.row0 + 1) * (sel.col1 - sel.col0 + 1)
        total = 0
        for row in rows[sel.row0 : sel.row1 + 1]:
            total += max(0, min(sel.col1 + 1, len(row.wave)) - sel.col0)
        return total


class WaveDocument:
    """Editable WaveJSON document with snapshot based undo/redo."""

    def __init__(self, *, auto_extend_clocks: bool = True):
        self.rows: list[SignalRow] = []
        self.edges: list[Any] = []
        self.config: OrderedDict[str, Any] = OrderedDict()
        self._fields: OrderedDict[str, Any] = OrderedDict()
        self._signal_position = 0
        self.auto_extend_clocks = auto_extend_clocks
        self.notes: list[str] = []
        self.path: str | None = None

        self._undo: list[str] = []
        self._redo: list[str] = []
        self._saved_snapshot = ""
        self._dirty = False
        self._last_tag: str | None = None
        self._last_record_time = 0.0
        self.new(record=False)

    # ------------------------------------------------------------------
    # Loading / saving
    # ------------------------------------------------------------------
    def new(self, *, record: bool = True) -> None:
        if record:
            self._record("new")
        self._apply_dict(_default_document(), notes=[])
        self._undo.clear()
        self._redo.clear()
        self._saved_snapshot = self.snapshot()
        self._dirty = False
        self.path = None
        self._last_tag = None

    def load_dict(self, data: dict[str, Any], *, source: str = "") -> None:
        if not isinstance(data, dict):
            raise DocumentError("the document root must be a JSON object")
        self.notes.clear()
        notes: list[str] = []
        self._apply_dict(data, notes=notes)
        self.notes.extend(notes)
        self._undo.clear()
        self._redo.clear()
        self.path = source or None
        self._saved_snapshot = self.snapshot()
        self._dirty = False
        self._last_tag = None

    def _apply_dict(self, data: dict[str, Any], notes: list[str]) -> None:
        signal = data.get("signal", [])
        if not isinstance(signal, list):
            raise DocumentError('"signal" must be a JSON array')
        self.rows = _flatten_signal_list(signal, notes)
        self.edges = copy.deepcopy(data.get("edge", [])) if isinstance(data.get("edge", []), list) else []
        config = data.get("config", {})
        self.config = OrderedDict(config) if isinstance(config, dict) else OrderedDict()
        self.config.setdefault("hscale", 1)
        self.config.setdefault("skin", "default")
        self._fields = OrderedDict()
        self._signal_position = 0
        for index, (key, value) in enumerate(data.items()):
            if key == "signal":
                self._signal_position = index
            self._fields[key] = copy.deepcopy(value)
        if self.auto_extend_clocks:
            self.extend_clocks(record=False)
        self._normalise_basics()
    def _normalise_basics(self) -> None:
        if not isinstance(self.config, OrderedDict):
            self.config = OrderedDict(self.config)

    def load_json_text(self, text: str, *, source: str = "") -> None:
        data = self.parse_json_text(text)
        self.load_dict(data, source=source)

    @staticmethod
    def parse_json_text(text: str) -> dict[str, Any]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            if json5 is None:
                raise DocumentError(
                    f"JSON error: {exc.msg}", line=exc.lineno, column=exc.colno
                ) from exc
            try:
                data = json5.loads(text)
            except Exception as exc2:  # noqa: BLE001 - json5 has many error types
                message = str(exc2) or "Invalid JSON"
                line, column = _extract_json5_position(message)
                raise DocumentError(message, line=line, column=column) from exc2
        if not isinstance(data, dict):
            raise DocumentError("the document root must be a JSON object")
        return data

    def apply_json_text(self, text: str, *, record: bool = True) -> None:
        """Apply editor content to the model without resetting history."""
        data = self.parse_json_text(text)
        notes: list[str] = []
        # Validate the structure before touching the current document.
        signal = data.get("signal", [])
        if not isinstance(signal, list):
            raise DocumentError('"signal" must be a JSON array')
        if record:
            self._record("json", coalesce=True)
        self.notes.clear()
        self._apply_dict(data, notes=notes)
        self.notes.extend(notes)
        self._dirty = True
        self._last_tag = None

    def dump_dict(self) -> dict[str, Any]:
        # Preserve the top-level key order of the loaded document.  ``signal``,
        # ``edge`` and ``config`` are placed where they originally appeared.
        original_order = list(self._fields.keys())
        result: OrderedDict[str, Any] = OrderedDict()
        signal_placed = False
        for key in original_order:
            if key.lower() == "signal":
                if not signal_placed:
                    result["signal"] = [row.to_dict() for row in self.rows]
                    signal_placed = True
                continue
            if key.lower() == "edge":
                result["edge"] = copy.deepcopy(self.edges)
                continue
            if key.lower() == "config":
                result["config"] = copy.deepcopy(dict(self.config))
                continue
            result[key] = copy.deepcopy(self._fields[key])
        if not signal_placed:
            # Insert at the remembered position rather than always at the end.
            items = list(result.items())
            at = max(0, min(self._signal_position, len(items)))
            items.insert(at, ("signal", [row.to_dict() for row in self.rows]))
            result = OrderedDict(items)
        if "edge" not in result:
            result["edge"] = copy.deepcopy(self.edges)
        if "config" not in result:
            result["config"] = copy.deepcopy(dict(self.config))
        return dict(result)

    def snapshot(self) -> str:
        return json.dumps(self.dump_dict(), ensure_ascii=False, separators=(",", ":"))

    def to_json_text(self, *, indent: int = 2) -> str:
        return json.dumps(self.dump_dict(), ensure_ascii=False, indent=indent) + "\n"

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    def _record(self, tag: str | None = None, *, coalesce: bool = False) -> None:
        now = time.monotonic()
        if (
            coalesce
            and tag is not None
            and tag == self._last_tag
            and now - self._last_record_time < 0.9
        ):
            self._last_record_time = now
            self._redo.clear()
            self._dirty = True
            return
        snapshot = self.snapshot()
        if self._undo and self._undo[-1] == snapshot:
            self._redo.clear()
            self._dirty = True
            self._last_tag = tag
            self._last_record_time = now
            return
        self._undo.append(snapshot)
        if len(self._undo) > MAX_HISTORY:
            self._undo.pop(0)
        self._redo.clear()
        self._dirty = True
        self._last_tag = tag
        self._last_record_time = now

    def begin_edit(self, tag: str | None = None, *, coalesce: bool = False) -> None:
        """Public alias used by widgets before mutating through a batch."""
        self._record(tag, coalesce=coalesce)

    def touch(self) -> None:
        self._dirty = True

    def _restore_snapshot(self, snapshot: str) -> None:
        data = json.loads(snapshot)
        self._apply_dict(data, notes=[])
        self._dirty = snapshot != self._saved_snapshot
        self._last_tag = None

    def undo(self) -> bool:
        if not self._undo:
            return False
        current = self.snapshot()
        snapshot = self._undo.pop()
        self._redo.append(current)
        self._restore_snapshot(snapshot)
        self._dirty = self.snapshot() != self._saved_snapshot
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        current = self.snapshot()
        snapshot = self._redo.pop()
        self._undo.append(current)
        self._restore_snapshot(snapshot)
        self._dirty = self.snapshot() != self._saved_snapshot
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_saved(self, path: str | None = None) -> None:
        self._saved_snapshot = self.snapshot()
        if path is not None:
            self.path = path
        self._dirty = False

    # ------------------------------------------------------------------
    # Geometry / stats
    # ------------------------------------------------------------------
    @property
    def column_count(self) -> int:
        return max((len(row.wave) for row in self.rows), default=0)

    @property
    def time_units(self) -> float:
        return max((row.time_units for row in self.rows), default=0.0)

    @property
    def name_width(self) -> int:
        return max((len(row.name) for row in self.rows), default=0)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def row(self, index: int) -> SignalRow | None:
        if 0 <= index < len(self.rows):
            return self.rows[index]
        return None

    def hscale(self) -> int:
        return max(1, _as_int(self.config.get("hscale", 1), 1))

    def skin_name(self) -> str:
        value = self.config.get("skin", "default")
        return value if isinstance(value, str) and value else "default"

    @property
    def head(self) -> dict[str, Any]:
        value = self._fields.get("head")
        return value if isinstance(value, dict) else {}

    @property
    def foot(self) -> dict[str, Any]:
        value = self._fields.get("foot")
        return value if isinstance(value, dict) else {}

    @property
    def gaps(self) -> str:
        value = self._fields.get("gaps")
        return value if isinstance(value, str) else ""

    def data_label_count(self, row: SignalRow) -> int:
        from .wavedrom_render import lane_layout

        return len(lane_layout(row, self.hscale()).markers)

    # ------------------------------------------------------------------
    # Clocks
    # ------------------------------------------------------------------
    def extend_clocks(self, *, record: bool = True) -> list[int]:
        """Extend clock lanes to the longest signal (requirement #4)."""
        if record:
            self._record("extend-clocks")
        target = self.time_units
        changed: list[int] = []
        if target <= 0:
            return changed
        for index, row in enumerate(self.rows):
            if row.is_clock and row.extend_clock(target):
                changed.append(index)
        if changed:
            self._dirty = True
        return changed

    def extend_clock_to_longest(self, index: int) -> bool:
        row = self.row(index)
        if row is None:
            return False
        return row.extend_clock(self.time_units)

    # ------------------------------------------------------------------
    # Row operations
    # ------------------------------------------------------------------
    def _default_wave(self, columns: int, *, clock: bool = False) -> str:
        columns = max(1, columns)
        return ("p" + "." * (columns - 1)) if clock else ("0" + "." * (columns - 1))

    def make_row(self, *, name: str = "signal", columns: int | None = None, clock: bool | None = None) -> SignalRow:
        columns = columns if columns is not None else max(DEFAULT_COLUMNS, self.column_count)
        is_clock = clock if clock is not None else clock_like(name)
        return SignalRow(
            OrderedDict(
                (
                    ("name", name),
                    ("wave", self._default_wave(columns, clock=is_clock)),
                    ("node", "." * max(1, columns)),
                    ("data", ""),
                    ("phase", 0),
                    ("period", 1),
                )
            )
        )

    def insert_rows(self, index: int, rows: Iterable[SignalRow], *, record: bool = True) -> None:
        if record:
            self._record("insert-row")
        new_rows = list(rows)
        if not new_rows:
            return
        index = max(0, min(index, len(self.rows)))
        for row in new_rows:
            row.ensure_length(max(1, len(row.wave)))
        self.rows[index:index] = new_rows
        if self.auto_extend_clocks:
            self.extend_clocks(record=False)
        self._dirty = True

    def insert_blank(self, index: int, *, name: str = "signal", clock: bool | None = None) -> int:
        row = self.make_row(name=name, clock=clock)
        self.insert_rows(index, [row])
        return index

    def add_row(self, *, name: str = "signal") -> int:
        row = self.make_row(name=name)
        self.insert_rows(len(self.rows), [row])
        return len(self.rows) - 1

    def delete_rows(self, indices: Iterable[int]) -> list[int]:
        selected = sorted({i for i in indices if 0 <= i < len(self.rows)})
        if not selected:
            return []
        self._record("delete-row")
        for index in reversed(selected):
            del self.rows[index]
        self._prune_edges()
        if self.auto_extend_clocks:
            self.extend_clocks(record=False)
        self._dirty = True
        return selected

    def duplicate_rows(self, indices: Iterable[int]) -> list[int]:
        selected = sorted({i for i in indices if 0 <= i < len(self.rows)})
        if not selected:
            return []
        self._record("duplicate-row")
        insert_at = selected[-1] + 1
        clones = [self.rows[i].clone() for i in selected]
        self.rows[insert_at:insert_at] = clones
        if self.auto_extend_clocks:
            self.extend_clocks(record=False)
        self._dirty = True
        return list(range(insert_at, insert_at + len(clones)))

    def copy_rows(self, indices: Iterable[int]) -> list[dict[str, Any]]:
        return [self.rows[i].to_dict() for i in sorted(set(indices)) if 0 <= i < len(self.rows)]

    def paste_rows(self, payload: Any, index: int | None = None) -> list[int]:
        rows = _normalise_clipboard_rows(payload)
        if not rows:
            return []
        self._record("paste-row")
        if index is None:
            index = len(self.rows)
        index = max(0, min(index, len(self.rows)))
        new_rows = [SignalRow(item) for item in rows]
        self.rows[index:index] = new_rows
        if self.auto_extend_clocks:
            self.extend_clocks(record=False)
        self._dirty = True
        return list(range(index, index + len(new_rows)))

    def move_rows(self, indices: Iterable[int], target: int) -> list[int]:
        selected = sorted({i for i in indices if 0 <= i < len(self.rows)})
        if not selected:
            return []
        self._record("move-row")
        moving = [self.rows[i] for i in selected]
        before = sum(1 for i in selected if i < target)
        for index in reversed(selected):
            del self.rows[index]
        insert_at = max(0, min(target - before, len(self.rows)))
        self.rows[insert_at:insert_at] = moving
        self._dirty = True
        return list(range(insert_at, insert_at + len(moving)))

    def move_row_up(self, index: int) -> int:
        if index <= 0 or index >= len(self.rows):
            return index
        self.move_rows([index], index - 1)
        return index - 1

    def move_row_down(self, index: int) -> int:
        if index < 0 or index >= len(self.rows) - 1:
            return index
        self.move_rows([index], index + 2)
        return index + 1

    # ------------------------------------------------------------------
    # Cell / waveform operations
    # ------------------------------------------------------------------
    def set_name(self, index: int, name: str) -> bool:
        row = self.row(index)
        if row is None:
            return False
        if row.name == name:
            return False
        self._record("name")
        row.name = name
        if row.is_clock and self.auto_extend_clocks:
            self.extend_clocks(record=False)
        self._dirty = True
        return True

    def update_row(self, index: int, values: dict[str, Any]) -> bool:
        """Update arbitrary row fields from the properties dialog."""
        row = self.row(index)
        if row is None:
            return False
        self._record("row-properties")
        changed = False
        for key in ("name", "wave", "node", "period", "phase"):
            if key not in values:
                continue
            value = values[key]
            if key == "period":
                value = max(1, int(value or 1))
            elif key == "phase":
                value = max(0.0, float(value or 0))
            elif key in ("name", "wave", "node"):
                value = "" if value is None else str(value)
            if row._data.get(key) != value:
                row._data[key] = value
                changed = True
        if "data" in values:
            items = values["data"]
            if isinstance(items, str):
                items = items.split()
            items = [str(item) for item in (items or [])]
            if row.data_items() != items:
                row.set_data_items(items)
                changed = True
        if changed:
            row.ensure_length(len(row.wave))
            if self.auto_extend_clocks:
                self.extend_clocks(record=False)
            self._dirty = True
        return changed

    def set_data_label(self, index: int, label_index: int, value: str) -> bool:
        row = self.row(index)
        if row is None:
            return False
        existing = row.data_items()
        old = existing[label_index] if 0 <= label_index < len(existing) else ""
        if old == value:
            return False
        self._record("data-label")
        row.set_data_label(label_index, value)
        self._dirty = True
        return True

    def apply_wave_chars(self, cells: Iterable[tuple[int, int]], char: str, *, tag: str = "wave") -> int:
        """Set the same raw wave character in every selected cell."""
        char = sanitize_wave_char(char)
        if char is None:
            return 0
        self._record(tag, coalesce=True)
        changed = 0
        # Extend the document to cover all selected columns first, so painting
        # into the empty area to the right works as expected.
        max_col = -1
        cell_list = list(cells)
        for y, x in cell_list:
            max_col = max(max_col, x)
        if max_col >= 0:
            for row in self.rows:
                row.ensure_length(max_col + 1)
        for y, x in cell_list:
            row = self.row(y)
            if row is None:
                continue
            if row.set_wave_char(x, char):
                changed += 1
        if self.auto_extend_clocks:
            self.extend_clocks(record=False)
        if changed:
            self._dirty = True
        return changed

    def apply_wave_sequence(self, cells: Iterable[tuple[int, int]], chars: str) -> int:
        chars = "".join(c for c in (chars or "") if sanitize_wave_char(c) is not None)
        if not chars:
            return 0
        cell_list = list(cells)
        if not cell_list:
            return 0
        if len(chars) == 1:
            return self.apply_wave_chars(cell_list, chars)
        self._record("wave-paste")
        changed = 0
        max_col = max((x for _, x in cell_list), default=-1)
        if max_col >= 0:
            for row in self.rows:
                row.ensure_length(max_col + 1)
        for (y, x), char in zip(cell_list, chars):
            row = self.row(y)
            if row is None:
                continue
            if row.set_wave_char(x, char):
                changed += 1
        if self.auto_extend_clocks:
            self.extend_clocks(record=False)
        if changed:
            self._dirty = True
        return changed

    def clear_cells(self, cells: Iterable[tuple[int, int]]) -> int:
        return self.apply_wave_chars(cells, ".", tag="clear-cells")

    def clear_row(self, index: int, *, keep_name: bool = True) -> bool:
        row = self.row(index)
        if row is None:
            return False
        self._record("clear-row")
        length = max(1, len(row.wave), self.column_count)
        if not keep_name:
            row.name = ""
        row._data["wave"] = "." * length
        row._data["data"] = ""
        row._data["node"] = "." * length
        if self.auto_extend_clocks:
            self.extend_clocks(record=False)
        self._dirty = True
        return True

    def clear_rows(self, indices: Iterable[int], *, keep_name: bool = True) -> int:
        rows = sorted({i for i in indices if 0 <= i < len(self.rows)})
        if not rows:
            return 0
        self._record("clear-row")
        length = max(1, self.column_count)
        for index in rows:
            row = self.rows[index]
            if not keep_name:
                row.name = ""
            row._data["wave"] = "." * max(length, len(row.wave), 1)
            row._data["data"] = ""
            row._data["node"] = "." * max(length, len(row.node), 1)
        if self.auto_extend_clocks:
            self.extend_clocks(record=False)
        self._dirty = True
        return len(rows)

    def set_char_toggle(self, index: int, col: int, char: str) -> bool:
        row = self.row(index)
        if row is None:
            return False
        current = row.char_at(col)
        new_char = "." if current == char else char
        return bool(self.apply_wave_chars([(index, col)], new_char, tag="draw"))

    def set_node(self, index: int, col: int, char: str) -> bool:
        row = self.row(index)
        if row is None or col < 0:
            return False
        if char and char != ".":
            # Node markers must be unique so edges can reference them.
            used = set()
            for other in self.rows:
                used.update(ch for ch in other.node if ch != ".")
            if char in used and row.node[col : col + 1] != char:
                return False
        self._record("node")
        if row.node and char == ".":
            row.set_node_char(col, ".")
        else:
            row.set_node_char(col, char)
        self._prune_edges()
        self._dirty = True
        return True

    def node_markers(self) -> dict[str, tuple[int, int]]:
        markers: dict[str, tuple[int, int]] = {}
        for y, row in enumerate(self.rows):
            for x, char in enumerate(row.node):
                if char != ".":
                    markers.setdefault(char, (y, x))
        return markers

    def _prune_edges(self) -> None:
        markers = self.node_markers()
        kept: list[Any] = []
        for edge in self.edges:
            if not isinstance(edge, str):
                kept.append(edge)
                continue
            head = edge.strip().split(" ", 1)[0]
            if len(head) < 2:
                kept.append(edge)
                continue
            start, end = head[0], head[-1]
            if start in markers and end in markers:
                kept.append(edge)
        self.edges = kept

    # ------------------------------------------------------------------
    # Columns / config
    # ------------------------------------------------------------------
    def add_columns(self, count: int = 1) -> None:
        count = max(1, int(count))
        self._record("add-column")
        for row in self.rows:
            if not row.wave:
                continue
            row.ensure_length(len(row.wave))
            row._data["wave"] = row.wave + "." * count
            row._data["node"] = row.node + "." * count
        if self.auto_extend_clocks:
            self.extend_clocks(record=False)
        self._dirty = True

    def delete_columns(self, start: int, count: int = 1) -> None:
        count = max(1, int(count))
        self._record("delete-column")
        for row in self.rows:
            wave = row.wave
            node = row.node
            if wave:
                row._data["wave"] = wave[:start] + wave[start + count :]
            if node:
                row._data["node"] = node[:start] + node[start + count :]
        if self.auto_extend_clocks:
            self.extend_clocks(record=False)
        self._dirty = True

    def set_config(self, key: str, value: Any) -> bool:
        if self.config.get(key) == value:
            return False
        self._record("config")
        self.config[key] = value
        self._dirty = True
        return True

    def set_hscale(self, value: int) -> None:
        self.set_config("hscale", max(1, min(100, int(value))))

    def set_skin(self, skin: str) -> None:
        self.set_config("skin", skin)

    def set_period(self, index: int, value: int) -> bool:
        row = self.row(index)
        if row is None:
            return False
        value = max(1, int(value))
        if row.period == value:
            return False
        self._record("period")
        row.period = value
        if self.auto_extend_clocks:
            self.extend_clocks(record=False)
        self._dirty = True
        return True

    def set_phase(self, index: int, value: float) -> bool:
        row = self.row(index)
        if row is None:
            return False
        if abs(row.phase - float(value)) < 1e-9:
            return False
        self._record("phase")
        row.phase = max(0.0, float(value))
        self._dirty = True
        return True

    def set_edges(self, edges: Sequence[Any]) -> None:
        self._record("edges")
        self.edges = copy.deepcopy(list(edges))
        self._dirty = True

    # ------------------------------------------------------------------
    # Clipboard payloads
    # ------------------------------------------------------------------
    def clipboard_payload(self, indices: Iterable[int]) -> str:
        rows = self.copy_rows(indices)
        return json.dumps({"signal": rows}, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    def ascii_text(self) -> str:
        from .ascii_render import document_to_ascii

        return document_to_ascii(self)

    def summary(self) -> str:
        return f"{len(self.rows)} signals · {self.column_count} cells"


def _normalise_clipboard_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            try:
                payload = json5.loads(text) if json5 else None
            except Exception:
                return []
    if isinstance(payload, dict):
        if "signal" in payload and isinstance(payload["signal"], list):
            payload = payload["signal"]
        elif "wave" in payload or "name" in payload:
            payload = [payload]
        else:
            return []
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            rows.append(dict(item))
        elif isinstance(item, list):
            # Tolerate grouped clipboard payloads.
            rows.extend(_normalise_clipboard_rows(item))
    return rows


def _format_json_error(exc: json.JSONDecodeError) -> str:
    return f"JSON error at line {exc.lineno}, column {exc.colno}: {exc.msg}"


def _format_json5_error(exc: Exception) -> str:
    text = str(exc)
    return f"JSON error: {text}" if text else "Invalid JSON"


def _extract_json5_position(message: str) -> tuple[int | None, int | None]:
    patterns = (
        r"line\s+(\d+)\s+column\s+(\d+)",
        r"(?:<string>|[^\s:]+):(\d+).*?column\s+(\d+)",
        r"at\s+line\s+(\d+).*?column\s+(\d+)",
        r"\((\d+):(\d+)\)",
    )
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None, None


def expand_row(row: SignalRow) -> str:
    """Return the explicit per-cell waveform (used by tests/tools)."""
    return expand_raw_waves(row.wave)


def waveform_summary(row: SignalRow) -> str:
    if row.wave:
        return row.wave
    return ""
