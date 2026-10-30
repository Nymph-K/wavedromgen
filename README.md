<p align="center"><img src="asset/md/logo.png" width="96" alt="WaveDromGen logo"></p>

# WaveDromGen v2.2

**A GUI digital timing-diagram editor with WaveDrom-compatible rendering, a live JSON editor and direct waveform manipulation.**

![WaveDromGen v2 main window](asset/md/v2_main.png)

WaveDromGen lets you draw timing diagrams visually, edit the underlying WaveJSON at the same time, and keep both views in sync. The waveform renderer uses WaveDrom's own skin geometry, so exported diagrams look like the diagrams produced by [WaveDrom](https://wavedrom.com) while every cell remains interactive.

> 中文说明：[README_cn.md](README_cn.md)

---

## Highlights

| | Feature |
|---|---|
| ✏️ | **Inline editing** — double-click a signal name or a bus `data` label, type, and press <kbd>Enter</kbd> to walk the signal names or <kbd>Tab</kbd> to walk the data labels. |
| ↕️ | **Drag to reorder** — drag signals by the left gutter; a drop line shows exactly where the signal will be inserted. Handles stay aligned whatever the name length. |
| ↔️ | **Split views** — Wave above/below the editor, side-by-side, or either pane alone. Valid JSON renders live; waveform edits rewrite the JSON. |
| 🗂️ | **Tabs** — open several WaveJSON files at once; each tab keeps its own editor text, selection, zoom and scroll position, and signals or groups can be copied between tabs. |
| ⏱️ | **Adaptive clocks** — lanes whose names contain `clk` or `clock` follow the longest signal automatically, shrinking as well as growing. |
| 🧩 | **Signal groups** — select signals and press <kbd>Ctrl</kbd>+<kbd>G</kbd> to wrap them in a named group; groups can be nested, selected by their bracket, copied, duplicated, moved and ungrouped as a unit. Empty `{}` rows are supported too. |
| ➕ | **Signal editing** — add, insert, delete, duplicate, copy and paste signals or groups, all with configurable shortcuts. New signals match the clock length and <kbd>Ctrl</kbd>+<kbd>Enter</kbd> starts editing the new name. |
| 🖱️ | **Range waveform editing** — drag-select any block of cells (including empty cycles right of the lane end) and type WaveDrom characters (`0 1 x z = u d p P n N l L h H 2..9 \| .`) to paint the whole block. Copy/paste moves the complete rectangular block. |
| ⏹️ | **Cycle delete / insert** — <kbd>Del</kbd> removes the selected cycles, <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>←</kbd>/<kbd>→</kbd> inserts a cycle, and the middle mouse button toggles an insert mode for continuous typing. A palette of common wave characters and cycle buttons sits above the canvas. |
| 🎯 | **Insert caret & multi-lane insert** — insert mode highlights the target cycle with a vertical caret; middle-drag selects several lanes and typing inserts into all of them at once. |
| 🎛️ | **Diagram settings** — a dialog for skin, `hscale`, head/foot text and `tick`/`tock`/`every`, plus quick `period`/`phase` editing. |
| ⌨️ | **Configurable shortcuts** — 72 actions, keyboard capture, conflict detection, presets and saving in Preferences. |
| 🎨 | **Polished UI** — light/dark themes (dark mode switches the waveform to the dark skin), English/中文 UI, zoom, time ruler, selection, context menus, recent files and a compact editor. |
| 🧩 | **WaveJSON compatible** — nested signal groups, `{}` spacer rows, `period`, `phase`, array or string `data`, `node`, `edge` arrows and sharp lines, JSONML `head`/`foot`, unknown fields preserved. |
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

