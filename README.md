<p align="center"><img src="asset/md/logo.png" width="96" alt="WaveDromGen logo"></p>

# WaveDromGen v2

**A GUI digital timing-diagram editor with WaveDrom-compatible rendering, a live JSON editor and direct waveform manipulation.**

![WaveDromGen v2 main window](asset/md/v2_main.png)

WaveDromGen lets you draw timing diagrams visually, edit the underlying WaveJSON at the same time, and keep both views in sync. The waveform renderer uses WaveDrom's own skin geometry, so exported diagrams look like the diagrams produced by [WaveDrom](https://wavedrom.com) while every cell remains interactive.

> 中文说明：[README_cn.md](README_cn.md)

---

## Highlights

| | Feature |
|---|---|
| ✏️ | **Inline editing** — double-click a signal name or a bus `data` label, type, and press <kbd>Enter</kbd> / <kbd>Tab</kbd> to jump straight to the next name/data field. |
| ↕️ | **Drag to reorder** — drag signals by the left gutter; a drop line shows exactly where the signal will be inserted. |
| ↔️ | **Split views** — Wave above/below the editor, side-by-side, or either pane alone. Valid JSON renders live; waveform edits rewrite the JSON. |
| ⏱️ | **Clock auto-extension** — lanes whose names contain `clk` or `clock` are stretched to the longest signal automatically. |
| ➕ | **Signal editing** — add, insert, delete, duplicate, copy and paste signals, all with configurable shortcuts. |
| 🖱️ | **Range waveform editing** — drag-select any block of cells and type WaveDrom characters (`0 1 x z = u d p P n N l L h H 2..9 | .`) to paint the whole block. |
| ⌨️ | **Configurable shortcuts** — 60 actions, keyboard capture, conflict detection, presets and saving in Preferences. |
| 🎨 | **Polished UI** — light/dark themes, English/中文 UI, zoom, time ruler, selection, context menus, recent files and a compact editor. |
| 🧩 | **WaveJSON compatible** — skins, `period`, `phase`, `data`, `node`, `edge`, `head`/`foot`, unknown fields preserved. |
| 🪶 | **Lightweight text editor** — line numbers, current-line highlight, JSON/JSON5 highlighting, smart indent, find/replace, format and inline error markers. |

![Inline data-label editing](asset/md/v2_inline_edit.png)

---

## Install and run

Requirements: **Python 3.10+**.

```bash
git clone https://github.com/Nymph-K/wavedromgen.git
cd wavedromgen
python -m pip install -r requirements.txt
python main.py
```

Open a diagram directly:

```bash
python main.py examples/demo.json
```

On Windows you can build a single executable with PyInstaller:

```bash
python -m pip install pyinstaller
python package2exe.py
```

The executable is written to `dist/WaveDromGen.exe`.

---

## The interface

- **Menu bar** — File, Edit, Signal, View, Tools, Help.
- **Main toolbar** — file actions, undo/redo, signal operations, view modes, zoom, theme, settings.
- **Tool rail** — Select, Clock, Signal, Bus, Unknown, High-Z, Gap, Text, Clear and Node tools.
- **Wave canvas** — a time ruler, signal gutter with drag handles, snap-to-cell selection and inline label editors.
- **WaveJSON panel** — live editor with a `Live` badge, apply/format/wrap/copy buttons and an error banner.
- **Status bar** — active cell, selection, sync state, signal count and zoom.

The splitter between the waveform and editor remembers its size. Use **View → Split Top / Bottom** (<kbd>Ctrl</kbd>+<kbd>3</kbd>) or **Split Left / Right** (<kbd>Ctrl</kbd>+<kbd>4</kbd>); <kbd>Ctrl</kbd>+<kbd>1</kbd> shows only the waveform and <kbd>Ctrl</kbd>+<kbd>2</kbd> only the editor.

![Dark theme](asset/md/v2_dark.png)

---

## Editing guide

### Names and data labels

Double-click a signal name or a bus label, or press <kbd>F2</kbd> on the active cell.

