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
from WaveDromGen.model import Selection  # noqa: E402
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
            for tab in getattr(self.win, "tabs", []):
                tab.doc.mark_saved()
            # Never block the test run on a modal "save changes?" dialog.
            self.win._maybe_save = lambda *args, **kwargs: True
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

    def test_delete_removes_cycle(self):
        from WaveDromGen.model import Selection

        self.win._apply_editor_text(
            json.dumps(
                {
                    "signal": [
                        {"name": "clk", "wave": "p....."},
                        {"name": "a", "wave": "0123.."},
                    ]
                }
            )
        )
        QTest.qWait(100)
        self._focus_canvas()
        self.canvas.selection = Selection(1, 1, 1, 2)
        self.canvas.active_cell = (1, 1)
        QTest.keyClick(self.canvas, Qt.Key_Delete)
        QTest.qWait(60)
        # Delete removes the selected cycles instead of replacing them with "."
        self.assertEqual(self.win.doc.rows[1].wave, "03..")
        self.assertEqual(len(self.win.doc.rows[0].wave), 4)
        # Shift+Delete is still the "clear to ." command
        self.canvas.selection = Selection(1, 0, 1, 0)
        self.canvas.active_cell = (1, 0)
        QTest.keyClick(self.canvas, Qt.Key_Delete, Qt.ShiftModifier)
        QTest.qWait(60)
        self.assertTrue(self.win.doc.rows[1].wave.startswith("."))

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
        QTest.qWait(80)
        self.assertEqual(len(self.win.doc.rows), count + 1)
        # Ctrl+Return also starts editing the new signal name.
        self.assertTrue(self.canvas._editing)
        QTest.keyClick(self.canvas._editor, Qt.Key_Escape)
        QTest.qWait(40)
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



class WaveCompatibilityTests(GuiTestBase):
    GROUP_DOC = {
        "signal": [
            {"name": "clk", "wave": "p..Pp..P"},
            [
                "Master",
                ["ctrl", {"name": "write", "wave": "01.0...."}, {"name": "read", "wave": "0...1..0"}],
                {"name": "addr", "wave": "x3.x4..x", "data": ["A1", "A2"]},
                {"name": "wdata", "wave": "x3.x....", "data": ["D1"]},
            ],
            {},
            ["Slave", ["ctrl", {"name": "ack", "wave": "x01x0.1x"}], {"name": "rdata", "wave": "x.....4x"}],
        ],
        "edge": ["b-|a t1"],
        "head": {"text": "Title"},
        "config": {"hscale": 1, "skin": "default"},
        "extra": {"keep": True},
    }

    def _load(self, source):
        self.win._apply_editor_text(json.dumps(source))
        self.win.editor_panel.set_text(self.win._json_text())
        self.win.editor_panel.mark_synced()
        self.canvas.refresh()
        QTest.qWait(60)

    def test_group_click_selects_group_and_ungroup(self):
        self._load(self.GROUP_DOC)
        QTest.qWait(80)
        group = next(item for item in self.canvas._layout.groups if item.name == "Master")
        QTest.mouseClick(
            self.canvas,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(int(group.x - 2), int((group.top + group.bottom) / 2)),
        )
        QTest.qWait(40)
        self.assertEqual(self.canvas.selected_rows(), list(range(group.span.start, group.span.end + 1)))
        self.assertIsNotNone(self.canvas.selected_group_span())
        self.win._ungroup_selection()
        QTest.qWait(80)
        tree = self.win.doc.dump_dict()["signal"]
        # "Master" is dissolved; its nested "ctrl" group stays intact.
        self.assertEqual(tree[1][0], "ctrl")
        self.assertEqual(tree[2]["name"], "addr")
        self.assertEqual(tree[3]["name"], "wdata")

    def test_group_copy_paste_keeps_structure(self):
        self._load(self.GROUP_DOC)
        QTest.qWait(60)
        self.win._select_rows([1, 2, 3, 4])
        self.win._copy_rows()
        self.win._select_rows([7])
        self.win._paste_rows()
        QTest.qWait(80)
        tree = self.win.doc.dump_dict()["signal"]
        self.assertEqual(tree[-1][0], "Master")
        self.assertEqual(tree[-1][1][0], "ctrl")

    def test_empty_row_and_unknown_fields_survive_format(self):
        source = {
            "signal": [
                {"name": "a", "wave": "01..", "node": ".x..", "custom": {"k": 1}},
                {},
                ["G", {"name": "b", "wave": "10.."}],
            ],
            "edge": ["a-|b setup"],
            "head": {"text": ["tspan", ["tspan", {"class": "h1"}, "big"], " tail"], "tick": 0},
            "config": {"hscale": 2, "skin": "lowkey", "marks": False},
            "extra": {"keep": True},
        }
        self._load(source)
        QTest.qWait(60)
        self.win._format_json()
        QTest.qWait(120)
        self.assertFalse(self.win.editor_panel.has_error)
        formatted = json.loads(self.win.editor_panel.text())
        self.assertEqual(formatted["signal"][1], {})
        self.assertEqual(formatted["signal"][2][0], "G")
        self.assertEqual(formatted["edge"], ["a-|b setup"])
        self.assertEqual(formatted["head"]["text"][1][1], {"class": "h1"})
        self.assertEqual(formatted["config"]["marks"], False)
        self.assertEqual(formatted["extra"], {"keep": True})
        self.assertEqual(formatted["signal"][0]["custom"], {"k": 1})

    def test_data_labels_written_as_arrays(self):
        self._load({"signal": [{"name": "bus", "wave": "x.==x", "data": "A B"}]})
        QTest.qWait(60)
        self.win.doc.set_data_label(0, 0, "HEAD")
        self.win._sync_editor_from_doc(force=True)
        QTest.qWait(40)
        self.assertIn('"HEAD"', self.win.editor_panel.text())
        self.assertIn("[", self.win.editor_panel.text())
        self.assertEqual(self.win.doc.rows[0].data_value, ["HEAD", "B"])


