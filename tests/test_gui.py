# coding=utf-8
"""GUI integration tests for the Qt front-end (run with the offscreen plugin)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from WaveDromGen.app import MainWindow, ensure_fonts  # noqa: E402
from WaveDromGen.settings import Settings  # noqa: E402
from WaveDromGen.theme import apply_theme, resolve_theme  # noqa: E402


def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication([])
        ensure_fonts()
        apply_theme(app, resolve_theme("light"))
    return app


class GuiTestBase(unittest.TestCase):
    app: QApplication

    @classmethod
    def setUpClass(cls):
        cls.app = _qapp()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings_path = Path(self.tmp.name) / "settings.json"
        self.settings = Settings(settings_path)
        self.settings.data["window_geometry"] = ""
        self.settings.data["zoom"] = 1.0
        self.settings.data["view_mode"] = "stacked"
        self.settings.data["language"] = "en"
        self.settings.data["theme"] = "light"
        apply_theme(self.app, resolve_theme("light"))
        self.win = MainWindow(self.settings)
        self.win.resize(1180, 700)
        self.win.show()
        QTest.qWait(120)
        self.canvas = self.win.canvas

    def tearDown(self):
        try:
            self.win.doc.mark_saved()
            self.win.editor_panel.set_text(self.win._json_text())
            self.win.editor_panel.mark_synced()
            self.win.close()
        except Exception:
            pass
        QTest.qWait(20)
        self.tmp.cleanup()

    def _focus_canvas(self):
        self.canvas.setFocus(Qt.OtherFocusReason)
        QTest.qWait(20)

    def _click_row_gutter(self, row_index: int):
        row = self.canvas._layout.rows[row_index]
        QTest.mouseClick(
            self.canvas,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(15, int(row.slot_top + 12)),
        )
        QTest.qWait(30)


class InlineEditingTests(GuiTestBase):
    def test_double_click_name_and_tab_to_data(self):
        self.win._apply_editor_text(
            json.dumps(
                {
                    "signal": [
                        {"name": "clk", "wave": "p......."},
                        {"name": "bus", "wave": "x.==x...", "data": ["OLD", "NEXT"]},
                    ],
                    "config": {"hscale": 1, "skin": "default"},
                }
            )
        )
        QTest.qWait(100)
        canvas = self.win.canvas
        row = canvas._layout.rows[1]
        name_rect = row.name_rect
        QTest.mouseDClick(
            canvas,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(int(name_rect.center().x()), int(name_rect.center().y())),
        )
        QTest.qWait(40)
        self.assertTrue(canvas._editing)
        self.assertEqual(canvas._editing_target.kind, "name")
        canvas._editor.setText("addr")
        QTest.keyClick(canvas._editor, Qt.Key_Tab)
        QTest.qWait(100)
        self.assertEqual(self.win.doc.rows[1].name, "addr")
        self.assertTrue(canvas._editing)
        self.assertEqual(canvas._editing_target.kind, "data")
        self.assertEqual(canvas._editing_target.data_index, 0)
        canvas._editor.setText("HEAD")
        QTest.keyClick(canvas._editor, Qt.Key_Escape)
        QTest.qWait(40)
        self.assertFalse(canvas._editing)

    def test_edit_data_label_by_double_click(self):
        self.win._apply_editor_text(
            json.dumps(
                {
                    "signal": [
                        {"name": "bus", "wave": "x.==x...", "data": ["OLD", "NEXT"]},
                    ],
                    "config": {"hscale": 1, "skin": "default"},
                }
            )
        )
        QTest.qWait(100)
        canvas = self.win.canvas
        target = canvas._layout.target_by_key("data", 0, 0)
        QTest.mouseDClick(
            canvas,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(int(target.rect.center().x()), int(target.rect.center().y())),
        )
        QTest.qWait(40)
        self.assertTrue(canvas._editing)
        self.assertEqual(canvas._editing_target.kind, "data")
        canvas._editor.setText("HEAD")
        QTest.keyClick(canvas._editor, Qt.Key_Return)
        QTest.qWait(100)
        self.assertEqual(self.win.doc.rows[0].data_items()[0], "HEAD")


class CanvasEditingTests(GuiTestBase):
    def test_select_cells_and_type_waveform_character(self):
        canvas = self.canvas
        row = canvas._layout.rows[1]
        x0 = row.char_x(2) + 4
        x1 = row.char_x(4) + 4
        y = row.slot_top + 12
        QTest.mousePress(canvas, Qt.LeftButton, Qt.NoModifier, QPoint(int(x0), int(y)))
        QTest.mouseMove(canvas, QPoint(int(x1), int(y)))
        QTest.mouseRelease(canvas, Qt.LeftButton, Qt.NoModifier, QPoint(int(x1), int(y)))
        QTest.qWait(30)
        self.assertIsNotNone(canvas.selection)
        self._focus_canvas()
        QTest.keyClick(canvas, Qt.Key_Equal)
        QTest.qWait(60)
        self.assertEqual(self.win.doc.rows[1].wave[2:5], "===")
        self.assertIn("===", self.win.editor_panel.text())

    def test_ctrl_a_and_clock_tool(self):
        self._focus_canvas()
        QTest.keyClick(self.canvas, Qt.Key_A, Qt.ControlModifier)
        QTest.qWait(30)
        self.assertIsNotNone(self.canvas.selection)
        self.assertEqual(self.canvas.selection.normalized().col1, 19)
        QTest.keyClick(self.canvas, Qt.Key_Z)
        QTest.qWait(60)
        self.assertTrue(all(row.wave.startswith("z") for row in self.win.doc.rows))

    def test_auto_advance(self):
        self._focus_canvas()
        self.win.doc.rows[1].wave = "0" + "." * 19
        self.canvas._set_active(1, 0)
        QTest.keyClick(self.canvas, Qt.Key_1)
        QTest.qWait(30)
        self.assertEqual(self.win.doc.rows[1].wave[0], "1")
        self.assertEqual(self.canvas.active_cell, (1, 1))

    def test_clear_cell_with_delete(self):
        self._focus_canvas()
        self.canvas._set_active(1, 0)
        QTest.keyClick(self.canvas, Qt.Key_Delete)
        QTest.qWait(40)
        self.assertEqual(self.win.doc.rows[1].wave[0], ".")

    def test_clock_extension_after_columns(self):
        before = len(self.win.doc.rows[0].wave)
        self.win._add_column()
        QTest.qWait(50)
        self.assertEqual(len(self.win.doc.rows[0].wave), before + 1)
        self.assertEqual(len(self.win.doc.rows[1].wave), before + 1)


class RowOperationTests(GuiTestBase):
    def test_row_shortcuts_copy_paste_delete(self):
        self._click_row_gutter(1)
        count = len(self.win.doc.rows)
        self._focus_canvas()
        QTest.keyClick(self.canvas, Qt.Key_C, Qt.ControlModifier)
        QTest.qWait(40)
        self.assertIn("signal", QApplication.clipboard().text())
        QTest.keyClick(self.canvas, Qt.Key_V, Qt.ControlModifier)
        QTest.qWait(80)
        self.assertEqual(len(self.win.doc.rows), count + 1)
        QTest.keyClick(self.canvas, Qt.Key_Delete, Qt.ControlModifier)
        QTest.qWait(80)
        self.assertEqual(len(self.win.doc.rows), count)

    def test_insert_and_add_rows(self):
        count = len(self.win.doc.rows)
        self._focus_canvas()
        self.canvas._set_active(0, 0)
        QTest.keyClick(self.canvas, Qt.Key_Insert)
        QTest.qWait(80)
        self.assertEqual(len(self.win.doc.rows), count + 1)
        QTest.keyClick(self.canvas, Qt.Key_Return, Qt.ControlModifier)
        QTest.qWait(80)
        self.assertEqual(len(self.win.doc.rows), count + 2)

    def test_drag_reorder(self):
        first = self.win.doc.rows[0].name
        row0 = self.canvas._layout.rows[0]
        row2 = self.canvas._layout.rows[2]
        QTest.mousePress(self.canvas, Qt.LeftButton, Qt.NoModifier, QPoint(15, int(row0.slot_top + 12)))
        QTest.mouseMove(self.canvas, QPoint(15, int(row2.slot_top + 12)))
        QTest.mouseRelease(self.canvas, Qt.LeftButton, Qt.NoModifier, QPoint(15, int(row2.slot_top + 12)))
        QTest.qWait(100)
        self.assertNotEqual(self.win.doc.rows[0].name, first)

    def test_undo_redo_row_change(self):
        count = len(self.win.doc.rows)
        self._focus_canvas()
        QTest.keyClick(self.canvas, Qt.Key_Return, Qt.ControlModifier)
        QTest.qWait(60)
        self.assertEqual(len(self.win.doc.rows), count + 1)
        QTest.keyClick(self.canvas, Qt.Key_Z, Qt.ControlModifier)
        QTest.qWait(60)
        self.assertEqual(len(self.win.doc.rows), count)
        QTest.keyClick(self.canvas, Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
        QTest.qWait(60)
        self.assertEqual(len(self.win.doc.rows), count + 1)


class LiveJsonTests(GuiTestBase):
    def test_json_to_wave_and_clock_extension(self):
        text = json.dumps(
            {
                "signal": [
                    {"name": "clk", "wave": "p..."},
                    {"name": "a", "wave": "0" * 30},
                ],
                "config": {"hscale": 1, "skin": "default"},
            }
        )
        self.win.editor_panel.editor.setPlainText(text)
        QTest.qWait(450)
        self.assertEqual([row.name for row in self.win.doc.rows], ["clk", "a"])
        self.assertEqual(len(self.win.doc.rows[0].wave), 30)
        self.assertFalse(self.win.editor_panel.has_error)

    def test_invalid_json_keeps_last_valid_waveform(self):
        before = [row.name for row in self.win.doc.rows]
        self.win.editor_panel.editor.setPlainText('{"signal": [ }')
        QTest.qWait(450)
        self.assertTrue(self.win.editor_panel.has_error)
        self.assertEqual([row.name for row in self.win.doc.rows], before)

    def test_wave_to_json(self):
        self._focus_canvas()
        self.canvas._set_active(1, 0)
        QTest.keyClick(self.canvas, Qt.Key_1)
        QTest.qWait(80)
        self.assertIn('"wave": "11', self.win.editor_panel.text())

    def test_view_modes(self):
        for key, mode in ((Qt.Key_1, "wave"), (Qt.Key_2, "editor"), (Qt.Key_3, "stacked"), (Qt.Key_4, "side")):
            self._focus_canvas()
            QTest.keyClick(self.canvas, key, Qt.ControlModifier)
            QTest.qWait(60)
            self.assertEqual(self.win._view_mode, mode)
        self.assertTrue(self.win.wave_view.isVisible())
        self.assertTrue(self.win.editor_panel.isVisible())


class FileTests(GuiTestBase):
    def test_save_and_reopen(self):
        self._focus_canvas()
        self.canvas._set_active(1, 0)
        QTest.keyClick(self.canvas, Qt.Key_1)
        QTest.qWait(50)
        path = Path(self.tmp.name) / "roundtrip.json"
        self.assertTrue(self.win.save_file(str(path)))
        self.assertFalse(self.win.doc.dirty)
        text = path.read_text(encoding="utf-8")
        self.assertIn('"signal"', text)
        self.win.open_file(str(path))
        QTest.qWait(80)
        self.assertFalse(self.win.doc.dirty)
        self.assertTrue(self.win.doc.rows[1].wave.startswith("11"))

    def test_empty_document_can_add_signal(self):
        self.win._apply_editor_text('{"signal": [], "config": {"hscale": 1, "skin": "default"}}')
        QTest.qWait(100)
        self.assertEqual(len(self.win.doc.rows), 0)
        self.assertTrue(self.win.actions["row_add"].isEnabled())
        self._focus_canvas()
        self.win._insert_signal("end")
        QTest.qWait(80)
        self.assertEqual(len(self.win.doc.rows), 1)


class SettingsAndThemeTests(GuiTestBase):
    def test_language_switch_retranslates_menus(self):
        self.win._set_language("zh")
        QTest.qWait(80)
        titles = [action.text() for action in self.win.menuBar().actions()]
        self.assertIn("文件", titles)
        self.assertIn("工具", titles)
        self.win._set_language("en")
        QTest.qWait(80)
        self.assertIn("File", [action.text() for action in self.win.menuBar().actions()])

    def test_dark_theme_applies(self):
        self.win._apply_theme("dark")
        QTest.qWait(80)
        self.assertTrue(self.win.theme.dark)
        self.win._apply_theme("light")
        QTest.qWait(80)
        self.assertFalse(self.win.theme.dark)

    def test_shortcut_change_is_persisted(self):
        from WaveDromGen.settings import Settings as SettingsClass

        self.win.shortcut_map["row_duplicate"] = ["Ctrl+Shift+D"]
        self.win._apply_shortcuts()
        sequences = [seq.toString() for seq in self.win.actions["row_duplicate"].shortcuts()]
        self.assertIn("Ctrl+Shift+D", sequences)
        self.win.settings.set_shortcuts(self.win.shortcut_map)
        self.win.settings.save()
        loaded = SettingsClass(self.settings.path)
        self.assertEqual(loaded.shortcuts()["row_duplicate"], ["Ctrl+Shift+D"])

    def test_manual_json_applies_on_focus_loss(self):
        self.win.editor_panel.set_live(False)
        editor = self.win.editor_panel.editor
        editor.setFocus(Qt.OtherFocusReason)
        QTest.qWait(20)
        editor.setPlainText(
            '{"signal":[{"name":"manual","wave":"0..."}],"config":{"hscale":1,"skin":"default"}}'
        )
        QTest.qWait(40)
        self.assertNotEqual(self.win.doc.rows[0].name, "manual")
        self._focus_canvas()
        QTest.qWait(120)
        self.assertEqual(self.win.doc.rows[0].name, "manual")
        self.assertFalse(self.win.editor_panel.has_error)


class ExportTests(GuiTestBase):
    def test_render_png_and_svg_helpers(self):
        from PySide6.QtCore import QRectF, QSize
        from PySide6.QtGui import QPainter
        from PySide6.QtSvg import QSvgGenerator

        from WaveDromGen.layout import DiagramLayout
        from WaveDromGen.renderer import PaintState, WaveRenderer, pixmap_for_document
        from WaveDromGen.skins import get_skin

        image, layout = pixmap_for_document(self.win.doc, zoom=1.5)
        self.assertGreater(image.width(), 100)
        self.assertGreater(image.height(), 50)
        png = Path(self.tmp.name) / "diagram.png"
        self.assertTrue(image.save(str(png), "PNG"))
        self.assertGreater(png.stat().st_size, 100)
        skin = get_skin(self.win.doc.skin_name())
        svg_layout = DiagramLayout(self.win.doc, zoom=1.5, skin=skin, chrome=False, placeholder=False)
        svg_path = Path(self.tmp.name) / "diagram.svg"
        generator = QSvgGenerator()
        generator.setFileName(str(svg_path))
        generator.setSize(QSize(int(svg_layout.width), int(svg_layout.height)))
        generator.setViewBox(QRectF(0, 0, svg_layout.width, svg_layout.height))
        painter = QPainter(generator)
        WaveRenderer().paint(
            painter,
            svg_layout,
            PaintState(show_chrome=False, show_selection=False),
        )
        painter.end()
        self.assertIn("<svg", svg_path.read_text(encoding="utf-8"))



if __name__ == "__main__":
    unittest.main()
