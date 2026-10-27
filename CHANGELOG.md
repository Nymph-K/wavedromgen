# Changelog

All notable changes to WaveDromGen are documented here.

## [2.1.0] — 2026-10-28

This release focuses on WaveDrom compatibility, signal groups, cycle-level
editing and working on several diagrams at once.

### Added

- Named signal groups, including nested groups: click a group bracket to select
  the whole group, `Ctrl+G` groups the selection, `Ctrl+Shift+G` ungroups,
  double-click renames. Groups can be copied, cut, pasted, duplicated, moved and
  deleted as a unit, and grouping a group with plain signals builds a larger
  nested group.
- Empty `{}` spacer lanes are preserved on load/save and can be inserted from
  **Signal → Insert Empty Row {}**.
- `data` labels edited in the GUI are written as WaveJSON arrays
  (`"data": ["head", "body", "tail"]`).
- **Diagram Settings** dialog for the common `config`/`head`/`foot` options:
  skin, `hscale`, head/foot text, `tick`, `tock` and `every`.
- Quick `period` / `phase` editing from the right-click menu, in addition to the
  signal properties dialog.
- Insert-mode editing: press the middle mouse button on a cell to insert typed
  characters and push the rest of the lane right; leave with `Esc` or another
  middle click. **Ctrl+Shift+←/→** inserts one cycle before/after the selection
  for every selected lane.
- **Delete** now really deletes the selected cycles (the lane shifts left);
  **Shift+Delete** keeps the old "replace with `.`" behaviour.
- Multiple document tabs with per-tab editor text, selection, zoom and scroll
  position; whole signals or groups can be copied between tabs and windows.
- Waveform cycles to the right of the last character can be selected, dragged
  over continuously and edited.
- The JSON editor follows the waveform selection: it scrolls to the lane's
  `wave` line and highlights the selected cycle characters.
- Dark mode can switch the waveform to the official `dark` skin automatically
  (**Preferences → Behaviour**, enabled by default).
- Export dialogs default to the current file name and remember the last export
  folder.
- New `groups.json` and `arrows.json` examples.

### Changed

- Clock lanes follow the longest signal in both directions: they shrink when the
  longest signal gets shorter, not only grow.
- In inline label editing, `Enter` jumps to the next signal name and `Tab` to
  the next data label (wrapping around); the two kinds can still be reached from
  each other.
- New signals use the clock length, and `Ctrl+Enter` opens the name editor for
  the new lane.
- Drag handles in the signal gutter stay left-aligned for long signal names.
- Signal group brackets and rotated group names are rendered on screen and in
  PNG/SVG exports.
- JSON synchronisation and **Format JSON** now round-trip groups, empty rows,
  `edge` arrows/sharp lines, JSONML `head`/`foot` text and unknown fields
  instead of flattening or dropping them.
- WaveDrom JSONML `head`/`foot` text keeps inner spaces when flattened.

### Fixed

- Selecting signals beyond the end of a short `wave` string is possible, and
  painting there extends the lane instead of being ignored.
- Deleting the longest signal shortens the clocks again.
- Long signal names no longer push the drag handle out of alignment.
- Group names and brackets are exported with the diagram.

## [2.0.0] — 2026-10-26

A complete rewrite of the desktop UI on Qt/PySide6 with a WaveDrom-compatible
interactive renderer.

### Added

- Double-click inline editing for signal names and bus `data` labels, with
  Enter/Tab/Shift+Tab navigation between editable fields and Esc to cancel.
- Drag-and-drop signal reordering in the left gutter, plus Alt+↑/↓.
- Wave / Editor split views in top-bottom and left-right orientations, with
  live JSON → waveform rendering and waveform → JSON updates.
- Automatic clock extension for lanes named `clk`/`clock`, including periodic
  rectangular clocks and per-row `period` support.
- Add, insert above/below, delete, duplicate, copy, cut and paste for signals,
  with configurable shortcuts and system-clipboard WaveJSON transfer.
- Rectangular cell selection and direct waveform-character painting
  (`0 1 . x z = u d 2..9 p P n N l L h H |`).
- A configurable shortcut system with 60 actions, key capture, conflict
  detection and persistence in Preferences.
- Light/dark themes, English/中文 UI, zoom, time ruler, selection overlays,
  context menus, recent files, drag-and-drop file opening and window-state
  persistence.
- Exact WaveDrom skin rendering for `default`, `lowkey`, `narrow` and `dark`.
- Lightweight JSON/JSON5 editor with line numbers, syntax highlighting, current
  line highlight, smart indent, find/replace, format, error line markers and a
  live/manual sync switch.
- Row properties (name, wave, data, node, period, phase), relation editor,
  ASCII preview and PNG/SVG export.
- Unit and offscreen GUI test suite.

### Changed

- Requirements are now `PySide6>=6.6` and `json5>=0.9.14`; legacy Python
  `wavedrom`/CairoSVG/Pillow runtime dependencies are no longer needed.
- Application settings live in `%APPDATA%/WaveDromGen/settings.json`
  (Windows) or `~/.config/WaveDromGen/settings.json` (Linux).
- Saving writes canonical UTF-8 JSON, preserving unknown WaveJSON fields.

### Removed

- The v1 Tkinter interface and its generated icon database. The old code
  remains available in Git history.
- The outdated French documentation and legacy UI screenshots.

### Known limitations

- Nested WaveJSON signal groups are flattened for editing and a note is shown;
  unknown top-level fields are still preserved.
- Advanced `head`/`foot` JSONML styling is preserved in the document but only
  basic text/tick/tock rendering is drawn.
