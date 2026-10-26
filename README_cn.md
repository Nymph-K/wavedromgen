<p align="center"><img src="asset/md/logo.png" width="96" alt="WaveDromGen logo"></p>

# WaveDromGen v2

**基于 Qt 的图形化数字时序图编辑器，兼容 WaveDrom 渲染，支持 JSON 实时双向同步与直接编辑波形。**

![WaveDromGen v2 主界面](asset/md/v2_main.png)

WaveDromGen 让你既能像 WaveDrom 一样写 WaveJSON，也能像绘图工具一样直接点击、框选和拖动波形。波形渲染使用 WaveDrom 官方皮肤几何与符号，导出的图与 WaveDrom 一致，同时每个单元格都可以交互编辑。

> English documentation: [README.md](README.md)

---

## 主要特性

| | 功能 |
|---|---|
| ✏️ | **双击直接编辑文字**：双击信号名或总线 `data` 标签即可输入；按 <kbd>Enter</kbd>/<kbd>Tab</kbd> 自动提交并跳到下一个可编辑名称/数据标签，<kbd>Shift</kbd>+<kbd>Tab</kbd> 回到上一个，<kbd>Esc</kbd> 取消。 |
| ↕️ | **拖动排序**：按住左侧行号区域上下拖动信号，蓝色插入线显示目标位置；<kbd>Alt</kbd>+<kbd>↑</kbd>/<kbd>↓</kbd> 也可移动。 |
| ↔️ | **上下/左右分栏**：波形与 JSON 编辑器可上下、左右分栏或单独显示；合法 JSON 实时渲染到波形，波形编辑实时更新 JSON。 |
| ⏱️ | **时钟自动扩展**：名称包含 `clk`/`clock` 的信号自动拉长到最长信号；矩形时钟按周期平铺。 |
| ➕ | **信号增删改**：添加、插入、删除、复制、粘贴、清空一条波形，全部提供可配置快捷键。 |
| 🖱️ | **框选 + 波形字符**：拖动选择任意单元格区域，直接输入 `0 1 x z = u d p P n N l L h H 2..9 \| .` 等 WaveDrom 字符完成批量编辑。 |
| ⌨️ | **快捷键可配置**：60 个操作，支持按键捕获、冲突检测、恢复默认并保存到配置文件。 |
| 🎨 | **GUI 优化**：浅色/深色主题、中英文界面、缩放、时间标尺、选中高亮、右键菜单、最近文件、工具栏与工具侧栏。 |
| 🧩 | **兼容 WaveJSON**：支持 `period`、`phase`、`data`、`node`、`edge`、`head`/`foot`、皮肤与未知字段保留。 |
| 🪶 | **轻量编辑器**：行号、当前行高亮、JSON/JSON5 语法高亮、智能缩进、查找替换、格式化、错误行标记。 |

![双击编辑 data 标签](asset/md/v2_inline_edit.png)

---

## 安装与运行

需要 **Python 3.10+**。

```bash
git clone https://github.com/Nymph-K/wavedromgen.git
cd wavedromgen
python -m pip install -r requirements.txt
python main.py
```

直接打开示例：

```bash
python main.py examples/demo.json
```

Windows 下可打包为单文件 exe：

```bash
python -m pip install pyinstaller
python package2exe.py
```

生成文件位于 `dist/WaveDromGen.exe`。

---

## 使用说明

### 1. 名称与数据标签

双击信号名或总线标签，或按 <kbd>F2</kbd>：

- <kbd>Enter</kbd>/<kbd>Tab</kbd>：提交并编辑下一个名称/数据标签；
- <kbd>Shift</kbd>+<kbd>Tab</kbd>：提交并编辑上一个；
- <kbd>Esc</kbd>：取消。

空的 bus 段会显示虚线的 `data` 占位符，双击即可创建标签。

### 2. 框选波形单元格

单击单元格、拖动框选，或使用 <kbd>Shift</kbd>+方向键 / <kbd>Ctrl</kbd>+<kbd>A</kbd> 扩展选择。直接键入 WaveDrom 字符会写入所有选中单元格：

| 字符 | 含义 |
|---|---|
| `0` / `1` | 低电平 / 高电平 |
| `.` | 保持前一个状态 |
| `x` / `z` | 未知态 / 高阻态 |
| `=` | 数据总线（对应一个 `data` 标签） |
| `2`–`9` | 带颜色的数据总线 |
| `p`/`P`, `n`/`N` | 上升沿/下降沿时钟；大写带边沿标记 |
| `l`/`L`, `h`/`H` | 时钟低/高相位；大写带边沿标记 |
| `u` / `d` | 总线上升/下降过渡 |
| `\|` | 间隔标记 |

单选单元格时，输入后光标自动前进到下一格（可在首选项中关闭）。**复制单元格 / 粘贴单元格** 支持波形字符块，<kbd>Del</kbd> 将选中单元格恢复为 `.`。

### 3. 时钟自动扩展

名称包含 `clk` 或 `clock` 的信号会自动与最长信号对齐。`p.......` 这类时钟用 `.` 续接；`0011` 这类矩形时钟按可重复周期平铺。可在 **首选项 → 行为** 中关闭，或使用 **信号 → 时钟扩展到最长**。

### 4. 信号操作