class CycleEditingTests(GuiTestBase):
    def _load(self, source):
        self.win._apply_editor_text(json.dumps(source))
        self.win.editor_panel.set_text(self.win._json_text())
        self.win.editor_panel.mark_synced()
        self.canvas.refresh()
        QTest.qWait(60)

    def test_insert_cycle_before_and_after(self):
        from WaveDromGen.model import Selection

        self._load({"signal": [{"name": "a", "wave": "0123"}, {"name": "b", "wave": "0101"}]})
        self.canvas.selection = Selection(0, 1, 1, 1)
        self.canvas.active_cell = (0, 1)
        self._focus_canvas()
        self.win._insert_cycle(True)
        QTest.qWait(60)
        self.assertEqual(self.win.doc.rows[0].wave, "0.123")
        self.assertEqual(self.win.doc.rows[1].wave, "0.101")
        self.win._insert_cycle(False)
        QTest.qWait(60)
        self.assertEqual(self.win.doc.rows[0].wave, "0..123")

    def test_middle_click_toggles_insert_mode(self):
        self._load({"signal": [{"name": "a", "wave": "0123"}]})
        QTest.qWait(40)
        row = self.canvas._layout.rows[0]
        QTest.mouseClick(
            self.canvas,
            Qt.MiddleButton,
            Qt.NoModifier,
            QPoint(int(row.char_x(2) + 4), int(row.slot_top + 12)),
        )
        QTest.qWait(50)
        self.assertTrue(self.canvas.insert_mode)
        QTest.keyClick(self.canvas, Qt.Key_X)
        QTest.qWait(50)
        self.assertEqual(self.win.doc.rows[0].wave, "01x23")
        QTest.keyClick(self.canvas, Qt.Key_Escape)
        QTest.qWait(30)
        self.assertFalse(self.canvas.insert_mode)

    def test_right_side_empty_cycle_editing(self):
        self._load({"signal": [{"name": "a", "wave": "01.."}, {"name": "clk", "wave": "p..."}]})
        QTest.qWait(40)
        row = self.canvas._layout.rows[0]
        QTest.mouseClick(
            self.canvas,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(int(row.char_x(6) + 4), int(row.slot_top + 12)),
        )
        QTest.qWait(60)
        self.assertEqual(self.canvas.active_cell, (0, 6))
        self._focus_canvas()
        QTest.keyClick(self.canvas, Qt.Key_1)
        QTest.qWait(70)
        self.assertEqual(len(self.win.doc.rows[0].wave), 7)
        self.assertEqual(self.win.doc.rows[0].wave[6], "1")

    def test_enter_walks_names_and_tab_walks_data_labels(self):
        self._load(
            {
                "signal": [
                    {"name": "clk", "wave": "p......."},
                    {"name": "bus", "wave": "x.==x...", "data": ["OLD", "NEXT"]},
                    {"name": "sig", "wave": "01......"},
                ]
            }
        )
        QTest.qWait(60)
        self.canvas.edit_name_at(1)
        QTest.qWait(40)
        QTest.keyClick(self.canvas._editor, Qt.Key_Return)
        QTest.qWait(80)
        self.assertEqual(self.canvas._editing_target.kind, "name")
        self.assertEqual(self.canvas._editing_target.row, 2)
        QTest.keyClick(self.canvas._editor, Qt.Key_Escape)
        QTest.qWait(40)
        self.canvas.edit_name_at(1)
        QTest.qWait(40)
        QTest.keyClick(self.canvas._editor, Qt.Key_Tab)
        QTest.qWait(80)
        self.assertEqual(self.canvas._editing_target.kind, "data")
        self.assertEqual(self.canvas._editing_target.data_index, 0)
        QTest.keyClick(self.canvas._editor, Qt.Key_Tab)
        QTest.qWait(80)
        self.assertEqual(self.canvas._editing_target.data_index, 1)
        QTest.keyClick(self.canvas._editor, Qt.Key_Return)
        QTest.qWait(80)
        self.assertEqual(self.canvas._editing_target.kind, "name")
        QTest.keyClick(self.canvas._editor, Qt.Key_Escape)
        QTest.qWait(30)

    def test_ctrl_enter_opens_name_editor(self):
        self._focus_canvas()
        QTest.keyClick(self.canvas, Qt.Key_Return, Qt.ControlModifier)
        QTest.qWait(100)
        self.assertTrue(self.canvas._editing)
        self.assertEqual(self.canvas._editing_target.kind, "name")
        self.canvas._editor.setText("payload")
        QTest.keyClick(self.canvas._editor, Qt.Key_Return)
        QTest.qWait(80)
        self.assertEqual(self.win.doc.rows[-1].name, "payload")

    def test_editor_follows_waveform_selection(self):
        from WaveDromGen.model import Selection

        self._load(
            {
                "signal": [
                    {"name": "clk", "wave": "p......."},
                    {"name": "bus", "wave": "x.==x...", "data": ["A", "B"]},
                ]
            }
        )
        QTest.qWait(60)
        self._focus_canvas()
        self.canvas.selection = Selection(1, 3, 1, 4)
        self.canvas.active_cell = (1, 3)
        self.canvas._emit_cursor_info()
        QTest.qWait(60)
        editor = self.win.editor_panel.editor
        ranges = editor.wave_value_ranges()
        self.assertEqual(len(ranges), 2)
        self.assertTrue(editor._wave_selections)
        selection = editor._wave_selections[-1]
        text = editor.toPlainText()
        start = selection.cursor.selectionStart() - ranges[1][0]
        end = selection.cursor.selectionEnd() - ranges[1][0]
        self.assertEqual((start, end), (3, 5))
        self.assertEqual(text[selection.cursor.selectionStart(): selection.cursor.selectionEnd()], "=x")


