# LightFlow 光学电路板

在「文件 → 平台尺寸、孔位和形状」的「孔位」中选择 LightFlow（标识 `lightflow`）。此平台参考 IQC Waterloo 的 QITI 团队使用 LightFlow Optics 设计的 [OQD 光学电路板](https://github.com/OpenQuantumDesign/oqd-OCB)。数据来自该仓库截至 2026 年 10 月的 LightFlow JSON（`Optical Modules/json/OM_S_01.json` 和 `OM_MOD_01_Cooling.json`）、孔位图（`Optical Modules/drawings/OM_S_01.pdf`）与渲染图。

## 平台规范

| LightFlow / OQD | 本项目中的实现 |
|---|---|
| 各元件的 `beam_height` 为 25.4 mm | 光轴和 3D 显示的光束高度均为 25.4 mm |
| ½ 英寸厚的铝板，固定到光学台的孔是 1/4-20 通孔，深 12.7 mm | 3D 板厚 12.7 mm |
| 各安装座使用机加工底座 | 灰色底座沿用元件占地尺寸，底座高度为 1 英寸减安装座底面至光轴的高度 |
| 底座用 8-32 螺纹孔固定，深 6.25 mm（A 孔） | 二维布局显示孔位，物料清单计入螺钉 |
| M2 定位销，孔深 2.1 mm（B 孔） | 二维布局显示 2 mm 孔，物料清单计入定位销 |
| 固定激光器等大型元件或板对板装配的 1/4-20 螺纹孔（C 孔） | 暂无元件类型使用 |
| 固定到光学台的 1/4-20 通孔（E 孔） | 在 1 英寸网格上自动挑选无遮挡的孔位，靠近每个角，长边每约 8 英寸增加一处 |

## 底座与孔位

坐标采用元件库坐标系，x 沿光束，y 横向，孔位以光学中心为基准。大部分底座是实验室自制件，于 2026-10-19 在 `component_library/lightflow small mount - new` 中测量。先用 `tools/sldprt_to_step.py` 将 SolidWorks 文件导出为 STEP，再读取占地、顶面和竖直孔位。缺少实验室专用底座的元件采用 OQD 平台的 LightFlow 库元件。

| 元件类型 | 底座 | 占地 x × y (mm) | 顶面高度 (mm) | 板上 8-32 孔 | M2 定位销 |
|---|---|---|---|---|---|
| `mirror_polaris_half` | 实验室 `polarismount` | 10.2 × 25.0，以 K05S1 螺纹孔为中心（x −8.02） | 12.7 | (−8.02, 0)，从板底固定安装座 | (−8.02, ±5) |
| `mirror_newport_half` | 实验室 `newport_M05` | 12 × 25，x −9.4 居中 | 12.7 | (−9.4, 0) | (−9.4, ±5) |
| `hwp_half`、`qwp_half` | 实验室 `RSP05` | 10.2 × 36 | 11.43 | (−0.64, ±13) 沉孔，底部中央螺钉固定安装座 | — |
| `pbs_half` | 实验室 `halfinchpbsmount` | 16 × 38 | 19.05（立方体承座） | (0, ±13.5) 沉孔 | (0, ±5) |
| `lens_1in`、`fiber_cage`、`hwp_crm`、`qwp_crm` | 实验室 `cagemount` | 15 × 61 | 5.1 | (0, ±25.1) 沉孔 | (0, ±10)、(5.45, ±10) |
| `iris` | 实验室 `irismount`，IDA12 固定在立柱侧面的光束高度处，带底脚 | 9.4 × 21.4，位于光束一侧 | 35.4（立柱） | (−0.16, −6.33) 长圆孔 | (−0.15, −22.18)、(−0.15, −16.28) |
| `shutter` | 实验室 `SRSshutter.json` | 26 × 60 | 20.65 | (0, −20.05)、(0, 29.95) | — |
| `aom` | 实验室 `IntraactionATM.json` / `IntraactionAOM-ATM` | 53.4 × 50.7 | 12.9 | (±22.75, 0) | (0, 0) |
| `mirror_d`（DMM1 内的 1 英寸 D 形镜） | 实验室 `Left D-Shaped Mirror Mount`，DMM1 装在自带立柱和带槽底脚上（`component_library/step/DMM1_lab.step`） | 11.7 × 35.2，立柱在光束左侧 | —（立柱将反射镜抬到 1 英寸） | (−4.48, 23.9) 长圆孔 | (−4.48, 13.95)、(−4.48, 8.05) |
| `fiber` | OQD “Schafter Kirchhoff collimator Ver 2” | 40.2 × 42 | — | (−23.5, ±15) | (−23.5, ±5) |
| `photodiode` | OQD “1 inch photodiode” | 28.25 × 27 | 5.4 | (−21.7, ±6.35) | — |
| `dump` | OQD “Small Beam Block” | 12.5 × 11 | 10.4 | (−8.25, 0) | — |

LightFlow JSON 中原点的 y 向比例从 +y 一侧计算。按这个方向解读，`SRSshutter.json` 和 `IntraactionATM.json` 的所有孔会落到占地范围内。

在 3D 视图中，自制底座使用真实模型。`component_library/step/LightFlow/LF_*.step` 的姿态记录在 `tools/simplify_cad.py` 的 `POSES` 中，原点在光学中心下方的板面，x 沿光束、z 向上。运行 `python tools/simplify_cad.py LF_<名称>` 会在 `component_library/mesh/LightFlow/` 下生成网格。二维轮廓和重叠检查使用表中的占地矩形。

暂未用到的自制件有 `RDMount_new`（Radiant Dyes，11.4 mm，本项目中的 MDI-HS 已高于 1 英寸）、`planebeamsplitter`（暂未定义平板分束器）、`GnHAOM`、`GnHAOMv2`、`ATMplate`、`insulationlayer` 和 `AllMount`。

其他元件采用与安装座占地尺寸相同的底座，底部设置一个 8-32 孔。如果安装座底面已经低于光轴 1 英寸或以上，例如 KM100、RSP1、MDI-HS，则直接固定在板上。

## 示例模型的限制

- 实验室使用笼式光纤耦合器 `fiber_cage`（非球面透镜装在 CP33，笼杆连接到 FC/APC 板），前板装在实验室自制的 `cagemount` 上，与 Olego 的方式一致。PAF2/HCA3 的 `fiber` 类型仍沿用 OQD 准直器固定座的孔位并下沉 1.6 mm。
- AOM 横跨 50.7 mm，沿光束方向的长度及其高度均暂估为 25 mm（`mounts3d.py` 的 `LIGHTFLOW_BODY`）。
- 可调光阑立柱位于光束哪一侧、长圆孔定位销的朝向尚待核对。

运行 `python examples/make_lightflow_board.py` 可生成 `examples/lightflow_board.json`。
