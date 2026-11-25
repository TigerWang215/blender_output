# PyOpticL 离子阱基板

在「文件 → 平台尺寸、孔位和形状」的「孔位」下选择 PyOpticL。该类型的标识为 `pyopticl`，参考 UMass 离子阱团队的 [PyOpticL](https://github.com/UMassIonTrappers/PyOpticL) 截至 2026 年 10 月的实现，尤其是 `PyOpticL/library/__init__.py` 的 Baseplate、`library/adapters.py` 的 Surface_Adapter，以及 `library/thorlabs.py` 的安装座位置定义。

## 基板规范和项目中的实现

| PyOpticL 规范 | 本项目中的实现 |
|---|---|
| 1 英寸厚的实心板（模块使用 `base_dz = 1 in`） | 3D 板厚 25.4 mm（`PYOPTICL_PLATE_T`） |
| 光学平面高于板面 0.5 英寸（`optical_height`） | 元件光轴高度 12.7 mm，3D 选项卡自动采用该值 |
| 按元件位置钻孔 | 各元件下绘制灰色 8-32 孔位，浅色十字表示用于吸附的 1 英寸设计网格 |
| 网格 1 英寸，边角偏移半格 | `hole_pitch = 25.4`、`hole_offset = 12.7`，网格点以 A1 等标识 |
| Polaris 安装座（K05S1 等）用一颗 8-32 螺钉从底部固定，安装座底面比光轴低 ½ 英寸 | 直接固定到基板，BOM 计入 1 枚螺钉 |
| RSP05、RSP1、PDA10A2 使用高 10 mm 的 `Surface_Adapter`，沿光束横向布置两颗间距 25 或 40 mm 的 8-32 螺钉，并通过 `drill()` 下沉 2 mm | 安装座下显示绿色转接块，二维轮廓参与重叠检查，3D 显示深色槽口 |
| 分束立方体放在 `Surface_Adapter` 上，嵌入 1 mm 并立于板上 | 应用于 `pbs_half`、`pbs` 和 `bs` |
| KM05、KM100、HCA3 等光轴以下部分较高的安装座，需要按包围盒加 5 mm 挖槽 | 3D 显示深色槽口，BOM 含 `(pocket)` 条目 |
| HCA3 光纤端口安装座用三颗间距 12.7 mm 的 8-32 螺钉 | BOM 计入 3 枚螺钉 |
| IDA12 使用 `Slide_Adapter` | BOM 计入滑入式转接件和 1 枚螺钉，暂未绘制 3D 转接件 |
| 基板通过网格上手动选择的 1/4-20 沉孔（`mount_holes`）固定到光学台 | 自动选择距四角最近的无遮挡网格点，长边每约 8 英寸补一个孔 |

当前示例的 3D 凹槽以板面深色块表示。安装座底面偏移量来自本项目的网格，可能与 PyOpticL 相差不足 1 mm。

## 添加元件类型

在 `optolayout/mounts3d.py` 中，使用表面转接件的类型加入 `PYOPTICL_ADAPTERS`，填写高度、螺钉间距和最小长度。如果转接件立于平台而非安装座底部，设定 `top`。使用多颗螺钉的类型加入 `PYOPTICL_SCREWS`。

运行 `python examples/make_pyopticl_board.py` 可生成 `examples/pyopticl_board.json`。