class ThemeAndTabTests(GuiTestBase):
    def test_dark_theme_switches_wave_skin(self):
        self.assertNotEqual(self.win.doc.skin_name(), "dark")
        self.win._toggle_theme()
        QTest.qWait(100)
        self.assertTrue(self.win.theme.dark)
        self.assertEqual(self.win.doc.skin_name(), "dark")
        self.win._toggle_theme()
        QTest.qWait(100)
        self.assertFalse(self.win.theme.dark)
        self.assertEqual(self.win.doc.skin_name(), "default")

    def test_tabs_keep_documents_and_cross_paste(self):
        self.win._apply_editor_text(
            json.dumps({"signal": [{"name": "clk", "wave": "p..."}, {"name": "bus", "wave": "x.==x"}]})
        )
        # Keep the editor text and the model in sync (programmatic apply).
        self.win.editor_panel.set_text(self.win._json_text())
        self.win.editor_panel.mark_synced()
        QTest.qWait(100)
        other = Path(self.tmp.name) / "second.json"
        other.write_text(
            json.dumps({"signal": [{"name": "x", "wave": "01.."}, {"name": "y", "wave": "10.."}]}),
            encoding="utf-8",
        )
        self.win.open_file(str(other))
        QTest.qWait(150)
        self.assertEqual(len(self.win.tabs), 2)
        self.assertTrue(self.win.tab_bar.isVisible())
        self.assertEqual([row.name for row in self.win.doc.rows], ["x", "y"])
        # Copy two lanes in the first tab...
        self.win._activate_tab(0)
        QTest.qWait(80)
        self.win._select_rows([0, 1])
        self.win._copy_rows()
        # ...and paste them into the second one.
        self.win._activate_tab(1)
        QTest.qWait(80)
        self.win._select_rows([0])
        self.win._paste_rows()
        QTest.qWait(100)
        self.assertEqual([row.name for row in self.win.doc.rows], ["x", "clk", "bus", "y"])
        # Closing a tab keeps the other document alive.
        for tab in self.win.tabs:
            tab.doc.mark_saved()
        self.win.editor_panel.set_text(self.win._json_text())
        self.win.editor_panel.mark_synced()
        self.win._close_tab(1)
        QTest.qWait(100)
        self.assertEqual(len(self.win.tabs), 1)


