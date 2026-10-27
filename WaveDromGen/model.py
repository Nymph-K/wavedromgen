# coding=utf-8
"""Document model for WaveDromGen v2.

The model intentionally mirrors WaveJSON closely: opening a file and saving it
again must not lose unknown fields, named signal groups, empty lanes or any
other syntax WaveDrom understands but this editor does not have a dedicated
widget for.  The live JSON editor must be able to round-trip the document
exactly (apart from the convenience defaults added to newly created rows).
"""
from __future__ import annotations

import copy
import json
import math
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
    def is_blank_entry(self) -> bool:
        """True for a bare ``{}`` lane: no name, no wave, no nodes, no data."""
        return not self._data

    @property
    def shows_placeholder_name(self) -> bool:
        """Only lanes that actually carry a waveform get the "signal" hint."""
        return bool(self.wave)

    @property
    def char_count(self) -> int:
        return len(self.wave)

    @property
    def time_units(self) -> float:
        return row_time_units(self, 1)

    # -- data ---------------------------------------------------------
    def data_items(self) -> list[str]:
        return data_items(self.data_value)

    def set_data_items(self, items: Sequence[str], *, as_list: bool | None = None) -> None:
        """Store the ``data`` array.

        ``as_list=None`` keeps the original spelling (string or array).  GUI
        editing passes ``as_list=True`` so labels are written as a proper
        WaveJSON array instead of a space separated string.
        """
        items = [str(item) for item in items]
        original = self._data.get("data", "")
        if as_list is None:
            as_list = isinstance(original, (list, tuple))
        if as_list:
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
        self.set_data_items(items, as_list=True)

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
        if not self.wave:
            return False
        new_wave = clock_extension(self, target_time_units)
        return self._set_wave(new_wave)

    def fit_clock(self, target_time_units: float) -> bool:
        """Extend *or* shrink a clock lane so it matches ``target_time_units``."""
        if not self.is_clock or not self.wave:
            return False
        new_wave = clock_fitted(self, target_time_units)
        return self._set_wave(new_wave)

    def _set_wave(self, new_wave: Any) -> bool:
        if not isinstance(new_wave, str) or new_wave == self.wave:
            return False
        self._data["wave"] = new_wave
        if len(self.node) < len(new_wave):
            self._data["node"] = self.node + "." * (len(new_wave) - len(self.node))
        elif len(self.node) > len(new_wave):
            self._data["node"] = self.node[: len(new_wave)]
        return True

    def insert_wave(self, index: int, chars: str = ".") -> bool:
        """Insert ``chars`` before ``index``, shifting the rest to the right."""
        if not chars:
            return False
        wave = self.wave
        if not wave:
            return False
        index = max(0, min(index, len(wave)))
        self._data["wave"] = wave[:index] + chars + wave[index:]
        node = self.node or ""
        if not node:
            node = "." * len(wave)
        index = max(0, min(index, len(node)))
        self._data["node"] = node[:index] + "." * len(chars) + node[index:]
        return True

    def delete_wave(self, start: int, end: int) -> bool:
        """Delete the inclusive character range ``[start, end]``."""
        wave = self.wave
        if not wave:
            return False
        length = len(wave)
        start = max(0, min(int(start), length))
        end = max(start, min(int(end), length - 1))
        if start >= length or end < start:
            return False
        count = end - start + 1
        self._data["wave"] = wave[:start] + wave[end + 1 :]
        node = self.node
        if node:
            self._data["node"] = node[:start] + node[start + count :]
        return True

    # -- serialisation ------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        if not self._data:
            # Preserve bare ``{}`` spacer lanes exactly as written.
            return {}
        result: OrderedDict[str, Any] = OrderedDict()
        # Keep the familiar WaveDrom field order, then any extra fields.
        for key in ROW_FIELD_ORDER:
            if key in self._data:
                result[key] = copy.deepcopy(self._data[key])
        for key, value in self._data.items():
            if key not in result:
                result[key] = copy.deepcopy(value)
        # Rows loaded with only e.g. ``node`` must not gain empty name/wave
        # keys: WaveDrom treats a missing name/wave as empty too, and keeping
        # the document untouched makes save/reload a perfect round trip.
        if ("name" in self._data or "wave" in self._data) and self._data:
            result.setdefault("name", "")
            result.setdefault("wave", "")
        return dict(result)

    def clone(self) -> "SignalRow":
        return SignalRow(copy.deepcopy(self._data))

    def to_value(self) -> Any:
        """Serialise for the ``signal`` array (see :meth:`to_dict`)."""
        return self.to_dict()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"SignalRow(name={self.name!r}, wave={self.wave!r})"