| 操作 | 默认快捷键 |
|---|---|
| 在上方插入 | <kbd>Insert</kbd> |
| 在下方插入 | <kbd>Ctrl</kbd>+<kbd>Insert</kbd> |
| 在末尾添加 | <kbd>Ctrl</kbd>+<kbd>Enter</kbd> |
| 复制信号 | <kbd>Ctrl</kbd>+<kbd>D</kbd> |
| 复制 / 剪切 / 粘贴 | <kbd>Ctrl</kbd>+<kbd>C</kbd> / <kbd>X</kbd> / <kbd>V</kbd> |
| 删除 | <kbd>Ctrl</kbd>+<kbd>Delete</kbd> |
| 上移 / 下移 | <kbd>Alt</kbd>+<kbd>↑</kbd> / <kbd>Alt</kbd>+<kbd>↓</kbd> |
| 清空信号 | <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Delete</kbd> |

单击行号选中一行，<kbd>Shift</kbd>+单击选择范围，拖动即可排序。复制/粘贴通过系统剪贴板传递 WaveJSON。

### 5. JSON 实时同步

编辑器同时接受标准 JSON 和宽松 JSON5（注释、单引号、无引号键、尾逗号）。输入后短暂延迟自动应用；非法内容不会破坏当前波形，并会显示错误行号/列号。  
<kbd>Ctrl</kbd>+<kbd>Enter</kbd> 立即应用，<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>F</kbd> 格式化。

右上角 **Live** 徽标或 **工具 → 切换实时同步** 可在实时/手动模式间切换。手动模式下离开编辑器时，合法文本仍会自动应用。

### 6. 视图与快捷键

- <kbd>Ctrl</kbd>+<kbd>1</kbd>：仅波形；<kbd>Ctrl</kbd>+<kbd>2</kbd>：仅编辑器；
- <kbd>Ctrl</kbd>+<kbd>3</kbd>：上下分栏；<kbd>Ctrl</kbd>+<kbd>4</kbd>：左右分栏；
- <kbd>Ctrl</kbd>+<kbd>0</kbd> / <kbd>=</kbd> / <kbd>-</kbd>：重置/放大/缩小；
- <kbd>Ctrl</kbd>+<kbd>f</kbd> / <kbd>h</kbd>：查找/替换；
- <kbd>F1</kbd>：快速帮助与完整快捷键表；
- **首选项 → 快捷键**：重新绑定任意操作（每个操作最多两个组合），支持冲突检测与恢复默认。

![快捷键设置](asset/md/v2_shortcuts.png)

### 7. 皮肤、导出与标注

- **视图 → 皮肤**：`default`、`lowkey`、`narrow`、`dark` 官方皮肤；
- **视图 → 水平比例**：修改 WaveDrom `hscale`；
- **文件 → 导出 PNG / SVG**，或 **复制波形图片** 到剪贴板；
- 使用 **节点工具** 放置单字符节点，然后在 **工具 → 关系标注** 中添加 `a~>b setup` 等连线；
- **工具 → ASCII 预览**：生成可粘贴到终端/提交信息的字符图。

![深色主题](asset/md/v2_dark.png)

---

## 兼容性说明

- 支持平面 `signal` 数组；嵌套信号组会在打开时被展平并给出提示。
- 支持 `period`、`phase`、`data`、`node`、`edge`、`head`/`foot` 基础内容与 `config.hscale`/`skin`/`marks`。
- 未知字段会保留，并在保存时原样写回。
- 保存始终使用 UTF-8 标准 JSON；JSON5 仅用于编辑便利。

---

## 目录结构

```text
WaveDromGen/
  app.py             Qt 主窗口、菜单、工具栏与文件读写
  waveview.py        交互画布、双击编辑、框选、拖动排序
  renderer.py        波形/关系渲染与 PNG/SVG 导出
  layout.py          几何、命中测试、标签编辑目标
  model.py           WaveJSON 文档模型、撤销/重做、时钟规则、JSON5
  wavedrom_render.py WaveDrom brick/marker 算法的 Python 移植
  skins.py           皮肤加载与 SVG 符号绘制
  editor.py          轻量 JSON 编辑器
  shortcuts.py       操作注册表与快捷键冲突检测
  settings.py        首选项持久化
  theme.py / icons.py / dialogs.py
  resources/         skins.json 与应用图标
examples/            可直接打开的 WaveJSON 示例
tests/               单元测试与 Qt GUI 测试
```

渲染核心是 WaveDrom 官方 brick 与 data marker 算法的直接移植，并加载官方皮肤符号，因此几何外观与 WaveDrom 一致。

---

## 测试

```bash
python -m unittest discover -s tests -v
```

覆盖 brick 算法、时钟扩展、JSON/JSON5、撤销/重做、设置与快捷键，以及离屏 GUI 测试：双击编辑、拖动排序、框选输入、信号剪贴板、实时 JSON、分栏、主题、保存/打开与 PNG/SVG 导出。

---

## 许可与致谢

- 原项目 WaveDromGen：Henson / blueyesess 及贡献者  
  <https://github.com/blueyesess/wavedromgen>
- WaveDrom 几何与皮肤符号：Aliaksei Chapyzhenka 及贡献者，MIT  
  <https://github.com/wavedrom/wavedrom>
- PySide6（LGPLv3）、json5（MIT）

本 v2 代码以 MIT 许可发布，详见 [LICENSE](LICENSE) 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。v1 Tkinter 版本保留在 Git 历史中。
