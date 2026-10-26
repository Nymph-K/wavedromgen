# Changelog

All notable changes to WaveDromGen are documented here.

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
