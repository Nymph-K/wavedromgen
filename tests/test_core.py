# coding=utf-8
"""Unit tests for the waveform engine, document model and settings."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from WaveDromGen.ascii_render import document_to_ascii  # noqa: E402
from WaveDromGen.model import (  # noqa: E402
    DocumentError,
    Selection,
    SignalRow,
    WaveDocument,
)
from WaveDromGen.settings import Settings  # noqa: E402
from WaveDromGen.shortcuts import ShortcutRegistry  # noqa: E402
from WaveDromGen.wavedrom_render import (  # noqa: E402
    find_lane_markers,
    lane_layout,
    parse_wave_lane,
    sanitize_wave_char,
)


class RenderPortTests(unittest.TestCase):
    def test_bricks_match_official_wavedrom(self):
        cases = {
            ("x.==.=x", 1, 0): (
                14,
                [5.0, 8.0, 11.0],
                "xxx xxx xxx xxx xmv-2 vvv-2 vmv-2-2 vvv-2 vvv-2 vvv-2 vmv-2-2 vvv-2 vmx-2 xxx",
            ),
            ("x.345x|=.x", 1, 0): (
                20,
                [5.0, 7.0, 9.0, 16.0],
                "xxx xxx xxx xxx xmv-3 vvv-3 vmv-3-4 vvv-4 vmv-4-5 vvv-5 vmx-5 xxx xxx xxx xmv-2 vvv-2 vvv-2 vvv-2 vmx-2 xxx",
            ),
            ("p.......", 1, 0): (
                16,
                [],
                "pclk nclk pclk nclk pclk nclk pclk nclk pclk nclk pclk nclk pclk nclk pclk nclk",
            ),
            ("p...", 2, 0): (
                16,
                [],
                "pclk 111 nclk 000 pclk 111 nclk 000 pclk 111 nclk 000 pclk 111 nclk 000",
            ),
        }
        for (wave, period, phase), (length, markers, bricks) in cases.items():
            parsed, unseen = parse_wave_lane(wave, period=period, phase=phase)
            self.assertEqual(len(parsed), length)
            self.assertEqual(find_lane_markers(parsed), markers)
            self.assertEqual(" ".join(parsed), bricks)
            self.assertEqual(unseen, 0)

    def test_phase_shift(self):
        parsed, unseen = parse_wave_lane("x.3x=x4x=x=x=x=x", phase=0.5)
        self.assertEqual(len(parsed), 31)
        self.assertEqual(find_lane_markers(parsed), [4, 8, 12, 16, 20, 24, 28])

    def test_lane_layout_data_is_not_dropped(self):
        row = SignalRow({"name": "bus", "wave": "x.==.=x", "data": ["head", "body", "tail"]})
        layout = lane_layout(row)
        self.assertEqual(list(layout.data), ["head", "body", "tail"])
        self.assertEqual(list(layout.markers), [5.0, 8.0, 11.0])

    def test_sanitize_chars(self):
        self.assertEqual(sanitize_wave_char("X"), "x")
        self.assertEqual(sanitize_wave_char("Z"), "z")
        self.assertEqual(sanitize_wave_char("U"), "u")
        self.assertEqual(sanitize_wave_char("P"), "P")
        self.assertIsNone(sanitize_wave_char("q"))
        self.assertIsNone(sanitize_wave_char(""))


class ModelTests(unittest.TestCase):
    def test_default_document(self):
        doc = WaveDocument()
        self.assertEqual(doc.row_count, 3)
        self.assertEqual(doc.column_count, 20)
        self.assertFalse(doc.dirty)
        self.assertEqual(doc.rows[0].name, "clk")
        self.assertTrue(doc.rows[0].is_clock)

    def test_roundtrip_preserves_unknown_fields(self):
        source = {
            "signal": [
                {"name": "a", "wave": "01", "custom": 7, "node": ".."},
                {"name": "b", "wave": "x.", "data": ["X"]},
            ],
            "edge": ["a~b"],
            "config": {"hscale": 2, "skin": "lowkey", "marks": False},
            "head": {"text": "Title"},
            "foot": {"text": "Caption"},
            "extra": {"keep": True},
        }
        doc = WaveDocument()
        doc.load_dict(source)
        dumped = doc.dump_dict()
        self.assertEqual(dumped["extra"], {"keep": True})
        self.assertEqual(dumped["head"], {"text": "Title"})
        self.assertEqual(dumped["signal"][0]["custom"], 7)
        self.assertEqual(dumped["config"]["marks"], False)
        self.assertEqual(doc.hscale(), 2)
        self.assertEqual(doc.skin_name(), "lowkey")

    def test_clock_auto_extension(self):
        doc = WaveDocument()
        doc.load_dict(
            {
                "signal": [
                    {"name": "clk", "wave": "p..."},
                    {"name": "long", "wave": "0" * 30},
                ],
                "config": {"hscale": 1, "skin": "default"},
            }
        )
        self.assertEqual(len(doc.rows[0].wave), 30)
        self.assertTrue(doc.rows[0].wave.startswith("p"))
        self.assertEqual(len(doc.rows[0].node), 30)

    def test_rectangular_clock_extension(self):
        row = SignalRow({"name": "clock", "wave": "0011", "node": "...."})
        doc = WaveDocument()
        doc.load_dict({"signal": [row.to_dict(), {"name": "long", "wave": "0" * 12}]})
        self.assertEqual(len(doc.rows[0].wave), 12)
        self.assertEqual(doc.rows[0].wave[:8], "00110011")

    def test_period_clock_extension_uses_time_units(self):
        doc = WaveDocument()
        doc.load_dict(
            {
                "signal": [
                    {"name": "clk", "wave": "p...", "period": 2},
                    {"name": "long", "wave": "0" * 20},
                ]
            }
        )
        self.assertEqual(len(doc.rows[0].wave), 10)  # 10 chars × 2 = 20 time units
        self.assertEqual(doc.rows[0].time_units, 20)

    def test_auto_extension_can_be_disabled(self):
        doc = WaveDocument(auto_extend_clocks=False)
        doc.load_dict(
            {
                "signal": [
                    {"name": "clk", "wave": "p..."},
                    {"name": "long", "wave": "0" * 30},
                ]
            }
        )
        self.assertEqual(len(doc.rows[0].wave), 4)

    def test_editing_and_undo_redo(self):
        doc = WaveDocument()
        before = doc.snapshot()
        changed = doc.apply_wave_chars([(1, 0), (1, 1)], "x")
        self.assertEqual(changed, 2)
        self.assertEqual(doc.rows[1].wave[:2], "xx")
        self.assertTrue(doc.undo())
        self.assertEqual(doc.snapshot(), before)
        self.assertTrue(doc.redo())
        self.assertEqual(doc.rows[1].wave[:2], "xx")

    def test_row_operations(self):
        doc = WaveDocument()
        doc.insert_blank(1, name="new")
        self.assertEqual([r.name for r in doc.rows][1], "new")
        clones = doc.duplicate_rows([1])
        self.assertEqual(len(doc.rows), 5)
        self.assertEqual(clones, [2])
        doc.move_rows([2], 0)
        self.assertEqual(doc.rows[0].name, "new")
        doc.delete_rows([0])
        self.assertEqual(len(doc.rows), 4)
        self.assertFalse(doc.dirty is False)  # modified

    def test_data_labels(self):
        doc = WaveDocument()
        doc.load_dict({"signal": [{"name": "bus", "wave": "x.==.=x", "data": ["A", "B"]}]})
        self.assertEqual(doc.rows[0].data_items(), ["A", "B"])
        doc.set_data_label(0, 3, "D")
        self.assertEqual(doc.rows[0].data_items(), ["A", "B", "", "D"])
        self.assertEqual(doc.data_label_count(doc.rows[0]), 3)

    def test_clock_rename_triggers_extension(self):
        doc = WaveDocument()
        doc.load_dict(
            {
                "signal": [
                    {"name": "a", "wave": "0" * 40},
                    {"name": "clock", "wave": "p..."},
                ]
            }
        )
        self.assertEqual(len(doc.rows[1].wave), 40)
        doc.set_name(1, "sys_clk")
        self.assertEqual(len(doc.rows[1].wave), 40)

    def test_json5_and_errors(self):
        doc = WaveDocument()
        doc.apply_json_text(
            """
            {
              // comment
              signal: [
                {name: 'clk', wave: 'p.......'},
                {name: 'bus', wave: 'x.==x...', data: ['A','B'], },
              ],
              config: {hscale: 1, skin: 'default'},
            }
            """
        )
        self.assertEqual(doc.rows[0].name, "clk")
        self.assertEqual(doc.rows[1].name, "bus")
        with self.assertRaises(DocumentError) as ctx:
            doc.apply_json_text('{"signal": [ }')
        self.assertTrue(str(ctx.exception))

    def test_parse_error_line(self):
        with self.assertRaises(DocumentError) as ctx:
            WaveDocument.parse_json_text('{\n "signal": [\n  }\n}')
        self.assertIsNotNone(ctx.exception.line)
        self.assertGreater(ctx.exception.line, 0)

    def test_ascii_contains_names_and_labels(self):
        doc = WaveDocument()
        doc.load_dict(
            {
                "signal": [
                    {"name": "clk", "wave": "p......."},
                    {"name": "bus", "wave": "x.==.=x", "data": ["head", "body", "tail"]},
                ],
                "config": {"hscale": 1, "skin": "default"},
            }
        )
        text = document_to_ascii(doc)
        self.assertIn("clk", text)
        self.assertIn("head", text)
        self.assertIn("bus", text)
        lines = text.splitlines()
        self.assertGreaterEqual(len(lines), 5)

    def test_selection_cell_count(self):
        rows = [SignalRow({"name": "a", "wave": "0" * 10}), SignalRow({"name": "b", "wave": "0" * 5})]
        sel = Selection(0, 2, 1, 7)
        self.assertEqual(sel.cell_count(rows), 6 + 3)
        self.assertEqual(sel.normalized().row0, 0)


class CompatibilityTests(unittest.TestCase):
    """WaveDrom features that must survive a load/format/save cycle."""

    GROUP_DOC = {
        "signal": [
            {"name": "clk", "wave": "p..Pp..P"},
            [
                "Master",
                [
                    "ctrl",
                    {"name": "write", "wave": "01.0...."},
                    {"name": "read", "wave": "0...1..0"},
                ],
                {"name": "addr", "wave": "x3.x4..x", "data": "A1 A2"},
                {"name": "wdata", "wave": "x3.x....", "data": "D1"},
            ],
            {},
            ["Slave", ["ctrl", {"name": "ack", "wave": "x01x0.1x"}], {"name": "rdata", "wave": "x.....4x"}],
        ],
        "edge": ["b-|a t1", "c<->e 3 ms"],
        "head": {"text": ["tspan", ["tspan", {"class": "error h1"}, "err "], "plain"], "tick": 0},
        "foot": {"text": "caption", "tock": 5},
        "config": {"hscale": 2, "skin": "lowkey", "hbounds": [0, 8], "marks": False},
        "extra": {"keep": True},
    }

    def test_nested_groups_roundtrip(self):
        doc = WaveDocument()
        doc.load_dict(self.GROUP_DOC)
        self.assertEqual([row.name for row in doc.rows], ["clk", "write", "read", "addr", "wdata", "", "ack", "rdata"])
        spans = doc.group_spans()
        self.assertEqual(
            [(span.group.display_name, span.start, span.end, span.depth) for span in spans],
            [("ctrl", 1, 2, 1), ("Master", 1, 4, 0), ("ctrl", 6, 6, 1), ("Slave", 6, 7, 0)],
        )
        dumped = doc.dump_dict()
        self.assertEqual(dumped["signal"], self.GROUP_DOC["signal"])
        self.assertEqual(dumped["head"], self.GROUP_DOC["head"])
        self.assertEqual(dumped["edge"], self.GROUP_DOC["edge"])
        self.assertEqual(dumped["config"]["hbounds"], [0, 8])
        self.assertEqual(dumped["extra"], {"keep": True})
        self.assertEqual(doc.max_group_depth(), 2)
        self.assertEqual(doc.group_depth(3), 1)

    def test_empty_row_and_partial_rows_roundtrip(self):
        source = {
            "signal": [
                {"name": "a", "wave": "01.."},
                {},
                {"node": "...a"},
                {"name": "b", "wave": "10..", "custom": 1},
            ]
        }
        doc = WaveDocument()
        doc.load_dict(source)
        self.assertEqual(len(doc.rows), 4)
        dumped = doc.dump_dict()["signal"]
        self.assertEqual(dumped, source["signal"])
        self.assertFalse(lane_layout(doc.rows[1]).bricks)
        self.assertEqual(len(lane_layout(doc.rows[2]).bricks), 0)

    def test_group_and_ungroup(self):
        doc = WaveDocument()
        doc.load_dict(
            {
                "signal": [
                    {"name": "clk", "wave": "p..."},
                    ["G", {"name": "a", "wave": "01.."}],
                    {"name": "b", "wave": "10.."},
                ]
            }
        )
        new_rows = doc.group_rows([0, 1], "Top")
        self.assertEqual(new_rows, [0, 1])
        tree = doc.dump_dict()["signal"]
        self.assertEqual(tree[0][0], "Top")
        self.assertEqual(tree[0][1]["name"], "clk")
        self.assertEqual(tree[0][2][0], "G")
        doc.undo()
        self.assertEqual(doc.dump_dict()["signal"][0]["name"], "clk")
        doc.ungroup_rows([1])
        self.assertEqual(doc.dump_dict()["signal"][1]["name"], "a")

    def test_group_clipboard_preserves_structure(self):
        doc = WaveDocument()
        doc.load_dict(self.GROUP_DOC)
        payload = doc.copy_nodes_payload([1, 2, 3, 4])
        other = WaveDocument()
        other.load_dict({"signal": [{"name": "fresh", "wave": "0..."}]})
        pasted = other.paste_rows(payload, 1)
        self.assertEqual(len(pasted), 4)
        tree = other.dump_dict()["signal"]
        self.assertEqual(tree[1][0], "Master")
        self.assertEqual(tree[1][1][0], "ctrl")

    def test_data_label_edits_use_arrays(self):
        doc = WaveDocument()
        doc.load_dict({"signal": [{"name": "bus", "wave": "x.==x", "data": "A B"}]})
        self.assertEqual(doc.rows[0].data_value, "A B")
        doc.set_data_label(0, 0, "HEAD")
        self.assertEqual(doc.rows[0].data_value, ["HEAD", "B"])
        doc.set_data_label(0, 3, "TAIL")
        self.assertEqual(doc.rows[0].data_value, ["HEAD", "B", "", "TAIL"])
        doc.update_row(0, {"data": ["x", "y"]})
        self.assertEqual(doc.rows[0].data_value, ["x", "y"])

    def test_clock_shrinks_when_longest_signal_shrinks(self):
        doc = WaveDocument()
        doc.load_dict(
            {
                "signal": [
                    {"name": "clk", "wave": "p" + "." * 19},
                    {"name": "a", "wave": "0" * 20},
                ]
            }
        )
        self.assertEqual(len(doc.rows[0].wave), 20)
        doc.update_row(1, {"wave": "0" * 6})
        self.assertEqual(len(doc.rows[0].wave), 6)
        self.assertTrue(doc.rows[0].wave.startswith("p"))

    def test_delete_and_insert_cells(self):
        doc = WaveDocument()
        doc.load_dict(
            {
                "signal": [
                    {"name": "a", "wave": "0123"},
                    {"name": "clk", "wave": "p..."},
                ]
            }
        )
        self.assertEqual(doc.delete_cells([(0, 1), (0, 2)]), 2)
        self.assertEqual(doc.rows[0].wave, "03")
        self.assertEqual(len(doc.rows[1].wave), 2)
        doc.insert_cells([0, 1], 1, count=2)
        self.assertEqual(doc.rows[0].wave, "0..3")
        self.assertEqual(len(doc.rows[1].wave), 4)
        self.assertTrue(doc.undo())
        self.assertEqual(doc.rows[0].wave, "03")

    def test_new_signal_matches_clock(self):
        doc = WaveDocument(auto_extend_clocks=False)
        doc.load_dict(
            {
                "signal": [
                    {"name": "clk", "wave": "p" + "." * 11},
                    {"name": "a", "wave": "0" * 5},
                ]
            }
        )
        row = doc.make_row()
        self.assertEqual(len(row.wave), 12)
        self.assertEqual(len(row.wave), len(doc.rows[0].wave))

    def test_format_keeps_unsupported_fields(self):
        doc = WaveDocument()
        doc.load_dict(self.GROUP_DOC)
        text = doc.to_json_text()
        parsed = WaveDocument.parse_json_text(text)
        self.assertEqual(parsed, doc.dump_dict())
        # A formatted dump is stable and loses nothing.
        self.assertEqual(parsed["signal"][1][0], "Master")
        self.assertEqual(parsed["signal"][2], {})
        # Re-applying the formatted text keeps the group structure intact.
        doc.apply_json_text(text)
        self.assertEqual(doc.dump_dict()["signal"], self.GROUP_DOC["signal"])



class SettingsTests(unittest.TestCase):
    def test_settings_roundtrip_and_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            settings = Settings(path)
            settings.set("language", "zh", save=True)
            settings.set("editor_font_size", 12.0, save=True)
            settings.add_recent(str(Path(tmp) / "demo.json"))
            loaded = Settings(path)
            self.assertEqual(loaded.get("language"), "zh")
            self.assertEqual(loaded.get("editor_font_size"), 12.0)
            self.assertIn("demo.json", loaded.get("recent_files")[0])

    def test_shortcut_defaults_and_conflicts(self):
        registry = ShortcutRegistry()
        mapping = registry.normalize_mapping(registry.defaults())
        self.assertIn("Ctrl+N", mapping["new"])
        self.assertIn("Ctrl+Shift+Z", mapping["redo"])
        self.assertIn("Ctrl+Del", mapping["row_delete"])
        self.assertEqual(ShortcutRegistry.conflicts(mapping), [])
        conflict = mapping.copy()
        conflict["save"] = ["Ctrl+N"]
        self.assertTrue(ShortcutRegistry.conflicts(conflict))

    def test_shortcut_disable(self):
        registry = ShortcutRegistry()
        resolved = registry.resolve({"new": [], "save": ["Ctrl+Shift+S"]})
        self.assertEqual(resolved["new"], [])
        self.assertEqual(resolved["save"], ["Ctrl+Shift+S"])


if __name__ == "__main__":
    unittest.main()
