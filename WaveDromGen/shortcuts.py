# coding=utf-8
"""Action registry and configurable keyboard shortcuts."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from PySide6.QtGui import QAction, QKeySequence


@dataclass(frozen=True)
class ActionDef:
    id: str
    label: str
    label_zh: str
    category: str
    default: tuple[str, ...] = ()
    description: str = ""
    scope: str = "app"  # app | canvas | editor

    def localized(self, language: str) -> str:
        return self.label_zh if language == "zh" else self.label


CATEGORY_ORDER = ("File", "Edit", "Signal", "View", "Tools", "Editor", "Help")
CATEGORY_ZH = {
    "File": "文件",
    "Edit": "编辑",
    "Signal": "信号",
    "View": "视图",
    "Tools": "工具",
    "Editor": "编辑器",
    "Help": "帮助",
}


ACTIONS: tuple[ActionDef, ...] = (
    # File
    ActionDef("new", "New", "新建", "File", ("Ctrl+N",), "Create a new diagram", "app"),
    ActionDef("open", "Open…", "打开…", "File", ("Ctrl+O",), "Open a WaveJSON file", "app"),
    ActionDef("save", "Save", "保存", "File", ("Ctrl+S",), "Save the current diagram", "app"),
    ActionDef("save_as", "Save As…", "另存为…", "File", ("Ctrl+Shift+S",), "Save to a new file", "app"),
    ActionDef("export_png", "Export PNG…", "导出 PNG…", "File", ("Ctrl+Shift+E",), "Export a PNG image", "app"),
    ActionDef("export_svg", "Export SVG…", "导出 SVG…", "File", ("Ctrl+Alt+E",), "Export an SVG image", "app"),
    ActionDef("copy_image", "Copy Diagram as Image", "复制波形图片", "File", ("Ctrl+Shift+I",), "Copy the rendered diagram", "app"),
    ActionDef("quit", "Quit", "退出", "File", ("Ctrl+Q",), "Close WaveDromGen", "app"),
    # Edit / rows and cells
    ActionDef("undo", "Undo", "撤销", "Edit", ("Ctrl+Z",), "Undo the last waveform edit", "app"),
    ActionDef("redo", "Redo", "重做", "Edit", ("Ctrl+Shift+Z", "Ctrl+Y"), "Redo the last edit", "app"),
    ActionDef("select_all", "Select All", "全选", "Edit", ("Ctrl+A",), "Select all cells or editor text", "app"),
    ActionDef("row_insert_above", "Insert Signal Above", "在上方插入信号", "Signal", ("Insert",), "Insert a blank signal above", "canvas"),
    ActionDef("row_insert_below", "Insert Signal Below", "在下方插入信号", "Signal", ("Ctrl+Insert",), "Insert a blank signal below", "canvas"),
    ActionDef("row_add", "Add Signal at End", "添加信号到末尾", "Signal", ("Ctrl+Return",), "Append a blank signal", "canvas"),
    ActionDef("row_duplicate", "Duplicate Signal", "复制信号", "Signal", ("Ctrl+D",), "Duplicate selected signals", "canvas"),
    ActionDef("row_copy", "Copy Signal", "复制波形", "Signal", ("Ctrl+C",), "Copy selected signals as WaveJSON", "canvas"),
    ActionDef("row_cut", "Cut Signal", "剪切波形", "Signal", ("Ctrl+X",), "Cut selected signals", "canvas"),
    ActionDef("row_paste", "Paste Signal", "粘贴波形", "Signal", ("Ctrl+V",), "Paste signals from the clipboard", "canvas"),
    ActionDef("row_delete", "Delete Signal", "删除信号", "Signal", ("Ctrl+Delete",), "Delete selected signals", "canvas"),
    ActionDef("row_move_up", "Move Signal Up", "上移信号", "Signal", ("Alt+Up",), "Move selected signals up", "canvas"),
    ActionDef("row_move_down", "Move Signal Down", "下移信号", "Signal", ("Alt+Down",), "Move selected signals down", "canvas"),
    ActionDef("row_properties", "Signal Properties…", "信号属性…", "Signal", ("Ctrl+Shift+P",), "Edit name, wave, period and phase", "app"),
    ActionDef("row_clear", "Clear Signal", "清空信号", "Signal", ("Ctrl+Shift+Delete",), "Clear the waveform and data of selected signals", "canvas"),
    ActionDef("cell_copy", "Copy Cells", "复制单元格", "Edit", ("Ctrl+Shift+C",), "Copy selected waveform characters", "canvas"),
    ActionDef("cell_paste", "Paste Cells", "粘贴单元格", "Edit", ("Ctrl+Shift+V",), "Paste waveform characters into the selection", "canvas"),
    ActionDef("clear_cells", "Clear Cells", "清除单元格", "Edit", ("Shift+Delete",), "Set selected cells to '.'", "canvas"),
    ActionDef("edit_active", "Edit Name / Data", "编辑名称/数据", "Edit", ("F2",), "Edit the active signal name or data label", "canvas"),
    ActionDef("edit_data", "Edit Data Label", "编辑数据标签", "Edit", ("Shift+F2",), "Edit the data label under the active cell", "canvas"),
    ActionDef("add_column", "Add Column", "添加列", "Signal", ("Alt+C",), "Append a time column", "app"),
    ActionDef("delete_column", "Delete Column", "删除列", "Signal", ("Alt+Shift+C",), "Delete the active time column", "app"),
    ActionDef("extend_clocks", "Extend Clocks to Longest", "时钟扩展到最长", "Signal", ("Alt+Shift+K",), "Stretch clk/clock lanes to the longest signal", "app"),
    # View
    ActionDef("view_wave", "Wave Only", "仅波形", "View", ("Ctrl+1",), "Show the waveform only", "app"),
    ActionDef("view_editor", "Editor Only", "仅编辑器", "View", ("Ctrl+2",), "Show the JSON editor only", "app"),
    ActionDef("view_stacked", "Split Top / Bottom", "上下分栏", "View", ("Ctrl+3",), "Wave above, editor below", "app"),
    ActionDef("view_side", "Split Left / Right", "左右分栏", "View", ("Ctrl+4",), "Wave left, editor right", "app"),
    ActionDef("zoom_in", "Zoom In", "放大", "View", ("Ctrl+=",), "Increase the waveform zoom", "app"),
    ActionDef("zoom_out", "Zoom Out", "缩小", "View", ("Ctrl+-",), "Decrease the waveform zoom", "app"),
    ActionDef("zoom_reset", "Reset Zoom", "重置缩放", "View", ("Ctrl+0",), "Reset zoom to 100%", "app"),
    ActionDef("fit_width", "Fit Width", "适应宽度", "View", ("Ctrl+Shift+0",), "Fit the whole diagram width", "app"),
    ActionDef("toggle_theme", "Toggle Dark Mode", "切换深色模式", "View", ("Ctrl+Shift+T",), "Switch light/dark theme", "app"),
    ActionDef("show_shortcuts", "Keyboard Shortcuts…", "快捷键设置…", "Tools", ("Ctrl+Shift+K",), "View and customise shortcuts", "app"),
    ActionDef("settings", "Preferences…", "首选项…", "Tools", ("Ctrl+,",), "Open application settings", "app"),
    # Tools
    ActionDef("tool_select", "Select", "选择", "Tools", ("Alt+V",), "Select cells and edit labels", "canvas"),
    ActionDef("tool_clk", "Clock", "时钟", "Tools", ("Alt+K",), "Draw / cycle a clock edge", "canvas"),
    ActionDef("tool_sig", "Signal", "信号", "Tools", ("Alt+S",), "Draw a single-bit signal", "canvas"),
    ActionDef("tool_bus", "Bus", "总线", "Tools", ("Alt+B",), "Draw a bus segment", "canvas"),
    ActionDef("tool_x", "Unknown", "未知态", "Tools", ("Alt+X",), "Draw an unknown (x) region", "canvas"),
    ActionDef("tool_z", "High-Z", "高阻", "Tools", ("Alt+Z",), "Draw a high-impedance region", "canvas"),
    ActionDef("tool_gap", "Gap", "间隔", "Tools", ("Alt+G",), "Draw a waveform gap", "canvas"),
    ActionDef("tool_text", "Text", "文字", "Tools", ("Alt+T",), "Edit a name or data label", "canvas"),
    ActionDef("tool_clear", "Clear", "清除", "Tools", ("Alt+E",), "Clear waveform cells", "canvas"),
    ActionDef("tool_node", "Node", "节点", "Tools", ("Alt+O",), "Annotate a node for relations", "canvas"),
    ActionDef("relations", "Relation Editor…", "关系标注…", "Tools", ("Ctrl+R",), "Edit edge labels between nodes", "app"),
    ActionDef("ascii_preview", "ASCII Preview…", "ASCII 预览…", "Tools", ("Alt+A",), "Show an ASCII rendering", "app"),
    ActionDef("copy_ascii", "Copy ASCII", "复制 ASCII", "Tools", (), "Copy the ASCII rendering", "app"),
    ActionDef("toggle_live", "Toggle Live JSON Sync", "切换实时同步", "Tools", ("Ctrl+Shift+L",), "Apply JSON as you type", "app"),
    ActionDef("format_json", "Format JSON", "格式化 JSON", "Editor", ("Ctrl+Shift+F",), "Pretty-print the JSON text", "editor"),
    ActionDef("find", "Find", "查找", "Editor", ("Ctrl+F",), "Find text in the JSON editor", "editor"),
    ActionDef("replace", "Replace", "替换", "Editor", ("Ctrl+H",), "Find and replace in the JSON editor", "editor"),
    ActionDef("help", "Quick Help", "快速帮助", "Help", ("F1",), "Show gestures, waveform characters and shortcuts", "app"),
)


class ShortcutRegistry:
    def __init__(self):
        self.actions: OrderedDict[str, ActionDef] = OrderedDict((a.id, a) for a in ACTIONS)
        self.by_category: OrderedDict[str, list[ActionDef]] = OrderedDict()
        for action in ACTIONS:
            self.by_category.setdefault(action.category, []).append(action)

    # ------------------------------------------------------------------
    def defaults(self) -> dict[str, list[str]]:
        return {action.id: list(action.default) for action in ACTIONS}

    def resolve(self, stored: dict | None) -> dict[str, list[str]]:
        """Merge stored user shortcuts with defaults.

        An explicitly empty list in the settings disables a shortcut.
        """
        mapping = self.defaults()
        if isinstance(stored, dict):
            for action_id, values in stored.items():
                if action_id not in self.actions:
                    continue
                if values is None:
                    mapping[action_id] = []
                elif isinstance(values, str):
                    mapping[action_id] = [v.strip() for v in values.split(",") if v.strip()]
                elif isinstance(values, (list, tuple)):
                    mapping[action_id] = [str(v).strip() for v in values if str(v).strip()]
                else:
                    mapping[action_id] = []
        return mapping

    def action(self, action_id: str) -> ActionDef | None:
        return self.actions.get(action_id)

    def label(self, action_id: str, language: str = "en") -> str:
        action = self.actions.get(action_id)
        return action.localized(language) if action else action_id

    # ------------------------------------------------------------------
    @staticmethod
    def normalize_sequence(sequence: str) -> str:
        text = (sequence or "").strip()
        if not text:
            return ""
        key = QKeySequence(text)
        if not key.isEmpty():
            return key.toString(QKeySequence.PortableText)
        parts = [p.strip() for p in text.split("+")]
        result: list[str] = []
        for part in parts:
            if part.lower() in ("ctrl", "control"):
                result.append("Ctrl")
            elif part.lower() == "shift":
                result.append("Shift")
            elif part.lower() == "alt":
                result.append("Alt")
            elif part.lower() == "meta":
                result.append("Meta")
            elif part in ("Return", "Enter"):
                result.append("Return")
            elif part in ("Escape", "Esc"):
                result.append("Esc")
            elif part in ("Del", "Delete"):
                result.append("Del")
            elif part in ("Ins", "Insert"):
                result.append("Ins")
            elif len(part) == 1:
                result.append(part.upper())
            elif part:
                result.append(part)
        return "+".join(result)

    @classmethod
    def normalize_mapping(cls, mapping: dict[str, list[str]]) -> dict[str, list[str]]:
        return {
            key: [cls.normalize_sequence(seq) for seq in values if cls.normalize_sequence(seq)]
            for key, values in mapping.items()
        }

    @classmethod
    def conflicts(cls, mapping: dict[str, list[str]], language: str = "en") -> list[tuple[str, list[str]]]:
        owners: dict[str, list[str]] = {}
        for action_id, sequences in mapping.items():
            for seq in sequences:
                if not seq:
                    continue
                owners.setdefault(seq, []).append(action_id)
        return [(seq, ids) for seq, ids in owners.items() if len(ids) > 1]


def apply_to_actions(
    actions: dict[str, QAction],
    mapping: dict[str, list[str]],
) -> None:
    normalized = ShortcutRegistry.normalize_mapping(mapping)
    for action_id, action in actions.items():
        sequences = normalized.get(action_id, [])
        action.setShortcuts([QKeySequence(seq) for seq in sequences if seq])