class Group:
    """A named WaveDrom signal group: ``["name", {...}, {...}]``."""

    __slots__ = ("name", "children", "preserve_empty")

    def __init__(self, name: Any = None, children: list[Any] | None = None):
        self.name = name
        self.children: list[Any] = list(children or [])
        self.preserve_empty = not self.children

    @property
    def display_name(self) -> str:
        if self.name is None:
            return ""
        if isinstance(self.name, str):
            return self.name
        return str(self.name)

    @property
    def has_name(self) -> bool:
        return self.name is not None and bool(str(self.name).strip())

    def to_value(self) -> list[Any]:
        values: list[Any] = []
        if self.name is not None:
            values.append(copy.deepcopy(self.name))
        values.extend(child.to_value() for child in self.children)
        return values

    def clone(self) -> "Group":
        group = Group(copy.deepcopy(self.name), [child.clone() for child in self.children])
        group.preserve_empty = self.preserve_empty
        return group

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Group(name={self.name!r}, children={len(self.children)})"


class RawEntry:
    """An unsupported ``signal`` entry kept verbatim so it is never lost."""

    __slots__ = ("value",)

    def __init__(self, value: Any):
        self.value = copy.deepcopy(value)

    def to_value(self) -> Any:
        return copy.deepcopy(self.value)

    def clone(self) -> "RawEntry":
        return RawEntry(self.value)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"RawEntry({self.value!r})"


SignalNode = SignalRow | Group | RawEntry


@dataclass(frozen=True)
class GroupSpan:
    """Geometry information for one rendered group bracket."""

    group: Group
    start: int
    end: int  # inclusive row index
    depth: int

    @property
    def row_count(self) -> int:
        return self.end - self.start + 1


def _parse_signal_nodes(items: Sequence[Any]) -> list[SignalNode]:
    nodes: list[SignalNode] = []
    for item in items:
        if isinstance(item, list):
            if not item:
                # An empty array carries no information; keep it verbatim.
                nodes.append(RawEntry([]))
                continue
            first = item[0]
            if isinstance(first, (str, int, float)) and not isinstance(first, bool):
                nodes.append(Group(first, _parse_signal_nodes(item[1:])))
            else:
                nodes.append(Group(None, _parse_signal_nodes(item)))
        elif isinstance(item, dict):
            nodes.append(SignalRow(item))
        elif item is None:
            # WaveDrom would fail to render ``null``; show it as a spacer lane
            # instead of dropping the entry.
            nodes.append(SignalRow({}))
        else:
            nodes.append(RawEntry(item))
    return nodes


def rows_of_nodes(nodes: Sequence[Any]) -> list[SignalRow]:
    rows: list[SignalRow] = []
    for node in nodes:
        if isinstance(node, Group):
            rows.extend(rows_of_nodes(node.children))
        elif isinstance(node, SignalRow):
            rows.append(node)
    return rows


