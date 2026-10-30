# coding=utf-8
"""Dialog windows for preferences, shortcuts, help and advanced editing."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .shortcuts import CATEGORY_ORDER, CATEGORY_ZH, ShortcutRegistry
from .theme import Theme


class ShortcutEdit(QLineEdit):
    sequencesChanged = Signal(list)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Press a shortcut…")
        self.setClearButtonEnabled(False)
        self._sequences: list[str] = []
        self.setToolTip("Press a key combination. Backspace removes the last one, Delete clears.")

    def sequences(self) -> list[str]:
        return list(self._sequences)

    def set_sequences(self, values) -> None:
        self._sequences = [str(v) for v in values if str(v).strip()]
        self.setText(", ".join(QKeySequence(seq).toString(QKeySequence.NativeText) for seq in self._sequences))

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            event.accept()
            return
        if key == Qt.Key_Escape:
            self.clearFocus()
            event.accept()
            return
        if key == Qt.Key_Delete:
            self._sequences.clear()
            self._publish()
            event.accept()
            return
        if key == Qt.Key_Backspace:
            if self._sequences:
                self._sequences.pop()
                self._publish()
            event.accept()
            return
        try:
            sequence = QKeySequence(event.keyCombination()).toString(QKeySequence.PortableText)
        except Exception:
            sequence = ""
        if not sequence:
            event.accept()
            return
        normalized = ShortcutRegistry.normalize_sequence(sequence)
        if not normalized:
            event.accept()
            return
        if normalized in self._sequences:
            event.accept()
            return
        if len(self._sequences) >= 2:
            self._sequences[-1] = normalized
        else:
            self._sequences.append(normalized)
        self._publish()
        event.accept()

    def _publish(self) -> None:
        display = ", ".join(QKeySequence(seq).toString(QKeySequence.NativeText) for seq in self._sequences)
        self.setText(display)
        self.sequencesChanged.emit(list(self._sequences))


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent,
        *,
        settings,
        registry: ShortcutRegistry,
        shortcut_map: dict[str, list[str]],
        language: str = "en",
        tab_index: int = 0,
    ):
        super().__init__(parent)
        self.settings = settings
        self.registry = registry
        self.shortcut_map = {k: list(v) for k, v in shortcut_map.items()}
        self.language = language
        self.setWindowTitle("Preferences" if language != "zh" else "首选项")
        self.resize(820, 610)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        self.tabs = tabs
        layout.addWidget(tabs, 1)
        tabs.addTab(self._general_tab(), "General" if language != "zh" else "常规")
        tabs.addTab(self._shortcut_tab(), "Shortcuts" if language != "zh" else "快捷键")
        tabs.setCurrentIndex(1 if tab_index else 0)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Save" if language != "zh" else "保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消" if language == "zh" else "Cancel")
        reset = QPushButton("Reset defaults" if language != "zh" else "恢复默认")
        reset.clicked.connect(self._reset_all)
        buttons.addButton(reset, QDialogButtonBox.ResetRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def _general_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("中文", "zh")
        self.language_combo.setCurrentIndex(0 if self.language != "zh" else 1)
        form.addRow("Language / 语言", self.language_combo)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Follow system", "auto")
        theme = self.settings.get("theme", "light")
        index = max(0, self.theme_combo.findData(theme))
        self.theme_combo.setCurrentIndex(index)
        form.addRow("Theme", self.theme_combo)
        layout.addLayout(form)

        behaviour = QGroupBox("Behaviour")
        blayout = QVBoxLayout(behaviour)
        self.auto_clocks = QCheckBox("Automatically extend clk/clock lanes to the longest signal")
        self.auto_clocks.setChecked(bool(self.settings.get("auto_extend_clocks", True)))
        self.auto_advance = QCheckBox(
            "After typing any waveform character, jump to the next cycle "
            "(even when the character is unchanged)"
        )
        self.auto_advance.setChecked(bool(self.settings.get("auto_advance_cell", True)))
        self.live_sync = QCheckBox("Apply valid JSON to the waveform while typing")
        self.live_sync.setChecked(bool(self.settings.get("live_json_sync", True)))
        self.link_skin = QCheckBox("Use the dark WaveDrom skin when the dark theme is active")
        self.link_skin.setChecked(bool(self.settings.get("link_wave_skin_to_theme", True)))
        self.show_help = QCheckBox("Show quick help on startup")
        self.show_help.setChecked(bool(self.settings.get("show_shortcut_help_on_start", False)))
        blayout.addWidget(self.auto_clocks)
        blayout.addWidget(self.auto_advance)
        blayout.addWidget(self.live_sync)
        blayout.addWidget(self.link_skin)
        blayout.addWidget(self.show_help)
        layout.addWidget(behaviour)

        editor_box = QGroupBox("Editor")
        eform = QFormLayout(editor_box)
        self.editor_wrap = QCheckBox("Word wrap")
        self.editor_wrap.setChecked(bool(self.settings.get("editor_wrap", False)))
        eform.addRow(self.editor_wrap)
        self.font_size = QDoubleSpinBox()
        self.font_size.setRange(8.0, 20.0)
        self.font_size.setSingleStep(0.5)
        self.font_size.setValue(float(self.settings.get("editor_font_size", 10.5)))
        eform.addRow("Font size", self.font_size)
        self.indent = QSpinBox()
        self.indent.setRange(1, 8)
        self.indent.setValue(int(self.settings.get("editor_indent", 2)))
        eform.addRow("Indent spaces", self.indent)
        self.json_indent = QSpinBox()
        self.json_indent.setRange(0, 8)
        self.json_indent.setValue(int(self.settings.get("json_indent", 2)))
        eform.addRow("JSON output indent", self.json_indent)
        layout.addWidget(editor_box)
        layout.addStretch(1)
        return page

    def _shortcut_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search actions…")
        self.search.setClearButtonEnabled(True)
        self.category = QComboBox()
        self.category.addItem("All categories", "")
        for category in CATEGORY_ORDER:
            self.category.addItem(CATEGORY_ZH.get(category, category) if self.language == "zh" else category, category)
        top.addWidget(self.search, 1)
        top.addWidget(self.category)
        layout.addLayout(top)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            ["Action", "Category", "Shortcut"] if self.language != "zh" else ["操作", "分类", "快捷键"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        editor_row = QHBoxLayout()
        editor_row.addWidget(QLabel("Shortcut"))
        self.shortcut_edit = ShortcutEdit()
        self.shortcut_edit.sequencesChanged.connect(self._on_shortcut_edited)
        editor_row.addWidget(self.shortcut_edit, 1)
        self.reset_one = QPushButton("Reset")
        self.reset_one.clicked.connect(self._reset_selected)
        editor_row.addWidget(self.reset_one)
        layout.addLayout(editor_row)
        self.conflict_label = QLabel("")
        self.conflict_label.setObjectName("Muted")
        self.conflict_label.setWordWrap(True)
        layout.addWidget(self.conflict_label)
        hint = QLabel(
            "Click an action, then press up to two key combinations. Backspace removes the last one, Delete clears all. "
            "Changes are applied when you save."
            if self.language != "zh"
            else "选择操作后按最多两个快捷键；Backspace 删除最后一个，Delete 清空。保存后立即生效。"
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.search.textChanged.connect(self._filter)
        self.category.currentIndexChanged.connect(self._filter)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self._populate()
        return page

    # ------------------------------------------------------------------
    def _populate(self) -> None:
        selected_id = self._selected_action_id()
        self.table.setRowCount(0)
        rows = []
        query = self.search.text().strip().lower()
        category = self.category.currentData() or ""
        for action in self.registry.actions.values():
            if category and action.category != category:
                continue
            haystack = " ".join((action.label, action.label_zh, action.id, action.category)).lower()
            if query and query not in haystack:
                continue
            rows.append(action)
        self.table.setRowCount(len(rows))
        for row, action in enumerate(rows):
            item = QTableWidgetItem(action.localized(self.language))
            item.setData(Qt.UserRole, action.id)
            item.setToolTip(action.description)
            self.table.setItem(row, 0, item)
            category_text = CATEGORY_ZH.get(action.category, action.category) if self.language == "zh" else action.category
            self.table.setItem(row, 1, QTableWidgetItem(category_text))
            sequences = self.shortcut_map.get(action.id, [])
            display = ", ".join(QKeySequence(seq).toString(QKeySequence.NativeText) for seq in sequences) or "—"
            self.table.setItem(row, 2, QTableWidgetItem(display))
        if selected_id:
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0).data(Qt.UserRole) == selected_id:
                    self.table.selectRow(row)
                    break
        self._update_conflicts()

    def _selected_action_id(self) -> str | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return item.data(Qt.UserRole) if item else None

    def _selection_changed(self) -> None:
        action_id = self._selected_action_id()
        if not action_id:
            self.shortcut_edit.set_sequences([])
            self.shortcut_edit.setEnabled(False)
            return
        self.shortcut_edit.setEnabled(True)
        self.shortcut_edit.set_sequences(self.shortcut_map.get(action_id, []))

    def _on_shortcut_edited(self, sequences: list[str]) -> None:
        action_id = self._selected_action_id()
        if not action_id:
            return
        self.shortcut_map[action_id] = list(sequences)
        row = self.table.currentRow()
        if row >= 0:
            display = ", ".join(QKeySequence(seq).toString(QKeySequence.NativeText) for seq in sequences) or "—"
            self.table.item(row, 2).setText(display)
        self._update_conflicts()

    def _filter(self) -> None:
        self._populate()

    def _update_conflicts(self) -> None:
        conflicts = ShortcutRegistry.conflicts(self.shortcut_map, self.language)
        if not conflicts:
            self.conflict_label.setText("No conflicting shortcuts" if self.language != "zh" else "没有冲突的快捷键")
            self.conflict_label.setStyleSheet("")
            return
        parts = []
        for seq, ids in conflicts[:8]:
            labels = ", ".join(self.registry.label(i, self.language) for i in ids)
            parts.append(f"{QKeySequence(seq).toString(QKeySequence.NativeText)}: {labels}")
        prefix = "Conflicts" if self.language != "zh" else "快捷键冲突"
        self.conflict_label.setText(prefix + " — " + "; ".join(parts))
        self.conflict_label.setStyleSheet("color: #dc2626;")

    def _reset_selected(self) -> None:
        action_id = self._selected_action_id()
        if not action_id:
            return
        action = self.registry.action(action_id)
        if action:
            self.shortcut_map[action_id] = list(action.default)
            self.shortcut_edit.set_sequences(self.shortcut_map[action_id])
            self._populate()

    def _reset_all(self) -> None:
        self.shortcut_map = self.registry.defaults()
        self.auto_clocks.setChecked(True)
        self.auto_advance.setChecked(True)
        self.live_sync.setChecked(True)
        self.link_skin.setChecked(True)
        self.show_help.setChecked(False)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData("light")))
        self.editor_wrap.setChecked(False)
        self.font_size.setValue(10.5)
        self.indent.setValue(2)
        self.json_indent.setValue(2)
        self._populate()

    # ------------------------------------------------------------------
    def values(self) -> dict:
        return {
            "language": self.language_combo.currentData(),
            "theme": self.theme_combo.currentData(),
            "auto_extend_clocks": self.auto_clocks.isChecked(),
            "auto_advance_cell": self.auto_advance.isChecked(),
            "live_json_sync": self.live_sync.isChecked(),
            "link_wave_skin_to_theme": self.link_skin.isChecked(),
            "show_shortcut_help_on_start": self.show_help.isChecked(),
            "editor_wrap": self.editor_wrap.isChecked(),
            "editor_font_size": self.font_size.value(),
            "editor_indent": self.indent.value(),
            "json_indent": self.json_indent.value(),
            "shortcuts": ShortcutRegistry.normalize_mapping(self.shortcut_map),
        }


class ShortcutHelpDialog(QDialog):
    def __init__(
        self,
        parent,
        *,
        registry: ShortcutRegistry,
        shortcut_map: dict[str, list[str]],
        language: str = "en",
    ):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts" if language != "zh" else "快捷键与帮助")
        self.resize(780, 650)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(_shortcuts_html(registry, shortcut_map, language))
        tabs.addTab(browser, "Shortcuts" if language != "zh" else "快捷键")
        chars = QTextBrowser()
        chars.setHtml(_characters_html(language))
        tabs.addTab(chars, "Wave Characters" if language != "zh" else "波形字符")
        gestures = QTextBrowser()
        gestures.setHtml(_gestures_html(language))
        tabs.addTab(gestures, "Mouse && Workflow" if language != "zh" else "鼠标与流程")
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("Close" if language != "zh" else "关闭")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class RowPropertiesDialog(QDialog):
    def __init__(self, parent, row, *, language: str = "en"):
        super().__init__(parent)
        self.row = row
        self.setWindowTitle("Signal Properties" if language != "zh" else "信号属性")
        self.resize(620, 440)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(9)
        self.name = QLineEdit(row.name)
        self.wave = QLineEdit(row.wave)
        self.wave.setFont(self.wave.font())
        self.data = QPlainTextEdit("\n".join(row.data_items()))
        self.data.setPlaceholderText("head\nbody\ntail" if language != "zh" else "head\nbody\ntail")
        self.data.setFixedHeight(72)
        self.node = QLineEdit(row.node)

        timing = QGroupBox("Timing (rarely used)" if language != "zh" else "时序（不常用）")
        timing_form = QFormLayout(timing)
        self.period = QSpinBox()
        self.period.setRange(1, 99)
        self.period.setValue(row.period)
        self.period.setToolTip(
            "WaveDrom multiplies every wave character by this width"
            if language != "zh"
            else "WaveDrom 会将每个波形字符的宽度乘以该值"
        )
        self.phase = QDoubleSpinBox()
        self.phase.setRange(0.0, 99.0)
        self.phase.setSingleStep(0.25)
        self.phase.setDecimals(2)
        self.phase.setValue(row.phase)
        self.phase.setToolTip(
            "Horizontal shift in time slots (0.5 = one half cycle)"
            if language != "zh"
            else "以时间槽为单位的水平偏移（0.5 表示半个周期）"
        )
        timing_form.addRow("Period", self.period)
        timing_form.addRow("Phase", self.phase)

        form.addRow("Name", self.name)
        form.addRow("Wave", self.wave)
        form.addRow("Data labels (one per line)", self.data)
        form.addRow("Node annotations", self.node)
        layout.addLayout(form)
        layout.addWidget(timing)
        note = QLabel(
            "Wave characters follow WaveDrom: 0 1 x z = u d p P n N l L h H | . < > "
            "Period multiplies the width of each character; phase is in time slots."
            if language != "zh"
            else "波形字符遵循 WaveDrom：0 1 x z = u d p P n N l L h H | . < > "
            "Period 表示每个字符占用的时间槽数量，Phase 以时间槽为单位。"
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Apply" if language != "zh" else "应用")
        buttons.button(QDialogButtonBox.Cancel).setText("取消" if language == "zh" else "Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        labels = [line.strip() for line in self.data.toPlainText().splitlines() if line.strip()]
        return {
            "name": self.name.text(),
            "wave": self.wave.text(),
            "data": labels,
            "node": self.node.text(),
            "period": self.period.value(),
            "phase": self.phase.value(),
        }


class DiagramSettingsDialog(QDialog):
    """GUI editor for ``config``, ``head`` and ``foot``."""

    def __init__(self, parent, doc, *, language: str = "en"):
        super().__init__(parent)
        self.doc = doc
        self.language = language
        self.setWindowTitle("Diagram Settings" if language != "zh" else "波形图设置")
        self.resize(560, 620)
        layout = QVBoxLayout(self)

        config_box = QGroupBox("Diagram" if language != "zh" else "波形图")
        config_form = QFormLayout(config_box)
        self.skin = QComboBox()
        from .skins import available_skins

        for skin in available_skins():
            self.skin.addItem(skin, skin)
        index = self.skin.findData(doc.skin_name())
        self.skin.setCurrentIndex(max(0, index))
        self.hscale = QSpinBox()
        self.hscale.setRange(1, 20)
        self.hscale.setValue(max(1, int(doc.hscale())))
        self.hscale.setToolTip("Horizontal scale of the diagram")
        config_form.addRow("Skin", self.skin)
        config_form.addRow("Horizontal scale (hscale)", self.hscale)
        layout.addWidget(config_box)

        head = doc.head
        foot = doc.foot
        head_box = QGroupBox("Head (above the diagram)" if language != "zh" else "头部（波形上方）")
        head_form = QFormLayout(head_box)
        self.head_text = QLineEdit(_text_value(head.get("text")))
        self.head_tick = QLineEdit(_tick_text(head.get("tick")))
        self.head_tock = QLineEdit(_tick_text(head.get("tock")))
        self.head_tick.setPlaceholderText("0 or 1 2 3")
        self.head_tock.setPlaceholderText("0.5 or 1 2 3")
        self.head_every = QSpinBox()
        self.head_every.setRange(1, 99)
        self.head_every.setValue(_every_value(head))
        head_form.addRow("Text", self.head_text)
        head_form.addRow("Tick labels", self.head_tick)
        head_form.addRow("Tock labels", self.head_tock)
        head_form.addRow("Every N cycles", self.head_every)
        layout.addWidget(head_box)

        foot_box = QGroupBox("Foot (below the diagram)" if language != "zh" else "尾部（波形下方）")
        foot_form = QFormLayout(foot_box)
        self.foot_text = QLineEdit(_text_value(foot.get("text")))
        self.foot_tick = QLineEdit(_tick_text(foot.get("tick")))
        self.foot_tock = QLineEdit(_tick_text(foot.get("tock")))
        self.foot_tick.setPlaceholderText("0 or 1 2 3")
        self.foot_tock.setPlaceholderText("0.5 or 1 2 3")
        self.foot_every = QSpinBox()
        self.foot_every.setRange(1, 99)
        self.foot_every.setValue(_every_value(foot))
        foot_form.addRow("Text", self.foot_text)
        foot_form.addRow("Tick labels", self.foot_tick)
        foot_form.addRow("Tock labels", self.foot_tock)
        foot_form.addRow("Every N cycles", self.foot_every)
        layout.addWidget(foot_box)

        note = QLabel(
            "Tick/tock accept a number, a start value or a list of labels. "
            "Rich JSONML text (arrays of tspan objects) is preserved when the text field is left unchanged."
            if language != "zh"
            else "Tick/tock 可填数字、起始值或标签列表。"
            "如果文本字段未修改，原有的 JSONML 富文本（tspan 数组）会被保留。"
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Apply" if language != "zh" else "应用")
        buttons.button(QDialogButtonBox.Cancel).setText("取消" if language == "zh" else "Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        head = _section_values(
            self.head_text,
            self.head_tick,
            self.head_tock,
            self.head_every,
            self.doc.head,
        )
        foot = _section_values(
            self.foot_text,
            self.foot_tick,
            self.foot_tock,
            self.foot_every,
            self.doc.foot,
        )
        return {
            "skin": self.skin.currentData(),
            "hscale": self.hscale.value(),
            "head": head,
            "foot": foot,
        }


def _text_value(value) -> str:
    """Flatten WaveDrom JSONML text into a plain string for a line edit."""
    return _text_value_raw(value).strip()


def _text_value_raw(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return "".join(_text_value_raw(item) for item in value[1:])
    if isinstance(value, dict):
        return ""
    return str(value)


def _tick_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value)
    return str(value)


def _every_value(section: dict) -> int:
    try:
        return max(1, int(section.get("every", 1)))
    except (TypeError, ValueError):
        return 1


def _parse_tick(text: str):
    text = (text or "").strip()
    if not text:
        return None
    parts = text.replace(",", " ").split()
    values = []
    for part in parts:
        try:
            number = float(part)
        except ValueError:
            return text
        values.append(int(number) if number.is_integer() else number)
    if len(values) == 1:
        return values[0]
    return values


def _section_values(text_edit, tick_edit, tock_edit, every_spin, original: dict) -> dict:
    values: dict = {}
    original_text = _text_value(original.get("text"))
    new_text = text_edit.text().strip()
    if new_text:
        if isinstance(original.get("text"), (list, tuple)) and new_text == original_text:
            values["text"] = original["text"]
        else:
            values["text"] = new_text
    for key, edit in (("tick", tick_edit), ("tock", tock_edit)):
        parsed = _parse_tick(edit.text())
        if parsed is not None:
            values[key] = parsed
    if ("tick" in values or "tock" in values) and every_spin.value() > 1:
        values["every"] = every_spin.value()
    return values



class RelationDialog(QDialog):
    def __init__(self, parent, doc, *, language: str = "en"):
        super().__init__(parent)
        self.doc = doc
        self.language = language
        self.setWindowTitle("Relation Editor" if language != "zh" else "关系标注")
        self.resize(760, 440)
        layout = QVBoxLayout(self)
        nodes = ", ".join(sorted(doc.node_markers().keys())) or "—"
        info = QLabel(
            f"Available nodes: {nodes}\nUse the Node tool to place single-character markers on waveform cells."
            if language != "zh"
            else f"可用节点：{nodes}\n使用节点工具在波形单元格上放置单字符标记。"
        )
        info.setObjectName("Muted")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["From", "Shape", "To", "Label"] if language != "zh" else ["起点", "样式", "终点", "标签"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)
        row_buttons = QHBoxLayout()
        add = QPushButton("Add edge" if language != "zh" else "添加关系")
        remove = QPushButton("Remove edge" if language != "zh" else "删除关系")
        add.clicked.connect(self._add_row)
        remove.clicked.connect(self._remove_row)
        row_buttons.addWidget(add)
        row_buttons.addWidget(remove)
        row_buttons.addStretch(1)
        layout.addLayout(row_buttons)
        hint = QLabel(
            "Shapes: ~ -~ <~> ~> -~> ~-> - -| -|- <-> <-|> <-|-> -> -|> -|-> |-> +"
            if language != "zh"
            else "样式：~ -~ <~> ~> -~> ~-> - -| -|- <-> <-|> <-|-> -> -|> -|-> |-> +"
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for edge in doc.edges:
            if not isinstance(edge, str):
                continue
            head, _, label = edge.partition(" ")
            if len(head) < 2:
                continue
            self._append(head[0], head[1:-1] or "-", head[-1], label)

    def _append(self, start: str, shape: str, end: str, label: str = "") -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(start))
        self.table.setItem(row, 1, QTableWidgetItem(shape))
        self.table.setItem(row, 2, QTableWidgetItem(end))
        self.table.setItem(row, 3, QTableWidgetItem(label))

    def _add_row(self) -> None:
        nodes = sorted(self.doc.node_markers().keys())
        self._append(nodes[0] if nodes else "", "~", nodes[-1] if nodes else "", "")

    def _remove_row(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def edges(self) -> list[str]:
        result: list[str] = []
        for row in range(self.table.rowCount()):
            start = (self.table.item(row, 0).text().strip() if self.table.item(row, 0) else "")
            shape = (self.table.item(row, 1).text().strip() if self.table.item(row, 1) else "-")
            end = (self.table.item(row, 2).text().strip() if self.table.item(row, 2) else "")
            label = (self.table.item(row, 3).text().strip() if self.table.item(row, 3) else "")
            if not start or not end:
                continue
            result.append(f"{start}{shape}{end}" + (f" {label}" if label else ""))
        return result


class AsciiDialog(QDialog):
    def __init__(self, parent, text: str, *, language: str = "en"):
        super().__init__(parent)
        self.setWindowTitle("ASCII Preview" if language != "zh" else "ASCII 预览")
        self.resize(820, 560)
        layout = QVBoxLayout(self)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setPlainText(text)
        from .theme import mono_font

        self.view.setFont(mono_font(10.5))
        layout.addWidget(self.view, 1)
        buttons = QHBoxLayout()
        copy = QPushButton("Copy" if language != "zh" else "复制")
        close = QPushButton("Close" if language != "zh" else "关闭")
        copy.clicked.connect(lambda: self._copy(text))
        close.clicked.connect(self.accept)
        buttons.addStretch(1)
        buttons.addWidget(copy)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _copy(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(text)


class AboutDialog(QDialog):
    def __init__(self, parent, theme: Theme, *, language: str = "en"):
        super().__init__(parent)
        self.setWindowTitle("About WaveDromGen" if language != "zh" else "关于 WaveDromGen")
        self.resize(520, 380)
        layout = QVBoxLayout(self)
        title = QLabel("WaveDromGen")
        title.setStyleSheet(f"font-size: 22pt; font-weight: 700; color: {theme.accent.name()};")
        layout.addWidget(title)
        version = QLabel(f"Version {__version__} · interactive WaveDrom-compatible editor")
        version.setObjectName("Muted")
        layout.addWidget(version)
        text = QTextBrowser()
        text.setOpenExternalLinks(True)
        text.setHtml(
            "<p>WaveDromGen is a GUI digital timing diagram editor. This version is a "
            "Qt rewrite with live JSON synchronisation, inline label editing, "
            "drag-and-drop signals, range selection, clock auto-extension and "
            "configurable shortcuts.</p>"
            "<p>The waveform geometry and skin symbols are derived from "
            "<a href='https://github.com/wavedrom/wavedrom'>WaveDrom</a> by Aliaksei Chapyzhenka, "
            "used under the MIT licence. Qt rendering and the application remain separate works.</p>"
            "<p><a href='https://wavedrom.com/tutorial.html'>WaveDrom tutorial</a> · "
            "<a href='https://github.com/blueyesess/wavedromgen'>Original repository</a></p>"
        )
        layout.addWidget(text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


# ----------------------------------------------------------------------
# Help HTML
# ----------------------------------------------------------------------
def _shortcuts_html(registry: ShortcutRegistry, mapping: dict[str, list[str]], language: str) -> str:
    rows = []
    for category in CATEGORY_ORDER:
        actions = [a for a in registry.actions.values() if a.category == category]
        if not actions:
            continue
        rows.append(f"<h3>{escape(CATEGORY_ZH.get(category, category) if language == 'zh' else category)}</h3>")
        rows.append("<table width='100%' cellspacing='0' cellpadding='4'>")
        for action in actions:
            seqs = mapping.get(action.id, [])
            keys = ", ".join(QKeySequence(seq).toString(QKeySequence.NativeText) for seq in seqs) or "—"
            rows.append(
                f"<tr><td width='45%'>{escape(action.localized(language))}</td>"
                f"<td style='color:#7a8494'>{escape(keys)}</td></tr>"
            )
        rows.append("</table>")
    body = "".join(rows)
    title = "Keyboard shortcuts" if language != "zh" else "键盘快捷键"
    note = (
        "Shortcuts are global unless noted. You can rebind every action in Preferences → Shortcuts."
        if language != "zh"
        else "大多数快捷键可全局使用；可在“首选项 → 快捷键”中重新绑定。"
    )
    return f"<h2>{title}</h2><p style='color:#7a8494'>{note}</p>{body}"


def _characters_html(language: str) -> str:
    return """
    <h2>WaveDrom wave characters</h2>
    <table cellspacing='0' cellpadding='5' width='100%'>
    <tr><th align='left'>Character</th><th align='left'>Meaning</th><th align='left'>Example</th></tr>
    <tr><td><code>0</code> / <code>1</code></td><td>Low / high level</td><td><code>0..1..0.</code></td></tr>
    <tr><td><code>.</code></td><td>Continue the previous state</td><td><code>1....</code></td></tr>
    <tr><td><code>x</code></td><td>Unknown / don't care</td><td><code>x...</code></td></tr>
    <tr><td><code>z</code></td><td>High impedance</td><td><code>z...</code></td></tr>
    <tr><td><code>=</code></td><td>Data bus; consumes the next <code>data</code> label</td><td><code>x.==.=x</code></td></tr>
    <tr><td><code>2</code>…<code>9</code></td><td>Data bus with a WaveDrom colour</td><td><code>x.345x</code></td></tr>
    <tr><td><code>p</code> / <code>P</code></td><td>Positive-edge clock; <code>P</code> adds an edge marker</td><td><code>p.......</code></td></tr>
    <tr><td><code>n</code> / <code>N</code></td><td>Negative-edge clock; <code>N</code> adds an edge marker</td><td><code>n.......</code></td></tr>
    <tr><td><code>l</code> / <code>L</code></td><td>Low phase of a clock; <code>L</code> adds a marker</td><td><code>l.......</code></td></tr>
    <tr><td><code>h</code> / <code>H</code></td><td>High phase of a clock; <code>H</code> adds a marker</td><td><code>h.......</code></td></tr>
    <tr><td><code>u</code> / <code>d</code></td><td>Bus with an up/down transition</td><td><code>x.ud.x</code></td></tr>
    <tr><td><code>|</code></td><td>Waveform gap marker</td><td><code>p.....|...</code></td></tr>
    <tr><td><code>&lt;</code> / <code>&gt;</code></td><td>Sub-cycle (sharp) transitions</td><td><code>0&lt;1&gt;0</code></td></tr>
    </table>
    <h3>Editing a range</h3>
    <p>Drag across cells to select a rectangle, then type any wave character. The character is written
    to every selected cell. <b>Delete</b> removes the selected cycles (the rest of the lane shifts left),
    <b>Shift+Delete</b> sets them to <code>.</code>, and <b>Ctrl+Shift+←/→</b> inserts one cycle before/after
    the selection. <b>Copy Cells</b> / <b>Paste Cells</b> move the whole rectangular block: a copied
    3×2 block is pasted as a 3×2 block, and pasting a single row into one cell fills several cycles.</p>
    <h3>Waveform palette</h3>
    <p>The palette above the canvas has one button per common wave character
    (<code>0 1 x . z = 2 3 4 5 p n u d h l</code>), insert-cycle-left/right, delete-cycle and empty-row
    buttons. Clicking a character writes it to the current selection, exactly like typing it.</p>
    <h3>Insert mode</h3>
    <p>Click the middle mouse button on a waveform cell to toggle insert mode, or use the <b>INS</b> palette
    button. Every character you type is inserted at the caret and the rest of the lane is pushed right; a
    vertical caret marks the insertion column. Press <b>Esc</b> or click the middle mouse button again to
    leave insert mode. Drag with the middle mouse button in the gutter (or over the waveform) to select
    several lanes; insert mode then inserts the character into every selected lane at once.</p>
    <h3>Clocks</h3>
    <p>Signals whose name contains <code>clk</code> or <code>clock</code> automatically follow the longest
    signal: they are extended <i>and</i> shortened. A clock is extended with <code>.</code>, so
    <code>p.......</code> stays a clock; rectangular <code>0</code>/<code>1</code> clocks repeat their pattern.</p>
    <h3>Empty rows and groups</h3>
    <p><code>{}</code> inserts an empty spacer row (Signal → Insert Empty Row). Select several signals and use
    <b>Ctrl+G</b> to wrap them in a named group; nested groups are preserved, and clicking a group bracket
    selects the whole group. <b>Ctrl+Shift+G</b> ungroups the selected group again.</p>
    """


def _gestures_html(language: str) -> str:
    return """
    <h2>Mouse & workflow</h2>
    <table cellspacing='0' cellpadding='5' width='100%'>
    <tr><th align='left'>Gesture</th><th align='left'>Action</th></tr>
    <tr><td>Double-click a name</td><td>Edit the signal name inline. <b>Enter</b> commits and opens the next signal name.</td></tr>
    <tr><td>Double-click a data label</td><td>Edit the bus label. <b>Tab</b> commits and opens the next data label.</td></tr>
    <tr><td>Double-click a group bracket</td><td>Rename the group.</td></tr>
    <tr><td>Click a group bracket</td><td>Select every signal of the group (Ctrl+click toggles, Shift+click extends).</td></tr>
    <tr><td>Drag in the left gutter</td><td>Reorder the selected signals; groups keep their nested structure.</td></tr>
    <tr><td>Drag on the waveform</td><td>Select a rectangular block of cells, including empty cycles to the right. Copy/paste moves the whole block.</td></tr>
    <tr><td>Middle click</td><td>Toggle insert mode at the clicked cell; the caret shows the insertion column.</td></tr>
    <tr><td>Middle drag</td><td>Select several signal rows and insert the typed characters into all of them.</td></tr>
    <tr><td>Type on a selection</td><td>Write a WaveDrom character to all selected cells (with auto-advance if enabled).</td></tr>
    <tr><td>Right-click</td><td>Context menu for labels, signals, groups and cells.</td></tr>
    <tr><td>Ctrl + mouse wheel</td><td>Zoom; Shift + wheel scrolls horizontally.</td></tr>
    <tr><td>Split view</td><td>Edit JSON and waveform simultaneously; valid JSON renders live and waveform edits update the JSON.</td></tr>
    </table>
    <h3>Useful defaults</h3>
    <p><b>Insert</b> inserts a signal above, <b>Ctrl+Insert</b> below, <b>Ctrl+Return</b> appends a signal and
    starts editing its name, <b>Ctrl+D</b> duplicates, <b>Ctrl+C / X / V</b> copy, cut and paste signals or whole
    groups, <b>Alt+↑/↓</b> moves a signal. <b>Delete</b> removes cycles, <b>Ctrl+Shift+←/→</b> inserts cycles.
    Press <b>F2</b> to edit a name or data label and <b>F1</b> for this help.</p>
    <h3>Tabs and live JSON</h3>
    <p>Every opened file gets its own tab (<b>Ctrl+Tab</b> / <b>Ctrl+Shift+Tab</b>, <b>Ctrl+W</b> closes) and the
    clipboard keeps whole groups, so signals can be copied between diagrams. The editor applies valid JSON after
    a short debounce; if the JSON is invalid the waveform keeps the last valid state and the error line is shown.</p>
    """
