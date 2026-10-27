# coding=utf-8
"""WaveDrom-compatible waveform geometry.

This module is a faithful Python port of the part of WaveDrom that turns a
``wave`` string into a sequence of 20x20 px SVG "bricks" and locates the bus
data labels.  Keeping the algorithm identical means the Qt front-end produces
the same diagram as https://wavedrom.com while still allowing us to draw with
a QPainter and hit-test every cell for interactive editing.

Original JavaScript implementation: https://github.com/wavedrom/wavedrom
Copyright (c) 2011-2026 Aliaksei Chapyzhenka, MIT licence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

BRICK_SIZE = 20.0
ROW_HEIGHT = 30.0
WAVE_HEIGHT = 20.0
WAVE_TOP = 5.0
LABEL_X = 6.0
NAME_END = -10.0

BUS_CHARS = frozenset("=23456789")
CLOCK_CHARS = frozenset("pPnNlLhH")
LEVEL_CHARS = frozenset("01")
EXTEND_CHARS = frozenset(".|")
VALID_WAVE_CHARS = frozenset("01.xz=ud|23456789pnPNlhLH<>")

_FIRST_BRICK = {
    "p": ("pclk", "111", "nclk", "000"),
    "n": ("nclk", "000", "pclk", "111"),
    "P": ("Pclk", "111", "nclk", "000"),
    "N": ("Nclk", "000", "pclk", "111"),
    "l": "000",
    "L": "000",
    "0": "000",
    "h": "111",
    "H": "111",
    "1": "111",
    "=": "vvv-2",
    "2": "vvv-2",
    "3": "vvv-3",
    "4": "vvv-4",
    "5": "vvv-5",
    "6": "vvv-6",
    "7": "vvv-7",
    "8": "vvv-8",
    "9": "vvv-9",
    "d": "ddd",
    "u": "uuu",
    "z": "zzz",
}

_BRICK_X1 = {
    "p": "pclk",
    "n": "nclk",
    "P": "Pclk",
    "N": "Nclk",
    "h": "pclk",
    "l": "nclk",
    "H": "Pclk",
    "L": "Nclk",
}
_BRICK_X2 = {
    "0": "0",
    "1": "1",
    "x": "x",
    "d": "d",
    "u": "u",
    "z": "z",
    "=": "v",
    "2": "v",
    "3": "v",
    "4": "v",
    "5": "v",
    "6": "v",
    "7": "v",
    "8": "v",
    "9": "v",
}
_BRICK_X3 = {
    "0": "",
    "1": "",
    "x": "",
    "d": "",
    "u": "",
    "z": "",
    "=": "-2",
    "2": "-2",
    "3": "-3",
    "4": "-4",
    "5": "-5",
    "6": "-6",
    "7": "-7",
    "8": "-8",
    "9": "-9",
}
_BRICK_Y1 = {
    "p": "0",
    "n": "1",
    "P": "0",
    "N": "1",
    "h": "1",
    "l": "0",
    "H": "1",
    "L": "0",
    "0": "0",
    "1": "1",
    "x": "x",
    "d": "d",
    "u": "u",
    "z": "z",
    "=": "v",
    "2": "v",
    "3": "v",
    "4": "v",
    "5": "v",
    "6": "v",
    "7": "v",
    "8": "v",
    "9": "v",
}
_BRICK_Y2 = {k: v for k, v in _BRICK_X3.items()}
_BRICK_X4 = {
    "p": "111",
    "n": "000",
    "P": "111",
    "N": "000",
    "h": "111",
    "l": "000",
    "H": "111",
    "L": "000",
    "0": "000",
    "1": "111",
    "x": "xxx",
    "d": "ddd",
    "u": "uuu",
    "z": "zzz",
    "=": "vvv-2",
    "2": "vvv-2",
    "3": "vvv-3",
    "4": "vvv-4",
    "5": "vvv-5",
    "6": "vvv-6",
    "7": "vvv-7",
    "8": "vvv-8",
    "9": "vvv-9",
}
_BRICK_X5 = {"p": "nclk", "n": "pclk", "P": "nclk", "N": "pclk"}
_BRICK_X6 = {"p": "000", "n": "111", "P": "000", "N": "111"}
_BRICK_EXCLUDE = {
    "hp": "111",
    "Hp": "111",
    "ln": "000",
    "Ln": "000",
    "nh": "111",
    "Nh": "111",
    "pl": "000",
    "Pl": "000",
}


@dataclass(frozen=True)
class BrickLayout:
    """Everything needed to draw one wave lane."""

    bricks: tuple[str, ...]
    markers: tuple[float, ...]
    unseen_markers: int
    x_offset: float
    hscale: int
    period: float
    phase: float
    data: tuple[str, ...]

    @property
    def width(self) -> float:
        return len(self.bricks) * BRICK_SIZE

    @property
    def time_units(self) -> float:
        if not self.bricks:
            return 0.0
        return len(self.bricks) / (2.0 * self.hscale)


def _gen_brick(texts, extra: int, times: int) -> list[str]:
    if not isinstance(texts, (list, tuple)):
        texts = [texts]
    out: list[str] = []
    if len(texts) == 4:
        for _ in range(times):
            out.append(texts[0])
            out.extend([texts[1]] * extra)
            out.append(texts[2])
            out.extend([texts[3]] * extra)
        return out
    if len(texts) == 1:
        texts = [texts[0], texts[0]]
    out.append(texts[0])
    out.extend([texts[1]] * (times * (2 * (extra + 1)) - 1))
    return out


def _gen_wave_brick(text: str, extra: int, times: int) -> list[str]:
    if len(text) < 2:
        return _gen_brick("xxx", extra, times)
    prev, cur = text[0], text[1]
    current_clock = _BRICK_X1.get(cur)
    if current_clock is None:
        mapped = _BRICK_X2.get(cur)
        if mapped is None:
            return _gen_brick("xxx", extra, times)
        previous = _BRICK_Y1.get(prev)
        if previous is None:
            return _gen_brick("xxx", extra, times)
        return _gen_brick(
            [previous + "m" + mapped + _BRICK_Y2.get(prev, "") + _BRICK_X3.get(cur, ""),
             _BRICK_X4.get(cur, "xxx")],
            extra,
            times,
        )
    if text in _BRICK_EXCLUDE:
        current_clock = _BRICK_EXCLUDE[text]
    next_clock = _BRICK_X5.get(cur)
    if next_clock is None:
        return _gen_brick([current_clock, _BRICK_X4.get(cur, "xxx")], extra, times)
    return _gen_brick(
        [current_clock, _BRICK_X4.get(cur, "xxx"), next_clock, _BRICK_X6.get(cur, "000")],
        extra,
        times,
    )


def _gen_first_wave_brick(char: str, extra: int, times: int) -> list[str]:
    value = _FIRST_BRICK.get(char, "xxx")
    return _gen_brick(value, extra, times)


def parse_wave_lane(
    wave: str,
    *,
    hscale: int = 1,
    period: float = 1,
    phase: float = 0.0,
) -> tuple[list[str], int]:
    """Port of WaveDrom's ``parseWaveLane``.

    Returns ``(bricks, unseen_markers)``.  ``phase`` is expressed in whole
    time slots (a value of 0.5 shifts by one half-slot == one brick).
    """
    hscale = max(1, int(hscale))
    period = max(1, int(round(period or 1)))
    phase_bricks = max(0, math.ceil(phase * 2 - 1e-9))
    extra = period * hscale - 1

    wave = wave or "."
    stack = list(wave)
    next_char = stack.pop(0)
    repeats = 1
    while stack and stack[0] in EXTEND_CHARS:
        stack.pop(0)
        repeats += 1

    result = _gen_first_wave_brick(next_char, extra, repeats)
    while stack:
        top = next_char
        next_char = stack.pop(0)
        sub_cycle = False
        if next_char == "<":
            sub_cycle = True
            if not stack:
                break
            next_char = stack.pop(0)
        if next_char == ">":
            sub_cycle = False
            if not stack:
                break
            next_char = stack.pop(0)
        repeats = 1
        while stack and stack[0] in EXTEND_CHARS:
            stack.pop(0)
            repeats += 1
        if sub_cycle:
            result.extend(_gen_wave_brick(top + next_char, 0, repeats - period))
        else:
            result.extend(_gen_wave_brick(top + next_char, extra, repeats))

    unseen: list[str] = []
    for _ in range(phase_bricks):
        if result:
            unseen.append(result.pop(0))
    unseen_markers = _unseen_marker_count(unseen, result)
    return result, unseen_markers


def _unseen_marker_count(unseen: list[str], remaining: list[str]) -> int:
    if not unseen:
        return 0
    count = len(find_lane_markers(unseen))
    if remaining:
        if find_lane_markers([unseen[-1]]) and find_lane_markers([remaining[0]]):
            count -= 1
    return max(0, count)


def is_bus_brick(brick: str) -> bool:
    return brick.startswith("vvv-")


def find_lane_markers(bricks: Sequence[str]) -> list[float]:
    """Port of WaveDrom's ``findLaneMarkers`` (positions in bricks)."""
    result: list[float] = []
    group_count = 0
    lane_count = 0
    for brick in bricks:
        if is_bus_brick(brick):
            lane_count += 1
        else:
            if lane_count:
                result.append(group_count - (lane_count + 1) / 2.0)
                lane_count = 0
        group_count += 1
    if lane_count:
        result.append(group_count - (lane_count + 1) / 2.0)
    return result


