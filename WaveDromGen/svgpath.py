# coding=utf-8
"""Minimal SVG path parser used for the WaveDrom skin symbols.

Only the commands needed by the official skin files are implemented, plus a
few common extras.  Coordinates are returned as absolute values in the
symbol's 20x20 coordinate system.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(
    r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?"
)


@dataclass(frozen=True)
class PathOp:
    kind: str
    values: tuple[float, ...] = ()


def parse_path(data: str) -> list[PathOp]:
    tokens = _TOKEN_RE.findall(data or "")
    result: list[PathOp] = []
    i = 0
    command: str | None = None
    cx = cy = 0.0
    sx = sy = 0.0
    last_cubic: tuple[float, float] | None = None
    last_quad: tuple[float, float] | None = None
    while i < len(tokens):
        token = tokens[i]
        if token.isalpha():
            command = token
            i += 1
            if command in "Zz":
                result.append(PathOp("Z"))
                cx, cy = sx, sy
                last_cubic = last_quad = None
                continue
        if command is None:
            raise ValueError(f"SVG path does not start with a command: {data!r}")

        def number(idx: int) -> float:
            nonlocal i
            value = float(tokens[i + idx])
            return value

        def advance(n: int) -> None:
            nonlocal i
            i += n

        try:
            if command in "Mm":
                x = number(0)
                y = number(1)
                advance(2)
                if command == "m":
                    x += cx
                    y += cy
                cx, cy = x, y
                sx, sy = x, y
                result.append(PathOp("M", (x, y)))
                command = "l" if command == "m" else "L"
                last_cubic = last_quad = None
            elif command in "Ll":
                x = number(0)
                y = number(1)
                advance(2)
                if command == "l":
                    x += cx
                    y += cy
                cx, cy = x, y
                result.append(PathOp("L", (x, y)))
                last_cubic = last_quad = None
            elif command in "Hh":
                x = number(0)
                advance(1)
                if command == "h":
                    x += cx
                cx = x
                result.append(PathOp("L", (x, cy)))
                last_cubic = last_quad = None
            elif command in "Vv":
                y = number(0)
                advance(1)
                if command == "v":
                    y += cy
                cy = y
                result.append(PathOp("L", (cx, y)))
                last_cubic = last_quad = None
            elif command in "Cc":
                values = [number(k) for k in range(6)]
                advance(6)
                if command == "c":
                    values = [
                        values[0] + cx, values[1] + cy,
                        values[2] + cx, values[3] + cy,
                        values[4] + cx, values[5] + cy,
                    ]
                x1, y1, x2, y2, x, y = values
                result.append(PathOp("C", (x1, y1, x2, y2, x, y)))
                last_cubic = (x2, y2)
                last_quad = None
                cx, cy = x, y
            elif command in "Ss":
                values = [number(k) for k in range(4)]
                advance(4)
                if command == "s":
                    values = [values[0] + cx, values[1] + cy, values[2] + cx, values[3] + cy]
                x2, y2, x, y = values
                if last_cubic is None:
                    x1, y1 = cx, cy
                else:
                    x1, y1 = 2 * cx - last_cubic[0], 2 * cy - last_cubic[1]
                result.append(PathOp("C", (x1, y1, x2, y2, x, y)))
                last_cubic = (x2, y2)
                last_quad = None
                cx, cy = x, y
            elif command in "Qq":
                values = [number(k) for k in range(4)]
                advance(4)
                if command == "q":
                    values = [values[0] + cx, values[1] + cy, values[2] + cx, values[3] + cy]
                x1, y1, x, y = values
                result.append(PathOp("Q", (x1, y1, x, y)))
                last_quad = (x1, y1)
                last_cubic = None
                cx, cy = x, y
            elif command in "Tt":
                x = number(0)
                y = number(1)
                advance(2)
                if command == "t":
                    x += cx
                    y += cy
                if last_quad is None:
                    x1, y1 = cx, cy
                else:
                    x1, y1 = 2 * cx - last_quad[0], 2 * cy - last_quad[1]
                result.append(PathOp("Q", (x1, y1, x, y)))
                last_quad = (x1, y1)
                last_cubic = None
                cx, cy = x, y
            elif command in "Aa":
                values = [number(k) for k in range(7)]
                advance(7)
                rx, ry, rotation, large, sweep, x, y = values
                if command == "a":
                    x += cx
                    y += cy
                result.append(PathOp("A", (rx, ry, rotation, large, sweep, x, y)))
                last_cubic = last_quad = None
                cx, cy = x, y
            else:
                raise ValueError(f"unsupported SVG command {command!r}")
        except (IndexError, ValueError) as exc:
            raise ValueError(f"invalid SVG path {data!r} at token {i}") from exc
    return result


def path_bounds(data: str) -> tuple[float, float, float, float]:
    """Approximate bounds (control points included) for a path."""
    ops = parse_path(data)
    xs: list[float] = []
    ys: list[float] = []
    for op in ops:
        vals = op.values
        if op.kind in ("M", "L"):
            xs.append(vals[0])
            ys.append(vals[1])
        elif op.kind in ("C", "Q"):
            xs.extend(vals[0::2])
            ys.extend(vals[1::2])
        elif op.kind == "A":
            xs.extend((vals[5],))
            ys.extend((vals[6],))
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))