class WaveEditingV22Tests(GuiTestBase):
    """Regression tests for blank lanes, groups, insert mode and block edits."""

    def _load(self, source):
        self.win._apply_editor_text(json.dumps(source))
        self.win.editor_panel.set_text(self.win._json_text())
        self.win.editor_panel.mark_synced()
        self.canvas.refresh()
        QTest.qWait(70)

    def test_blank_lanes_are_not_padded_by_other_lanes(self):
        self._load({"signal": [{"name": "a", "wave": "01.."}, {}, {"name": "b", "wave": "10.."}]})
        self._focus_canvas()
        self.canvas.set_active_cell(0, 8)
        QTest.keyClick(self.canvas, Qt.Key_1)
        QTest.qWait(80)
        self.assertEqual(self.win.doc.rows[1].wave, "")
        self.assertEqual(self.win.doc.rows[2].wave, "10..")
        self.assertEqual(self.win.doc.rows[0].wave, "01......1")

    def test_group_label_is_not_covered_by_the_bracket(self):
        from PySide6.QtCore import QRectF

        self._load(
            {
                "signal": [
                    ["Master", {"name": "a", "wave": "01.."}, {"name": "b", "wave": "10.."}],
                    {"name": "c", "wave": "0..."},
                ]
            }
        )
        group = self.canvas._layout.groups[0]
        self.assertGreaterEqual(group.x - group.name_x, 15.0)
        bracket = QRectF(group.x - 6, group.top, 6, group.bottom - group.top)
        self.assertFalse(group.name_rect.intersects(bracket))

    def test_typing_dot_extends_empty_cycles(self):
        self._load({"signal": [{"name": "a", "wave": "01.."}]})
        self._focus_canvas()
        self.canvas.set_active_cell(0, 7)
        QTest.keyClick(self.canvas, Qt.Key_Period)
        QTest.qWait(80)
        self.assertEqual(self.win.doc.rows[0].wave, "01......")

    def test_auto_advance_when_character_is_unchanged(self):
        self._load({"signal": [{"name": "a", "wave": "01.."}]})
        self._focus_canvas()
        self.canvas.set_active_cell(0, 1)
        QTest.keyClick(self.canvas, Qt.Key_1)  # same character as the cell
        QTest.qWait(60)
        self.assertEqual(self.canvas.active_cell, (0, 2))
        self.canvas.set_auto_advance(False)
        self.canvas.set_active_cell(0, 1)
        QTest.keyClick(self.canvas, Qt.Key_1)
        QTest.qWait(60)
        self.assertEqual(self.canvas.active_cell, (0, 1))
        self.canvas.set_auto_advance(True)

    def test_palette_buttons_apply_characters_and_insert_cycles(self):
        self._load({"signal": [{"name": "a", "wave": "...."}]})
        texts = [button.text() for button in self.win.palette_buttons]
        for char in "01x.z=2345pnudhl":
            self.assertIn(char, texts)
        self.assertTrue(self.win.palette_toggle.isCheckable())
        self.canvas.set_active_cell(0, 0)
        self.win._apply_palette_char("x")
        QTest.qWait(80)
        self.assertEqual(self.win.doc.rows[0].wave, "x...")
        self.canvas.selection = Selection(0, 1, 0, 1)
        self.win._insert_cycle(True)
        QTest.qWait(60)
        self.assertEqual(self.win.doc.rows[0].wave, "x....")

    def test_middle_drag_selects_rows_and_inserts_into_all(self):
        self._load(
            {
                "signal": [
                    {"name": "a", "wave": "0123"},
                    {"name": "b", "wave": "0123"},
                    {"name": "c", "wave": "0123"},
                ]
            }
        )
        row0 = self.canvas._layout.rows[0]
        row2 = self.canvas._layout.rows[2]
        start = QPoint(15, int(row0.slot_top + 12))
        end = QPoint(15, int(row2.slot_top + 12))
        QTest.mousePress(self.canvas, Qt.MiddleButton, Qt.NoModifier, start)
        QTest.mouseMove(self.canvas, end)
        QTest.qWait(30)
        QTest.mouseRelease(self.canvas, Qt.MiddleButton, Qt.NoModifier, end)
        QTest.qWait(80)
        self.assertEqual(self.canvas.selected_rows(), [0, 1, 2])
        self.assertTrue(self.canvas.insert_mode)
        self.canvas.setFocus(Qt.OtherFocusReason)
        self.canvas.active_cell = (0, 1)
        QTest.keyClick(self.canvas, Qt.Key_X)
        QTest.qWait(80)
        self.assertEqual([row.wave for row in self.win.doc.rows], ["0x123"] * 3)
        self.canvas.set_insert_mode(False)

    def test_insert_mode_button_and_caret(self):
        from WaveDromGen.model import Selection as Sel

        self._load(
            {
                "signal": [
                    {"name": "a", "wave": "0123"},
                    {"name": "b", "wave": "0123"},
                ]
            }
        )
        self.canvas.selection = Sel(0, 2, 1, 2)
        self.canvas.active_cell = (0, 2)
        self.win.palette_toggle.click()
        QTest.qWait(60)
        self.assertTrue(self.canvas.insert_mode)
        self.assertTrue(self.win.palette_toggle.isChecked())
        self.assertIn("INSERT", self.win.status_cursor.text())
        # The canvas must render the insertion caret without errors.
        image = self.canvas.grab()
        self.assertFalse(image.isNull())
        self.win.palette_toggle.click()
        QTest.qWait(60)
        self.assertFalse(self.canvas.insert_mode)

    def test_multi_row_selection_highlights_only_wave_strings(self):
        self._load(
            {
                "signal": [
                    {"name": "clk", "wave": "p......."},
                    {"name": "bus", "wave": "x.==x...", "data": ["A", "B"]},
                    {"name": "sig", "wave": "01......"},
                ]
            }
        )
        self._focus_canvas()
        self.canvas.set_row_selection([1, 2])
        self.canvas._emit_cursor_info()
        QTest.qWait(80)
        editor = self.win.editor_panel.editor
        # No broad text selection: only the wave strings are highlighted.
        self.assertFalse(editor.textCursor().hasSelection())
        text = editor.toPlainText()
        highlighted = [
            text[selection.cursor.selectionStart(): selection.cursor.selectionEnd()]
            for selection in editor._wave_selections
        ]
        self.assertEqual(highlighted, ["x.==x...", "01......"])

    def test_palette_groups_and_group_buttons(self):
        self._load(
            {
                "signal": [
                    {"name": "a", "wave": "01.."},
                    {"name": "b", "wave": "10.."},
                ]
            }
        )
        texts = [button.text() for button in self.win.palette_buttons]
        for char in ("0", "1", "x", "z", ".", "=", "2", "9", "u", "d", "p", "P", "N", "L", "|", "<", ">"):
            self.assertIn(char, texts)
        classes = {button.text(): button.property("paletteClass") for button in self.win.palette_buttons}
        self.assertEqual(classes["0"], "level")
        self.assertEqual(classes["="], "bus")
        self.assertEqual(classes["p"], "clock")
        self.assertEqual(classes["|"], "special")
        self.assertIn(self.win.palette_group_button.text(), ("Group", "分组"))
        self.assertIn(self.win.palette_ungroup_button.text(), ("Ungroup", "取消分组"))
        self.assertTrue(self.win.palette_group_button.isEnabled())
        # Group two signals through the model, then use the ungroup button.
        self.win._select_rows([0, 1])
        self.win.doc.group_rows([0, 1], "G")
        self.win._after_model_edit(selection=[0, 1])
        self.canvas.set_row_selection([0, 1])
        self.win._update_actions()
        self.assertTrue(self.win.palette_ungroup_button.isEnabled())
        self.win.palette_ungroup_button.click()
        QTest.qWait(80)
        self.assertFalse(isinstance(self.win.doc.dump_dict()["signal"][0], list))

    def test_contextual_ctrl_c_and_ctrl_v(self):
        self._load(
            {
                "signal": [
                    {"name": "a", "wave": "012345"},
                    {"name": "b", "wave": "012345"},
                ]
            }
        )
        self.canvas.selection = Selection(0, 1, 1, 3)
        self._focus_canvas()
        QTest.keyClick(self.canvas, Qt.Key_C, Qt.ControlModifier)
        QTest.qWait(60)
        self.assertEqual(QApplication.clipboard().text(), "123\n123")
        self.canvas.selection = Selection(0, 4, 1, 4)
        self.canvas.active_cell = (0, 4)
        QTest.keyClick(self.canvas, Qt.Key_V, Qt.ControlModifier)
        QTest.qWait(80)
        self.assertEqual([row.wave for row in self.win.doc.rows], ["0123123", "0123123"])
        # With a signal-row selection, Ctrl+C/Ctrl+V work on WaveJSON signals.
        self._click_row_gutter(0)
        QTest.keyClick(self.canvas, Qt.Key_C, Qt.ControlModifier)
        QTest.qWait(60)
        self.assertIn('"signal"', QApplication.clipboard().text())
        before = len(self.win.doc.rows)
        QTest.keyClick(self.canvas, Qt.Key_V, Qt.ControlModifier)
        QTest.qWait(100)
        self.assertEqual(len(self.win.doc.rows), before + 1)

    def test_rectangular_block_copy_and_paste(self):
        self._load(
            {
                "signal": [
                    {"name": "a", "wave": "012345"},
                    {"name": "b", "wave": "012345"},
                ]
            }
        )
        self.canvas.selection = Selection(0, 1, 1, 3)
        self.assertEqual(self.canvas.cell_text(), "123\n123")
        self.canvas.selection = Selection(0, 4, 1, 4)
        QApplication.clipboard().setText("123\n123")
        self.win._paste_cells()
        QTest.qWait(80)
        self.assertEqual([row.wave for row in self.win.doc.rows], ["0123123", "0123123"])
        # A single copied line pasted into one cell spans several cycles.
        QApplication.clipboard().setText("99")
        self.canvas.set_active_cell(0, 0)
        self.win._paste_cells()
        QTest.qWait(80)
        self.assertEqual(self.win.doc.rows[0].wave, "9923123")

    def test_chinese_dialog_options(self):
        from PySide6.QtWidgets import QCheckBox, QLabel

        from WaveDromGen.dialogs import DiagramSettingsDialog, RowPropertiesDialog, SettingsDialog

        settings_dialog = SettingsDialog(
            self.win,
            settings=self.win.settings,
            registry=self.win.registry,
            shortcut_map=self.win.shortcut_map,
            language="zh",
        )
        texts = [label.text() for label in settings_dialog.findChildren(QLabel)]
        texts.extend(box.text() for box in settings_dialog.findChildren(QCheckBox))
        joined = " ".join(texts)
        self.assertIn("自动将 clk", joined)
        self.assertIn("输入任意波形字符", joined)
        self.assertIn("字号", joined)
        settings_dialog.deleteLater()

        diagram_dialog = DiagramSettingsDialog(self.win, self.win.doc, language="zh")
        diagram_texts = " ".join(label.text() for label in diagram_dialog.findChildren(QLabel))
        self.assertIn("皮肤", diagram_texts)
        self.assertIn("水平比例", diagram_texts)
        self.assertIn("Tick 标签", diagram_texts)
        diagram_dialog.deleteLater()

        row_dialog = RowPropertiesDialog(self.win, self.win.doc.rows[0], language="zh")
        row_texts = " ".join(label.text() for label in row_dialog.findChildren(QLabel))
        self.assertIn("名称", row_texts)
        self.assertIn("波形", row_texts)
        row_dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
