# coding=utf-8
"""Main application window and entry point for WaveDromGen v2."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QPoint, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QDesktopServices,
    QFontDatabase,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
)
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QToolBar,
    QToolButton,
    QWidget,
)

from . import __version__
from .ascii_render import document_to_ascii
from .dialogs import (
    AboutDialog,
    AsciiDialog,
    RelationDialog,
    RowPropertiesDialog,
    SettingsDialog,
    ShortcutHelpDialog,
)
from .editor import JsonPanel
from .icons import has_icon, make_icon
from .layout import DiagramLayout
from .model import DocumentError, WaveDocument
from .renderer import CanvasColors, PaintState, WaveRenderer, pixmap_for_document
from .settings import Settings
from .shortcuts import (
    CATEGORY_ZH,
    ShortcutRegistry,
    apply_to_actions,
)
from .skins import available_skins, get_skin
from .theme import Theme, apply_theme, resolve_theme
from .waveview import WaveView

APP_NAME = "WaveDromGen"
ASSET_DIR = Path(__file__).resolve().parent.parent / "asset"
APP_ICON = Path(__file__).resolve().parent / "resources" / "app.ico"
if not APP_ICON.exists():
    APP_ICON = ASSET_DIR / "app.ico"


def ensure_fonts() -> None:
    """Make the bundled UI usable in environments with a minimal font DB."""
    families = set(QFontDatabase.families())
    if "Segoe UI" in families:
        return
    if os.name == "nt":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        fonts = windir / "Fonts"
        for name in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf", "consolab.ttf", "msyh.ttc", "msyhbd.ttc"):
            path = fonts / name
            if path.exists():
                QFontDatabase.addApplicationFont(str(path))


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, *, initial_path: str | None = None):
        super().__init__()
        self.settings = settings
        self.language = settings.get("language", "en")
        if self.language not in ("en", "zh"):
            self.language = "en"
        self.registry = ShortcutRegistry()
        self.shortcut_map = self.registry.resolve(settings.shortcuts())
        self.theme_name = settings.get("theme", "light")
        self.theme: Theme = resolve_theme(self.theme_name)
        self.doc = WaveDocument(
            auto_extend_clocks=bool(settings.get("auto_extend_clocks", True))
        )
        self.actions: dict[str, QAction] = {}
        self.local_actions: dict[str, QAction] = {}
        self._inline_editing = False
        self._view_mode = "stacked"
        self._last_split_mode = "stacked"
        self._applying_json = False
        self._cursor_info_text = "Ready"
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(lambda: self.status_message.setText("") if hasattr(self, "status_message") else None)
        self._splitter_timer = QTimer(self)
        self._splitter_timer.setSingleShot(True)
        self._splitter_timer.setInterval(350)
        self._splitter_timer.timeout.connect(self._save_splitter_ratios)
        self._first_show = True

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(APP_ICON)))
        self.setMinimumSize(920, 560)
        self._create_actions()
        self._create_ui()
        self._create_menus()
        self._create_toolbar()
        self._configure_shortcuts()
        self._apply_icons()
        self._connect_signals()
        self._apply_theme(self.theme_name, initial=True)
        self._set_document(self.doc, reset_view=True)
        self._restore_window_state()
        self._set_view_mode(settings.get("view_mode", "stacked"), initial=True)
        self.canvas.set_auto_advance(bool(settings.get("auto_advance_cell", True)))
        self.editor_panel.set_live(bool(settings.get("live_json_sync", True)))
        self.editor_panel.set_text(self._json_text(), reset_undo=True)
        self.editor_panel.mark_synced()
        self._sync_config_actions()
        self._update_actions()
        self._update_status()
        self._update_title()
        self._show_status(
            self._tr("Ready. Tip: double-click a name or data label to edit it.", "就绪。提示：双击信号名或数据标签即可编辑。"),
            6000,
        )
        if initial_path:
            QTimer.singleShot(0, lambda: self.open_file(initial_path))
        if self.settings.get("show_shortcut_help_on_start", False):
            QTimer.singleShot(350, self._show_help)

    # ==================================================================
    # Translation helpers
    # ==================================================================
    def _tr(self, en: str, zh: str) -> str:
        return zh if self.language == "zh" else en

    def _menu_title(self, category: str) -> str:
        return CATEGORY_ZH.get(category, category) if self.language == "zh" else category

    # ==================================================================
    # Actions
    # ==================================================================
    def _create_actions(self) -> None:
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.view_group = QActionGroup(self)
        self.view_group.setExclusive(True)
        checkable_tools = [d.id for d in self.registry.actions.values() if d.category == "Tools" and d.id.startswith("tool_")]
        checkable_views = ["view_wave", "view_editor", "view_stacked", "view_side"]
        for action_id, definition in self.registry.actions.items():
            action = QAction(self)
            action.setCheckable(action_id in checkable_tools or action_id in checkable_views or action_id == "toggle_live")
            action.setShortcutContext(Qt.ApplicationShortcut)
            action.triggered.connect(lambda checked=False, aid=action_id: self._dispatch(aid, checked))
            self.actions[action_id] = action
            if action_id in checkable_tools:
                self.tool_group.addAction(action)
            if action_id in checkable_views:
                self.view_group.addAction(action)
        self.actions["tool_select"].setChecked(True)
        self.actions["toggle_live"].setChecked(bool(self.settings.get("live_json_sync", True)))
        self._create_local_actions()
        self._update_action_texts()

    def _create_local_actions(self) -> None:
        self.skin_group = QActionGroup(self)
        self.skin_group.setExclusive(True)
        for skin in available_skins():
            action = QAction(self)
            action.setCheckable(True)
            action.setData(skin)
            action.triggered.connect(lambda checked=False, s=skin: self._set_skin(s))
            self.skin_group.addAction(action)
            self.local_actions[f"skin:{skin}"] = action
        self.hscale_group = QActionGroup(self)
        self.hscale_group.setExclusive(True)
        for value in (1, 2, 3, 4, 6, 8):
            action = QAction(f"{value}×", self)
            action.setCheckable(True)
            action.setData(value)
            action.triggered.connect(lambda checked=False, v=value: self._set_hscale(v))
            self.hscale_group.addAction(action)
            self.local_actions[f"hscale:{value}"] = action
        self.language_group = QActionGroup(self)
        self.language_group.setExclusive(True)
        for code, text in (("en", "English"), ("zh", "中文")):
            action = QAction(text, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, c=code: self._set_language(c))
            self.language_group.addAction(action)
            self.local_actions[f"language:{code}"] = action

    def _update_action_texts(self) -> None:
        for action_id, definition in self.registry.actions.items():
            action = self.actions[action_id]
            action.setText(definition.localized(self.language))
            shortcuts = self.shortcut_map.get(action_id, [])
            shortcut_text = ", ".join(QKeySequence(seq).toString(QKeySequence.NativeText) for seq in shortcuts)
            tip = definition.description or definition.localized(self.language)
            if shortcut_text:
                tip += f"  ({shortcut_text})"
            action.setToolTip(tip)
            action.setStatusTip(definition.description or action.text())
        for action_id, action in self.local_actions.items():
            if action_id.startswith("skin:"):
                skin = action_id.split(":", 1)[1]
                action.setText(_skin_label(skin, self.language))
            elif action_id.startswith("language:"):
                code = action_id.split(":", 1)[1]
                action.setText("English" if code == "en" else "中文")
        self._sync_config_actions()

    def _sync_config_actions(self) -> None:
        skin = self.doc.skin_name()
        if f"skin:{skin}" in self.local_actions:
            self.local_actions[f"skin:{skin}"].setChecked(True)
        hscale = self.doc.hscale()
        if f"hscale:{hscale}" in self.local_actions:
            self.local_actions[f"hscale:{hscale}"].setChecked(True)
        if "language:en" in self.local_actions:
            self.local_actions[f"language:{self.language}"].setChecked(True)
        for mode in ("wave", "editor", "stacked", "side"):
            action = self.actions.get(f"view_{mode}")
            if action:
                action.setChecked(self._view_mode == mode)
        tool_action = self.actions.get(f"tool_{self.canvas.tool if hasattr(self, 'canvas') else 'select'}")
        if tool_action:
            tool_action.setChecked(True)
        live_action = self.actions.get("toggle_live")
        if live_action and hasattr(self, "editor_panel"):
            live_action.setChecked(self.editor_panel.live_enabled)

    def _configure_shortcuts(self) -> None:
        apply_to_actions(self.actions, self.shortcut_map)
        for action_id, definition in self.registry.actions.items():
            action = self.actions[action_id]
            if definition.scope == "canvas":
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                self.canvas.addAction(action)
            elif definition.scope == "editor":
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                self.code_editor.addAction(action)
            else:
                action.setShortcutContext(Qt.ApplicationShortcut)
                self.addAction(action)
        self._update_action_texts()

    def _apply_icons(self) -> None:
        for action_id, action in self.actions.items():
            icon_name = _icon_for_action(action_id)
            if icon_name and has_icon(icon_name):
                action.setIcon(make_icon(icon_name, self.theme, 20))

    # ==================================================================
    # UI
    # ==================================================================
    def _create_ui(self) -> None:
        self.setDockNestingEnabled(False)
        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        self.wave_view = WaveView(self.doc)
        self.wave_view.setObjectName("WaveView")
        self.wave_view.setMinimumWidth(320)
        self.canvas = self.wave_view.canvas
        self.editor_panel = JsonPanel(
            self.theme,
            font_size=float(self.settings.get("editor_font_size", 10.5)),
            indent=int(self.settings.get("editor_indent", 2)),
            json_indent=int(self.settings.get("json_indent", 2)),
        )
        self.editor_panel.setObjectName("EditorPane")
        self.editor_panel.setMinimumWidth(300)
        self.code_editor = self.editor_panel.editor
        self.editor_panel.set_language(self.language)
        self.code_editor.set_wrap(bool(self.settings.get("editor_wrap", False)))
        self.editor_panel.wrap_button.setChecked(bool(self.settings.get("editor_wrap", False)))

        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setObjectName("MainSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.wave_view)
        self.splitter.addWidget(self.editor_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        self.tool_rail = QToolBar("Tools")
        self.tool_rail.setObjectName("ToolRail")
        self.tool_rail.setOrientation(Qt.Vertical)
        self.tool_rail.setMovable(False)
        self.tool_rail.setFloatable(False)
        self.tool_rail.setIconSize(QSize(22, 22))
        self.tool_rail.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.tool_rail.setContextMenuPolicy(Qt.PreventContextMenu)
        for action_id in (
            "tool_select",
            "tool_clk",
            "tool_sig",
            "tool_bus",
            "tool_x",
            "tool_z",
            "tool_gap",
            "tool_text",
            "tool_clear",
            "tool_node",
        ):
            self.tool_rail.addAction(self.actions[action_id])
            widget = self.tool_rail.widgetForAction(self.actions[action_id])
            if isinstance(widget, QToolButton):
                widget.setObjectName("ToolRailButton")
        central_layout.addWidget(self.tool_rail)
        central_layout.addWidget(self.splitter, 1)
        self.setCentralWidget(central)

        self.main_toolbar = QToolBar("Main")
        self.main_toolbar.setObjectName("MainToolBar")
        self.main_toolbar.setMovable(False)
        self.main_toolbar.setFloatable(False)
        self.main_toolbar.setIconSize(QSize(20, 20))
        self.main_toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.main_toolbar.setContextMenuPolicy(Qt.PreventContextMenu)
        self.addToolBar(Qt.TopToolBarArea, self.main_toolbar)

        status = self.statusBar()
        self.status_cursor = QLabel(self._tr("Ready", "就绪"))
        self.status_cursor.setObjectName("Muted")
        self.status_message = QLabel("")
        self.status_message.setObjectName("Muted")
        self.status_sync = QLabel("● Live")
        self.status_doc = QLabel("")
        self.status_doc.setObjectName("Muted")
        self.status_zoom = QLabel("100%")
        self.status_zoom.setObjectName("Muted")
        status.addWidget(self.status_cursor, 0)
        status.addWidget(self.status_message, 1)
        status.addPermanentWidget(self.status_sync)
        status.addPermanentWidget(self.status_doc)
        status.addPermanentWidget(self.status_zoom)
        status.setSizeGripEnabled(True)

        self.canvas.set_zoom(float(self.settings.get("zoom", 1.0)))
        self.canvas.setAutoFillBackground(False)
        self._apply_canvas_theme()

    def _create_toolbar(self) -> None:
        tb = self.main_toolbar
        tb.clear()
        for action_id in ("new", "open", "save", "export_png"):
            tb.addAction(self.actions[action_id])
        tb.addSeparator()
        for action_id in ("undo", "redo"):
            tb.addAction(self.actions[action_id])
        tb.addSeparator()
        for action_id in ("row_add", "row_insert_above", "row_insert_below", "row_duplicate", "row_delete", "row_move_up", "row_move_down"):
            tb.addAction(self.actions[action_id])
        tb.addSeparator()
        for action_id in ("view_wave", "view_editor", "view_stacked", "view_side"):
            tb.addAction(self.actions[action_id])
        tb.addSeparator()
        for action_id in ("zoom_out", "zoom_in", "zoom_reset"):
            tb.addAction(self.actions[action_id])
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        for action_id in ("toggle_theme", "settings", "help"):
            tb.addAction(self.actions[action_id])

    def _create_menus(self) -> None:
        menubar = self.menuBar()
        menubar.clear()
        def add(menu, action_id):
            menu.addAction(self.actions[action_id])

        file_menu = menubar.addMenu(self._menu_title("File"))
        add(file_menu, "new")
        add(file_menu, "open")
        self.recent_menu = QMenu(self._tr("Open Recent", "最近打开"), self)
        self.recent_menu.aboutToShow.connect(self._populate_recent_menu)
        file_menu.addMenu(self.recent_menu)
        file_menu.addSeparator()
        add(file_menu, "save")
        add(file_menu, "save_as")
        file_menu.addSeparator()
        add(file_menu, "export_png")
        add(file_menu, "export_svg")
        add(file_menu, "copy_image")
        file_menu.addSeparator()
        add(file_menu, "quit")

        edit_menu = menubar.addMenu(self._menu_title("Edit"))
        add(edit_menu, "undo")
        add(edit_menu, "redo")
        edit_menu.addSeparator()
        add(edit_menu, "row_cut")
        add(edit_menu, "row_copy")
        add(edit_menu, "row_paste")
        add(edit_menu, "row_duplicate")
        add(edit_menu, "row_delete")
        edit_menu.addSeparator()
        add(edit_menu, "row_insert_above")
        add(edit_menu, "row_insert_below")
        add(edit_menu, "row_add")
        edit_menu.addSeparator()
        add(edit_menu, "cell_copy")
        add(edit_menu, "cell_paste")
        add(edit_menu, "clear_cells")
        edit_menu.addSeparator()
        add(edit_menu, "select_all")
        add(edit_menu, "find")
        add(edit_menu, "replace")
        add(edit_menu, "format_json")

        signal_menu = menubar.addMenu(self._menu_title("Signal"))
        add(signal_menu, "row_add")
        add(signal_menu, "row_insert_above")
        add(signal_menu, "row_insert_below")
        signal_menu.addSeparator()
        add(signal_menu, "add_column")
        add(signal_menu, "delete_column")
        signal_menu.addSeparator()
        add(signal_menu, "row_properties")
        add(signal_menu, "row_clear")
        add(signal_menu, "extend_clocks")
        signal_menu.addSeparator()
        add(signal_menu, "relations")

        view_menu = menubar.addMenu(self._menu_title("View"))
        add(view_menu, "view_wave")
        add(view_menu, "view_editor")
        add(view_menu, "view_stacked")
        add(view_menu, "view_side")
        view_menu.addSeparator()
        add(view_menu, "zoom_in")
        add(view_menu, "zoom_out")
        add(view_menu, "zoom_reset")
        add(view_menu, "fit_width")
        view_menu.addSeparator()
        skin_menu = QMenu(self._tr("Skin", "皮肤"), self)
        for skin in available_skins():
            skin_menu.addAction(self.local_actions[f"skin:{skin}"])
        view_menu.addMenu(skin_menu)
        hscale_menu = QMenu(self._tr("Horizontal Scale", "水平比例"), self)
        for value in (1, 2, 3, 4, 6, 8):
            hscale_menu.addAction(self.local_actions[f"hscale:{value}"])
        view_menu.addMenu(hscale_menu)
        view_menu.addSeparator()
        add(view_menu, "toggle_theme")

        tools_menu = menubar.addMenu(self._menu_title("Tools"))
        for action_id in (
            "tool_select",
            "tool_clk",
            "tool_sig",
            "tool_bus",
            "tool_x",
            "tool_z",
            "tool_gap",
            "tool_text",
            "tool_clear",
            "tool_node",
        ):
            add(tools_menu, action_id)
        tools_menu.addSeparator()
        add(tools_menu, "relations")
        add(tools_menu, "ascii_preview")
        add(tools_menu, "copy_ascii")
        add(tools_menu, "toggle_live")
        tools_menu.addSeparator()
        add(tools_menu, "settings")
        add(tools_menu, "show_shortcuts")
        language_menu = QMenu(self._tr("Language", "语言"), self)
        for code in ("en", "zh"):
            language_menu.addAction(self.local_actions[f"language:{code}"])
        tools_menu.addMenu(language_menu)

        help_menu = menubar.addMenu(self._menu_title("Help"))
        add(help_menu, "help")
        help_menu.addSeparator()
        tutorial = help_menu.addAction(self._tr("WaveDrom Tutorial", "WaveDrom 教程"))
        tutorial.triggered.connect(lambda: QDesktopServices.openUrl(QUrl("https://wavedrom.com/tutorial.html")))
        repo = help_menu.addAction(self._tr("Original Repository", "原始仓库"))
        repo.triggered.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/blueyesess/wavedromgen")))
        help_menu.addSeparator()
        about = help_menu.addAction(self._tr("About WaveDromGen", "关于 WaveDromGen"))
        about.triggered.connect(self._show_about)

    def _populate_recent_menu(self) -> None:
        self.recent_menu.clear()
        recent = self.settings.get("recent_files", [])
        if not recent:
            action = self.recent_menu.addAction(self._tr("No recent files", "暂无最近文件"))
            action.setEnabled(False)
            return
        for path in recent:
            label = Path(path).name
            action = self.recent_menu.addAction(label)
            action.setToolTip(path)
            action.triggered.connect(lambda checked=False, p=path: self.open_file(p))
        self.recent_menu.addSeparator()
        clear = self.recent_menu.addAction(self._tr("Clear Recent Files", "清空最近文件"))
        clear.triggered.connect(self._clear_recent)

    def _clear_recent(self) -> None:
        self.settings.clear_recent()
        self._show_status(self._tr("Recent files cleared", "已清空最近文件"))

    # ==================================================================
    # Signals
    # ==================================================================
    def _connect_signals(self) -> None:
        self.canvas.documentEdited.connect(self._on_canvas_edited)
        self.canvas.selectionChanged.connect(self._on_selection_changed)
        self.canvas.cursorInfoChanged.connect(self._on_cursor_info)
        self.canvas.contextMenuRequested.connect(self._show_context_menu)
        self.canvas.editStateChanged.connect(self._on_canvas_edit_state)
        self.canvas.toolChanged.connect(self._on_tool_changed)
        self.canvas.zoomChanged.connect(self._on_zoom_changed)
        self.editor_panel.contentChanged.connect(self._on_editor_content)
        self.editor_panel.applyRequested.connect(self._on_editor_apply)
        self.editor_panel.editor.textChanged.connect(self._on_editor_text_changed)
        self.splitter.splitterMoved.connect(lambda *_: self._splitter_timer.start())
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_focus_changed)

    # ==================================================================
    # Document lifecycle
    # ==================================================================
    def _json_text(self, indent: int | None = None) -> str:
        if indent is None:
            indent = int(self.settings.get("json_indent", 2))
        return self.doc.to_json_text(indent=indent)

    def _set_document(self, doc: WaveDocument, *, reset_view: bool = False) -> None:
        self.doc = doc
        self.doc.auto_extend_clocks = bool(self.settings.get("auto_extend_clocks", True))
        self.wave_view.set_document(doc, reset_view=reset_view)
        self.canvas = self.wave_view.canvas
        self._apply_canvas_theme()
        self.editor_panel.set_text(self._json_text(), reset_undo=True)
        self.editor_panel.mark_synced()
        self._sync_config_actions()
        self._update_title()
        self._update_actions()
        self._update_status()

    def new_document(self) -> None:
        if not self._maybe_save():
            return
        self.doc = WaveDocument(auto_extend_clocks=bool(self.settings.get("auto_extend_clocks", True)))
        self._set_document(self.doc, reset_view=True)
        self._show_status(self._tr("New diagram created", "已新建波形图"))
        self.canvas.setFocus(Qt.OtherFocusReason)

    def _open_dialog(self) -> None:
        start = self.settings.get("last_directory", "") or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._tr("Open WaveJSON", "打开 WaveJSON"),
            start,
            self._tr("WaveJSON files (*.json *.json5);;All files (*.*)", "WaveJSON 文件 (*.json *.json5);;所有文件 (*.*)"),
        )
        if path:
            self.open_file(path)

    def open_file(self, path: str) -> None:
        if not self._maybe_save():
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except OSError as exc:
            QMessageBox.critical(self, self._tr("Open failed", "打开失败"), str(exc))
            return
        doc = WaveDocument(auto_extend_clocks=bool(self.settings.get("auto_extend_clocks", True)))
        try:
            doc.load_json_text(text, source=path)
        except DocumentError as exc:
            location = ""
            if exc.line:
                location = self._tr(f"Line {exc.line}, column {exc.column}: ", f"第 {exc.line} 行，第 {exc.column} 列：")
            QMessageBox.critical(
                self,
                self._tr("Invalid JSON", "JSON 无效"),
                location + str(exc),
            )
            return
        self.doc = doc
        self._set_document(doc, reset_view=True)
        self.editor_panel.mark_synced()
        self.settings.add_recent(path)
        self._sync_config_actions()
        self._update_title()
        self._show_status(self._tr(f"Opened {Path(path).name}", f"已打开 {Path(path).name}"))
        if doc.notes:
            self._show_status("Note: " + " ".join(doc.notes[:2]), 8000)

    def _save_dialog(self) -> bool:
        start = self.doc.path or str(Path(self.settings.get("last_directory", "")) or Path.home())
        if start and not start.endswith((".json", ".json5")):
            start += ".json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._tr("Save WaveJSON", "保存 WaveJSON"),
            start,
            self._tr("WaveJSON files (*.json);;All files (*.*)", "WaveJSON 文件 (*.json);;所有文件 (*.*)"),
        )
        if not path:
            return False
        if not Path(path).suffix:
            path += ".json"
        return self.save_file(path)

    def save(self) -> bool:
        if not self.doc.path:
            return self._save_dialog()
        return self.save_file(self.doc.path)

    def save_file(self, path: str) -> bool:
        self.canvas.commit_editing()
        if self.editor_panel.has_error:
            QMessageBox.warning(
                self,
                self._tr("Cannot save", "无法保存"),
                self._tr(
                    "The JSON editor contains errors. Fix them before saving.",
                    "JSON 编辑器中有错误，请修正后再保存。",
                ),
            )
            return False
        # Apply any debounced but valid editor content first.
        self.editor_panel.flush_pending()
        if self.editor_panel.has_error:
            return False
        if not self.editor_panel.live_enabled:
            # In manual mode the editor text may not have been applied yet.
            if not self._apply_editor_text(self.editor_panel.text()):
                return False
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(self._json_text(), encoding="utf-8", newline="\n")
        except OSError as exc:
            QMessageBox.critical(self, self._tr("Save failed", "保存失败"), str(exc))
            return False
        self.doc.mark_saved(path)
        self._sync_editor_from_doc(force=True)
        self.settings.add_recent(path)
        self._update_title()
        self._update_status()
        self._show_status(self._tr(f"Saved {Path(path).name}", f"已保存 {Path(path).name}"))
        return True

    def _editor_text_dirty(self) -> bool:
        text = self.editor_panel.text().strip()
        if not text:
            return bool(self.doc.rows)
        return text != self._json_text().strip()

    def _on_editor_text_changed(self) -> None:
        self._update_title()
        self._update_status()

    def _maybe_save(self) -> bool:
        self.canvas.commit_editing()
        if not self.doc.dirty and not self._editor_text_dirty():
            return True
        box = QMessageBox(self)
        box.setWindowTitle(self._tr("Unsaved changes", "未保存的修改"))
        box.setText(self._tr("Save changes to the current diagram?", "是否保存当前波形图的修改？"))
        box.setIcon(QMessageBox.Question)
        save_button = box.addButton(QMessageBox.Save)
        discard_button = box.addButton(QMessageBox.Discard)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(save_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_button:
            return self.save()
        if clicked is discard_button:
            return True
        return False

    # ==================================================================
    # Editor synchronisation
    # ==================================================================
    def _on_editor_content(self, text: str) -> None:
        if self._applying_json:
            return
        self._apply_editor_text(text)

    def _on_editor_apply(self, text: str) -> None:
        self._apply_editor_text(text)

    def _apply_editor_text(self, text: str) -> bool:
        if not text.strip():
            self.editor_panel.set_error(self._tr("The document is empty.", "文档为空。"))
            return False
        if self._applying_json:
            return False
        self._applying_json = True
        try:
            try:
                parsed = WaveDocument.parse_json_text(text)
            except DocumentError as exc:
                self.editor_panel.set_error(str(exc), exc.line, exc.column)
                self._update_status()
                return False
            try:
                current = json.loads(self.doc.to_json_text())
            except Exception:
                current = None
            if current is not None and parsed == current:
                self.editor_panel.mark_synced()
                self._update_status()
                return True
            try:
                self.doc.apply_json_text(text)
            except DocumentError as exc:
                self.editor_panel.set_error(str(exc), exc.line, exc.column)
                self._update_status()
                return False
            except Exception as exc:  # noqa: BLE001
                self.editor_panel.set_error(str(exc))
                self._update_status()
                return False
            self.canvas.refresh()
            self.editor_panel.mark_synced()
            if self.editor_panel.text().strip() != self._json_text().strip():
                self.editor_panel.sync_status.setText(
                    self._tr("Applied (clocks extended)", "已应用（时钟已扩展）")
                )
            self._sync_config_actions()
            self._update_title()
            self._update_actions()
            self._update_status()
            if self.doc.notes:
                self._show_status("Note: " + " ".join(self.doc.notes[:2]), 7000)
            return True
        finally:
            self._applying_json = False

    def _sync_editor_from_doc(self, *, force: bool = False) -> None:
        if self.editor_panel.has_error and not force:
            self.editor_panel.sync_status.setText(
                self._tr("Waveform changed — fix JSON to sync", "波形已修改，修正 JSON 后同步")
            )
            return
        canonical = self._json_text()
        if self.editor_panel.text().strip() == canonical.strip():
            self.editor_panel.mark_synced()
            return
        self.editor_panel.set_text(canonical)
        self.editor_panel.mark_synced()

    def _on_focus_changed(self, old, new) -> None:
        if old is None:
            return
        editor = self.editor_panel.editor
        focus_was_editor = old is editor or editor.isAncestorOf(old) if isinstance(old, QWidget) else False
        focus_is_editor = new is editor or editor.isAncestorOf(new) if isinstance(new, QWidget) else False
        if focus_was_editor and not focus_is_editor:
            if not self.editor_panel.has_error:
                if self.editor_panel.text().strip() != self._json_text().strip():
                    self._apply_editor_text(self.editor_panel.text())
            self._update_actions()

    # ==================================================================
    # Canvas events
    # ==================================================================
    def _on_canvas_edited(self, reason: str) -> None:
        self._sync_editor_from_doc()
        self._update_title()
        self._update_actions()
        self._update_status()

    def _on_selection_changed(self) -> None:
        self._update_actions()
        self._update_status()

    def _on_cursor_info(self, text: str) -> None:
        self._cursor_info_text = text
        self.status_cursor.setText(text)

    def _on_tool_changed(self, tool: str) -> None:
        action = self.actions.get(f"tool_{tool}")
        if action:
            action.setChecked(True)
        self._update_status()

    def _on_zoom_changed(self, zoom: float) -> None:
        self.settings.set("zoom", round(zoom, 4), save=False)
        self._update_status()

    def _on_canvas_edit_state(self, editing: bool) -> None:
        self._inline_editing = editing
        self._update_actions()

    def _show_context_menu(self, global_pos: QPoint, row: int, col: int) -> None:
        menu = QMenu(self)
        menu.addAction(self.actions["edit_active"])
        menu.addAction(self.actions["edit_data"])
        menu.addSeparator()
        for action_id in ("row_cut", "row_copy", "row_paste", "row_duplicate", "row_delete"):
            menu.addAction(self.actions[action_id])
        menu.addSeparator()
        for action_id in ("row_insert_above", "row_insert_below", "row_properties", "row_clear"):
            menu.addAction(self.actions[action_id])
        menu.addSeparator()
        menu.addAction(self.actions["cell_copy"])
        menu.addAction(self.actions["cell_paste"])
        menu.addAction(self.actions["clear_cells"])
        menu.exec(global_pos)

    # ==================================================================
    # Action dispatch
    # ==================================================================
    def _dispatch(self, action_id: str, checked: bool = False) -> None:
        if action_id.startswith("tool_"):
            self.canvas.set_tool(action_id[5:])
            self.canvas.setFocus(Qt.OtherFocusReason)
            self._update_status()
            return
        if action_id in ("view_wave", "view_editor", "view_stacked", "view_side"):
            self._set_view_mode(action_id[5:])
            return
        handler = {
            "new": self.new_document,
            "open": self._open_dialog,
            "save": self.save,
            "save_as": self._save_dialog,
            "export_png": self._export_png,
            "export_svg": self._export_svg,
            "copy_image": self._copy_image,
            "quit": self.close,
            "undo": self._undo,
            "redo": self._redo,
            "select_all": self._select_all,
            "row_insert_above": lambda: self._insert_signal("above"),
            "row_insert_below": lambda: self._insert_signal("below"),
            "row_add": lambda: self._insert_signal("end"),
            "row_duplicate": self._duplicate_rows,
            "row_copy": self._copy_rows,
            "row_cut": self._cut_rows,
            "row_paste": self._paste_rows,
            "row_delete": self._delete_rows,
            "row_move_up": lambda: self._move_rows(-1),
            "row_move_down": lambda: self._move_rows(1),
            "row_properties": self._row_properties,
            "row_clear": self._clear_rows,
            "cell_copy": self._copy_cells,
            "cell_paste": self._paste_cells,
            "clear_cells": self._clear_cells,
            "edit_active": self._edit_active,
            "edit_data": self._edit_data,
            "add_column": self._add_column,
            "delete_column": self._delete_column,
            "extend_clocks": self._extend_clocks,
            "zoom_in": lambda: self.canvas.set_zoom(self.canvas.zoom * 1.15),
            "zoom_out": lambda: self.canvas.set_zoom(self.canvas.zoom / 1.15),
            "zoom_reset": lambda: self.canvas.set_zoom(1.0),
            "fit_width": self._fit_width,
            "toggle_theme": self._toggle_theme,
            "settings": lambda: self._open_settings(0),
            "show_shortcuts": lambda: self._open_settings(1),
            "relations": self._open_relations,
            "ascii_preview": self._show_ascii,
            "copy_ascii": self._copy_ascii,
            "toggle_live": self._toggle_live,
            "format_json": self._format_json,
            "find": lambda: self._show_find(False),
            "replace": lambda: self._show_find(True),
            "help": self._show_help,
        }.get(action_id)
        if handler is not None:
            handler()

    def _focus_is_editor(self) -> bool:
        focus = QApplication.focusWidget()
        return focus is self.code_editor or (focus is not None and self.code_editor.isAncestorOf(focus))

    def _undo(self) -> None:
        focus = QApplication.focusWidget()
        if focus is self.code_editor or (focus is not None and self.code_editor.isAncestorOf(focus)):
            self.code_editor.undo()
            return
        if focus is not None and focus.objectName() == "InlineEdit" and hasattr(focus, "undo"):
            focus.undo()
            return
        if self.doc.undo():
            self.canvas.refresh()
            self._sync_editor_from_doc()
            self._sync_config_actions()
            self._update_title()
            self._update_actions()
            self._update_status()
        else:
            self._show_status(self._tr("Nothing to undo", "没有可撤销的操作"))

    def _redo(self) -> None:
        focus = QApplication.focusWidget()
        if focus is self.code_editor or (focus is not None and self.code_editor.isAncestorOf(focus)):
            self.code_editor.redo()
            return
        if focus is not None and focus.objectName() == "InlineEdit" and hasattr(focus, "redo"):
            focus.redo()
            return
        if self.doc.redo():
            self.canvas.refresh()
            self._sync_editor_from_doc()
            self._sync_config_actions()
            self._update_title()
            self._update_actions()
            self._update_status()
        else:
            self._show_status(self._tr("Nothing to redo", "没有可重做的操作"))

    def _select_all(self) -> None:
        if self._focus_is_editor():
            self.code_editor.selectAll()
            return
        focus = QApplication.focusWidget()
        if focus is not None and focus.objectName() == "InlineEdit" and hasattr(focus, "selectAll"):
            focus.selectAll()
            return
        self.canvas.select_all_cells()

    # ==================================================================
    # Row operations
    # ==================================================================
    def _selected_rows(self) -> list[int]:
        rows = self.canvas.selected_rows()
        return rows or ([self.canvas.active_cell[0]] if self.canvas.active_cell else [])

    def _select_rows(self, rows: list[int]) -> None:
        if not self.doc.rows:
            self.canvas.row_selection = None
            self.canvas.active_cell = None
            return
        rows = [r for r in rows if 0 <= r < len(self.doc.rows)]
        if not rows:
            return
        self.canvas.row_selection = (min(rows), max(rows))
        self.canvas.active_cell = (min(rows), 0)
        self.canvas.selection = None
        self.canvas._anchor = None
        self.canvas.update()
        self.canvas.selectionChanged.emit()

    def _after_model_edit(self, *, selection: list[int] | None = None) -> None:
        self.canvas.refresh()
        if selection:
            self._select_rows(selection)
        self._sync_editor_from_doc()
        self._sync_config_actions()
        self._update_title()
        self._update_actions()
        self._update_status()
        self.canvas.setFocus(Qt.OtherFocusReason)

    def _unique_signal_name(self) -> str:
        names = {row.name for row in self.doc.rows}
        if "signal" not in names:
            return "signal"
        index = 2
        while f"signal{index}" in names:
            index += 1
        return f"signal{index}"

    def _insert_signal(self, where: str) -> None:
        rows = self._selected_rows()
        active = rows[0] if rows else len(self.doc.rows) - 1
        if where == "above":
            index = max(0, active)
        elif where == "below":
            index = min(len(self.doc.rows), active + 1)
        else:
            index = len(self.doc.rows)
        name = self._unique_signal_name()
        new_index = self.doc.insert_blank(index, name=name)
        self._after_model_edit(selection=[new_index])

    def _duplicate_rows(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        new_rows = self.doc.duplicate_rows(rows)
        self._after_model_edit(selection=new_rows)

    def _delete_rows(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        removed = self.doc.delete_rows(rows)
        if not removed:
            return
        if self.doc.rows:
            target = min(min(removed), len(self.doc.rows) - 1)
            self._after_model_edit(selection=[target])
        else:
            self.canvas.refresh()
            self._sync_editor_from_doc()
            self._update_title()
            self._update_actions()
            self._update_status()

    def _copy_rows(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        payload = self.doc.clipboard_payload(rows)
        QApplication.clipboard().setText(payload)
        count = len(rows)
        self._show_status(self._tr(f"Copied {count} signal(s)", f"已复制 {count} 条波形"))

    def _cut_rows(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        self._copy_rows()
        self._delete_rows()

    def _paste_rows(self) -> None:
        text = QApplication.clipboard().text()
        if not text.strip():
            self._show_status(self._tr("Clipboard is empty", "剪贴板为空"))
            return
        rows = self._selected_rows()
        index = (max(rows) + 1) if rows else len(self.doc.rows)
        new_rows = self.doc.paste_rows(text, index)
        if not new_rows:
            self._show_status(self._tr("Clipboard does not contain WaveJSON signals", "剪贴板中没有可粘贴的波形信号"))
            return
        self._after_model_edit(selection=new_rows)

    def _move_rows(self, direction: int) -> None:
        rows = sorted(self._selected_rows())
        if not rows:
            return
        first, last = rows[0], rows[-1]
        if direction < 0 and first <= 0:
            return
        if direction > 0 and last >= len(self.doc.rows) - 1:
            return
        target = first - 1 if direction < 0 else last + 2
        moved = self.doc.move_rows(rows, target)
        self._after_model_edit(selection=moved)

    def _clear_rows(self) -> None:
        rows = sorted(self._selected_rows())
        if not rows:
            return
        self.doc.clear_rows(rows)
        self._after_model_edit(selection=rows)

    def _row_properties(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        row = self.doc.row(rows[0])
        if row is None:
            return
        dialog = RowPropertiesDialog(self, row, language=self.language)
        if dialog.exec():
            changed = self.doc.update_row(rows[0], dialog.values())
            if changed:
                self._after_model_edit(selection=rows)

    def _add_column(self) -> None:
        self.doc.add_columns(1)
        self._after_model_edit()

    def _delete_column(self) -> None:
        col = self.canvas.active_cell[1] if self.canvas.active_cell else 0
        self.doc.delete_columns(col, 1)
        self._after_model_edit()

    def _extend_clocks(self) -> None:
        changed = self.doc.extend_clocks()
        if changed:
            self._after_model_edit()
            self._show_status(self._tr("Clocks extended to the longest signal", "时钟已扩展到最长信号"))
        else:
            self._show_status(self._tr("Clocks are already aligned", "时钟长度已一致"))

    def _clear_cells(self) -> None:
        cells = self.canvas.selected_cells()
        if not cells:
            return
        changed = self.doc.clear_cells(cells)
        if changed:
            self.canvas.refresh()
            self._sync_editor_from_doc()
            self._update_title()
            self._update_actions()
            self._update_status()

    def _copy_cells(self) -> None:
        text = self.canvas.cell_text()
        if not text:
            self._show_status(self._tr("Select waveform cells first", "请先选择波形单元格"))
            return
        QApplication.clipboard().setText(text)
        self._show_status(self._tr("Cells copied", "已复制单元格"))

    def _paste_cells(self) -> None:
        text = QApplication.clipboard().text()
        if not text.strip():
            return
        count = self.canvas.apply_wave_text(text)
        if count:
            self._show_status(self._tr(f"Pasted into {count} cell(s)", f"已粘贴到 {count} 个单元格"))
        else:
            self._show_status(self._tr("Clipboard is not a waveform string", "剪贴板不是波形字符串"))

    def _edit_active(self) -> None:
        self.canvas.edit_active()

    def _edit_data(self) -> None:
        if not self.canvas.active_cell:
            return
        row, col = self.canvas.active_cell
        row_layout = self.canvas._layout.rows[row]
        target = row_layout.data_target_at(row_layout.char_x(col) + row_layout.char_width / 2)
        if target is not None:
            self.canvas.edit_data_at(row, target.data_index)
        else:
            self._show_status(self._tr("The active cell has no data label", "当前单元格没有数据标签"))

    # ==================================================================
    # View / editor actions
    # ==================================================================
    def _set_view_mode(self, mode: str, *, initial: bool = False) -> None:
        if mode not in ("wave", "editor", "stacked", "side"):
            mode = "stacked"
        if not initial:
            self._save_splitter_ratios()
        if mode in ("stacked", "side"):
            self._last_split_mode = mode
        self._view_mode = mode
        both = mode in ("stacked", "side")
        self.wave_view.setVisible(mode != "editor")
        self.editor_panel.setVisible(mode != "wave")
        if both:
            self.splitter.setOrientation(Qt.Vertical if mode == "stacked" else Qt.Horizontal)
            ratios = self.settings.get("splitter", {}).get(mode, [0.46, 0.54])
            if not initial:
                QTimer.singleShot(0, lambda r=list(ratios), m=mode: self._apply_splitter_ratios(m, r))
        self.settings.set("view_mode", mode, save=False)
        self._sync_config_actions()
        if not initial:
            self.settings.save()
            if mode == "editor":
                self.code_editor.setFocus(Qt.OtherFocusReason)
            elif mode == "wave":
                self.canvas.setFocus(Qt.OtherFocusReason)
        self._update_actions()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            QTimer.singleShot(0, self._apply_initial_splitter)

    def _apply_initial_splitter(self) -> None:
        if self._view_mode not in ("stacked", "side"):
            return
        ratios = self.settings.get("splitter", {}).get(self._view_mode, [0.46, 0.54])
        self._apply_splitter_ratios(self._view_mode, ratios)

    def _apply_splitter_ratios(self, mode: str, ratios: list[float]) -> None:
        if mode != self._view_mode or not (0.0 < ratios[0] < 1.0):
            return
        total = self.splitter.width() if mode == "side" else self.splitter.height()
        if total <= 0:
            return
        first = int(total * ratios[0])
        second = max(1, total - first)
        self.splitter.setSizes([first, second])

    def _save_splitter_ratios(self) -> None:
        if self._view_mode not in ("stacked", "side"):
            return
        if not (self.wave_view.isVisible() and self.editor_panel.isVisible()):
            return
        sizes = self.splitter.sizes()
        total = sum(sizes)
        if total <= 0:
            return
        ratio = sizes[0] / total
        splitter = dict(self.settings.get("splitter", {}))
        splitter[self._view_mode] = [round(ratio, 4), round(1 - ratio, 4)]
        self.settings.set("splitter", splitter, save=False)

    def _show_find(self, replace: bool) -> None:
        if self._view_mode == "wave":
            self._set_view_mode(self._last_split_mode)
        self.editor_panel.show_find(replace=replace)

    def _format_json(self) -> None:
        if self._view_mode == "wave":
            self._set_view_mode(self._last_split_mode)
        self.editor_panel.format_text()
        if not self.editor_panel.has_error:
            self._apply_editor_text(self.editor_panel.text())
            self.editor_panel.mark_synced()
        self.editor_panel.focus_editor()

    def _toggle_live(self) -> None:
        enabled = not self.editor_panel.live_enabled
        self.editor_panel.set_live(enabled)
        self.settings.set("live_json_sync", enabled)
        self.actions["toggle_live"].setChecked(enabled)
        if enabled:
            self.editor_panel.flush_pending()
        self._update_status()
        self._show_status(
            self._tr("Live JSON synchronisation on", "实时 JSON 同步已开启")
            if enabled
            else self._tr("Live JSON synchronisation off", "实时 JSON 同步已关闭")
        )

    def _fit_width(self) -> None:
        if not self.wave_view.isVisible():
            self._set_view_mode(self._last_split_mode)
        available = max(200, self.wave_view.viewport().width() - 30)
        wave_width = max(1.0, self.canvas._layout.width - self.canvas._layout.wave_origin)
        new_zoom = self.canvas.zoom * available / wave_width
        self.canvas.set_zoom(new_zoom)

    # ==================================================================
    # Export / clipboard
    # ==================================================================
    def _export_png(self) -> None:
        self.canvas.commit_editing()
        self.editor_panel.flush_pending()
        start = str(Path(self.settings.get("last_directory", "")) or Path.home()) + os.sep + "waveform.png"
        path, _ = QFileDialog.getSaveFileName(
            self, self._tr("Export PNG", "导出 PNG"), start, self._tr("PNG images (*.png)", "PNG 图片 (*.png)")
        )
        if not path:
            return
        if not Path(path).suffix:
            path += ".png"
        try:
            image, _ = pixmap_for_document(self.doc, zoom=2.0)
            if not image.save(path, "PNG"):
                raise OSError("could not write PNG")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self._tr("Export failed", "导出失败"), str(exc))
            return
        self._show_status(self._tr(f"Exported {Path(path).name}", f"已导出 {Path(path).name}"))

    def _export_svg(self) -> None:
        self.canvas.commit_editing()
        self.editor_panel.flush_pending()
        start = str(Path(self.settings.get("last_directory", "")) or Path.home()) + os.sep + "waveform.svg"
        path, _ = QFileDialog.getSaveFileName(
            self, self._tr("Export SVG", "导出 SVG"), start, self._tr("SVG images (*.svg)", "SVG 图片 (*.svg)")
        )
        if not path:
            return
        if not Path(path).suffix:
            path += ".svg"
        try:
            skin = get_skin(self.doc.skin_name())
            layout = DiagramLayout(self.doc, zoom=1.6, skin=skin, chrome=False, placeholder=False)
            generator = QSvgGenerator()
            generator.setFileName(path)
            generator.setSize(QSize(max(1, int(layout.width)), max(1, int(layout.height))))
            generator.setViewBox(QRectF(0, 0, layout.width, layout.height))
            generator.setTitle("WaveDromGen")
            generator.setDescription("WaveJSON timing diagram generated by WaveDromGen")
            generator.setResolution(96)
            painter = QPainter(generator)
            painter.fillRect(QRectF(0, 0, layout.width, layout.height), skin.background)
            WaveRenderer(self._canvas_colors()).paint(
                painter,
                layout,
                PaintState(show_chrome=False, show_selection=False, focused=False),
            )
            painter.end()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self._tr("Export failed", "导出失败"), str(exc))
            return
        self._show_status(self._tr(f"Exported {Path(path).name}", f"已导出 {Path(path).name}"))

    def _copy_image(self) -> None:
        self.canvas.commit_editing()
        try:
            image, _ = pixmap_for_document(self.doc, zoom=2.0)
            QApplication.clipboard().setPixmap(QPixmap.fromImage(image))
            self._show_status(self._tr("Diagram copied as image", "波形图片已复制"))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self._tr("Copy failed", "复制失败"), str(exc))

    def _copy_ascii(self) -> None:
        text = document_to_ascii(self.doc)
        QApplication.clipboard().setText(text)
        self._show_status(self._tr("ASCII diagram copied", "ASCII 波形已复制"))

    def _show_ascii(self) -> None:
        dialog = AsciiDialog(self, document_to_ascii(self.doc), language=self.language)
        dialog.exec()

    # ==================================================================
    # Dialogs / settings
    # ==================================================================
    def _open_settings(self, tab_index: int = 0) -> None:
        dialog = SettingsDialog(
            self,
            settings=self.settings,
            registry=self.registry,
            shortcut_map=self.shortcut_map,
            language=self.language,
            tab_index=tab_index,
        )
        if not dialog.exec():
            return
        values = dialog.values()
        old_language = self.language
        old_theme = self.theme_name
        new_theme = values["theme"]
        self.shortcut_map = values["shortcuts"]
        self.settings.update(
            {
                "language": values["language"],
                "theme": values["theme"],
                "auto_extend_clocks": values["auto_extend_clocks"],
                "auto_advance_cell": values["auto_advance_cell"],
                "live_json_sync": values["live_json_sync"],
                "show_shortcut_help_on_start": values["show_shortcut_help_on_start"],
                "editor_wrap": values["editor_wrap"],
                "editor_font_size": values["editor_font_size"],
                "editor_indent": values["editor_indent"],
                "json_indent": values["json_indent"],
                "shortcuts": ShortcutRegistry.normalize_mapping(self.shortcut_map),
            },
            save=True,
        )
        self.language = values["language"]
        self.doc.auto_extend_clocks = values["auto_extend_clocks"]
        self.canvas.set_auto_advance(values["auto_advance_cell"])
        self.editor_panel.set_live(values["live_json_sync"])
        self.editor_panel.wrap_button.setChecked(values["editor_wrap"])
        self.editor_panel.code_editor.set_wrap(values["editor_wrap"])
        self.editor_panel.code_editor.set_editor_font(values["editor_font_size"])
        self.editor_panel.code_editor.set_indent(values["editor_indent"])
        self.editor_panel.json_indent = int(values["json_indent"])
        self.actions["toggle_live"].setChecked(values["live_json_sync"])
        if values["auto_extend_clocks"]:
            self.doc.extend_clocks(record=True)
            self.canvas.refresh()
            self._sync_editor_from_doc()
        self._apply_shortcuts()
        if self.language != old_language:
            self.retranslate_ui()
        if new_theme != old_theme or old_theme == "auto":
            self._apply_theme(new_theme)
        self._update_title()
        self._update_actions()
        self._update_status()
        self._show_status(self._tr("Preferences saved", "首选项已保存"))

    def _apply_shortcuts(self) -> None:
        apply_to_actions(self.actions, self.shortcut_map)
        self._update_action_texts()
        conflicts = ShortcutRegistry.conflicts(
            ShortcutRegistry.normalize_mapping(self.shortcut_map), self.language
        )
        if conflicts:
            seq, ids = conflicts[0]
            names = ", ".join(self.registry.label(i, self.language) for i in ids)
            self._show_status(
                self._tr(f"Shortcut conflict: {seq} ({names})", f"快捷键冲突：{seq}（{names}）"),
                6000,
            )

    def _show_help(self) -> None:
        dialog = ShortcutHelpDialog(
            self,
            registry=self.registry,
            shortcut_map=self.shortcut_map,
            language=self.language,
        )
        dialog.exec()

    def _show_about(self) -> None:
        AboutDialog(self, self.theme, language=self.language).exec()

    def _open_relations(self) -> None:
        dialog = RelationDialog(self, self.doc, language=self.language)
        if dialog.exec():
            self.doc.set_edges(dialog.edges())
            self._after_model_edit()

    # ------------------------------------------------------------------
    # Theme / config
    # ------------------------------------------------------------------
    def _canvas_colors(self) -> CanvasColors:
        t = self.theme
        return CanvasColors(
            accent=t.accent,
            accent_soft=QColor(t.accent.red(), t.accent.green(), t.accent.blue(), 38),
            hover=QColor(t.accent.red(), t.accent.green(), t.accent.blue(), 18),
            row_alt=QColor(15, 23, 42, 8),
            gutter=QColor("#f6f7f9"),
            header=QColor("#f6f7f9"),
            border=QColor("#e2e6ec"),
            muted=QColor("#8a93a3"),
            danger=t.danger,
            white=QColor("#ffffff"),
            text=t.text,
        )

    def _apply_canvas_theme(self) -> None:
        self.canvas.set_colors(self._canvas_colors())
        self.canvas.refresh()

    def _apply_theme(self, name: str, *, initial: bool = False) -> None:
        self.theme_name = name
        self.theme = resolve_theme(name)
        apply_theme(QApplication.instance(), self.theme, mono_size=float(self.settings.get("editor_font_size", 10.5)))
        self.editor_panel.set_theme(self.theme)
        self.editor_panel.code_editor.set_editor_font(float(self.settings.get("editor_font_size", 10.5)))
        if not self.editor_panel.has_error:
            self.editor_panel.mark_synced()
        self.wave_view.set_view_background(self.theme.background)
        self._apply_canvas_theme()
        self._apply_icons()
        self._update_status_styles()
        self.settings.set("theme", name, save=False)
        if not initial:
            self.settings.save()
        self._sync_config_actions()

    def _toggle_theme(self) -> None:
        new = "light" if self.theme.dark else "dark"
        self._apply_theme(new)
        self._show_status(self._tr(f"Theme: {new}", f"主题：{'深色' if new == 'dark' else '浅色'}"))

    def _set_skin(self, skin: str) -> None:
        if self.doc.set_skin(skin):
            self.canvas.refresh()
            self._sync_editor_from_doc()
            self._sync_config_actions()
            self._update_title()
            self._update_actions()
            self._show_status(self._tr(f"Skin: {skin}", f"皮肤：{skin}"))

    def _set_hscale(self, value: int) -> None:
        if self.doc.set_hscale(value):
            self.canvas.refresh()
            self._sync_editor_from_doc()
            self._sync_config_actions()
            self._update_title()
            self._update_actions()
            self._show_status(self._tr(f"Horizontal scale: {value}×", f"水平比例：{value}×"))

    def _set_language(self, language: str) -> None:
        if language not in ("en", "zh") or language == self.language:
            return
        self.language = language
        self.settings.set("language", language, save=True)
        self.retranslate_ui()
        self._show_status(self._tr("Language: English", "语言：中文"))

    def retranslate_ui(self) -> None:
        self._update_action_texts()
        self.editor_panel.set_language(self.language)
        self._create_menus()
        self._create_toolbar()
        self._update_status()
        self._update_title()
        self.canvas.update()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def _update_status_styles(self) -> None:
        t = self.theme
        if self.editor_panel.has_error:
            self.status_sync.setStyleSheet(f"color: {t.danger.name()}; font-weight: 600;")
        elif self.editor_panel.live_enabled:
            self.status_sync.setStyleSheet(f"color: {t.success.name()}; font-weight: 600;")
        else:
            self.status_sync.setStyleSheet(f"color: {t.muted.name()};")

    def _update_status(self) -> None:
        if not hasattr(self, "status_sync"):
            return
        if self.editor_panel.has_error:
            self.status_sync.setText(self._tr("● JSON error", "● JSON 错误"))
        elif self.editor_panel.live_enabled:
            self.status_sync.setText(self._tr("● Live", "● 实时同步"))
        else:
            self.status_sync.setText(self._tr("○ Manual", "○ 手动应用"))
        self.status_doc.setText(
            self._tr(
                f"{len(self.doc.rows)} signals · {self.doc.column_count} cells",
                f"{len(self.doc.rows)} 个信号 · {self.doc.column_count} 列",
            )
        )
        self.status_zoom.setText(f"{int(round(self.canvas.zoom * 100))}%")
        self._update_status_styles()

    def _update_title(self) -> None:
        name = Path(self.doc.path).name if self.doc.path else self._tr("Untitled", "未命名")
        star = " *" if (self.doc.dirty or self._editor_text_dirty()) else ""
        self.setWindowTitle(f"{name}{star} — {APP_NAME} {__version__}")

    def _show_status(self, message: str, timeout: int = 4500) -> None:
        if not hasattr(self, "status_message"):
            return
        self.status_message.setText(message)
        self._status_timer.start(max(500, int(timeout)))

    # ------------------------------------------------------------------
    # Actions enabled states
    # ------------------------------------------------------------------
    def _update_actions(self) -> None:
        if not hasattr(self, "canvas"):
            return
        has_rows = bool(self.doc.rows)
        has_selection = bool(self.canvas.selection or self.canvas.active_cell)
        canvas_scope = [d.id for d in self.registry.actions.values() if d.scope == "canvas"]
        always_available = {"row_add", "row_insert_above", "row_insert_below", "row_paste", "tool_select"}
        for action_id in canvas_scope:
            enabled = (has_rows or action_id in always_available) and not self._inline_editing
            if action_id in ("cell_copy", "cell_paste", "clear_cells"):
                enabled = enabled and has_selection and has_rows
            action = self.actions.get(action_id)
            if action is not None:
                action.setEnabled(enabled)
        multi = len(self.doc.rows) > 1 and not self._inline_editing
        self.actions["row_move_up"].setEnabled(multi)
        self.actions["row_move_down"].setEnabled(multi)
        self.actions["row_properties"].setEnabled(has_rows and not self._inline_editing)
        self.actions["row_clear"].setEnabled(has_rows and not self._inline_editing)
        self.actions["add_column"].setEnabled(has_rows)
        self.actions["delete_column"].setEnabled(has_rows)
        self.actions["extend_clocks"].setEnabled(has_rows)
        self.actions["relations"].setEnabled(has_rows)
        self.actions["ascii_preview"].setEnabled(has_rows)
        self.actions["copy_ascii"].setEnabled(has_rows)
        self.actions["export_png"].setEnabled(has_rows)
        self.actions["export_svg"].setEnabled(has_rows)
        self.actions["copy_image"].setEnabled(has_rows)
        self.actions["undo"].setEnabled(True)
        self.actions["redo"].setEnabled(True)
        self.actions["toggle_live"].setChecked(self.editor_panel.live_enabled)
        self._sync_config_actions()

    # ------------------------------------------------------------------
    # Window state / closing
    # ------------------------------------------------------------------
    def _restore_window_state(self) -> None:
        geometry = self.settings.get("window_geometry", "")
        restored = False
        if geometry:
            try:
                restored = self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
            except Exception:
                restored = False
        if not restored:
            screen = self.screen().availableGeometry() if self.screen() else None
            width = min(1280, (screen.width() - 100) if screen else 1280)
            height = min(820, (screen.height() - 100) if screen else 820)
            self.resize(max(920, width), max(560, height))
            if screen:
                frame = self.frameGeometry()
                frame.moveCenter(screen.center())
                self.move(frame.topLeft())

    def _save_window_state(self) -> None:
        try:
            geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.settings.set("window_geometry", geometry, save=False)
        except Exception:
            pass
        self._save_splitter_ratios()
        self.settings.set("zoom", round(self.canvas.zoom, 4), save=False)
        self.settings.save()

    def closeEvent(self, event) -> None:
        if not self._maybe_save():
            event.ignore()
            return
        self._save_window_state()
        event.accept()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith((".json", ".json5")):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".json", ".json5")):
                self.open_file(path)
                event.acceptProposedAction()
                return
        event.ignore()


# ======================================================================
# Helpers
# ======================================================================
def _skin_label(skin: str, language: str) -> str:
    if language == "zh":
        return {"default": "默认", "lowkey": "低调", "narrow": "紧凑", "dark": "深色"}.get(skin, skin)
    return {"default": "Default", "lowkey": "Low-key", "narrow": "Narrow", "dark": "Dark"}.get(skin, skin.title())


def _icon_for_action(action_id: str) -> str | None:
    mapping = {
        "new": "new",
        "open": "open",
        "save": "save",
        "save_as": "save",
        "export_png": "export",
        "export_svg": "export",
        "copy_image": "wave",
        "undo": "undo",
        "redo": "redo",
        "row_insert_above": "insert",
        "row_insert_below": "insert",
        "row_add": "add",
        "row_duplicate": "duplicate",
        "row_copy": "copy",
        "row_cut": "cut",
        "row_paste": "paste",
        "row_delete": "delete",
        "row_move_up": "up",
        "row_move_down": "down",
        "row_properties": "row_props",
        "row_clear": "clear",
        "cell_copy": "copy",
        "cell_paste": "paste",
        "clear_cells": "clear",
        "edit_active": "text",
        "edit_data": "text",
        "add_column": "columns",
        "delete_column": "columns",
        "extend_clocks": "clk",
        "view_wave": "wave",
        "view_editor": "editor",
        "view_stacked": "split_v",
        "view_side": "split_h",
        "zoom_in": "zoom_in",
        "zoom_out": "zoom_out",
        "zoom_reset": "fit",
        "fit_width": "fit_width",
        "toggle_theme": "theme",
        "settings": "settings",
        "show_shortcuts": "help",
        "relations": "relation",
        "ascii_preview": "ascii",
        "copy_ascii": "copy",
        "toggle_live": "live",
        "format_json": "format",
        "find": "search",
        "replace": "search",
        "help": "help",
        "quit": "new",
    }
    if action_id in mapping:
        return mapping[action_id]
    if action_id.startswith("tool_"):
        return action_id[5:]
    return None


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(APP_ICON)))
    ensure_fonts()
    settings = Settings()
    theme = resolve_theme(settings.get("theme", "light"))
    apply_theme(app, theme, mono_size=float(settings.get("editor_font_size", 10.5)))
    initial_path = None
    for arg in argv[1:]:
        if not arg.startswith("-") and Path(arg).exists():
            initial_path = arg
            break
    window = MainWindow(settings, initial_path=initial_path)
    window.show()
    return app.exec()