def _node_row_count(node: Any) -> int:
    if isinstance(node, SignalRow):
        return 1
    if isinstance(node, Group):
        return sum(_node_row_count(child) for child in node.children)
    return 0


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
        # ``signal_tree`` is the source of truth; ``rows`` is a flat view of it.
        self.signal_tree: list[SignalNode] = []
        self.rows: list[SignalRow] = []
        self._row_nodes: list[SignalRow] = []
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
        self.signal_tree = _parse_signal_nodes(signal)
        self._rebuild_rows()
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
            self.fit_clocks(record=False)
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
                    result["signal"] = [node.to_value() for node in self.signal_tree]
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
            items.insert(at, ("signal", [node.to_value() for node in self.signal_tree]))
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
    # Tree helpers
    # ------------------------------------------------------------------
    def _rebuild_rows(self) -> None:
        self.rows = rows_of_nodes(self.signal_tree)
        self._row_nodes = list(self.rows)

    def _locate_row(self, row_index: int) -> tuple[list[Any], int] | None:
        """Return ``(parent_child_list, position)`` for a flat row index."""
        counter = [0]

        def walk(nodes: list[Any]):
            for position, node in enumerate(nodes):
                if isinstance(node, Group):
                    found = walk(node.children)
                    if found is not None:
                        return found
                elif isinstance(node, SignalRow):
                    if counter[0] == row_index:
                        return (nodes, position)
                    counter[0] += 1
            return None

        return walk(self.signal_tree)

    def _insert_nodes_at(self, index: int, nodes: Sequence[SignalNode]) -> None:
        if not nodes:
            return
        index = max(0, int(index))
        if not self.signal_tree or index >= len(self.rows):
            self.signal_tree.extend(nodes)
            return
        located = self._locate_row(index)
        if located is None:
            self.signal_tree.extend(nodes)
            return
        parent, position = located
        parent[position:position] = list(nodes)

    def _row_chain(self, row_index: int) -> list[tuple[list[Any], int]]:
        """Return the (sibling list, position) chain from the root to a row."""
        chain: list[tuple[list[Any], int]] = []
        counter = [0]

        def walk(nodes: list[Any]) -> bool:
            for position, node in enumerate(nodes):
                chain.append((nodes, position))
                if isinstance(node, Group):
                    if walk(node.children):
                        return True
                elif isinstance(node, SignalRow):
                    if counter[0] == row_index:
                        return True
                    counter[0] += 1
                chain.pop()
            return False

        walk(self.signal_tree)
        return chain

    def _live_lists(self) -> set[int]:
        live: set[int] = set()

        def walk(nodes: list[Any]) -> None:
            live.add(id(nodes))
            for node in nodes:
                if isinstance(node, Group):
                    walk(node.children)

        walk(self.signal_tree)
        return live

    def _insert_nodes_near(self, chain: Sequence[tuple[list[Any], int]], nodes: Sequence[SignalNode]) -> None:
        """Insert ``nodes`` where the chain's row used to be.

        After removing rows, the deepest surviving sibling list in the chain is
        used, so grouping signals that live inside (now empty) groups still
        produces a group at the right nesting level.
        """
        if not nodes:
            return
        live = self._live_lists()
        for sibling_list, position in reversed(chain):
            if id(sibling_list) in live:
                position = max(0, min(position, len(sibling_list)))
                sibling_list[position:position] = list(nodes)
                return
        self.signal_tree.extend(nodes)

    def _cancel_empty_group(self, node: Any) -> bool:
        return isinstance(node, Group) and not node.children and not node.preserve_empty

    def _prune_groups(self, nodes: list[Any] | None = None) -> None:
        nodes = self.signal_tree if nodes is None else nodes
        index = 0
        while index < len(nodes):
            node = nodes[index]
            if isinstance(node, Group):
                self._prune_groups(node.children)
                if self._cancel_empty_group(node):
                    del nodes[index]
                    continue
            index += 1

    def _collect_nodes(self, selected: set[int]) -> list[SignalNode]:
        """Deep-copy the selected rows, whole groups included when fully covered."""

        def walk(nodes: Sequence[Any]) -> list[SignalNode]:
            out: list[SignalNode] = []
            for node in nodes:
                if isinstance(node, Group):
                    rows = rows_of_nodes([node])
                    if rows and all(self._row_index[row] in selected for row in rows):
                        out.append(node.clone())
                    elif any(self._row_index.get(row) in selected for row in rows):
                        out.extend(walk(node.children))
                elif isinstance(node, SignalRow):
                    if self._row_index.get(node) in selected:
                        out.append(node.clone())
            return out

        self._row_index = {row: index for index, row in enumerate(self.rows)}
        return walk(self.signal_tree)

    def _remove_selected(self, selected: set[int]) -> None:
        """Remove rows from the tree in place (groups are pruned when empty)."""

        def walk(nodes: list[Any]) -> None:
            index = 0
            while index < len(nodes):
                node = nodes[index]
                if isinstance(node, Group):
                    walk(node.children)
                    if not node.children and not node.preserve_empty:
                        del nodes[index]
                        continue
                elif isinstance(node, SignalRow):
                    if self._row_index.get(node) in selected:
                        del nodes[index]
                        continue
                index += 1

        self._row_index = {row: index for index, row in enumerate(self.rows)}
        walk(self.signal_tree)

    def _selected_then_rebuild(self, selected: set[int]):
        """Yield deep copies of the selected nodes, then rebuild ``rows``."""
        nodes = self._collect_nodes(selected)
        self._remove_selected(selected)
        self._rebuild_rows()
        return nodes

    # ------------------------------------------------------------------
    # Groups (read only views)
    # ------------------------------------------------------------------
    def group_spans(self) -> list[GroupSpan]:
        spans: list[GroupSpan] = []
        counter = [0]

        def walk(nodes: Sequence[Any], depth: int) -> None:
            for node in nodes:
                if isinstance(node, Group):
                    start = counter[0]
                    walk(node.children, depth + 1)
                    end = counter[0] - 1
                    if end >= start:
                        spans.append(GroupSpan(node, start, end, depth))
                elif isinstance(node, SignalRow):
                    counter[0] += 1

        walk(self.signal_tree, 0)
        spans.sort(key=lambda span: (span.start, -span.depth))
        return spans

    def group_depth(self, row_index: int) -> int:
        for span in self.group_spans():
            if span.start <= row_index <= span.end:
                return span.depth + 1
        return 0

    def max_group_depth(self) -> int:
        spans = self.group_spans()
        return max((span.depth + 1 for span in spans), default=0)

    def span_at_row(self, row_index: int) -> GroupSpan | None:
        candidates = [span for span in self.group_spans() if span.start <= row_index <= span.end]
        if not candidates:
            return None
        return max(candidates, key=lambda span: span.depth)

    def span_by_group(self, group: Group) -> GroupSpan | None:
        for span in self.group_spans():
            if span.group is group:
                return span
        return None

    def rename_group(self, row_index: int, name: Any) -> bool:
        span = self.span_at_row(row_index)
        if span is None:
            return False
        if span.group.name == name:
            return False
        self._record("rename-group")
        span.group.name = copy.deepcopy(name)
        self._dirty = True
        return True

    def group_rows(self, indices: Iterable[int], name: Any) -> list[int]:
        selected = sorted({int(i) for i in indices if 0 <= int(i) < len(self.rows)})
        if not selected:
            return []
        self._record("group")
        first = selected[0]
        chain = self._row_chain(first)
        nodes = self._selected_then_rebuild(set(selected))
        group = Group(name, list(nodes))
        group.preserve_empty = False
        self._insert_nodes_near(chain, [group])
        self._rebuild_rows()
        if self.auto_extend_clocks:
            self.fit_clocks(record=False)
        self._dirty = True
        return list(range(first, min(first + len(selected), len(self.rows))))

    def ungroup_rows(self, indices: Iterable[int]) -> list[int]:
        """Dissolve the outermost fully selected groups (one level)."""
        selected = {int(i) for i in indices if 0 <= int(i) < len(self.rows)}
        if not selected:
            return []
        targets: list[Group] = []

        def find(nodes: list[Any], parent_selected: bool) -> None:
            for node in nodes:
                if not isinstance(node, Group):
                    continue
                rows = rows_of_nodes([node])
                fully = bool(rows) and all(self._row_index[row] in selected for row in rows)
                if fully and not parent_selected:
                    targets.append(node)
                elif not fully:
                    find(node.children, False)

        self._row_index = {row: index for index, row in enumerate(self.rows)}
        find(self.signal_tree, False)
        if not targets:
            return []
        changed: list[int] = []
        for group in targets:
            rows = rows_of_nodes([group])
            changed.extend(self._row_index[row] for row in rows)
        self._record("ungroup")
        targets_set = {id(group) for group in targets}

        def dissolve(nodes: list[Any]) -> None:
            index = 0
            while index < len(nodes):
                node = nodes[index]
                if isinstance(node, Group):
                    if id(node) in targets_set:
                        nodes[index : index + 1] = list(node.children)
                        continue
                    dissolve(node.children)
                index += 1

        dissolve(self.signal_tree)
        self._rebuild_rows()
        self._dirty = True
        first = min(changed)
        return list(range(first, min(first + len(changed), len(self.rows))))

    # ------------------------------------------------------------------
    # Geometry / stats
    # ------------------------------------------------------------------
    @property
    def column_count(self) -> int:
        return max((len(row.wave) for row in self.rows), default=0)

    @property
    def time_units(self) -> float:
        return max((row.time_units for row in self.rows), default=0.0)

    def clock_columns(self) -> int:
        return max((len(row.wave) for row in self.rows if row.is_clock and row.wave), default=0)

    def reference_columns(self) -> int:
        """Length used for new lanes: the clock length when there is one."""
        clock = self.clock_columns()
        if clock:
            return clock
        return max(DEFAULT_COLUMNS, self.column_count)

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
    def clock_target_units(self) -> float:
        """Time length a clock should have: the longest non-clock signal."""
        signal_units = [row.time_units for row in self.rows if row.wave and not row.is_clock]
        if signal_units:
            return max(signal_units)
        return max((row.time_units for row in self.rows if row.is_clock), default=0.0)

    def fit_clocks(self, *, record: bool = True, extend_only: bool = False) -> list[int]:
        """Keep clock lanes exactly as long as the longest signal lane."""
        target = self.clock_target_units()
        if target <= 0:
            return []
        changed: list[int] = []
        if record:
            self._record("fit-clocks")
        for index, row in enumerate(self.rows):
            if not row.is_clock:
                continue
            if extend_only:
                if row.extend_clock(target):
                    changed.append(index)
            elif row.fit_clock(target):
                changed.append(index)
        if changed:
            self._dirty = True
        return changed

    def extend_clocks(self, *, record: bool = True) -> list[int]:
        """Extend clock lanes to the longest signal (requirement #4)."""
        return self.fit_clocks(record=record, extend_only=True)

    def fit_clocks_quiet(self) -> list[int]:
        """Re-fit clocks after an edit without pushing a second history entry."""
        if not self.auto_extend_clocks:
            return []
        return self.fit_clocks(record=False)

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
        columns = columns if columns is not None else self.reference_columns()
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
        self._insert_nodes_at(index, new_rows)
        self._rebuild_rows()
        if self.auto_extend_clocks:
            self.fit_clocks(record=False)
        self._dirty = True

    def insert_blank(self, index: int, *, name: str = "signal", clock: bool | None = None) -> int:
        row = self.make_row(name=name, clock=clock)
        self.insert_rows(index, [row])
        return index

    def add_row(self, *, name: str = "signal") -> int:
        row = self.make_row(name=name)
        self.insert_rows(len(self.rows), [row])
        return len(self.rows) - 1

    def add_spacer_row(self, index: int | None = None) -> int:
        """Insert a bare ``{}`` spacer lane."""
        index = len(self.rows) if index is None else max(0, min(index, len(self.rows)))
        self._record("insert-spacer")
        self._insert_nodes_at(index, [SignalRow({})])
        self._rebuild_rows()
        self._dirty = True
        return index

    def delete_rows(self, indices: Iterable[int]) -> list[int]:
        selected = sorted({i for i in indices if 0 <= i < len(self.rows)})
        if not selected:
            return []
        self._record("delete-row")
        self._selected_then_rebuild(set(selected))
        self._prune_groups()
        self._rebuild_rows()
        if self.auto_extend_clocks:
            self.fit_clocks(record=False)
        self._dirty = True
        return selected

    def duplicate_rows(self, indices: Iterable[int]) -> list[int]:
        selected = sorted({i for i in indices if 0 <= i < len(self.rows)})
        if not selected:
            return []
        self._record("duplicate-row")
        nodes = self._collect_nodes(set(selected))
        insert_at = selected[-1] + 1
        self._insert_nodes_at(insert_at, [node.clone() for node in nodes])
        self._rebuild_rows()
        if self.auto_extend_clocks:
            self.fit_clocks(record=False)
        self._dirty = True
        count = sum(1 for node in nodes for _ in rows_of_nodes([node]))
        return list(range(insert_at, min(insert_at + count, len(self.rows))))

    def copy_rows(self, indices: Iterable[int]) -> list[dict[str, Any]]:
        self._row_index = {row: index for index, row in enumerate(self.rows)}
        selected = {i for i in indices if 0 <= i < len(self.rows)}
        if not selected:
            return []
        return [node.to_value() for node in self._collect_nodes(selected) if isinstance(node, SignalRow)]

    def copy_nodes_payload(self, indices: Iterable[int]) -> str:
        self._row_index = {row: index for index, row in enumerate(self.rows)}
        selected = {i for i in indices if 0 <= i < len(self.rows)}
        nodes = self._collect_nodes(selected) if selected else []
        return json.dumps({"signal": [node.to_value() for node in nodes]}, ensure_ascii=False, indent=2)

    def paste_rows(self, payload: Any, index: int | None = None) -> list[int]:
        nodes = _normalise_clipboard_nodes(payload)
        if not nodes:
            return []
        self._record("paste-row")
        if index is None:
            index = len(self.rows)
        index = max(0, min(index, len(self.rows)))
        self._insert_nodes_at(index, nodes)
        self._rebuild_rows()
        if self.auto_extend_clocks:
            self.fit_clocks(record=False)
        self._dirty = True
        count = len(rows_of_nodes(nodes))
        return list(range(index, min(index + count, len(self.rows))))

    def move_rows(self, indices: Iterable[int], target: int) -> list[int]:
        selected = sorted({i for i in indices if 0 <= i < len(self.rows)})
        if not selected:
            return []
        self._record("move-row")
        nodes = self._collect_nodes(set(selected))
        before = sum(1 for i in selected if i < target)
        self._remove_selected(set(selected))
        self._prune_groups()
        self._rebuild_rows()
        insert_at = max(0, min(target - before, len(self.rows)))
        self._insert_nodes_at(insert_at, nodes)
        self._rebuild_rows()
        if self.auto_extend_clocks:
            self.fit_clocks(record=False)
        self._dirty = True
        count = len(rows_of_nodes(nodes))
        return list(range(insert_at, min(insert_at + count, len(self.rows))))

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
            self.fit_clocks(record=False)
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
                row.set_data_items(items, as_list=True)
                changed = True
        if changed:
            row.ensure_length(len(row.wave))
            if self.auto_extend_clocks:
                self.fit_clocks(record=False)
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
            self.fit_clocks(record=False)
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
            self.fit_clocks(record=False)
        if changed:
            self._dirty = True
        return changed

    def clear_cells(self, cells: Iterable[tuple[int, int]]) -> int:
        return self.apply_wave_chars(cells, ".", tag="clear-cells")

    def delete_cells(self, cells: Iterable[tuple[int, int]]) -> int:
        """Delete waveform characters (cycles) from the selected cells."""
        grouped: dict[int, set[int]] = {}
        for y, x in cells:
            grouped.setdefault(y, set()).add(int(x))
        if not grouped:
            return 0
        self._record("delete-cells")
        changed = 0
        for y, cols in grouped.items():
            row = self.row(y)
            if row is None or not row.wave:
                continue
            for start, end in _runs(sorted(cols)):
                end = min(end, len(row.wave) - 1)
                if start > end:
                    continue
                if row.delete_wave(start, end):
                    changed += end - start + 1
        if self.auto_extend_clocks:
            self.fit_clocks(record=False)
        if changed:
            self._dirty = True
        return changed

    def insert_cells(
        self,
        rows: Iterable[int],
        column: int,
        *,
        count: int = 1,
        chars: str = ".",
    ) -> int:
        """Insert ``count`` waveform cycles before ``column`` in the given lanes."""
        count = max(1, int(count))
        chars = (chars or ".") * count
        targets = sorted({int(r) for r in rows if 0 <= int(r) < len(self.rows)})
        if not targets:
            return 0
        self._record("insert-cells")
        changed = 0
        for y in targets:
            row = self.rows[y]
            if not row.wave:
                continue
            if row.insert_wave(max(0, int(column)), chars):
                changed += 1
        if self.auto_extend_clocks:
            self.fit_clocks(record=False)
        if changed:
            self._dirty = True
        return changed

    def insert_text(self, index: int, column: int, chars: str) -> bool:
        """Insert typed characters at a column, padding short/empty lanes."""
        row = self.row(index)
        if row is None or not chars:
            return False
        self._record("insert-text")
        column = max(0, int(column))
        if len(row.wave) < column:
            row.ensure_length(column)
        if not row.wave:
            row.ensure_length(max(1, column + len(chars)))
        changed = row.insert_wave(column, chars)
        if self.auto_extend_clocks:
            self.fit_clocks(record=False)
        if changed:
            self._dirty = True
        return changed

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
            self.fit_clocks(record=False)
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
            self.fit_clocks(record=False)
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
            self.fit_clocks(record=False)
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
            self.fit_clocks(record=False)
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

    def set_skin(self, skin: str, *, record: bool = True, mark_dirty: bool = True) -> bool:
        if self.config.get("skin") == skin:
            return False
        if record:
            self._record("config")
        self.config["skin"] = skin
        if mark_dirty:
            self._dirty = True
        return True

    def set_section(self, name: str, values: dict[str, Any] | None) -> bool:
        """Replace ``head``/``foot`` (or any top level section) with ``values``."""
        name = str(name)
        cleaned: dict[str, Any] = {}
        for key, value in (values or {}).items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            cleaned[key] = copy.deepcopy(value)
        if not cleaned:
            if name not in self._fields:
                return False
            self._record("section")
            del self._fields[name]
            self._dirty = True
            return True
        if self._fields.get(name) == cleaned:
            return False
        self._record("section")
        self._fields[name] = cleaned
        self._dirty = True
        return True

    def apply_diagram_settings(
        self,
        *,
        skin: str | None = None,
        hscale: int | None = None,
        head: dict[str, Any] | None = None,
        foot: dict[str, Any] | None = None,
    ) -> bool:
        """Apply one batch of diagram settings with a single undo entry."""
        self._record("diagram-settings")
        changed = False
        if skin is not None and self.config.get("skin") != skin:
            self.config["skin"] = skin
            changed = True
        if hscale is not None:
            hscale = max(1, min(100, int(hscale)))
            if self.config.get("hscale") != hscale:
                self.config["hscale"] = hscale
                changed = True
        for key, values in (("head", head), ("foot", foot)):
            if values is None:
                continue
            cleaned = {
                k: copy.deepcopy(v)
                for k, v in values.items()
                if v is not None and not (isinstance(v, str) and not v.strip())
            }
            if cleaned:
                if self._fields.get(key) != cleaned:
                    self._fields[key] = cleaned
                    changed = True
            elif key in self._fields:
                del self._fields[key]
                changed = True
        if changed:
            self._dirty = True
        return changed

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
            self.fit_clocks(record=False)
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
        return self.copy_nodes_payload(indices)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    def ascii_text(self) -> str:
        from .ascii_render import document_to_ascii

        return document_to_ascii(self)

    def summary(self) -> str:
        return f"{len(self.rows)} signals · {self.column_count} cells"

    def signal_json(self) -> list[Any]:
        return [node.to_value() for node in self.signal_tree]


