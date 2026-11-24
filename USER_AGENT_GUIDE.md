# Optical Layout Designer 中文操作手册

Optical Layout Designer 中文版可用于设计光路、调整面包板、记录功率和生成 Blender 项目。使用 Blender 导出功能需要另行安装 Blender。扩展元件库或批量编辑时，可使用源码和命令行。

- 桌面应用位于 `/Applications/Optical Layout Designer.app`。
- 源码和示例在同一 Release 的源码包内。解压后从项目根目录执行本手册的源码命令。
- 使用 Codex 或其他智能体时，可以直接提供本手册。用法见[让智能体执行布局任务](#8-让智能体执行布局任务)。

## 1. 打开和保存项目

在 Finder 的「应用程序」中打开 Optical Layout Designer。第一次用可以点 **文件 → 打开示例**。`demo_schematic.json` 适合练习放置与连光束，`demo_399nm.json` 附带历史测量数据。已安装应用会在应用支持目录的 `Examples` 文件夹创建可编辑的示例副本。

用 **文件 → 新建** 或 **文件 → 另存为** 把正式布局保存到自己的项目目录。

| 文件或视图 | 用途 |
|---|---|
| `399nm 光束分配.json` | 保存平台规格、光路连接、元件位置、测量点和实验记录表设置 |
| `399nm 光束分配.logbook.sqlite` | 保存功率读数、测量时间、功率计、备注和光斑图片。首次写入才创建文件 |
| **光路图** | 定义有哪些元件、用什么型号、光束如何连接 |
| **平台布局** | 按实体尺寸摆放和旋转元件，查看孔位、距离与功率测量点 |
| **3D** | 核对模型、安装方式和光束高度，也可向 Blender 导出 |
| `.blend` | 从当时的布局生成的 Blender 项目，可独立编辑和保存 |

布局和配套日志有相同的文件名前缀。迁移或备份时，若已创建日志，将两个文件一起带走。提示缺少日志时，可选 **选择日志文件**、**使用新日志** 或 **打开布局（不加载日志）**。另存为新布局后，检查新文件旁的日志是否符合预期，特别是原布局曾关联其他目录里的日志时。

## 2. 新建和调整平台布局

### 设置面包板或安装平台

打开 **文件 → 平台尺寸、孔位和形状**，填写名称、宽度和高度。尺寸单位为 mm。「孔位」下拉列表用于选平台。

| 类型 | 孔位和安装特征 |
|---|---|
| 经典 1 英寸孔距 | 默认孔距 25.4 mm，第一排孔距边缘 12.7 mm，使用 1/4-20 规格 |
| Olego | 半英寸网格加中心孔，使用 4-40 规格，3D 使用对应的预设立柱 |
| PyOpticL | 设计网格供吸附，按元件布孔，光束高度 12.7 mm |
| LightFlow | 按元件布孔，光束高度 25.4 mm，支持型号对应的底座 |
| 预钻孔 | 只在元件安装位置布孔，平台布局没有规则孔网格 |

缺口是从板上切去的矩形。输入 `x, y, w, h`，多个矩形以半角分号分隔。例如 `0, 0, 25, 40; 500, 350, 50, 50`。坐标原点在板的左上角，**X 向右，Y 向下**。改变平台类型会应用相应预设。调整尺寸和缺口后，核对边缘附近的元件、支架和物料清单。

### 添加元件并连接光束

1. 切到 **光路图**。单击左侧的反射镜、透镜、AOM、PBS 或其他符号，再单击画布。
2. 在弹窗选择具体尺寸或安装方式，核对标签、料号和备注，然后点 **放置**。
3. 按 **B**，沿光的传播方向依次单击元件。单击空白处可开始另一条连接，按 **Esc** 退出绘制。「新光束」下拉项决定新段的波长与颜色。
4. 要在已有光束中插入元件，选好符号后直接单击光路图上的那段光束。插入后检查拆分出的两段及相关测量点。
5. 切到 **平台布局**，把板下方的待放置元件拖到板上。暂存区不在当前视野时，可缩小查看。再切到 **3D** 核对。

双击平台上的元件，可跳到光路图中的对应元件。核对 `M1`、`PBS1` 等标签，以区分同一类型的多个元件。

### 精确摆放和检查

| 操作 | 方法 |
|---|---|
| 调整 X、Y | 在平台布局拖动元件，或选中后在「属性」输入坐标 |
| 控制吸附 | 在「吸附」选孔位、半格或不吸附。按住 Mac 的 Option（⌥）拖动可临时取消吸附 |
| 微调位置 | 在平台布局按方向键移动一孔，Shift + 方向键移动 1 mm |
| 调整角度 | 在属性输入角度，或用 R / Shift+R 转动 ±45°，用右方括号 / 左方括号转动 ±5° |
| 自动定向 | 选中元件按 A，或在属性里按光束方向自动定向 |
| 检查重叠 | 重叠处有红色虚线边框。点 **平台布局 → 显示重叠元件** 可选中重叠项 |
| 查看孔位 | 用 **视图 → 在平台边缘显示孔位坐标** 开关列字母与行号。选中元件可看位置摘要 |
| 测距或光程 | 按 L 拖动测距。选中两个有光路相连的元件，在属性查看直线距离和沿光路的累计长度 |
| 调整视角 | F 适应窗口，Z 缩放至所选对象。3D 中拖动旋转、滚轮缩放、Shift + 拖动平移 |

手动旋转后该元件会关闭自动定向。反射镜的自动定向由相连光束计算，移动邻近元件可能改变镜面角度。要固定角度，检查自动定向的勾选状态。

**平台布局 → 按光路图重新排布** 会覆盖当前板上的摆位。已按孔位精确排好的布局，可以先另存为副本再试。

## 3. 修改型号、波长和测量数据

### 元件与光束属性

- 在 **光路图** 选中元件，到属性区改标签、类别、型号、料号或备注。也可用 **编辑 → 元件表** 批量调整并导出元件 CSV。
- 料号留空时沿用型号的默认料号。对装配尺寸相同的不同供应商料件，可以填实际料号。
- 要编辑已有光束的波长，在 **光路图** 选中该段，再用属性里的「波长」。切换「新光束」影响之后绘制的连接。
- 移除已有元件或光束，在光路图选中后用 **编辑 → 删除**。删除光束或光纤耦合器时，关联测量点可能归档。
- 用 **编辑 → 物料清单** 查看采购项，或用 **文件 → 导出物料清单（CSV）**。切换平台类型或装配高度后，重新核对支柱和转接件。

Mac 的组合键以菜单显示为准。菜单通常用 ⌘，部分工具提示显示 Ctrl。

### 功率测量、照片和记录表

1. 保存布局。在 **平台布局** 按 **M**，单击光束添加测量点。单击光纤耦合器可记录光纤输出端的功率。按住 Shift 可连续添加。
2. 沿光束拖动标记可调整测量位置。单击标记，或双击右侧「功率日志」的相应行，打开日志。
3. 输入数值、单位、功率计和备注，点 **添加读数**。支持 W、mW、µW、nW。程序将数值换算成 mW 存储，保留输入单位，并自动记录时间。
4. 在 **光斑照片** 页可添加文件或粘贴图片。图片和读数都存入配套的 SQLite 日志。
5. 误录时新增正确读数并说明原因，必要时用 **删除所选项** 隐藏旧读数。勾选 **显示已删除项** 可恢复隐藏项。

用 **平台布局 → 实验记录表** 选择测量点、调整显示名称和历史条数，并决定是否附带布局图。可复制到 OneNote 或 Excel，也可保存 PDF、CSV。整份日志从 **文件 → 导出功率日志（CSV）** 导出。

网页端可让实验室其他设备查看布局、填写功率和上传照片。默认网页服务仅监听本机，局域网配置见[网页端说明](https://github.com/FrankLyu/Optical-Layout-Designer/blob/29d6961885281eb86f8e66cccd20f6af6295143e/web/README.md)。

## 4. 一键输出到 Blender

1. 在光路设计器打开目标布局，切到 **3D**。检查光束高度、安装状态和待放置元件。普通支柱布局可在 3D 顶部指定高度。PyOpticL、LightFlow 有标准高度，Olego 上的元件还受立柱承座高度影响。
2. 点 **在 Blender 中打开**。也可从 **文件 → 在 Blender 中打开** 调用。应用以当前窗口中的布局为准，生成新的 `.blend` 并在新 Blender 窗口打开。此操作可把尚未保存的改动一并导出。
3. 在 Blender 的大纲列表查看 **光学元件**、**面包板与支架**、**光束** 等集合。选择例如 `M1` 的父对象，可一起移动该元件的多个网格。需要集中管理成果时，从 Blender 另存为到实际项目目录。
4. 自动生成的文件在 `~/Library/Application Support/Optical Layout Designer/Blender/`，文件名包含布局名和时间。

导出将布局 mm 换算成 Blender 米制坐标，显示单位设为毫米。光束附带发光材质，可切到材质预览或渲染模式检查。修改原光路后，可以重新导出一份 Blender 项目。

导出采用当前 3D 预览的网格。缺少厂家 CAD 的元件会用简化形状，规则孔位是面包板的表面标记。用于加工时，应另核对实际 STEP、机械尺寸和钻孔规格。

找不到 Blender 时，检查 `/Applications/Blender.app` 或 `~/Applications/Blender.app`。界面没有导出按钮时，保存当前布局，退出旧窗口并从「应用程序」重新打开更新版。

## 5. 导入新的光学元器件

### 选择哪种方式

- 库中已有同装配尺寸的型号时，先放置已有元件，再填写实际料号和备注。这适合在清单里区分供应商。
- 需要新形状、新安装方式或真实预览模型时，扩展源码里的元件库。桌面版的放置窗口用于选择已经登记的型号。
- 只用于渲染的模型可直接加到导出的 Blender 项目。需要参与光路连接、重叠检查和 BOM 时，应从光路设计器登记元件。

### 从厂家 STEP 添加一个型号

下面以待登记的 `KM200` 为例。文件命名、模型尺寸和变换以厂家 CAD 为准。命令在源码项目根目录运行。

1. **获取 STEP**。从厂家产品页下载模型，例如保存到 `component_library/step/KM200.step`。仓库主要带的是简化 PLY 网格，完整 STEP 要另行取得。
2. **对齐坐标**。元件库坐标以光学中心为原点，+X 沿光轴或光学面的法线，+Z 向上。若厂家文件使用其他坐标系，在 `tools/simplify_cad.py` 的 `POSES` 中以原文件名不含扩展名为键填写 `origin`、`x` 和 `z`。核对实际镜面、安装底面和底部长孔位置。
3. **生成 PLY**。在单独的源码 Python 3.13 环境安装项目依赖和 `cadquery-ocp`。如果已经安装 Conda，可从源码目录用以下命令创建项目环境并转换模型。已有环境时，可在该环境直接运行安装与转换命令。

   ```sh
   conda create -n optolayout-cad python=3.13 pip
   conda run -n optolayout-cad python -m pip install -r requirements.txt cadquery-ocp
   conda run -n optolayout-cad python tools/simplify_cad.py KM200
   ```

   输出通常是 `component_library/mesh/KM200.ply`。默认目标约 8000 个三角面，可用 `--triangles` 调整。终端输出 `base … mm below the optic` 可用于核对光轴距底面的高度。
4. **登记二维型号**。在 `optolayout/symbols.py` 里调用 `register()`，传入唯一类型键、显示名、绘图函数、默认料号以及分组。以下用相近反射镜的图形作示意。

   ```python
   register("mirror_km200", "2 英寸反射镜（KM200）",
            _scaled(_tl_mirror, 2.0), "KM200", "反射镜")
   ```

   在 `optolayout/model.py` 的 `SCH_KINDS["mirror"][2]` 中加入 `"mirror_km200"`，使放置反射镜时能选到它。列表首项是该类别的默认型号。
5. **登记装配与占地**。在 `optolayout/mounts3d.py` 的 `MODELS` 里用同一个类型键关联 `Model3D("KM200.step", base_height, mirror_disc=50.8)`。将 `base_height` 换成实际 mm 数值，`mirror_disc` 是另绘制的镜片直径。厂家模型已经有镜片时，检查是否重复绘制。把实测的 `(xmin, xmax, ymin, ymax)` 写入 `MESH_FOOTPRINT["KM200"]`，供重叠检测和转接件计算使用。
6. **配置平台专用支架**。Olego 用 `OLEGO_PILLARS` 映射立柱，必要时补底面的位置偏移。LightFlow 和 PyOpticL 按实际装配规则补底座、转接件与孔位。
7. **试放并检查**。在源码环境运行 `python run.py`，用小布局放置一个新型号。核对二维轮廓、3D 方向、安装面贴合、光轴高度和 BOM，必要时再导出到 Blender 对比。
8. **更新应用**。安装版带有独立的元件库副本。源码验证通过后，通过重新打包、签名和安装让新元件进入桌面版。

在该环境运行以下命令可读取 PLY 占地范围。若用上面的 Miniforge 环境，可把命令开头的 `python` 换成 `conda run -n optolayout-cad python`。

```sh
python -c "import pyvista as pv; print(pv.read('component_library/mesh/KM200.ply').bounds[:4])"
```

厂家链接和尺寸来源可记入 `component_library/mounts.json`。详细做法见[元件库说明](https://github.com/FrankLyu/Optical-Layout-Designer/blob/29d6961885281eb86f8e66cccd20f6af6295143e/component_library/README.md)、[Olego](https://github.com/FrankLyu/Optical-Layout-Designer/blob/29d6961885281eb86f8e66cccd20f6af6295143e/docs/OLEGO_MATING.md)、[PyOpticL](https://github.com/FrankLyu/Optical-Layout-Designer/blob/29d6961885281eb86f8e66cccd20f6af6295143e/docs/PYOPTICL_BOARD.md)和[LightFlow](https://github.com/FrankLyu/Optical-Layout-Designer/blob/29d6961885281eb86f8e66cccd20f6af6295143e/docs/LIGHTFLOW_BOARD.md)。

## 6. 让智能体编辑布局和功率数据

### 为任务选入口

| 任务 | 推荐做法 |
|---|---|
| 使用当前窗口中尚未保存的改动 | 操作桌面应用，先核对窗口标题与用户指的布局 |
| 批量调整位置、型号、料号和波长 | 用本项目的数据模型读入指定 JSON 并回读检查 |
| 查功率历史、录入实测值或更正误录 | 定位配套日志，并按测量点 ID 查找或使用 `Logbook` 追加 |
| 新增厂家型号和模型 | 在源码元件库操作，先验证小布局再更新安装版 |
| 从已保存的布局生成 Blender 文件 | 使用技能里的脚本，或在桌面应用打开后点一键按钮 |

批量编辑前核对桌面应用是否也打开了该文件。用户需要保留原稿时，保存到可区分的新文件。如果副本要携带历史，日志文件使用与新布局一致的前缀。

### JSON 数据关系

| 字段 | 含义 |
|---|---|
| `table` | 平台尺寸、孔距、缺口和装配规则。调用 `Table.apply_style()` 可切换预设 |
| `schematic.elements` | 元件类别 `kind`、可选型号 `part`、标签、料号、备注和示意坐标 |
| `schematic.links` | 有向光束连接。`source`、`target` 引用光路图元件 ID，`wavelength_nm` 是纳米波长 |
| `components` | 物理摆位。`sch_id` 链接到光路图，`x`、`y` 的单位为 mm，`pinned=true` 表示已手动放置 |
| `components[].angle` | 单位为度。0 表示光轴朝 +X，正角度在画面中逆时针。固定角度时设 `auto_angle=false` |
| `beams` | 物理布局的光段，端点引用布局元件 ID。同步后光束 ID 对应光路图连接 ID |
| `measurement_points` | `beam_id` 与 `t` 指定所属光段及比例位置，`t=0.5` 是中点。光纤输出点使用 `part_id` |
| `lab_sheet` | 实验记录表选择的测量点 ID、可读名称和输出选项 |

同步时，光路图提供型号、料号、标签与光束连接。修改这些数据时，应修改光路图相应条目。使用 `Layout.load()`、`LayoutScene.sync_from_schematic()` 和 `Layout.save()` 完成编辑。旧布局如果有布局元件却没有光路图元素，先调用 `layout.schematic_from_layout()`，这和桌面程序打开旧文件时的处理一致。

保留已有元件、光束和测量点 ID，以便原有连接、测量历史和归档记录继续关联。布置新元件后核对是否在板上。需要保留脚本指定的位置时，设置 `pinned=true`。

### 移动示例布局里的 M1

以下命令用已安装应用自带的 Python 和只读示例生成新布局，将 M1 沿 +Y 移一孔。输出文件已存在时会退出。

```sh
app='/Applications/Optical Layout Designer.app'
project="$app/Contents/Resources/project"
python="$app/Contents/Resources/python/bin/python3.13"

env QT_QPA_PLATFORM=offscreen PYTHONPATH="$project" "$python" -B - \
  "$project/examples/demo_schematic.json" "$PWD/练习布局-M1.json" <<'PY'
from pathlib import Path
import sys
from PySide6.QtWidgets import QApplication
from optolayout.model import Layout
from optolayout.scene import LayoutScene

source, output = map(Path, sys.argv[1:])
if output.exists() or output.is_symlink():
    raise SystemExit(f"请使用新文件名：{output}")
app = QApplication([])
scene = LayoutScene(Layout.load(source))
scene.sync_from_schematic()
mirror = next(part for part in scene.layout.components.values() if part.label == "M1")
y = mirror.y + scene.layout.table.hole_pitch
if not scene.layout.table.on_board(mirror.x, y):
    raise SystemExit("目标位置不在平台上")
scene.set_fields(mirror.id, {"y": y, "pinned": True})
print("重叠元件 ID", sorted(scene.clashes))
scene.layout.save(output)
saved = Layout.load(output)
assert saved.components[mirror.id].pinned
assert abs(saved.components[mirror.id].y - y) < 1e-9
print(output)
PY
```

处理真实布局时，先确认标签能唯一定位元件。保存后用应用重新打开，检查坐标、角度、光束连接以及原有测量点。若原始 JSON 只包含光路图，先同步到布局再导出几何。

### 读写功率日志

用 `logbook_path_for(layout_path)` 找到日志。只读分析可以用 SQLite 的只读连接。录入时按布局里的测量点 ID 定位，通过 `Logbook.register_point()` 和 `add_power()` 追加。运行以下示例前，填入实际文件、测量点和读数。

```python
from optolayout.logbook import Logbook, logbook_path_for
from optolayout.model import Layout

layout_path = "/绝对路径/正式布局.json"
layout = Layout.load(layout_path)
point = layout.points["真实测量点ID"]
book = Logbook(logbook_path_for(layout_path))
try:
    book.register_point(point.id, point.label)
    record_id = book.add_power(point.id, 25.4, "mW",
                               instrument="实际功率计", notes="核对后录入")
    print(record_id)
finally:
    book.close()
```

更正时可为新记录提供 `supersedes=旧记录ID`，原记录仍在数据库中。隐藏读数用 `set_deleted("power", [记录ID], deleted=True)`，恢复用 `deleted=False`。批量录入前核对测量点 ID、原始单位、时间与重复记录。请使用 SQLite backup API 备份仍在使用的数据库，以保证副本与最新写入一致。

## 7. 排查问题

| 现象 | 检查方法 |
|---|---|
| 新元件在 3D 中看不到 | 检查面包板下方或边缘，确认元件放在有效板面上 |
| 脚本写入的位置被重新排布 | 核对改的是 `components` 的实际坐标，并设置 `pinned=true` |
| 输入的角度自动变化 | 检查该元件是否打开自动定向 |
| 日志为空或找不到 | 核对布局与日志的目录和文件名、测量点 ID，以及打开时选择的日志选项 |
| 安装座显示成简化形状 | 在 3D 提示中检查缺少的模型，核对 PLY、文件名和三维型号登记 |
| Blender 导出失败 | 核对 Blender 应用位置，查看桌面提示的详情。若文件已生成但没打开，可从导出目录手动打开 |
| Blender 光束看不到光晕 | 切换到材质预览或渲染模式查看发光材质，并按需要配置 Blender 的合成效果 |

## 8. 让智能体执行布局任务

把本手册交给智能体，指定输入布局、拟改动的元件或测量点，以及输出位置。打开应用的窗口有未保存编辑时，先保存，或在应用中执行对应操作。

> 读这份手册，把这份布局的 M1 沿 +X 移动 25.4 mm，保留手动角度，另存为新布局，随后导出 Blender 项目。

先按第 6 节检查并保存布局，再按第 4 节从桌面应用生成 `.blend`。交付前回读保存的布局，检查坐标、角度、光路连接和测量点。用 Blender 核对面包板尺寸、光学元件分组和光束。如果用于加工，另行核对厂家 STEP 和钻孔规格。