- <kbd>Enter</kbd> / <kbd>Tab</kbd> — commit and edit the next name/data field.
- <kbd>Shift</kbd>+<kbd>Tab</kbd> — commit and edit the previous field.
- <kbd>Esc</kbd> — cancel.

Empty bus segments show a dashed `data` placeholder: double-click it to create the label.

### Selecting and painting cells

Click a cell, drag to select a rectangle, or use <kbd>Shift</kbd>+arrows / <kbd>Ctrl</kbd>+<kbd>A</kbd> to extend the selection. Typing a WaveDrom character applies it to **every selected cell**:

| Character | Meaning |
|---|---|
| `0`, `1` | Low / high level |
| `.` | Continue the previous state |
| `x` | Unknown / don't care |
| `z` | High impedance |
| `=` | Data bus; consumes the next `data` label |
| `2`–`9` | Data bus with a WaveDrom colour |
| `p`, `P` | Positive-edge clock (with edge marker for `P`) |
| `n`, `N` | Negative-edge clock (with edge marker for `N`) |
| `l`, `L` | Low clock phase (with marker for `L`) |
| `h`, `H` | High clock phase (with marker for `H`) |
| `u`, `d` | Bus up/down transition |
| `\|` | Gap marker |

When a single cell is selected, typing advances the cursor to the next cell (configurable). Use **Edit → Copy Cells** / **Paste Cells** for blocks of characters, and <kbd>Del</kbd> to turn selected cells back into `.` (continue).

### Clocks

Any signal whose name contains `clk` or `clock` is kept aligned with the longest signal. A clock written as `p.......` is simply extended with dots; rectangular `0`/`1` clocks are tiled with their repeating period. Toggle this in **Preferences → Behaviour**, or run **Signal → Extend Clocks to Longest**.

### Signals (lanes)

| Action | Default shortcut |
|---|---|
| Insert above | <kbd>Insert</kbd> |
| Insert below | <kbd>Ctrl</kbd>+<kbd>Insert</kbd> |
| Add at end | <kbd>Ctrl</kbd>+<kbd>Enter</kbd> |
| Duplicate | <kbd>Ctrl</kbd>+<kbd>D</kbd> |
| Copy / cut / paste | <kbd>Ctrl</kbd>+<kbd>C</kbd> / <kbd>X</kbd> / <kbd>V</kbd> |
| Delete | <kbd>Ctrl</kbd>+<kbd>Delete</kbd> |
| Move up / down | <kbd>Alt</kbd>+<kbd>↑</kbd> / <kbd>Alt</kbd>+<kbd>↓</kbd> |
| Clear signal | <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Delete</kbd> |

Click a row in the left gutter to select it, <kbd>Shift</kbd>+click to select a range, and drag to reorder. Row copy/paste uses the system clipboard, so WaveJSON signals can be moved between windows.

### Live JSON

![Shortcut settings](asset/md/v2_shortcuts.png)

The editor accepts strict JSON and relaxed JSON5 (comments, single quotes, unquoted keys and trailing commas). Valid content is applied after a short debounce; invalid content keeps the last valid waveform and shows the error line and column. <kbd>Ctrl</kbd>+<kbd>Enter</kbd> applies immediately, and **Format JSON** (<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>F</kbd>) pretty-prints the document.

Use the **Live** badge/button or **Tools → Toggle Live JSON Sync** to switch between live and manual application. In manual mode, valid text is still applied when you leave the editor.

### More shortcuts

Every action can be rebound in **Preferences → Shortcuts**. The table shows defaults; press a key combination in the shortcut field, up to two combinations per action. Conflicts are highlighted before saving.

A few useful defaults:

