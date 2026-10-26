# coding=utf-8
"""Readable ASCII timing-diagram preview.

One WaveDrom ``brick`` (half a cell) is rendered as two characters.  The
result is deliberately compact and is intended for commit messages, issues or
chat, not as a replacement for the graphical editor.
"""
from __future__ import annotations

from .wavedrom_render import lane_layout

HIGH = 0
LOW = 1
BUS = 2
X = 3
Z = 4
DASH = 5
GAP = 6


def _brick_state(brick: str) -> int:
    if not brick:
        return LOW
    if brick.startswith("vvv") or brick.startswith("vm"):
        return BUS
    if brick.startswith("xxx") or brick.startswith("xm"):
        return X
    if brick.startswith("zzz") or brick.startswith("zm"):
        return Z
    if brick.startswith(("ddd", "uuu", "dm", "um")):
        return DASH
    if brick.startswith("gap"):
        return GAP
    first = brick[0]
    if first in ("p", "P", "1") or brick.startswith("111"):
        return HIGH
    if first in ("n", "N", "0") or brick.startswith("000"):
        return LOW
    return LOW


def _segments(row) -> tuple[str, str, str, str]:
    """Return top, middle, bottom, and the number of rendered bricks."""
    layout = lane_layout(row, 1)
    bricks = list(layout.bricks)
    if not bricks:
        return "", "", "", 0
    top: list[str] = []
    bottom: list[str] = []
    previous = LOW
    for brick in bricks:
        state = _brick_state(brick)
        if state == HIGH and previous == LOW:
            top.append("┌─")
            bottom.append("┘ ")
        elif state == LOW and previous == HIGH:
            top.append("┐ ")
            bottom.append("└─")
        elif state == HIGH:
            top.append("──")
            bottom.append("  ")
        elif state == LOW:
            top.append("  ")
            bottom.append("──")
        elif state == BUS:
            top.append("──")
            bottom.append("──")
        elif state == X:
            top.append("╳╳")
            bottom.append("╳╳")
        elif state == Z:
            top.append("┄┄")
            bottom.append("┄┄")
        elif state == DASH:
            top.append("╌╌")
            bottom.append("╌╌")
        elif state == GAP:
            top.append("│ ")
            bottom.append("│ ")
        if state not in (BUS, X, Z, DASH, GAP):
            previous = state
    middle = [" "] * (len(bricks) * 2)
    # WaveDrom data markers are in brick units and are the authoritative
    # positions of bus labels, even for adjacent bus segments.
    for index, marker in enumerate(layout.markers):
        if index >= len(layout.data):
            break
        label = layout.data[index]
        if not label:
            continue
        start = max(0, int(round(marker * 2)) - len(label) // 2)
        for offset, char in enumerate(label):
            pos = start + offset
            if 0 <= pos < len(middle):
                middle[pos] = char
    return "".join(top), "".join(middle), "".join(bottom), len(bricks)


def document_to_ascii(doc) -> str:
    if not doc.rows:
        return "(empty diagram)"
    name_width = max(3, max(len(row.name or "") for row in doc.rows))
    blocks: list[list[str]] = []
    for row in doc.rows:
        top, middle, bottom, _ = _segments(row)
        if not top:
            continue
        prefix_top = "  " + " " * name_width + "  "
        prefix_mid = "  " + (row.name or "").ljust(name_width) + "  "
        prefix_bot = "  " + (row.name or "").ljust(name_width) + "  "
        if middle.strip():
            blocks.append([prefix_top + top, prefix_mid + middle, prefix_top + bottom])
        else:
            blocks.append([prefix_top + top, prefix_bot + bottom])
    width = max(len(line) for block in blocks for line in block)
    lines: list[str] = []
    for index, block in enumerate(blocks):
        if index:
            lines.append("")
        lines.extend(line.ljust(width).rstrip() for line in block)
    return "\n".join(lines)
