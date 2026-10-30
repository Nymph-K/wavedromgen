# Changelog

All notable changes to WaveDromGen are documented here.

## [2.3.0] — 2026-10-31

Palette and localisation polish for the v2.2 waveform editor.

### Added

- **Group / Ungroup buttons** in the waveform palette, in addition to
  <kbd>Ctrl</kbd>+<kbd>G</kbd> / <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd>.
- The palette now follows the familiar WaveDrom grouping and colour scheme:
  levels (`0 1 x z .`), buses (`= 2 3 4 5 6 7 8 9 u d`), clocks
  (`p n P N h l H L`) and specials (`| < >`), separated by group dividers under
  a “Draw / 绘制” label.
- Context-sensitive clipboard on the canvas: <kbd>Ctrl</kbd>+<kbd>C</kbd> /
  <kbd>Ctrl</kbd>+<kbd>V</kbd> copy/paste the waveform block when cells are
  selected, and whole WaveJSON signals/groups when signal rows are selected.
- Full Chinese localisation of the Preferences dialog (general and shortcut
  tabs), the Diagram Settings dialog and the Signal Properties dialog.

### Changed

- When several signal rows are selected, the JSON editor now highlights only
  the corresponding `wave` strings instead of selecting all the JSON text in
  between.

## [2.2.0] — 2026-10-30

Editing polish: a waveform palette, multi-lane insert mode and rectangular block
edits, plus a round of fixes for the v2.1 editor.

### Added

- **Waveform palette** above the canvas with one button per common wave character
  (`0 1 x . z = 2 3 4 5 p n u d h l`), insert-cycle-before/after, delete-cycle
  and empty `{}` row buttons. Clicking a character writes it to the selection.
- **Insert mode button** (`INS`) in the palette, in addition to the middle mouse
  button and the configurable action.
- **Insertion caret**: in insert mode a highlighted column and an I-beam caret
  show exactly which cycle will be pushed right.
- **Middle-button drag** selects several signal rows (in the gutter or across
  the waveform) and toggles insert mode; typing then inserts the character into
  every selected lane at once.
- **Multi-row selections are mirrored in the JSON editor**: the corresponding
  `wave` lines are highlighted and selected as a multi-line text selection.
- **Rectangular block copy/paste** for waveform cells: a copied block is pasted
  as a block (multiple rows and columns), and a single copied line pasted into
  one cell fills several cycles.
- Auto-advance is now switchable in **Preferences → Behaviour**: "jump to the
  next cycle after typing any waveform character", including characters that do
  not change the cell.

### Fixed

- Editing one lane no longer pads unrelated lanes (especially empty `{}` rows)
  with `0.....`. Only the lanes that receive characters are extended.
- Group names are no longer clipped by their bracket: labels get their own
  column, are drawn in full, and the bracket no longer overlaps them.
- Typing `.` into an empty cycle to the right of a lane now extends the lane
  (previously only non-`.` characters registered a change).
- Typing a character that equals the current cell no longer blocks
  auto-advance.
- Clearing cells (`Shift+Delete`) no longer creates cycles in empty lanes.
- The insert-mode caret, palette state and status text stay in sync.

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
