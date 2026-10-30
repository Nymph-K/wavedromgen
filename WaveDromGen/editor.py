# coding=utf-8
"""Lightweight JSON editor with line numbers, highlighting and live sync."""
from __future__ import annotations

import re

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFontMetricsF,
    QKeyEvent,
    QPainter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .icons import make_icon
from .theme import Theme, mono_font


class JsonHighlighter:
    """QSyntaxHighlighter is mixed in lazily to keep imports simple."""

    def __new__(cls, document, theme: Theme):
        from PySide6.QtGui import QSyntaxHighlighter

        class _Highlighter(QSyntaxHighlighter):
            def __init__(self, doc):
                super().__init__(doc)
                self.theme = theme
                self._build()

            def _build(self):
                t = self.theme

                def fmt(color: QColor, *, bold=False, italic=False) -> QTextCharFormat:
                    out = QTextCharFormat()
                    out.setForeground(color)
                    if bold:
                        out.setFontWeight(700)
                    if italic:
                        out.setFontItalic(True)
                    return out

                self.formats = {
                    "key": fmt(t.editor_key, bold=True),
                    "string": fmt(t.editor_string),
                    "number": fmt(t.editor_number),
                    "keyword": fmt(t.editor_keyword),
                    "punct": fmt(t.editor_punct),
                    "comment": fmt(t.editor_comment, italic=True),
                }

            def set_theme(self, theme: Theme):
                self.theme = theme
                self._build()
                self.rehighlight()

            def highlightBlock(self, text: str) -> None:
                # Comments first so strings inside comments are not coloured.
                for m in re.finditer(r"//[^\n]*", text):
                    self.setFormat(m.start(), m.end() - m.start(), self.formats["comment"])
                # Multi-line /* ... */ comments.
                start = 0
                if self.previousBlockState() == 1:
                    end = text.find("*/")
                    if end < 0:
                        self.setFormat(0, len(text), self.formats["comment"])
                        self.setCurrentBlockState(1)
                        return
                    self.setFormat(0, end + 2, self.formats["comment"])
                    start = end + 2
                    self.setCurrentBlockState(0)
                while start < len(text):
                    begin = text.find("/*", start)
                    if begin < 0:
                        break
                    end = text.find("*/", begin + 2)
                    if end < 0:
                        self.setFormat(begin, len(text) - begin, self.formats["comment"])
                        self.setCurrentBlockState(1)
                        break
                    self.setFormat(begin, end + 2 - begin, self.formats["comment"])
                    start = end + 2

                for m in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', text):
                    # Don't paint strings that fall inside a comment.
                    if self.format(m.start()).foreground().color() == self.formats["comment"].foreground().color():
                        continue
                    self.setFormat(m.start(), m.end() - m.start(), self.formats["string"])
                    tail = text[m.end():]
                    if re.match(r"\s*:", tail):
                        self.setFormat(m.start(), m.end() - m.start(), self.formats["key"])
                for m in re.finditer(r"(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text):
                    self.setFormat(m.start(), m.end() - m.start(), self.formats["number"])
                for m in re.finditer(r"\b(?:true|false|null)\b", text):
                    self.setFormat(m.start(), m.end() - m.start(), self.formats["keyword"])
                for m in re.finditer(r"[{}\[\],:]", text):
                    self.setFormat(m.start(), 1, self.formats["punct"])

        return _Highlighter(document)


class LineNumberArea(QWidget):
    def __init__(self, editor: "CodeEditor"):
        super().__init__(editor)
        self.editor = editor
        self.setMouseTracking(False)

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.line_number_area_paint_event(event)


class CodeEditor(QPlainTextEdit):
    """Compact editor: line numbers, JSON colouring, smart indent, find."""

    applyRequested = Signal()

    WAVE_VALUE_RE = re.compile(r'"wave"\s*:\s*"((?:\\.|[^"\\])*)"')

    def __init__(self, theme: Theme, *, font_size: float = 10.5, indent: int = 2):
        super().__init__()
        self.setObjectName("CodeEditor")
        self.theme = theme
        self.indent_size = max(1, indent)
        self._error_line: int | None = None
        self._search_text = ""
        self._search_case = False
        self._search_selections: list = []
        self._current_line_selection = None
        self._error_selection = None
        self._wave_selections: list = []
        self._wave_cursor = None
        self.line_number_area = LineNumberArea(self)
        self.setFrameShape(QPlainTextEdit.NoFrame)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabChangesFocus(False)
        self.setFont(mono_font(font_size))
        self.setTabStopDistance(QFontMetricsF(self.font()).horizontalAdvance(" ") * self.indent_size * 4)
        self.blockCountChanged.connect(self._update_line_number_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._on_cursor_moved)
        self.highlighter = JsonHighlighter(self.document(), theme)
        self._update_line_number_width()
        self._on_cursor_moved()

    # ------------------------------------------------------------------
    # Theme / font
    # ------------------------------------------------------------------
    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.highlighter.set_theme(theme)
        self.setStyleSheet(
            f"QPlainTextEdit#CodeEditor {{"
            f" background: {theme.editor_bg.name()};"
            f" color: {theme.text.name()};"
            f" border: none;"
            f" selection-background-color: {theme.selection.name()};"
            f" padding: 4px 0;"
            f"}}"
        )
        self.line_number_area.update()
        self._on_cursor_moved()

    def set_editor_font(self, size: float) -> None:
        self.setFont(mono_font(size))
        self.setTabStopDistance(QFontMetricsF(self.font()).horizontalAdvance(" ") * self.indent_size * 4)
        self._update_line_number_width()

    def set_indent(self, indent: int) -> None:
        self.indent_size = max(1, int(indent))
        self.setTabStopDistance(QFontMetricsF(self.font()).horizontalAdvance(" ") * self.indent_size * 4)

    def set_wrap(self, enabled: bool) -> None:
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth if enabled else QPlainTextEdit.NoWrap)
        self._update_line_number_width()

    # ------------------------------------------------------------------
    # Line numbers / extra selections
    # ------------------------------------------------------------------
    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 20 + int(QFontMetricsF(self.font()).horizontalAdvance("9") * digits)

    def _update_line_number_width(self) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)
        self.line_number_area.setFixedWidth(self.line_number_area_width())

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_width()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event) -> None:
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), self.theme.editor_gutter)
        painter.setFont(self.font())
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        current = self.textCursor().blockNumber()
        error = (self._error_line - 1) if self._error_line else None
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = block_number + 1
                color = self.theme.muted
                if number == current:
                    color = self.theme.accent
                elif error is not None and number == error:
                    color = self.theme.danger
                painter.setPen(color)
                painter.drawText(
                    0,
                    int(top),
                    self.line_number_area.width() - 7,
                    int(bottom - top),
                    int(Qt.AlignRight | Qt.AlignVCenter),
                    str(number),
                )
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1
        painter.end()

    def _on_cursor_moved(self) -> None:
        selections = []
        cursor = self.textCursor()
        current_format = QTextCharFormat()
        current_format.setBackground(self.theme.editor_line)
        current_format.setProperty(QTextFormat.FullWidthSelection, True)
        current = QTextEditExtraSelection()
        current.cursor = cursor
        current.cursor.clearSelection()
        current.format = current_format
        self._current_line_selection = current
        selections.append(current)
        if self._error_line:
            error_sel = QTextEditExtraSelection()
            err_cursor = QTextCursor(self.document().findBlockByNumber(max(0, self._error_line - 1)))
            err_cursor.select(QTextCursor.LineUnderCursor)
            err_format = QTextCharFormat()
            err_format.setBackground(QColor(self.theme.danger.red(), self.theme.danger.green(), self.theme.danger.blue(), 28))
            err_format.setUnderlineColor(self.theme.danger)
            err_format.setUnderlineStyle(QTextCharFormat.WaveUnderline)
            error_sel.cursor = err_cursor
            error_sel.format = err_format
            self._error_selection = error_sel
            selections.append(error_sel)
        if self._wave_selections:
            selections.extend(self._wave_selections)
        selections.extend(self._search_selections)
        self.setExtraSelections(selections)

    # ------------------------------------------------------------------
    # Wavedrom "wave" line focus (canvas -> editor synchronisation)
    # ------------------------------------------------------------------
    def wave_value_ranges(self) -> list[tuple[int, int]]:
        """Text positions of every ``"wave": "..."`` value in the document."""
        revision = self.document().revision()
        if getattr(self, "_wave_cache_rev", None) == revision and getattr(self, "_wave_cache", None):
            return self._wave_cache
        text = self.toPlainText()
        ranges = [(match.start(1), match.end(1)) for match in self.WAVE_VALUE_RE.finditer(text)]
        self._wave_cache = ranges
        self._wave_cache_rev = revision
        return ranges

    def clear_wave_focus(self) -> None:
        if not self._wave_selections and self._wave_cursor is None:
            return
        self._wave_selections = []
        self._wave_cursor = None
        self._on_cursor_moved()

    def focus_wave_rows(self, rows, char_start: int = -1, char_end: int = -1) -> bool:
        """Scroll to one or more ``wave`` lines and highlight their cycles."""
        ranges = self.wave_value_ranges()
        if isinstance(rows, int):
            rows = [rows]
        valid = sorted({int(row) for row in rows if 0 <= int(row) < len(ranges)})
        if not valid:
            self.clear_wave_focus()
            return False
        spans: list[tuple[int, int]] = []
        for row_index in valid:
            value_start, value_end = ranges[row_index]
            if char_start < 0 or char_end < 0:
                start, end = value_start, value_end
            else:
                length = value_end - value_start
                start = value_start + max(0, min(char_start, length))
                end = value_start + max(0, min(char_end + 1, length))
                if end <= start:
                    end = min(value_end, start + 1)
            spans.append((start, end))
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(self.theme.accent.red(), self.theme.accent.green(), self.theme.accent.blue(), 70))
        fmt.setUnderlineColor(self.theme.accent)
        fmt.setUnderlineStyle(QTextCharFormat.SingleUnderline)
        selections = []
        for start, end in spans:
            selection = QTextEditExtraSelection()
            cursor = QTextCursor(self.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            selection.cursor = cursor
            selection.format = fmt
            selections.append(selection)
        self._wave_selections = selections
        # A real text selection from the first to the last lane makes a
        # multi-row waveform selection visible in the editor as well.
        caret = QTextCursor(self.document())
        caret.setPosition(spans[0][0])
        if len(spans) > 1:
            caret.setPosition(spans[-1][1], QTextCursor.KeepAnchor)
        self._wave_cursor = caret
        self.setTextCursor(caret)
        self.centerCursor()
        self._on_cursor_moved()
        return True

    def focus_wave_line(self, row_index: int, char_start: int = -1, char_end: int = -1) -> bool:
        """Scroll to a lane's ``wave`` value and highlight the selected cycles."""
        return self.focus_wave_rows([row_index], char_start, char_end)

    def _rebuild_search_selections(self) -> None:
        self._search_selections = []
        text = self._search_text
        if text:
            flags = QTextDocument.FindFlags()
            if self._search_case:
                flags |= QTextDocument.FindCaseSensitively
            doc = self.document()
            cursor = QTextCursor(doc)
            count = 0
            while count < 2000:
                cursor = doc.find(text, cursor, flags)
                if cursor.isNull():
                    break
                sel = QTextEditExtraSelection()
                sel.cursor = QTextCursor(cursor)
                fmt = QTextCharFormat()
                fmt.setBackground(QColor(self.theme.warning.red(), self.theme.warning.green(), self.theme.warning.blue(), 46))
                sel.format = fmt
                self._search_selections.append(sel)
                count += 1
        self._on_cursor_moved()

    def set_error_line(self, line: int | None) -> None:
        self._error_line = line
        self._on_cursor_moved()
        self.line_number_area.update()

    def set_search_text(self, text: str, case: bool = False) -> None:
        self._search_text = text or ""
        self._search_case = bool(case)
        self._rebuild_search_selections()

    def clear_search(self) -> None:
        self.set_search_text("", False)

    # ------------------------------------------------------------------
    # Editing helpers
    # ------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key_Tab and not (mods & (Qt.ControlModifier | Qt.AltModifier)):
            if self.textCursor().hasSelection():
                self._indent_selection(True)
            else:
                self._insert_indent()
            event.accept()
            return
        if key == Qt.Key_Backtab:
            self._indent_selection(False)
            event.accept()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter) and (mods & Qt.ControlModifier):
            self.applyRequested.emit()
            event.accept()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter) and not (mods & Qt.ControlModifier):
            self._insert_newline()
            event.accept()
            return
        if key == Qt.Key_D and (mods & Qt.ControlModifier):
            self._duplicate_selection()
            event.accept()
            return
        if key in (Qt.Key_Slash, Qt.Key_Question) and (mods & Qt.ControlModifier):
            self._toggle_comment()
            event.accept()
            return
        super().keyPressEvent(event)

    def _insert_indent(self) -> None:
        cursor = self.textCursor()
        column = cursor.positionInBlock()
        count = self.indent_size - (column % self.indent_size)
        cursor.insertText(" " * count)
        self.setTextCursor(cursor)

    def _selected_blocks(self):
        cursor = self.textCursor()
        doc = self.document()
        start = doc.findBlock(cursor.selectionStart()).blockNumber()
        end = doc.findBlock(cursor.selectionEnd()).blockNumber()
        return start, end

    def _indent_selection(self, indent: bool) -> None:
        cursor = self.textCursor()
        if not cursor.hasSelection():
            block = cursor.block()
            text = block.text()
            if indent:
                new = " " * self.indent_size + text
            else:
                remove = 0
                while remove < min(self.indent_size, len(text)) and text[remove] == " ":
                    remove += 1
                new = text[remove:]
            if new != text:
                cursor.beginEditBlock()
                cursor.select(QTextCursor.LineUnderCursor)
                cursor.insertText(new)
                cursor.endEditBlock()
            return
        start, end = self._selected_blocks()
        cursor.beginEditBlock()
        for number in range(start, end + 1):
            block = self.document().findBlockByNumber(number)
            text = block.text()
            if indent:
                new = " " * self.indent_size + text
            else:
                remove = 0
                while remove < min(self.indent_size, len(text)) and text[remove] == " ":
                    remove += 1
                new = text[remove:]
            if new != text:
                edit = QTextCursor(block)
                edit.select(QTextCursor.LineUnderCursor)
                edit.insertText(new)
        cursor.endEditBlock()

    def _insert_newline(self) -> None:
        cursor = self.textCursor()
        block_text = cursor.block().text()
        pos = cursor.positionInBlock()
        before = block_text[:pos]
        after = block_text[pos:]
        leading = re.match(r"^[ \t]*", before).group(0)
        stripped = before.rstrip()
        extra = " " * self.indent_size if stripped.endswith(("{", "[")) else ""
        if stripped.endswith(("{", "[")) and after.lstrip().startswith(("}", "]")):
            cursor.beginEditBlock()
            cursor.insertText("\n" + leading + extra + "\n" + leading)
            cursor.movePosition(QTextCursor.Left)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            return
        if stripped.startswith(("}", "]")) and not extra:
            leading = leading[: max(0, len(leading) - self.indent_size)]
        cursor.insertText("\n" + leading + extra)
        self.setTextCursor(cursor)

    def _duplicate_selection(self) -> None:
        cursor = self.textCursor()
        if cursor.hasSelection():
            end = cursor.selectionEnd()
            text = cursor.selectedText().replace("\u2029", "\n")
            cursor.beginEditBlock()
            cursor.setPosition(end)
            cursor.insertText(text)
            cursor.endEditBlock()
            return
        block = cursor.block()
        text = block.text()
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.EndOfBlock)
        cursor.insertText("\n" + text)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def _toggle_comment(self) -> None:
        cursor = self.textCursor()
        start, end = self._selected_blocks() if cursor.hasSelection() else (
            cursor.blockNumber(),
            cursor.blockNumber(),
        )
        blocks = [self.document().findBlockByNumber(n) for n in range(start, end + 1)]
        all_commented = all(re.match(r"^\s*//", b.text()) for b in blocks)
        cursor.beginEditBlock()
        for block in blocks:
            text = block.text()
            edit = QTextCursor(block)
            if all_commented:
                match = re.match(r"^(\s*)// ?", text)
                if match:
                    edit.select(QTextCursor.LineUnderCursor)
                    edit.insertText(match.group(1) + text[match.end():])
            else:
                match = re.match(r"^(\s*)", text)
                indent = match.group(1) if match else ""
                edit.select(QTextCursor.LineUnderCursor)
                edit.insertText(indent + "// " + text[len(indent):])
        cursor.endEditBlock()

    # ------------------------------------------------------------------
    # Find / replace
    # ------------------------------------------------------------------
    def find_text(self, text: str, *, backward: bool = False, case: bool = False, wrap: bool = True) -> bool:
        if not text:
            return False
        flags = QTextDocument.FindFlags()
        if backward:
            flags |= QTextDocument.FindBackward
        if case:
            flags |= QTextDocument.FindCaseSensitively
        doc = self.document()
        start = self.textCursor()
        found = doc.find(text, start, flags)
        if found.isNull() and wrap:
            cursor = QTextCursor(doc)
            if backward:
                cursor.movePosition(QTextCursor.End)
            found = doc.find(text, cursor, flags)
        if found.isNull():
            return False
        self.setTextCursor(found)
        self.centerCursor()
        return True

    def replace_current(self, text: str, replacement: str, *, case: bool = False) -> bool:
        if not text or not self.textCursor().hasSelection():
            if not self.find_text(text, case=case):
                return False
        cursor = self.textCursor()
        selected = cursor.selectedText()
        if selected == text or (not case and selected.lower() == text.lower()):
            cursor.beginEditBlock()
            cursor.insertText(replacement)
            cursor.endEditBlock()
            self.find_text(text, case=case)
            return True
        return self.find_text(text, case=case)

    def replace_all(self, text: str, replacement: str, *, case: bool = False) -> int:
        if not text:
            return 0
        doc = self.document()
        flags = QTextDocument.FindFlags()
        if case:
            flags |= QTextDocument.FindCaseSensitively
        cursor = QTextCursor(doc)
        count = 0
        cursor.beginEditBlock()
        while True:
            found = doc.find(text, cursor, flags)
            if found.isNull():
                break
            found.insertText(replacement)
            cursor = found
            count += 1
            if count > 10000:
                break
        cursor.endEditBlock()
        return count

    # ------------------------------------------------------------------
    # Text assignment
    # ------------------------------------------------------------------
    def set_text_silently(self, text: str, *, reset_undo: bool = False) -> None:
        scroll = self.verticalScrollBar().value()
        cursor_pos = self.textCursor().position()
        self.blockSignals(True)
        self.setPlainText(text)
        self.blockSignals(False)
        if reset_undo:
            try:
                self.document().clearUndoRedoStacks()
            except Exception:
                pass
        cursor = self.textCursor()
        cursor.setPosition(min(cursor_pos, max(0, len(self.toPlainText()))))
        self.setTextCursor(cursor)
        self.verticalScrollBar().setValue(scroll)
        self.highlighter.rehighlight()
        self._on_cursor_moved()

    def goto_line(self, line: int, column: int = 0) -> None:
        block = self.document().findBlockByNumber(max(0, line - 1))
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + max(0, column - 1))
        self.setTextCursor(cursor)
        self.centerCursor()
        self.setFocus(Qt.OtherFocusReason)

    def line_column(self, position: int) -> tuple[int, int]:
        block = self.document().findBlock(position)
        return block.blockNumber() + 1, position - block.position() + 1

    def indent_guides(self) -> None:
        # Intentionally not implemented: keeping the widget light-weight.
        return None


