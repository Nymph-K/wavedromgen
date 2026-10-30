# coding=utf-8
"""Main application window and entry point for WaveDromGen v2."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
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
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QTabBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .ascii_render import document_to_ascii
from .dialogs import (
    AboutDialog,
    AsciiDialog,
    DiagramSettingsDialog,
    RelationDialog,
    RowPropertiesDialog,
    SettingsDialog,
    ShortcutHelpDialog,
)
from .editor import JsonPanel
from .icons import has_icon, make_icon
from .layout import DiagramLayout
from .model import DocumentError, Selection, WaveDocument
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


@dataclass
class DocTab:
    """One open diagram tab (the document plus its per-tab editor state)."""

    doc: WaveDocument
    editor_text: str = ""
    selection: Selection | None = None
    active_cell: tuple[int, int] | None = None
    selected_rows: list[int] = field(default_factory=list)
    zoom: float = 1.0
    scroll: tuple[int, int] = (0, 0)
    title: str = ""


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
        self.tabs: list[DocTab] = []
        self._active_tab = -1
        self._switching_tab = False
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
        self._new_tab(self.doc, reset_view=True)
        self._restore_window_state()
        self._set_view_mode(settings.get("view_mode", "stacked"), initial=True)
        self.canvas.set_auto_advance(bool(settings.get("auto_advance_cell", True)))
        self.editor_panel.set_live(bool(settings.get("live_json_sync", True)))
        self.editor_panel.set_text(self._json_text(), reset_undo=True)
        self.editor_panel.mark_synced()
        self._capture_tab_state()
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
            action.setCheckable(
                action_id in checkable_tools
                or action_id in checkable_views
                or action_id in ("toggle_live", "toggle_insert_mode")
            )
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

        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("DocumentTabs")
        self.tab_bar.setExpanding(False)
        self.tab_bar.setMovable(True)
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setUsesScrollButtons(True)
        self.tab_bar.setElideMode(Qt.ElideRight)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.tab_bar.tabCloseRequested.connect(self._close_tab)
        self.tab_bar.setVisible(False)
        outer_layout.addWidget(self.tab_bar)
        outer_layout.addWidget(central, 1)
        self.setCentralWidget(outer)

        self.main_toolbar = QToolBar("Main")
        self.main_toolbar.setObjectName("MainToolBar")
        self.main_toolbar.setMovable(False)
        self.main_toolbar.setFloatable(False)
        self.main_toolbar.setIconSize(QSize(20, 20))
        self.main_toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.main_toolbar.setContextMenuPolicy(Qt.PreventContextMenu)
        self.addToolBar(Qt.TopToolBarArea, self.main_toolbar)

        self.palette_bar = QToolBar("Wave Palette")
        self.palette_bar.setObjectName("WavePalette")
        self.palette_bar.setMovable(False)
        self.palette_bar.setFloatable(False)
        self.palette_bar.setContextMenuPolicy(Qt.PreventContextMenu)
        self.addToolBarBreak(Qt.TopToolBarArea)
        self.addToolBar(Qt.TopToolBarArea, self.palette_bar)
        self._populate_palette()

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

    # ------------------------------------------------------------------
    # Waveform palette
    # ------------------------------------------------------------------
    PALETTE_GROUPS = (
        ("level", ("0", "1", "x", "z", ".")),
        ("bus", ("=", "2", "3", "4", "5", "6", "7", "8", "9", "u", "d")),
        ("clock", ("p", "n", "P", "N", "h", "l", "H", "L")),
        ("special", ("|", "<", ">")),
    )

    _WAVE_TOOLTIPS = {
        "0": ("Low level", "低电平"),
        "1": ("High level", "高电平"),
        "x": ("Unknown / don't care", "未知态"),
        ".": ("Continue the previous state", "保持前一个状态"),
        "z": ("High impedance", "高阻态"),
        "=": ("Data bus (consumes a data label)", "数据总线（占用一个 data 标签）"),
        "2": ("Data bus, colour 2", "数据总线 颜色 2"),
        "3": ("Data bus, colour 3", "数据总线 颜色 3"),
        "4": ("Data bus, colour 4", "数据总线 颜色 4"),
        "5": ("Data bus, colour 5", "数据总线 颜色 5"),
        "6": ("Data bus, colour 6", "数据总线 颜色 6"),
        "7": ("Data bus, colour 7", "数据总线 颜色 7"),
        "8": ("Data bus, colour 8", "数据总线 颜色 8"),
        "9": ("Data bus, colour 9", "数据总线 颜色 9"),
        "p": ("Positive-edge clock", "上升沿时钟"),
        "P": ("Positive-edge clock with an edge marker", "带边沿标记的上升沿时钟"),
        "n": ("Negative-edge clock", "下降沿时钟"),
        "N": ("Negative-edge clock with an edge marker", "带边沿标记的下降沿时钟"),
        "h": ("High clock phase", "时钟高相位"),
        "H": ("High clock phase with an edge marker", "带边沿标记的时钟高相位"),
        "l": ("Low clock phase", "时钟低相位"),
        "L": ("Low clock phase with an edge marker", "带边沿标记的时钟低相位"),
        "u": ("Bus up transition", "总线上升沿过渡"),
        "d": ("Bus down transition", "总线下降沿过渡"),
        "|": ("Waveform gap marker", "波形间隔标记"),
        "<": ("Start a sub-cycle (sharp) transition", "开始子周期（尖锐跳变）"),
        ">": ("End a sub-cycle (sharp) transition", "结束子周期（尖锐跳变）"),
    }

    def _palette_button(
        self,
        text: str,
        tooltip: str,
        callback,
        *,
        checkable: bool = False,
        category: str = "action",
        width: int | None = None,
    ) -> QToolButton:
        button = QToolButton(self.palette_bar)
        button.setObjectName("PaletteButton")
        button.setText(text)
        button.setToolTip(tooltip)
        button.setCheckable(checkable)
        button.setFocusPolicy(Qt.NoFocus)
        button.setCursor(Qt.PointingHandCursor)
        button.setProperty("paletteClass", category)
        if width is not None:
            button.setMinimumWidth(width)
        elif checkable:
            button.setMinimumWidth(42)
        elif len(text) == 1:
            button.setFixedWidth(26)
        else:
            button.setMinimumWidth(44)
        button.clicked.connect(lambda checked=False, fn=callback: fn())
        self.palette_bar.addWidget(button)
        # The dynamic property must be known before the stylesheet is polished.
        button.style().unpolish(button)
        button.style().polish(button)
        return button

    def _populate_palette(self) -> None:
        bar = self.palette_bar
        old_widgets = list(getattr(self, "palette_buttons", []))
        old_label = getattr(self, "palette_label", None)
        if old_label is not None:
            old_widgets.append(old_label)
        bar.clear()
        for widget in old_widgets:
            widget.setParent(None)
            widget.deleteLater()
        self.palette_buttons = []
        label = QLabel(self._tr("Draw", "绘制"))
        label.setObjectName("PaletteLabel")
        self.palette_label = label
        bar.addWidget(label)
        for index, (category, chars) in enumerate(self.PALETTE_GROUPS):
            if index:
                bar.addSeparator()
            for char in chars:
                en, zh = self._WAVE_TOOLTIPS.get(char, (char, char))
                tooltip = zh if self.language == "zh" else en
                button = self._palette_button(
                    char,
                    f"{tooltip}  —  {char}",
                    lambda c=char: self._apply_palette_char(c),
                    category=category,
                )
                self.palette_buttons.append(button)
        bar.addSeparator()
        self.palette_group_button = self._palette_button(
            self._tr("Group", "分组"),
            self._tr(
                "Wrap the selected signals in a named group (Ctrl+G)",
                "将选中信号建立为命名分组（Ctrl+G）",
            ),
            self._group_selection,
            width=50,
        )
        self.palette_ungroup_button = self._palette_button(
            self._tr("Ungroup", "取消分组"),
            self._tr(
                "Dissolve the selected group (Ctrl+Shift+G)",
                "取消选中的分组（Ctrl+Shift+G）",
            ),
            self._ungroup_selection,
            width=70,
        )
        self.palette_buttons.append(self.palette_group_button)
        self.palette_buttons.append(self.palette_ungroup_button)
        bar.addSeparator()
        self.palette_toggle = self._palette_button(
            self._tr("INS", "插入"),
            self._tr(
                "Insert mode: typing pushes the rest of the lane right (middle mouse)",
                "插入模式：输入波形时后续波形右移（鼠标中键切换）",
            ),
            self._on_palette_insert_clicked,
            checkable=True,
            width=40,
        )
        self.palette_buttons.append(self.palette_toggle)
        self.palette_buttons.append(
            self._palette_button(
                "<| cycle",
                self._tr("Insert one cycle before the selection", "在选区前插入一个周期"),
                lambda: self._insert_cycle(True),
                width=58,
            )
        )
        self.palette_buttons.append(
            self._palette_button(
                "cycle |>",
                self._tr("Insert one cycle after the selection", "在选区后插入一个周期"),
                lambda: self._insert_cycle(False),
                width=58,
            )
        )
        self.palette_buttons.append(
            self._palette_button(
                self._tr("Del", "删除"),
                self._tr("Delete the selected cycles", "删除选中的波形周期"),
                self._delete_cells,
                width=34,
            )
        )
        self.palette_buttons.append(
            self._palette_button(
                "{}",
                self._tr("Insert an empty {} row", "插入空行 {}"),
                self._insert_spacer,
                width=30,
            )
        )
        self.palette_toggle.blockSignals(True)
        self.palette_toggle.setChecked(self.canvas.insert_mode if hasattr(self, "canvas") else False)
        self.palette_toggle.blockSignals(False)

    def _apply_palette_char(self, char: str) -> None:
        if not self.doc.rows:
            return
        self.canvas.apply_char(char)
        self.canvas.setFocus(Qt.OtherFocusReason)

    def _on_palette_insert_clicked(self) -> None:
        if not hasattr(self, "canvas"):
            return
        wanted = self.palette_toggle.isChecked()
        if self.canvas.insert_mode != wanted:
            self.canvas.set_insert_mode(wanted)
        self.canvas.setFocus(Qt.OtherFocusReason)

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
        add(file_menu, "close_tab")
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
        add(edit_menu, "row_insert_spacer")
        edit_menu.addSeparator()
        add(edit_menu, "delete_cells")
        add(edit_menu, "insert_cycle_before")
        add(edit_menu, "insert_cycle_after")
        add(edit_menu, "toggle_insert_mode")
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
        add(signal_menu, "group_selection")
        add(signal_menu, "ungroup_selection")
        add(signal_menu, "rename_group")
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
        add(view_menu, "next_tab")
        add(view_menu, "prev_tab")
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
        add(tools_menu, "diagram_config")
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
        self.canvas.insertModeChanged.connect(self._on_insert_mode_changed)
        self.canvas.waveFocusChanged.connect(self._on_wave_focus)
        self.canvas.groupRenameRequested.connect(self._rename_group_at)
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

    def _set_document(
        self, doc: WaveDocument, *, reset_view: bool = False, editor_text: str | None = None
    ) -> None:
        self.doc = doc
        self.doc.auto_extend_clocks = bool(self.settings.get("auto_extend_clocks", True))
        self.wave_view.set_document(doc, reset_view=reset_view)
        self.canvas = self.wave_view.canvas
        self._apply_canvas_theme()
        restored = editor_text if editor_text else self._json_text()
        self.editor_panel.set_text(restored, reset_undo=True)
        if editor_text and editor_text.strip() != self._json_text().strip():
            # Restore unapplied (possibly invalid) editor content of the tab.
            self._apply_editor_text(editor_text)
        else:
            self.editor_panel.mark_synced()
        self._sync_config_actions()
        self._update_title()
        self._update_actions()
        self._update_status()

    # ------------------------------------------------------------------
    # Document tabs
    # ------------------------------------------------------------------
    def _current_tab(self) -> DocTab | None:
        if 0 <= self._active_tab < len(self.tabs):
            return self.tabs[self._active_tab]
        return None

    def _capture_tab_state(self) -> None:
        tab = self._current_tab()
        if tab is None:
            return
        tab.doc = self.doc
        if hasattr(self, "editor_panel"):
            tab.editor_text = self.editor_panel.text()
        if hasattr(self, "canvas"):
            tab.selection = self.canvas.selection
            tab.active_cell = self.canvas.active_cell
            tab.selected_rows = self.canvas.row_selection_rows
            tab.zoom = self.canvas.zoom
        if hasattr(self, "wave_view"):
            tab.scroll = (
                self.wave_view.horizontalScrollBar().value(),
                self.wave_view.verticalScrollBar().value(),
            )

    def _tab_title(self, tab: DocTab) -> str:
        name = Path(tab.doc.path).name if tab.doc.path else self._tr("Untitled", "未命名")
        dirty = tab.doc.dirty
        if not dirty:
            if tab is self._current_tab() and hasattr(self, "editor_panel"):
                text = self.editor_panel.text().strip()
            else:
                text = (tab.editor_text or "").strip()
            if text:
                try:
                    dirty = text != tab.doc.to_json_text().strip()
                except Exception:
                    dirty = False
        return f"{name} •" if dirty else name

    def _refresh_tab_titles(self) -> None:
        if not hasattr(self, "tab_bar"):
            return
        for index, tab in enumerate(self.tabs):
            if index < self.tab_bar.count():
                title = self._tab_title(tab)
                if self.tab_bar.tabText(index) != title:
                    self.tab_bar.setTabText(index, title)
                path = tab.doc.path or self._tr("Unsaved diagram", "未保存的波形图")
                self.tab_bar.setTabToolTip(index, path)
        self.tab_bar.setVisible(len(self.tabs) > 1)

    def _new_tab(
        self,
        doc: WaveDocument | None = None,
        *,
        reset_view: bool = True,
        editor_text: str | None = None,
    ) -> DocTab:
        doc = doc or WaveDocument(
            auto_extend_clocks=bool(self.settings.get("auto_extend_clocks", True))
        )
        tab = DocTab(doc=doc, editor_text=editor_text or "", zoom=self.canvas.zoom if hasattr(self, "canvas") else 1.0)
        self._capture_tab_state()
        self.tabs.append(tab)
        self.tab_bar.blockSignals(True)
        self.tab_bar.addTab("")
        self.tab_bar.blockSignals(False)
        self._active_tab = len(self.tabs) - 1
        self._activate_tab(self._active_tab, reset_view=reset_view, editor_text=editor_text)
        return tab

    def _on_tab_changed(self, index: int) -> None:
        if self._switching_tab or index < 0:
            return
        self._activate_tab(index)

    def _activate_tab(
        self, index: int, *, reset_view: bool = False, editor_text: str | None = None
    ) -> None:
        if index < 0 or index >= len(self.tabs):
            return
        if (
            self._active_tab == index
            and self.tabs[index].doc is self.doc
            and hasattr(self, "wave_view")
            and self.wave_view.canvas.doc is self.doc
            and editor_text is None
            and not reset_view
        ):
            return
        self._switching_tab = True
        try:
            previous = self._current_tab()
            if previous is not None and index != self._active_tab:
                self._capture_tab_state()
            self._active_tab = index
            tab = self.tabs[index]
            self.doc = tab.doc
            text = editor_text if editor_text is not None else (tab.editor_text or None)
            self._set_document(tab.doc, reset_view=reset_view, editor_text=text)
            self._apply_tab_state(tab)
            self.tab_bar.blockSignals(True)
            self.tab_bar.setCurrentIndex(index)
            self.tab_bar.blockSignals(False)
            self._refresh_tab_titles()
            self._update_actions()
            self._update_status()
            self._update_title()
        finally:
            self._switching_tab = False

    def _apply_tab_state(self, tab: DocTab) -> None:
        canvas = self.canvas
        canvas.zoom = max(0.45, min(3.0, float(tab.zoom or 1.0)))
        canvas.selection = tab.selection
        canvas.active_cell = (
            tab.active_cell if tab.active_cell is not None else ((0, 0) if tab.doc.rows else None)
        )
        canvas._selected_rows = [
            index for index in tab.selected_rows if 0 <= index < len(tab.doc.rows)
        ]
        if canvas.active_cell is not None:
            canvas._anchor = canvas.active_cell
        else:
            canvas._anchor = None
        canvas.refresh()
        h, v = tab.scroll
        self.wave_view.horizontalScrollBar().setValue(max(0, h))
        self.wave_view.verticalScrollBar().setValue(max(0, v))

    def _close_tab(self, index: int) -> None:
        if not (0 <= index < len(self.tabs)):
            return
        if index != self._active_tab:
            self._activate_tab(index)
        self.canvas.commit_editing()
        if not self._maybe_save():
            return
        self.tabs.pop(index)
        self.tab_bar.blockSignals(True)
        self.tab_bar.removeTab(index)
        self.tab_bar.blockSignals(False)
        self._active_tab = -1
        if not self.tabs:
            self._new_tab()
            return
        new_index = min(index, len(self.tabs) - 1)
        self.tab_bar.blockSignals(True)
        self.tab_bar.setCurrentIndex(new_index)
        self.tab_bar.blockSignals(False)
        self._activate_tab(new_index)

    def new_tab(self) -> None:
        self._new_tab()

    def next_tab(self) -> None:
        if len(self.tabs) < 2:
            return
        self._activate_tab((self._active_tab + 1) % len(self.tabs))

    def previous_tab(self) -> None:
        if len(self.tabs) < 2:
            return
        self._activate_tab((self._active_tab - 1) % len(self.tabs))

    def close_current_tab(self) -> None:
        self._close_tab(self._active_tab)

    def new_document(self) -> None:
        doc = WaveDocument(auto_extend_clocks=bool(self.settings.get("auto_extend_clocks", True)))
        self._new_tab(doc, reset_view=True)
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

    def _find_open_tab(self, path: str) -> int | None:
        try:
            target = Path(path).resolve()
        except OSError:
            target = Path(path)
        for index, tab in enumerate(self.tabs):
            if not tab.doc.path:
                continue
            try:
                if Path(tab.doc.path).resolve() == target:
                    return index
            except OSError:
                continue
        return None

    def open_file(self, path: str) -> None:
        existing = self._find_open_tab(path)
        if existing is not None:
            self._activate_tab(existing)
            self._show_status(self._tr(f"Switched to {Path(path).name}", f"已切换到 {Path(path).name}"))
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
        # Replace a pristine untitled tab instead of opening yet another one.
        if (
            self._current_tab() is not None
            and not self.doc.path
            and self._is_default_document()
        ):
            tab = self.tabs[self._active_tab]
            tab.doc = doc
            tab.editor_text = ""
            tab.selection = None
            tab.active_cell = None
            tab.selected_rows = []
            self._set_document(doc, reset_view=True)
            self._refresh_tab_titles()
        else:
            self._new_tab(doc, reset_view=True)
        self.settings.add_recent(path)
        self._sync_config_actions()
        self._update_title()
        self._show_status(self._tr(f"Opened {Path(path).name}", f"已打开 {Path(path).name}"))
        if doc.notes:
            self._show_status("Note: " + " ".join(doc.notes[:2]), 8000)

    def _is_default_document(self) -> bool:
        """True when the active tab still holds the untouched sample document."""
        if self.doc.path or self.doc.dirty:
            return False
        if self._editor_text_dirty():
            return False
        try:
            return self.doc.snapshot() == WaveDocument().snapshot()
        except Exception:
            return False

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
        self._sync_editor_wave_focus()
        self._update_title()
        self._update_actions()
        self._update_status()

    def _sync_editor_wave_focus(self) -> None:
        """Re-apply the wave-line highlight after the editor text was refreshed."""
        if self._inline_editing or self._view_mode == "wave" or not self.canvas.hasFocus():
            return
        selection = self.canvas.selection
        if selection is not None:
            sel = selection.normalized()
            self.editor_panel.focus_wave(
                list(range(sel.row0, sel.row1 + 1)), sel.col0, sel.col1
            )
            return
        rows = self.canvas.selected_rows()
        if rows:
            self.editor_panel.focus_wave(rows, -1, -1)

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

    def _on_insert_mode_changed(self, enabled: bool) -> None:
        action = self.actions.get("toggle_insert_mode")
        if action is not None:
            action.setChecked(enabled)
        if hasattr(self, "palette_toggle"):
            self.palette_toggle.blockSignals(True)
            self.palette_toggle.setChecked(enabled)
            self.palette_toggle.blockSignals(False)
        if enabled:
            self._show_status(
                self._tr(
                    "Insert mode: type wave characters, Esc or middle-click to exit",
                    "插入模式：输入波形字符，按 Esc 或中键退出",
                ),
                6000,
            )
        else:
            self._update_status()
        self._update_actions()

    def _on_wave_focus(self, rows, start: int, end: int) -> None:
        """Follow the waveform selection in the JSON editor (requirement 4.7)."""
        if self._inline_editing or self._switching_tab or self._applying_json:
            return
        if self._view_mode == "wave" or not self.canvas.hasFocus():
            return
        if isinstance(rows, int):
            rows = [rows]
        self.editor_panel.focus_wave(rows, start, end)

    def _on_canvas_edit_state(self, editing: bool) -> None:
        self._inline_editing = editing
        self._update_actions()

    def _show_context_menu(self, global_pos: QPoint, row: int, col: int) -> None:
        menu = self._build_context_menu()
        menu.exec(global_pos)

    def _build_context_menu(self) -> QMenu:
        """Build the waveform context menu (separate for testability)."""
        menu = QMenu(self)
        menu.addAction(self.actions["edit_active"])
        menu.addAction(self.actions["edit_data"])
        menu.addSeparator()
        for action_id in ("row_cut", "row_copy", "row_paste", "row_duplicate", "row_delete"):
            menu.addAction(self.actions[action_id])
        menu.addSeparator()
        group_span = self.canvas.selected_group_span()
        if group_span is not None:
            menu.addAction(self.actions["ungroup_selection"])
            menu.addAction(self.actions["rename_group"])
        else:
            menu.addAction(self.actions["group_selection"])
        menu.addSeparator()
        for action_id in ("row_insert_above", "row_insert_below", "row_insert_spacer", "row_properties", "row_clear"):
            menu.addAction(self.actions[action_id])
        timing = menu.addMenu(self._tr("Period / Phase", "周期 / 相位"))
        for label, callback in (
            (self._tr("Period +1", "Period +1"), lambda: self._adjust_period(1)),
            (self._tr("Period −1", "Period −1"), lambda: self._adjust_period(-1)),
            (self._tr("Phase +0.5", "Phase +0.5"), lambda: self._adjust_phase(0.5)),
            (self._tr("Phase −0.5", "Phase −0.5"), lambda: self._adjust_phase(-0.5)),
        ):
            item = timing.addAction(label)
            item.triggered.connect(lambda checked=False, fn=callback: fn())
        timing.addAction(self.actions["row_properties"])
        menu.addSeparator()
        for action_id in ("delete_cells", "insert_cycle_before", "insert_cycle_after", "toggle_insert_mode"):
            menu.addAction(self.actions[action_id])
        menu.addSeparator()
        menu.addAction(self.actions["cell_copy"])
        menu.addAction(self.actions["cell_paste"])
        menu.addAction(self.actions["clear_cells"])
        return menu

    def _adjust_period(self, delta: int) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        row = self.doc.row(rows[0])
        if row is None:
            return
        if self.doc.set_period(rows[0], row.period + delta):
            self._after_model_edit(selection=rows)

    def _adjust_phase(self, delta: float) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        row = self.doc.row(rows[0])
        if row is None:
            return
        if self.doc.set_phase(rows[0], max(0.0, row.phase + delta)):
            self._after_model_edit(selection=rows)

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
            "row_insert_spacer": self._insert_spacer,
            "delete_cells": self._delete_cells,
            "insert_cycle_before": lambda: self._insert_cycle(True),
            "insert_cycle_after": lambda: self._insert_cycle(False),
            "toggle_insert_mode": self._toggle_insert_mode,
            "group_selection": self._group_selection,
            "ungroup_selection": self._ungroup_selection,
            "rename_group": lambda: self._rename_group_at(*self._active_group_range()),
            "diagram_config": self._open_diagram_settings,
            "next_tab": self.next_tab,
            "prev_tab": self.previous_tab,
            "close_tab": self.close_current_tab,
            "row_duplicate": self._duplicate_rows,
            "row_copy": self._copy_selection,
            "row_cut": self._cut_rows,
            "row_paste": self._paste_selection,
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
            self.canvas.set_row_selection([])
            self.canvas.active_cell = None
            return
        rows = [r for r in rows if 0 <= r < len(self.doc.rows)]
        if not rows:
            return
        self.canvas.set_row_selection(rows)
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
        if where == "end":
            # Ctrl+Enter: jump straight into the new signal's name field.
            self.canvas.edit_name_at(new_index)

    def _insert_spacer(self) -> None:
        rows = self._selected_rows()
        index = (rows[-1] + 1) if rows else len(self.doc.rows)
        new_index = self.doc.add_spacer_row(index)
        self._after_model_edit(selection=[new_index])
        self._show_status(self._tr("Inserted empty row {}", "已插入空行 {}"))

    def _delete_cells(self) -> None:
        self.canvas.delete_selection()

    def _insert_cycle(self, before: bool) -> None:
        changed = self.canvas.insert_cycles(before=before)
        if changed:
            self._show_status(
                self._tr("Inserted one cycle", "已插入一个波形周期")
            )
        self.canvas.setFocus(Qt.OtherFocusReason)

    def _toggle_insert_mode(self) -> None:
        self.canvas.set_insert_mode(not self.canvas.insert_mode)
        self.canvas.setFocus(Qt.OtherFocusReason)

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

    # ------------------------------------------------------------------
    # Context-sensitive clipboard (Ctrl+C / Ctrl+V)
    # ------------------------------------------------------------------
    def _has_cell_selection(self) -> bool:
        """True when the canvas has a waveform-cell selection.

        A row selection (left gutter, group bracket, middle-row drag) always
        wins: it copies signals/groups rather than a column of cells.
        """
        return bool(
            self.canvas.selection is not None
            and not self.canvas.row_selection_rows
            and self.canvas.selected_cells()
        )

    def _copy_selection(self) -> None:
        """Ctrl+C: copy waveform cells or whole signal rows, by context."""
        if self._has_cell_selection():
            self._copy_cells()
        else:
            self._copy_rows()

    def _paste_selection(self) -> None:
        """Ctrl+V: paste a waveform block or WaveJSON signals, by context."""
        if self._has_cell_selection():
            text = QApplication.clipboard().text()
            stripped = text.lstrip()
            if stripped and not stripped.startswith(("{", "[")):
                self._paste_cells()
                return
        self._paste_rows()

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

    # ------------------------------------------------------------------
    # Signal groups
    # ------------------------------------------------------------------
    def _active_group_range(self) -> tuple[int, int]:
        span = self.canvas.selected_group_span()
        if span is not None:
            return span.start, span.end
        rows = self._selected_rows()
        if rows:
            return min(rows), max(rows)
        return 0, -1

    def _group_selection(self) -> None:
        rows = sorted(self._selected_rows())
        if not rows:
            self._show_status(self._tr("Select one or more signals first", "请先选择要分组的信号"))
            return
        title = self._tr("Group Signals", "信号分组")
        label = self._tr("Group name:", "分组名称：")
        name, ok = QInputDialog.getText(self, title, label, text="group")
        if not ok:
            return
        name = (name or "").strip() or "group"
        new_rows = self.doc.group_rows(rows, name)
        if not new_rows:
            return
        self._after_model_edit(selection=new_rows)
        self._show_status(self._tr(f'Created group "{name}"', f'已创建分组“{name}”'))

    def _ungroup_selection(self) -> None:
        rows = sorted(self._selected_rows())
        if not rows:
            self._show_status(self._tr("Select a group first", "请先选择分组"))
            return
        new_rows = self.doc.ungroup_rows(rows)
        if not new_rows:
            self._show_status(self._tr("The selection is not a complete group", "所选内容不是完整的分组"))
            return
        self._after_model_edit(selection=new_rows)
        self._show_status(self._tr("Group dissolved", "已取消分组"))

    def _rename_group_at(self, start: int, end: int) -> None:
        if end < start:
            return
        span = self.doc.span_at_row(start)
        if span is None:
            span = self.doc.span_at_row(end)
        if span is None:
            self._show_status(self._tr("No group at the selection", "所选位置没有分组"))
            return
        title = self._tr("Rename Group", "重命名分组")
        label = self._tr("Group name:", "分组名称：")
        current = span.group.display_name
        name, ok = QInputDialog.getText(self, title, label, text=current)
        if not ok:
            return
        name = (name or "").strip()
        if not name or name == current:
            return
        if self.doc.rename_group(span.start, name):
            self._after_model_edit(selection=list(range(span.start, span.end + 1)))
            self._show_status(self._tr(f'Renamed group to "{name}"', f'分组已重命名为“{name}”'))

    def _open_diagram_settings(self) -> None:
        dialog = DiagramSettingsDialog(self, self.doc, language=self.language)
        if not dialog.exec():
            return
        values = dialog.values()
        changed = self.doc.apply_diagram_settings(
            skin=values["skin"],
            hscale=values["hscale"],
            head=values["head"],
            foot=values["foot"],
        )
        if changed:
            self._after_model_edit()
            self._show_status(self._tr("Diagram settings applied", "波形图设置已应用"))
        else:
            self.canvas.refresh()
            self._sync_editor_from_doc()

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
        count = self.canvas.apply_wave_block(text)
        if count:
            rows = len([line for line in text.replace("\r\n", "\n").split("\n") if line])
            if rows > 1:
                self._show_status(
                    self._tr(
                        f"Pasted a {rows}-row waveform block",
                        f"已粘贴 {rows} 行波形块",
                    )
                )
            else:
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
    def _export_default_path(self, suffix: str) -> str:
        """Default export path: the current file name in the last export folder."""
        doc = self.doc
        directory = self.settings.get("export_directory", "") or ""
        if not directory:
            if doc.path:
                directory = str(Path(doc.path).parent)
            else:
                directory = str(self.settings.get("last_directory", "") or Path.home())
        stem = Path(doc.path).stem if doc.path else self._tr("waveform", "waveform")
        return str(Path(directory) / f"{stem}{suffix}")

    def _remember_export_path(self, path: str) -> None:
        try:
            directory = str(Path(path).resolve().parent)
        except OSError:
            directory = str(Path(path).parent)
        self.settings.set("export_directory", directory, save=True)

    def _export_png(self) -> None:
        self.canvas.commit_editing()
        self.editor_panel.flush_pending()
        start = self._export_default_path(".png")
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
        self._remember_export_path(path)
        self._show_status(self._tr(f"Exported {Path(path).name}", f"已导出 {Path(path).name}"))

    def _export_svg(self) -> None:
        self.canvas.commit_editing()
        self.editor_panel.flush_pending()
        start = self._export_default_path(".svg")
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
        self._remember_export_path(path)
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
                "link_wave_skin_to_theme": values["link_wave_skin_to_theme"],
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
        else:
            self._sync_wave_skin_for_theme()
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
        self._sync_wave_skin_for_theme()

    def _sync_wave_skin_for_theme(self) -> None:
        """Keep the waveform skin in sync with the dark/light UI theme."""
        if not self.settings.get("link_wave_skin_to_theme", True):
            return
        if not hasattr(self, "doc") or self.doc is None or not hasattr(self, "canvas"):
            return
        current = self.doc.skin_name()
        if self.theme.dark:
            if current == "dark":
                return
            self.settings.set("light_skin", current, save=False)
            target = "dark"
        else:
            if current != "dark":
                return
            target = self.settings.get("light_skin", "default") or "default"
        mark_dirty = bool(self.doc.path) or self.doc.dirty
        if self.doc.set_skin(target, record=False, mark_dirty=mark_dirty):
            self.canvas.refresh()
            self._sync_editor_from_doc()
            self._sync_config_actions()
            self._update_title()
            self._update_status()

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
        self._populate_palette()
        self._update_actions()
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
        if hasattr(self, "tab_bar"):
            self._refresh_tab_titles()

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
        always_available = {
            "row_add",
            "row_insert_above",
            "row_insert_below",
            "row_insert_spacer",
            "row_paste",
            "tool_select",
        }
        for action_id in canvas_scope:
            enabled = (has_rows or action_id in always_available) and not self._inline_editing
            if action_id in ("cell_copy", "cell_paste", "clear_cells", "delete_cells"):
                enabled = enabled and has_selection and has_rows
            if action_id in ("group_selection", "ungroup_selection", "rename_group"):
                enabled = enabled and bool(self._selected_rows()) and has_rows
            action = self.actions.get(action_id)
            if action is not None:
                action.setEnabled(enabled)
        multi = len(self.doc.rows) > 1 and not self._inline_editing
        self.actions["row_move_up"].setEnabled(multi)
        self.actions["row_move_down"].setEnabled(multi)
        self.actions["next_tab"].setEnabled(len(self.tabs) > 1)
        self.actions["prev_tab"].setEnabled(len(self.tabs) > 1)
        self.actions["close_tab"].setEnabled(len(self.tabs) >= 1)
        self.actions["diagram_config"].setEnabled(True)
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
        palette_enabled = has_rows and not self._inline_editing
        for button in getattr(self, "palette_buttons", []):
            button.setEnabled(palette_enabled)
        if hasattr(self, "palette_group_button"):
            self.palette_group_button.setEnabled(palette_enabled)
            self.palette_ungroup_button.setEnabled(
                palette_enabled and self.canvas.selected_group_span() is not None
            )
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
        if not self._confirm_close_all_tabs():
            event.ignore()
            return
        self._save_window_state()
        event.accept()

    def _confirm_close_all_tabs(self) -> bool:
        self.canvas.commit_editing()
        self._capture_tab_state()
        for index in range(len(self.tabs)):
            if index != self._active_tab:
                self._activate_tab(index)
            if not self._maybe_save():
                return False
        return True

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