- <kbd>Ctrl</kbd>+<kbd>Z</kbd> / <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Z</kbd> — undo / redo (routes to the focused editor or waveform)
- <kbd>Ctrl</kbd>+<kbd>S</kbd> / <kbd>Ctrl</kbd>+<kbd>O</kbd> / <kbd>Ctrl</kbd>+<kbd>N</kbd> — save / open / new
- <kbd>Ctrl</kbd>+<kbd>f</kbd> / <kbd>Ctrl</kbd>+<kbd>h</kbd> — find / replace in the JSON editor
- <kbd>Ctrl</kbd>+<kbd>0</kbd> / <kbd>Ctrl</kbd>+<kbd>=</kbd> / <kbd>Ctrl</kbd>+<kbd>-</kbd> — reset / zoom in / zoom out
- <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>T</kbd> — toggle dark mode
- <kbd>F1</kbd> — quick help and full shortcut reference

### Skins and export

**View → Skin** switches between the official `default`, `lowkey`, `narrow` and `dark` skins. **View → Horizontal Scale** changes WaveDrom's `hscale`. Export PNG/SVG from the File menu; **Copy Diagram as Image** puts a high-resolution render on the clipboard.

### Relations and ASCII

Use the **Node** tool to place a one-character node marker on a waveform cell, then **Tools → Relation Editor** to add edges such as `a~>b setup`. The **ASCII Preview** shows a compact terminal-friendly rendering, and **Copy ASCII** puts it on the clipboard.

---

## WaveJSON compatibility

WaveDromGen v2 preserves the WaveJSON fields it understands and unknown fields it does not. It supports:

- `signal` lanes with `name`, `wave`, `data`, `node`, `period`, `phase` and extra fields;
- `config.hscale`, `config.skin`, `config.marks`;
- `edge` relations, basic `head`/`foot` text and tick/tock labels;
- nested signal **groups are flattened for editing** (a note is shown after opening such a file); a warning is displayed rather than silently losing the lanes.

The JSON editor accepts JSON5 for convenience. Saving always writes canonical UTF-8 JSON.

---

## Project layout

```text
WaveDromGen/
  app.py             Qt main window, actions, menus and file I/O
  waveview.py        interactive canvas, inline editors, selection and drag
  renderer.py        QPainter waveform/edge renderer and PNG export helper
  layout.py          geometry, hit testing, data-label targets and inline-edit targets
  model.py           WaveJSON document model, history, clock rules and JSON5 parsing
  wavedrom_render.py Python port of WaveDrom's brick/marker algorithm
  skins.py           skin loading and exact SVG-symbol drawing
  svgpath.py         minimal SVG path parser
  editor.py          lightweight JSON editor (line numbers, highlighting, find/replace)
  shortcuts.py       action registry, default keys and conflict detection
  settings.py        persisted preferences (~/.config or %APPDATA%)
  theme.py           light/dark QSS, palette and fonts
  icons.py           generated vector icons
  dialogs.py         preferences, shortcuts, properties, relations, ASCII and about
  ascii_render.py    compact ASCII preview
  resources/         skins.json + app icon (MIT WaveDrom skin data)
examples/            ready-to-open WaveJSON demos
tests/               unit and Qt GUI tests
```

The waveform renderer is a direct port of WaveDrom's brick and data-marker algorithm, using the official skin symbols. That is why the diagram geometry matches WaveDrom exactly while remaining fully interactive.

---

## Tests

```bash
python -m unittest discover -s tests -v
```

The suite covers the WaveDrom brick port, clock extension, JSON/JSON5 handling, undo/redo, settings and shortcuts, plus offscreen GUI tests for inline editing, drag/drop ordering, range painting, signal clipboard operations, live JSON, split views, themes, save/reopen and PNG/SVG export.

---

## Version history and credits

See [CHANGELOG.md](CHANGELOG.md).

- Original WaveDromGen by **Henson / blueyesess** and contributors: <https://github.com/blueyesess/wavedromgen>
- WaveDrom geometry and skin symbols by **Aliaksei Chapyzhenka** and contributors, MIT licence: <https://github.com/wavedrom/wavedrom>
- Qt bindings: [PySide6](https://doc.qt.io/qtforpython/) (LGPLv3)
- JSON5 parsing: [json5](https://github.com/dpranke/pyjson5) (MIT)

This v2 code is released under the MIT licence. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

If you find WaveDromGen useful, a star is appreciated. The v1 Tkinter implementation remains available in the repository history.