# Imported late to avoid a circular import in some PySide versions.
from PySide6.QtWidgets import QTextEdit  # noqa: E402


def QTextEditExtraSelection():  # noqa: N802 - Qt-style factory
    return QTextEdit.ExtraSelection()


class FindBar(QWidget):
    closeRequested = Signal()
    findNext = Signal(str, bool)
    findPrevious = Signal(str, bool)
    replaceRequested = Signal(str, str, bool)
    replaceAllRequested = Signal(str, str, bool)
    searchChanged = Signal(str, bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("FindBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find in JSON…")
        self.search.setClearButtonEnabled(True)
        self.replace = QLineEdit()
        self.replace.setPlaceholderText("Replace with…")
        self.case_button = QToolButton()
        self.case_button.setText("Aa")
        self.case_button.setCheckable(True)
        self.case_button.setToolTip("Match case")
        self.prev_button = QToolButton()
        self.prev_button.setText("↑")
        self.prev_button.setToolTip("Previous match (Shift+Enter)")
        self.next_button = QToolButton()
        self.next_button.setText("↓")
        self.next_button.setToolTip("Next match (Enter)")
        self.replace_button = QPushButton("Replace")
        self.replace_all_button = QPushButton("All")
        self.close_button = QToolButton()
        self.close_button.setText("✕")
        self.close_button.setToolTip("Close (Esc)")
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        layout.addWidget(self.search, 2)
        layout.addWidget(self.case_button)
        layout.addWidget(self.prev_button)
        layout.addWidget(self.next_button)
        layout.addWidget(self.status)
        layout.addWidget(self.replace, 2)
        layout.addWidget(self.replace_button)
        layout.addWidget(self.replace_all_button)
        layout.addStretch(1)
        layout.addWidget(self.close_button)
        self.language = "en"
        self.replace.setVisible(False)
        self.replace_button.setVisible(False)
        self.replace_all_button.setVisible(False)
        self.search.textChanged.connect(self._on_search_changed)
        self.search.returnPressed.connect(self._on_return_pressed)
        self.prev_button.clicked.connect(lambda: self.findPrevious.emit(self.search.text(), self.case_button.isChecked()))
        self.next_button.clicked.connect(lambda: self.findNext.emit(self.search.text(), self.case_button.isChecked()))
        self.replace_button.clicked.connect(
            lambda: self.replaceRequested.emit(self.search.text(), self.replace.text(), self.case_button.isChecked())
        )
        self.replace_all_button.clicked.connect(
            lambda: self.replaceAllRequested.emit(self.search.text(), self.replace.text(), self.case_button.isChecked())
        )
        self.close_button.clicked.connect(self.closeRequested.emit)
        self.case_button.toggled.connect(lambda _: self._on_search_changed(self.search.text()))

    def _t(self, en: str, zh: str) -> str:
        return zh if self.language == "zh" else en

    def set_language(self, language: str) -> None:
        self.language = language
        self.search.setPlaceholderText(self._t("Find in JSON…", "在 JSON 中查找…"))
        self.replace.setPlaceholderText(self._t("Replace with…", "替换为…"))
        self.case_button.setToolTip(self._t("Match case", "区分大小写"))
        self.prev_button.setToolTip(self._t("Previous match (Shift+Enter)", "上一个匹配（Shift+Enter）"))
        self.next_button.setToolTip(self._t("Next match (Enter)", "下一个匹配（Enter）"))
        self.replace_button.setText(self._t("Replace", "替换"))
        self.replace_all_button.setText(self._t("All", "全部"))
        self.close_button.setToolTip(self._t("Close (Esc)", "关闭（Esc）"))

    def _on_return_pressed(self) -> None:
        from PySide6.QtWidgets import QApplication

        if QApplication.keyboardModifiers() & Qt.ShiftModifier:
            self.findPrevious.emit(self.search.text(), self.case_button.isChecked())
        else:
            self.findNext.emit(self.search.text(), self.case_button.isChecked())

    def _on_search_changed(self, text: str) -> None:
        self.searchChanged.emit(text, self.case_button.isChecked())

    def show_bar(self, *, replace: bool = False) -> None:
        self.setVisible(True)
        self.replace.setVisible(replace)
        self.replace_button.setVisible(replace)
        self.replace_all_button.setVisible(replace)
        self.search.setFocus(Qt.OtherFocusReason)
        self.search.selectAll()

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.closeRequested.emit()
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                self.findPrevious.emit(self.search.text(), self.case_button.isChecked())
            else:
                self.findNext.emit(self.search.text(), self.case_button.isChecked())
            event.accept()
            return
        super().keyPressEvent(event)


class JsonPanel(QWidget):
    contentChanged = Signal(str)
    applyRequested = Signal(str)

    def __init__(
        self,
        theme: Theme,
        *,
        font_size: float = 10.5,
        indent: int = 2,
        json_indent: int = 2,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.theme = theme
        self.language = "en"
        self.live_enabled = True
        self.json_indent = max(0, int(json_indent))
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(240)
        self._debounce.timeout.connect(self._emit_content)
        self._syncing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QWidget()
        self.header.setObjectName("EditorHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(10, 4, 8, 4)
        header_layout.setSpacing(6)
        title = QLabel("WaveJSON")
        title.setObjectName("SectionTitle")
        self.badge = QLabel("Live")
        self.badge.setObjectName("Badge")
        self.badge.setToolTip("Live JSON ↔ waveform synchronisation")
        self.sync_status = QLabel("Synced")
        self.sync_status.setObjectName("Muted")
        self.format_button = QToolButton()
        self.format_button.setToolTip("Format JSON (Ctrl+Shift+F)")
        self.wrap_button = QToolButton()
        self.wrap_button.setCheckable(True)
        self.wrap_button.setToolTip("Toggle word wrap")
        self.copy_button = QToolButton()
        self.copy_button.setToolTip("Copy JSON")
        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip("Apply JSON (Ctrl+Enter)")
        header_layout.addWidget(title)
        header_layout.addWidget(self.badge)
        header_layout.addWidget(self.sync_status)
        header_layout.addStretch(1)
        header_layout.addWidget(self.apply_button)
        header_layout.addWidget(self.format_button)
        header_layout.addWidget(self.wrap_button)
        header_layout.addWidget(self.copy_button)
        layout.addWidget(self.header)

        self.error_banner = QLabel()
        self.error_banner.setObjectName("ErrorBanner")
        self.error_banner.setVisible(False)
        self.error_banner.setWordWrap(True)
        self.error_banner.setContentsMargins(10, 2, 10, 2)
        layout.addWidget(self.error_banner)

        self.find_bar = FindBar()
        self.find_bar.setVisible(False)
        layout.addWidget(self.find_bar)

        self.editor = CodeEditor(theme, font_size=font_size, indent=indent)
        self.code_editor = self.editor
        layout.addWidget(self.editor, 1)

        self.apply_button.clicked.connect(self._apply_now)
        self.copy_button.clicked.connect(self._copy)
        self.format_button.clicked.connect(self.format_text)
        self.wrap_button.toggled.connect(self.editor.set_wrap)
        self.editor.applyRequested.connect(self._apply_now)
        self.editor.textChanged.connect(self._on_text_changed)
        self.find_bar.closeRequested.connect(self.hide_find)
        self.find_bar.searchChanged.connect(self._search_changed)
        self.find_bar.findNext.connect(lambda text, case: self._find(text, case, False))
        self.find_bar.findPrevious.connect(lambda text, case: self._find(text, case, True))
        self.find_bar.replaceRequested.connect(self._replace_one)
        self.find_bar.replaceAllRequested.connect(self._replace_all)
        self._apply_icons()
        self.set_theme(theme)

    # ------------------------------------------------------------------
    def _apply_icons(self) -> None:
        self.format_button.setIcon(make_icon("format", self.theme, 16))
        self.wrap_button.setIcon(make_icon("wrap", self.theme, 16))
        self.copy_button.setIcon(make_icon("copy", self.theme, 16))

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self._apply_icons()
        self.editor.set_theme(theme)
        self._set_badge_style()

    def _t(self, en: str, zh: str) -> str:
        return zh if self.language == "zh" else en

    def set_language(self, language: str) -> None:
        self.language = language
        self.find_bar.set_language(language)
        self.apply_button.setText(self._t("Apply", "应用"))
        self.format_button.setToolTip(self._t("Format JSON (Ctrl+Shift+F)", "格式化 JSON（Ctrl+Shift+F）"))
        self.wrap_button.setToolTip(self._t("Toggle word wrap", "切换自动换行"))
        self.copy_button.setToolTip(self._t("Copy JSON", "复制 JSON"))
        self.apply_button.setToolTip(self._t("Apply JSON (Ctrl+Enter)", "应用 JSON（Ctrl+Enter）"))
        self.badge.setToolTip(self._t("Live JSON ↔ waveform synchronisation", "JSON 与波形实时同步"))
        self._set_badge_style()

    def _set_badge_style(self) -> None:
        t = self.theme
        if self.error_banner.text():
            self.badge.setText(self._t("Error", "错误"))
            background = "rgba(220,38,38,0.14)"
            color = t.danger.name()
        elif not self.live_enabled:
            self.badge.setText(self._t("Manual", "手动"))
            background = "rgba(120,120,120,0.15)"
            color = t.muted.name()
        else:
            self.badge.setText(self._t("Live", "实时"))
            background = "rgba(21,128,61,0.14)"
            color = t.success.name()
        self.badge.setStyleSheet(
            f"QLabel#Badge {{ background: {background}; color: {color};"
            f" border-radius: 5px; padding: 2px 8px; font-size: 8.5pt; font-weight: 600; }}"
        )

    # ------------------------------------------------------------------
    def text(self) -> str:
        return self.editor.toPlainText()

    def set_text(self, text: str, *, reset_undo: bool = False) -> None:
        self._syncing = True
        self.editor.set_text_silently(text, reset_undo=reset_undo)
        self._syncing = False
        self._debounce.stop()
        self.editor.clear_wave_focus()

    def set_live(self, enabled: bool) -> None:
        self.live_enabled = bool(enabled)
        self.apply_button.setVisible(not self.live_enabled)
        self._set_badge_style()

    def _on_text_changed(self) -> None:
        if self._syncing:
            return
        self.editor.clear_wave_focus()
        self.set_error(None)
        self.sync_status.setText(self._t("Editing…", "编辑中…"))
        if self.live_enabled:
            self._debounce.start()
        else:
            self.sync_status.setText(self._t("Press Apply", "点击应用"))

    def _emit_content(self) -> None:
        if self.live_enabled:
            self.contentChanged.emit(self.text())

    def _apply_now(self) -> None:
        self._debounce.stop()
        self.applyRequested.emit(self.text())

    def set_error(self, message: str | None, line: int | None = None, column: int | None = None) -> None:
        self.error_banner.setVisible(bool(message))
        if message:
            location = (
                self._t(f"Line {line}, column {column}: ", f"第 {line} 行，第 {column} 列：")
                if line
                else ""
            )
            self.error_banner.setText(location + message)
            self.editor.set_error_line(line)
            self.sync_status.setText(self._t("Invalid JSON", "JSON 无效"))
            self.sync_status.setStyleSheet(f"color: {self.theme.danger.name()};")
        else:
            self.error_banner.setText("")
            self.editor.set_error_line(None)
            self.sync_status.setText(self._t("Synced", "已同步") if self.live_enabled else self._t("Manual", "手动"))
            self.sync_status.setStyleSheet("")
        self._set_badge_style()

    @property
    def has_error(self) -> bool:
        return bool(self.error_banner.text())

    def flush_pending(self) -> None:
        """Apply a pending debounced edit immediately."""
        if self._debounce.isActive():
            self._debounce.stop()
            self.contentChanged.emit(self.text())

    def mark_synced(self) -> None:
        self.sync_status.setText(
            self._t("Synced", "已同步") if self.live_enabled else self._t("Applied", "已应用")
        )
        self.sync_status.setStyleSheet("")
        self.error_banner.setText("")
        self.error_banner.setVisible(False)
        self.editor.set_error_line(None)
        self._set_badge_style()

    def goto_error(self, line: int, column: int = 0) -> None:
        self.editor.goto_line(line, column)

    # ------------------------------------------------------------------
    def format_text(self) -> None:
        import json

        from .model import DocumentError, WaveDocument

        text = self.text()
        try:
            data = WaveDocument.parse_json_text(text)
            formatted = json.dumps(data, ensure_ascii=False, indent=self.json_indent) + "\n"
        except DocumentError as exc:
            self.set_error(str(exc), exc.line, exc.column)
            return
        except Exception as exc:  # noqa: BLE001
            self.set_error(str(exc))
            return
        self.set_text(formatted)
        self.mark_synced()

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.text())
        self.sync_status.setText(self._t("Copied", "已复制"))
        QTimer.singleShot(1200, lambda: self.sync_status.setText(self._t("Synced", "已同步")))

    # ------------------------------------------------------------------
    def show_find(self, *, replace: bool = False) -> None:
        self.find_bar.show_bar(replace=replace)
        if self.editor.textCursor().hasSelection():
            self.find_bar.search.setText(self.editor.textCursor().selectedText())
        self.find_bar.search.setFocus(Qt.OtherFocusReason)

    def hide_find(self) -> None:
        self.find_bar.setVisible(False)
        self.editor.clear_search()
        self.editor.setFocus(Qt.OtherFocusReason)

    def _search_changed(self, text: str, case: bool) -> None:
        self.editor.set_search_text(text, case)
        if not text:
            self.find_bar.set_status("")
        else:
            self.find_bar.set_status("")

    def _find(self, text: str, case: bool, backward: bool) -> None:
        found = self.editor.find_text(text, backward=backward, case=case)
        self.find_bar.set_status(self._t("No match", "无匹配") if not found else "")

    def _replace_one(self, text: str, replacement: str, case: bool) -> None:
        found = self.editor.replace_current(text, replacement, case=case)
        self.find_bar.set_status(self._t("Replaced", "已替换") if found else self._t("No match", "无匹配"))

    def _replace_all(self, text: str, replacement: str, case: bool) -> None:
        count = self.editor.replace_all(text, replacement, case=case)
        self.find_bar.set_status(self._t(f"{count} replaced", f"已替换 {count} 处") if count else self._t("No match", "无匹配"))

    def focus_editor(self) -> None:
        self.editor.setFocus(Qt.OtherFocusReason)

    def focus_wave(self, rows, char_start: int = -1, char_end: int = -1) -> None:
        """Jump to one or more lanes' ``wave`` lines without stealing focus."""
        self.editor.focus_wave_rows(rows, char_start, char_end)

    def clear_wave_focus(self) -> None:
        self.editor.clear_wave_focus()