def data_items(value) -> list[str]:
    """Normalise a WaveDrom ``data`` value to a list of strings."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    if isinstance(value, str):
        text = value.strip()
        return text.split() if text else []
    return [str(value)]


def _phase_offset(phase: float) -> float:
    """Horizontal offset (in 20px brick units) used by WaveDrom for phase."""
    if phase > 0:
        return math.ceil(2 * phase) - 2 * phase
    return -2 * phase


def lane_layout(row, hscale: int = 1) -> BrickLayout:
    """Build the brick layout for a SignalRow-like object.

    Lanes without a ``wave`` string (``{}`` spacer lanes, or lanes that only
    carry ``node`` markers) render no bricks at all, exactly like WaveDrom.
    """
    wave = getattr(row, "wave", "") or ""
    if not isinstance(wave, str):
        wave = ""
    period = max(1, int(round(getattr(row, "period", 1) or 1)))
    phase = float(getattr(row, "phase", 0) or 0)
    if wave:
        bricks, unseen = parse_wave_lane(wave, hscale=hscale, period=period, phase=phase)
    else:
        bricks, unseen = [], 0
    markers = find_lane_markers(bricks)
    if hasattr(row, "data_items"):
        try:
            items = [str(item) for item in row.data_items()]
        except Exception:
            items = []
    else:
        items = data_items(getattr(row, "data", None))
    return BrickLayout(
        bricks=tuple(bricks),
        markers=tuple(markers),
        unseen_markers=unseen,
        x_offset=_phase_offset(phase),
        hscale=max(1, int(hscale)),
        period=period,
        phase=phase,
        data=tuple(items[unseen:]),
    )


def row_time_units(row, hscale: int = 1) -> float:
    wave = getattr(row, "wave", "") or ""
    if not isinstance(wave, str) or not wave:
        return 0.0
    period = max(1, int(round(getattr(row, "period", 1) or 1)))
    # Ignore WaveDrom sub-cycle markers when estimating the visible length.
    clean = wave.replace("<", "").replace(">", "")
    return len(clean) * period


def char_to_time_index(row, char_index: int) -> float:
    period = max(1, int(round(getattr(row, "period", 1) or 1)))
    return char_index * period


def clock_like(name: str) -> bool:
    low = (name or "").lower()
    return "clk" in low or "clock" in low


def expand_raw_waves(value: str) -> str:
    """Expand '.' continuations to explicit characters (for ASCII/tests)."""
    if not value:
        return ""
    out: list[str] = []
    last = "."
    for ch in value:
        if ch == ".":
            out.append(last)
        elif ch == "|":
            out.append(last)
        else:
            out.append(ch)
            last = ch
    return "".join(out)


def clock_extension(row, target_time_units: float) -> str:
    """Return the extended raw wave for a clock row.

    WaveDrom clocks (``p``/``n``/``P``/``N``/``l``/``L``/``h``/``H``) continue
    through ``.``, so appending dots already extends them.  Rectangular clocks
    written as ``0``/``1`` runs need their repeating pattern tiled instead.
    """
    wave = getattr(row, "wave", "") or ""
    if not isinstance(wave, str):
        return wave
    period = max(1, int(round(getattr(row, "period", 1) or 1)))
    target_chars = max(1, math.ceil(target_time_units / period - 1e-9))
    if len(wave) >= target_chars:
        return wave

    if not wave or set(wave) <= {"."}:
        base = "p"
        return base + "." * (target_chars - 1)

    if any(ch in CLOCK_CHARS for ch in wave):
        return wave + "." * (target_chars - len(wave))

    if any(ch in LEVEL_CHARS for ch in wave) and set(wave) <= set("01."):
        pattern = _find_repeat(wave)
        if pattern:
            out = wave
            i = len(wave)
            while len(out) < target_chars:
                out += pattern[i % len(pattern)]
                i += 1
            return out
        return wave + "." * (target_chars - len(wave))

    return wave + "." * (target_chars - len(wave))


def _find_repeat(wave: str) -> str | None:
    """Find a short repeating 0/1 pattern that covers ``wave``.

    Only exact raw repeats are considered (``0101`` -> ``01``).  Trailing
    incomplete units are allowed as long as they match the pattern prefix.
    """
    n = len(wave)
    for size in range(2, n // 2 + 1):
        pattern = wave[:size]
        if "0" not in pattern or "1" not in pattern:
            continue
        if all(wave[i] == pattern[i % size] for i in range(n)):
            return pattern
    # A single period, e.g. "01" -> "01".
    if n >= 2 and set(wave) == {"0", "1"}:
        return wave
    return None


def build_ascii_rows(rows, hscale: int = 1) -> list[tuple[str, str, str, str]]:
    """Very small ASCII preview used by the Tools dialog.

    Returns tuples of ``(name, top, middle, bottom)`` using box drawing chars.
    This intentionally favours readability over pixel-perfect proportions.
    """
    rendered: list[tuple[str, str, str, str]] = []
    for row in rows:
        name = getattr(row, "name", "") or ""
        layout = lane_layout(row, hscale)
        top = ""
        mid = ""
        bot = ""
        for marker_index, brick in enumerate(layout.bricks):
            if is_bus_brick(brick):
                top += "─" * 4
                mid += " BUS"
                bot += "─" * 4
            elif brick in ("111", "pclk", "Pclk"):
                top += "─── "
                mid += "    "
                bot += "─── "
            elif brick in ("000", "nclk", "Nclk"):
                top += "    "
                mid += "    "
                bot += "────"
            elif brick.startswith("x"):
                top += "╳╳╳╳"
                mid += "╳╳╳╳"
                bot += "╳╳╳╳"
            elif brick.startswith("z"):
                top += "┄┄┄┄"
                mid += "┄┄┄┄"
                bot += "┄┄┄┄"
            else:
                top += "────"
                mid += "    "
                bot += "────"
        rendered.append((name, top, mid, bot))
    return rendered


def sanitize_wave_char(char: str) -> str | None:
    if not char:
        return None
    if char in VALID_WAVE_CHARS:
        return char
    upper = char.upper()
    if upper in ("X", "Z", "U", "D"):
        return upper.lower()
    if upper in ("P", "N", "L", "H"):
        return upper
    return None


def iter_selected_cells(
    row_count: int,
    selection,
    row_lengths: Iterable[int],
) -> Iterable[tuple[int, int]]:
    """Yield ``(row, col)`` for a rectangular selection.

    ``selection`` is ``(row0, col0, row1, col1)`` inclusive.  Columns beyond a
    row's current wave length are not returned; callers can extend the row
    first if they want to paint into empty columns.
    """
    row0, col0, row1, col1 = selection
    if row0 > row1:
        row0, row1 = row1, row0
    if col0 > col1:
        col0, col1 = col1, col0
    for y, length in enumerate(row_lengths):
        if y < row0 or y > row1:
            continue
        for x in range(col0, col1 + 1):
            if x < length:
                yield y, x