def _runs(values: Sequence[int]) -> list[tuple[int, int]]:
    """Group sorted integers into inclusive runs."""
    runs: list[tuple[int, int]] = []
    start = None
    previous = None
    for value in values:
        if start is None:
            start = previous = int(value)
            continue
        if int(value) == previous + 1:
            previous = int(value)
            continue
        runs.append((start, previous))
        start = previous = int(value)
    if start is not None:
        runs.append((start, previous))
    return runs


def _normalise_clipboard_nodes(payload: Any) -> list[SignalNode]:
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
        elif "wave" in payload or "name" in payload or "node" in payload:
            payload = [payload]
        else:
            return []
    if not isinstance(payload, list):
        return []
    return _parse_signal_nodes(payload)


def _normalise_clipboard_rows(payload: Any) -> list[dict[str, Any]]:
    """Backwards compatible helper returning only flat lanes."""
    return [row.to_dict() for row in rows_of_nodes(_normalise_clipboard_nodes(payload))]


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


def clock_fitted(row: Any, target_time_units: float) -> str:
    """Return ``row.wave`` resized (both directions) to ``target_time_units``."""
    wave = getattr(row, "wave", "") or ""
    if not isinstance(wave, str) or not wave:
        return wave
    period = max(1, int(round(getattr(row, "period", 1) or 1)))
    target_chars = max(1, int(math.ceil(target_time_units / period - 1e-9)))
    if len(wave) < target_chars:
        return clock_extension(row, target_time_units)
    if len(wave) == target_chars:
        return wave
    return _truncate_wave(wave, target_chars)


def _truncate_wave(wave: str, chars: int) -> str:
    out: list[str] = []
    visible = 0
    index = 0
    while index < len(wave) and visible < chars:
        char = wave[index]
        out.append(char)
        if char not in "<>":
            visible += 1
        index += 1
    text = "".join(out)
    # Drop dangling sub-cycle markers left by the cut.
    while text and text[-1] in "<>":
        text = text[:-1]
    while text.count("<") > text.count(">"):
        at = text.rfind("<")
        if at < 0:
            break
        text = text[:at] + text[at + 1 :]
    return text