The executable is written to `dist/WaveDromGen.exe`. Prebuilt Windows
executables are attached to the [releases](https://github.com/Nymph-K/wavedromgen/releases).

---

## The interface

- **Document tabs** — one tab per open WaveJSON file; close with <kbd>Ctrl</kbd>+<kbd>W</kbd> and switch with <kbd>Ctrl</kbd>+<kbd>Tab</kbd> / <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Tab</kbd>.
- **Menu bar** — File, Edit, Signal, View, Tools, Help.
- **Main toolbar** — file actions, undo/redo, signal operations, view modes, zoom, theme, settings.
- **Wave palette** — one clickable button per common wave character, plus insert-cycle-left/right, delete-cycle, empty `{}` row and the `INS` insert-mode toggle.
- **Tool rail** — Select, Clock, Signal, Bus, Unknown, High-Z, Gap, Text, Clear and Node tools.
- **Wave canvas** — a time ruler, signal gutter with drag handles and group brackets, snap-to-cell selection, an insert caret and inline label editors.
- **WaveJSON panel** — live editor with a `Live` badge, apply/format/wrap/copy buttons and an error banner.
- **Status bar** — active cell, selection, insert mode, sync state, signal count and zoom.

The splitter between the waveform and editor remembers its size. Use **View → Split Top / Bottom** (<kbd>Ctrl</kbd>+<kbd>3</kbd>) or **Split Left / Right** (<kbd>Ctrl</kbd>+<kbd>4</kbd>); <kbd>Ctrl</kbd>+<kbd>1</kbd> shows only the waveform and <kbd>Ctrl</kbd>+<kbd>2</kbd> only the editor.

Each opened file gets its own tab with its own editor text and viewport, so several diagrams can be open at once:

![Two documents in tabs](asset/md/v2_tabs.png)

![Dark theme](asset/md/v2_dark.png)

---

## Editing guide

### Names and data labels

Double-click a signal name or a bus label, or press <kbd>F2</kbd> on the active cell.

- <kbd>Enter</kbd> — commit and edit the next **signal name**.
- <kbd>Tab</kbd> — commit and edit the next **data label**.
- <kbd>Shift</kbd>+<kbd>Enter</kbd> / <kbd>Shift</kbd>+<kbd>Tab</kbd> — the same in the other direction.
- <kbd>Esc</kbd> — cancel.

Both kinds of fields stay reachable: from a name, <kbd>Tab</kbd> jumps to its data labels, and from a data label <kbd>Enter</kbd> reaches the next name. Empty bus segments show a dashed `data` placeholder: double-click it to create the label.

### Selecting and painting cells

Click a cell, drag to select a rectangle, or use <kbd>Shift</kbd>+arrows / <kbd>Ctrl</kbd>+<kbd>A</kbd> to extend the selection. Empty cycles to the right of a lane can be selected too — keep dragging right and the canvas keeps growing and scrolling, and typing there extends the lane. Typing a WaveDrom character applies it to **every selected cell**:

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
| `<`, `>` | Sub-cycle (sharp) transitions |

When a single cell is selected, typing advances the cursor to the next cycle — including when the typed character is the same as the current cell. This is controlled by **Preferences → Behaviour → “After typing any waveform character, jump to the next cycle”**. Use **Edit → Copy Cells** / **Paste Cells** for rectangular blocks: a copied 3×2 block is pasted as a 3×2 block, and pasting a single line into one cell fills several cycles.

The **wave palette** above the canvas writes any of the common characters (`0 1 x . z = 2 3 4 5 p n u d h l`) to the current selection with one click.

### Deleting and inserting cycles

| Action | Default shortcut |
|---|---|
| Delete selected cycles (lanes shift left) | <kbd>Del</kbd> |
| Clear selected cycles to `.` | <kbd>Shift</kbd>+<kbd>Del</kbd> |
| Insert one cycle before the selection | <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>←</kbd> |
| Insert one cycle after the selection | <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>→</kbd> |
| Insert mode | middle mouse button / `INS` palette button |

Insert mode is a continuous typing mode: the middle click places the caret, every waveform character you type is inserted and the rest of the lane moves right, and <kbd>Esc</kbd> or another middle click leaves the mode. A highlighted column and an I-beam caret show the insertion point. Insert/delete apply to every lane in the selection, so several signals can be edited in lock-step.

Drag with the middle mouse button in the gutter (or across the waveform) to select several lanes; insert mode turns on and typing inserts the character into all selected lanes at once. Multi-row waveform selections are mirrored in the JSON editor: the corresponding `wave` lines are highlighted and selected there as well.

![Insert mode caret and the waveform palette](asset/md/v2_insert.png)

### Clocks

Any signal whose name contains `clk` or `clock` follows the longest signal in both directions: it is extended when another lane grows and shortened when the longest lane shrinks. A clock written as `p.......` is extended with dots; rectangular `0`/`1` clocks are tiled with their repeating period. Toggle this in **Preferences → Behaviour**, or run **Signal → Extend Clocks to Longest**.

### Signals (lanes)

| Action | Default shortcut |
|---|---|
| Insert above | <kbd>Insert</kbd> |
| Insert below | <kbd>Ctrl</kbd>+<kbd>Insert</kbd> |
| Add at end (and edit the name) | <kbd>Ctrl</kbd>+<kbd>Enter</kbd> |
| Insert empty `{}` row | <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Insert</kbd> |
| Duplicate | <kbd>Ctrl</kbd>+<kbd>D</kbd> |
| Copy / cut / paste | <kbd>Ctrl</kbd>+<kbd>C</kbd> / <kbd>X</kbd> / <kbd>V</kbd> |
| Delete | <kbd>Ctrl</kbd>+<kbd>Delete</kbd> |
| Move up / down | <kbd>Alt</kbd>+<kbd>↑</kbd> / <kbd>Alt</kbd>+<kbd>↓</kbd> |
| Clear signal | <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Delete</kbd> |
| Group selection | <kbd>Ctrl</kbd>+<kbd>G</kbd> |
| Ungroup | <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd> |

Click a row in the left gutter to select it, <kbd>Ctrl</kbd>+click to toggle rows, <kbd>Shift</kbd>+click to select a range, and drag to reorder. Row copy/paste uses the system clipboard, so WaveJSON signals — groups included — can be moved between tabs and windows. New lanes use the clock length.

### Signal groups

WaveDrom groups (`["Master", {...}, ...]`) are edited as real groups rather than being flattened. A group is drawn with its rounded bracket and rotated name; the brackets nest for nested groups.

- Click a group bracket to select every lane of the group; double-click to rename it.
- **Ctrl+G** wraps the selected lanes in a new named group. Selecting a whole group plus plain lanes and grouping them produces a larger nested group; grouping lanes that live inside different groups moves them into the new one.
- **Ctrl+Shift+G** dissolves the selected group and keeps its children (nested groups stay intact).
- Copy, cut, paste, duplicate, move and delete act on whole groups when the selection covers them.

![Selecting a group; the editor follows the selection](asset/md/v2_groups.png)

### Diagram settings

**Tools → Diagram Settings** (<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>G</kbd>) edits the common `config`/`head`/`foot` options: skin, `hscale`, head and foot text, tick/tock labels and the `every` interval. The signal properties dialog (**Ctrl+Shift+P**) and the right-click **Period / Phase** menu edit the per-lane `period` and `phase`.

### Live JSON

![Shortcut settings](asset/md/v2_shortcuts.png)

The editor accepts strict JSON and relaxed JSON5 (comments, single quotes, unquoted keys and trailing commas). Valid content is applied after a short debounce; invalid content keeps the last valid waveform and shows the error line and column. <kbd>Ctrl</kbd>+<kbd>Enter</kbd> applies immediately, and **Format JSON** (<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>F</kbd>) pretty-prints the document. Selecting waveform cells scrolls the editor to the lane's `wave` line and highlights the selected cycle characters.

Use the **Live** badge/button or **Tools → Toggle Live JSON Sync** to switch between live and manual application. In manual mode, valid text is still applied when you leave the editor.

### More shortcuts

Every action can be rebound in **Preferences → Shortcuts**. The table shows defaults; press a key combination in the shortcut field, up to two combinations per action. Conflicts are highlighted before saving.

A few useful defaults:

- <kbd>Ctrl</kbd>+<kbd>Z</kbd> / <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Z</kbd> — undo / redo (routes to the focused editor or waveform)
- <kbd>Ctrl</kbd>+<kbd>S</kbd> / <kbd>Ctrl</kbd>+<kbd>O</kbd> / <kbd>Ctrl</kbd>+<kbd>N</kbd> — save / open / new
- <kbd>Ctrl</kbd>+<kbd>W</kbd> — close the current tab
- <kbd>Ctrl</kbd>+<kbd>f</kbd> / <kbd>Ctrl</kbd>+<kbd>h</kbd> — find / replace in the JSON editor
- <kbd>Ctrl</kbd>+<kbd>0</kbd> / <kbd>Ctrl</kbd>+<kbd>=</kbd> / <kbd>Ctrl</kbd>+<kbd>-</kbd> — reset / zoom in / zoom out
- <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>T</kbd> — toggle dark mode (the waveform switches to the dark skin)
- <kbd>F1</kbd> — quick help and full shortcut reference

### Skins and export

**View → Skin** switches between the official `default`, `lowkey`, `narrow` and `dark` skins. When the dark UI theme is active the waveform automatically uses the `dark` skin; this can be turned off in **Preferences → Behaviour**. **View → Horizontal Scale** changes WaveDrom's `hscale`. Export PNG/SVG from the File menu; the dialog defaults to the current file name and remembers the last export folder. **Copy Diagram as Image** puts a high-resolution render on the clipboard.

### Relations and ASCII

Use the **Node** tool to place a one-character node marker on a waveform cell, then **Tools → Relation Editor** to add edges such as `a~>b setup`. Curved splines, orthogonal sharp lines and `+` tees are supported and are preserved when the JSON is reformatted. The **ASCII Preview** shows a compact terminal-friendly rendering, and **Copy ASCII** puts it on the clipboard.

---

## WaveJSON compatibility

WaveDromGen v2.2 preserves the WaveJSON fields it understands and unknown fields it does not. It supports:

- `signal` lanes with `name`, `wave`, `data` (string or array), `node`, `period`, `phase` and extra fields;
- **named signal groups**, including nested groups, kept as arrays instead of being flattened;
- empty `{}` spacer lanes, and lanes that only carry `node` markers;
- `config.hscale`, `config.skin`, `config.marks` and other `config` keys;
- `edge` relations (arrows and sharp lines), `head`/`foot` text, tick/tock labels and JSONML rich text;
- unknown top-level and per-lane fields.

JSON synchronisation and **Format JSON** round-trip those constructs, so opening a WaveDrom file and saving it again does not lose groups, arrows, empty rows or metadata. The JSON editor accepts JSON5 for convenience; saving always writes canonical UTF-8 JSON.


---

## Project layout

```text
WaveDromGen/
  app.py             Qt main window, document tabs, actions, menus and file I/O
  waveview.py        interactive canvas, inline editors, selection, insert mode and drag
  renderer.py        QPainter waveform/group/edge renderer and PNG export helper
  layout.py          geometry, group brackets, hit testing, data-label targets
  model.py           WaveJSON document model: groups, history, clock fitting, JSON5
  wavedrom_render.py Python port of WaveDrom's brick/marker algorithm
  skins.py           skin loading and exact SVG-symbol drawing
  svgpath.py         minimal SVG path parser
  editor.py          lightweight JSON editor (line numbers, highlighting, find/replace)
  shortcuts.py       action registry, default keys and conflict detection
  settings.py        persisted preferences (~/.config or %APPDATA%)
  theme.py           light/dark QSS, palette and fonts
  icons.py           generated vector icons
  dialogs.py         preferences, shortcuts, properties, diagram settings, relations, ASCII and about
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

The suite covers the WaveDrom brick port, clock extension and shrinking, groups and nested groups, empty rows, JSON/JSON5 handling and round-trips, lane-scoped cell edits, rectangular block paste, undo/redo, settings and shortcuts, plus offscreen GUI tests for inline editing and Enter/Tab navigation, drag/drop ordering, range painting (including empty cycles right of the lane end), the wave palette, middle-drag multi-lane insert, the insert caret, signal and group clipboard operations, multi-row editor selection, tabs and cross-tab paste, dark-skin switching, live JSON, split views, save/reopen and PNG/SVG export.

---

## Version history and credits

See [CHANGELOG.md](CHANGELOG.md).

- Original WaveDromGen by **Henson / blueyesess** and contributors: <https://github.com/blueyesess/wavedromgen>
- WaveDrom geometry and skin symbols by **Aliaksei Chapyzhenka** and contributors, MIT licence: <https://github.com/wavedrom/wavedrom>
- Qt bindings: [PySide6](https://doc.qt.io/qtforpython/) (LGPLv3)
- JSON5 parsing: [json5](https://github.com/dpranke/pyjson5) (MIT)

This v2 code is released under the MIT licence. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

If you find WaveDromGen useful, a star is appreciated. The v1 Tkinter implementation remains available in the repository history.
